from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from services.pdf.factura_manual_pdf import generar_factura_manual_pdf
import os
from fastapi import UploadFile, File, Form
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
        cur = conn.cursor()

        # ====================================================
        # 1. Crear factura (cabecera)
        # ====================================================
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
            payload["codigo_cliente"],
            payload["fecha_emision"],
            payload.get("termino_pago"),
            payload.get("moneda", "USD"),
            payload.get("total", 0)
        ))

        factura_id = cur.fetchone()[0]

        # ====================================================
        # 2. Insertar líneas de factura
        # ====================================================
        for linea in payload.get("servicios", []):
            total_linea = linea["cantidad"] * linea["precio_unitario"]

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
                linea["descripcion"],
                linea["cantidad"],
                linea["precio_unitario"],
                total_linea
            ))

            # ====================================================
            # 3. Vincular servicio con factura
            # ====================================================
            cur.execute("""
                INSERT INTO factura_servicio (
                    factura_id,
                    servicio_id,
                    num_informe
                )
                VALUES (%s, %s, %s)
            """, (
                factura_id,
                linea["servicio_id"],
                linea.get("num_informe")
            ))

        # ====================================================
        # 🔽 NUEVO: Generar PDF y guardar ruta
        # ====================================================
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

        # ====================================================
        # Commit final
        # ====================================================
        conn.commit()

        cur.close()
        cur_dict.close()

        return {
            "message": "Factura manual creada correctamente",
            "factura_id": factura_id,
            "pdf_path": pdf_path
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        # ================= Guardar XML =================
        xml_dir = "backend_api/storage/xml"
        os.makedirs(xml_dir, exist_ok=True)

        xml_path = os.path.join(xml_dir, xml.filename)

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
            data["numero_factura"],
            data["clave_electronica"],
            data["fecha_emision"],
            data["termino_pago"],
            data["moneda"],
            data["total"],
            xml_path
        ))

        factura_id = cur.fetchone()[0]

        # ================= Detalles =================
        for d in data["detalles"]:
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
                d["descripcion"],
                d["cantidad"],
                d["precio_unitario"],
                d["impuesto"],
                d["total_linea"]
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

        conn.commit()
        cur.close()

        return {
            "message": "Factura electrónica cargada correctamente",
            "factura_id": factura_id
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# GET /factura/{id}
# ============================================================
@router.get("/{factura_id}")
def get_factura(factura_id: int, conn=Depends(get_db)):
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

        cur.close()

        return {
            "factura": factura,
            "detalles": detalles
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
