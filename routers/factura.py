from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from psycopg2.extras import RealDictCursor
import os
import uuid

from services.xml.factura_electronica_parser import parse_factura_electronica
from database import get_db

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
)

# ============================================================
# POST /factura/manual
# ============================================================
@router.post("/manual")
def crear_factura_manual(payload: dict, conn=Depends(get_db)):

    try:
        from services.pdf.factura_manual_pdf import generar_factura_manual_pdf
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="El módulo de generación de PDF no está disponible."
        )

    cur = None
    cur_dict = None

    try:
        if not payload.get("servicios"):
            raise HTTPException(
                status_code=400,
                detail="La factura debe contener al menos un servicio."
            )

        cur = conn.cursor()

        # ================= Crear factura =================
        cur.execute("""
            INSERT INTO factura (
                tipo_factura,
                codigo_cliente,
                fecha_emision,
                termino_pago,
                moneda,
                total
            )
            VALUES (
                'MANUAL',
                %s, %s, %s, %s, %s
            )
            RETURNING id
        """, (
            payload.get("codigo_cliente"),
            payload.get("fecha_emision"),
            payload.get("termino_pago"),
            payload.get("moneda", "USD"),
            payload.get("total", 0)
        ))

        factura_id = cur.fetchone()[0]

        # ================= Detalles + vinculación =================
        for linea in payload["servicios"]:
            cantidad = float(linea.get("cantidad", 0))
            precio = float(linea.get("precio_unitario", 0))
            total_linea = cantidad * precio
            servicio_id = linea.get("servicio_id")

            cur.execute("""
                INSERT INTO factura_detalle (
                    factura_id,
                    descripcion,
                    cantidad,
                    precio_unitario,
                    total_linea
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                factura_id,
                linea.get("descripcion"),
                cantidad,
                precio,
                total_linea
            ))

            cur.execute("""
                INSERT INTO factura_servicio (
                    factura_id,
                    servicio_id,
                    num_informe
                )
                VALUES (%s, %s, %s)
            """, (
                factura_id,
                servicio_id,
                linea.get("num_informe")
            ))

            # 🔒 MARCAR SERVICIO COMO FACTURADO
            cur.execute("""
                UPDATE servicios
                SET factura = %s
                WHERE consec = %s
            """, (factura_id, servicio_id))

        # ================= Generar PDF =================
        cur_dict = conn.cursor(cursor_factory=RealDictCursor)

        cur_dict.execute(
            "SELECT * FROM factura WHERE id = %s",
            (factura_id,)
        )
        factura = cur_dict.fetchone()

        cur_dict.execute(
            "SELECT * FROM factura_detalle WHERE factura_id = %s",
            (factura_id,)
        )
        detalles = cur_dict.fetchall()

        pdf_path = generar_factura_manual_pdf(factura, detalles)

        cur.execute(
            "UPDATE factura SET pdf_path = %s WHERE id = %s",
            (pdf_path, factura_id)
        )

        conn.commit()

        return {
            "message": "Factura manual creada correctamente",
            "factura_id": factura_id,
            "pdf_path": pdf_path
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()
        if cur_dict:
            cur_dict.close()


# ============================================================
# POST /factura/electronica
# ============================================================
@router.post("/electronica")
def cargar_factura_electronica(
    servicio_id: int = Form(...),
    codigo_cliente: str = Form(...),
    num_informe: str = Form(...),
    xml: UploadFile = File(...),
    conn=Depends(get_db)
):
    cur = None

    try:
        # ================= Guardar XML =================
        xml_dir = os.path.join("backend_api", "storage", "xml")
        os.makedirs(xml_dir, exist_ok=True)

        unique_name = f"{uuid.uuid4()}_{xml.filename}"
        xml_path = os.path.join(xml_dir, unique_name)

        with open(xml_path, "wb") as f:
            f.write(xml.file.read())

        # ================= Parsear XML =================
        data = parse_factura_electronica(xml_path)

        cur = conn.cursor()

        # ================= Insert factura =================
        cur.execute("""
            INSERT INTO factura (
                tipo_factura,
                codigo_cliente,
                numero_factura,
                clave_electronica,
                fecha_emision,
                termino_pago,
                moneda,
                total,
                xml_path
            )
            VALUES (
                'ELECTRONICA',
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        """, (
            codigo_cliente,
            data.get("numero_factura"),
            data.get("clave_electronica"),
            data.get("fecha_emision"),
            data.get("termino_pago"),
            data.get("moneda"),
            data.get("total"),
            xml_path
        ))

        factura_id = cur.fetchone()[0]

        # ================= Detalles =================
        for d in data.get("detalles", []):
            cur.execute("""
                INSERT INTO factura_detalle (
                    factura_id,
                    descripcion,
                    cantidad,
                    precio_unitario,
                    impuesto,
                    total_linea
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                factura_id,
                d.get("descripcion"),
                d.get("cantidad"),
                d.get("precio_unitario"),
                d.get("impuesto"),
                d.get("total_linea")
            ))

        # ================= Vincular servicio =================
        cur.execute("""
            INSERT INTO factura_servicio (
                factura_id,
                servicio_id,
                num_informe
            )
            VALUES (%s, %s, %s)
        """, (
            factura_id,
            servicio_id,
            num_informe
        ))

        # 🔒 MARCAR SERVICIO COMO FACTURADO
        cur.execute("""
            UPDATE servicios
            SET factura = %s
            WHERE consec = %s
        """, (factura_id, servicio_id))

        conn.commit()

        return {
            "message": "Factura electrónica cargada correctamente",
            "factura_id": factura_id
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()


# ============================================================
# GET /factura/{id}
# ============================================================
@router.get("/{factura_id}")
def get_factura(factura_id: int, conn=Depends(get_db)):
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT * FROM factura WHERE id = %s", (factura_id,))
        factura = cur.fetchone()

        if not factura:
            raise HTTPException(status_code=404, detail="Factura no encontrada")

        cur.execute("""
            SELECT *
            FROM factura_detalle
            WHERE factura_id = %s
        """, (factura_id,))
        detalles = cur.fetchall()

        return {
            "factura": factura,
            "detalles": detalles
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()
