from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import datetime

from database import get_db
from services.xml.factura_electronica_parser import parse_factura_electronica

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
)

def obtener_siguiente_numero_factura(cur):
    cur.execute("""
        SELECT COALESCE(
            MAX(numero_factura::int),
            2199
        )
        FROM factura
        WHERE tipo_factura = 'MANUAL'
    """)
    return cur.fetchone()[0] + 1


@router.post("/manual")
def crear_factura_manual(payload: dict, conn=Depends(get_db)):

    try:
        from services.pdf.factura_manual_pdf import generar_factura_manual_pdf
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Módulo de generación de PDF no disponible"
        )

    cur = None

    try:
        servicio_id = payload.get("servicio_id")
        total = payload.get("total")

        if not servicio_id:
            raise HTTPException(status_code=400, detail="Servicio requerido")

        if total in (None, ""):
            raise HTTPException(status_code=400, detail="Total requerido")

        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ================= OBTENER SERVICIO =================
        cur.execute("""
            SELECT *
            FROM servicios
            WHERE consec = %s
        """, (servicio_id,))
        servicio = cur.fetchone()

        if not servicio:
            raise HTTPException(status_code=404, detail="Servicio no encontrado")

        if servicio.get("factura"):
            raise HTTPException(
                status_code=400,
                detail="Este servicio ya fue facturado"
            )

        # ================= NUMERO FACTURA =================
        numero_factura = obtener_siguiente_numero_factura(cur)
        fecha_factura = datetime.now()

        # ================= INSERT FACTURA =================
        cur.execute("""
            INSERT INTO factura (
                tipo_factura,
                numero_factura,
                codigo_cliente,
                fecha_emision,
                termino_pago,
                moneda,
                total
            )
            VALUES (
                'MANUAL',
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        """, (
            numero_factura,
            servicio["cliente"],
            fecha_factura,
            payload.get("termino_pago"),
            payload.get("moneda", "USD"),
            total
        ))

        factura_id = cur.fetchone()["id"]

        # ================= DETALLE =================
        cur.execute("""
            INSERT INTO factura_detalle (
                factura_id,
                descripcion,
                cantidad,
                precio_unitario,
                total_linea
            )
            VALUES (%s, %s, 1, %s, %s)
        """, (
            factura_id,
            payload.get("descripcion"),
            total,
            total
        ))

        # ================= PDF =================
        pdf_data = {
            "numero_factura": numero_factura,
            "fecha_factura": fecha_factura,
            "cliente": servicio["cliente"],
            "buque": servicio["buque_contenedor"],
            "operacion": servicio["operacion"],
            "num_informe": servicio["num_informe"],
            "periodo": f"{servicio['fecha_inicio']} a {servicio['fecha_fin']}",
            "descripcion": payload.get("descripcion"),
            "moneda": payload.get("moneda", "USD"),
            "termino_pago": payload.get("termino_pago"),
            "total": total
        }

        pdf_path = generar_factura_manual_pdf(pdf_data)

        # ================= UPDATE FACTURA =================
        cur.execute("""
            UPDATE factura
            SET pdf_path = %s
            WHERE id = %s
        """, (pdf_path, factura_id))

        # ================= BLOQUEAR SERVICIO =================
        cur.execute("""
            UPDATE servicios
            SET
                factura = %s,
                valor_factura = %s,
                fecha_factura = %s,
                terminos_pago = %s
            WHERE consec = %s
        """, (
            numero_factura,
            total,
            fecha_factura.date(),
            payload.get("termino_pago"),
            servicio_id
        ))

        conn.commit()

        return {
            "status": "ok",
            "factura_id": factura_id,
            "numero_factura": numero_factura,
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


@router.get("/{factura_id}")
def get_factura(factura_id: int, conn=Depends(get_db)):
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


