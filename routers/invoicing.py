from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from datetime import date
from database import get_db

router = APIRouter(
    prefix="/invoicing",
    tags=["Invoicing & Billing"]
)

# ============================================================
# GET /invoicing/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(
    cliente: str = Query(..., min_length=1),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT
                consec,
                num_informe,
                buque_contenedor,
                operacion,
                fecha_inicio,
                fecha_fin,
                cliente,
                detalle,
                terminos_pago,
                honorarios,
                factura
            FROM servicios
            WHERE
                cliente = %s
                AND estado = 'Finalizado'
                AND num_informe IS NOT NULL
                AND factura IS NULL
            ORDER BY fecha_inicio
        """, (cliente,))

        data = cur.fetchall()

        return {
            "total": len(data),
            "data": data
        }

    finally:
        cur.close()


# ============================================================
# POST /invoicing/emitir
# EMITE FACTURA Y GUARDA SNAPSHOT COMPLETO
# ============================================================
@router.post("/emitir")
def emitir_factura(
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado:
    {
        servicio_id,
        tipo_factura,
        numero_documento,
        moneda,
        total,
        termino_pago,
        descripcion
    }
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1️⃣ Obtener servicio
        cur.execute("""
            SELECT *
            FROM servicios
            WHERE consec = %s
        """, (payload["servicio_id"],))

        servicio = cur.fetchone()
        if not servicio:
            raise HTTPException(404, "Servicio no encontrado")

        # 2️⃣ Calcular periodo operación
        periodo = ""
        if servicio.get("fecha_inicio") and servicio.get("fecha_fin"):
            periodo = f"{servicio['fecha_inicio']} → {servicio['fecha_fin']}"

        # 3️⃣ INSERT SNAPSHOT EN INVOICING
        cur.execute("""
            INSERT INTO invoicing (
                factura_id,
                tipo_factura,
                tipo_documento,
                numero_documento,
                codigo_cliente,
                nombre_cliente,
                fecha_emision,
                moneda,
                total,
                num_informe,
                termino_pago,
                buque_contenedor,
                operacion,
                periodo_operacion,
                descripcion_servicio
            ) VALUES (
                %(factura_id)s,
                %(tipo_factura)s,
                'FACTURA',
                %(numero_documento)s,
                %(codigo_cliente)s,
                %(nombre_cliente)s,
                NOW(),
                %(moneda)s,
                %(total)s,
                %(num_informe)s,
                %(termino_pago)s,
                %(buque_contenedor)s,
                %(operacion)s,
                %(periodo_operacion)s,
                %(descripcion_servicio)s
            )
            RETURNING id
        """, {
            "factura_id": servicio["consec"],
            "tipo_factura": payload["tipo_factura"],
            "numero_documento": payload["numero_documento"],
            "codigo_cliente": servicio["cliente"],
            "nombre_cliente": servicio["cliente"],
            "moneda": payload["moneda"],
            "total": payload["total"],
            "num_informe": servicio["num_informe"],
            "termino_pago": payload["termino_pago"],
            "buque_contenedor": servicio.get("buque_contenedor"),
            "operacion": servicio.get("operacion"),
            "periodo_operacion": periodo,
            "descripcion_servicio": payload.get("descripcion", "")
        })

        factura_id = cur.fetchone()["id"]

        # 4️⃣ Marcar servicio como facturado
        cur.execute("""
            UPDATE servicios
            SET factura = %s
            WHERE consec = %s
        """, (payload["numero_documento"], servicio["consec"]))

        conn.commit()

        return {
            "status": "ok",
            "factura_id": factura_id,
            "numero_documento": payload["numero_documento"]
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error emitiendo factura: {str(e)}")

    finally:
        cur.close()
