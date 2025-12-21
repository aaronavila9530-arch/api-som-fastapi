from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date

from database import get_db

router = APIRouter(
    prefix="/incoming-payments",
    tags=["Incoming Payments"]
)

# ============================================================
# POST /incoming-payments
# Registrar pago manual (NO aplicado)
# ============================================================
@router.post("")
def create_incoming_payment(
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado:
    {
        "origen": "MANUAL",
        "codigo_cliente": "MSL-0001-C",
        "nombre_cliente": "MSL",
        "banco": "BAC",
        "documento": "2202",
        "numero_referencia": "16561516",
        "fecha_pago": "2025-12-19",
        "monto": 1000.00
    }
    """

    required_fields = [
        "origen",
        "codigo_cliente",
        "nombre_cliente",
        "banco",
        "fecha_pago",
        "monto"
    ]

    for field in required_fields:
        if not payload.get(field):
            raise HTTPException(
                status_code=400,
                detail=f"Campo requerido faltante: {field}"
            )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        sql = """
            INSERT INTO incoming_payments (
                origen,
                codigo_cliente,
                nombre_cliente,
                banco,
                documento,
                numero_referencia,
                fecha_pago,
                monto,
                estado
            ) VALUES (
                %(origen)s,
                %(codigo_cliente)s,
                %(nombre_cliente)s,
                %(banco)s,
                %(documento)s,
                %(numero_referencia)s,
                %(fecha_pago)s,
                %(monto)s,
                'UNAPPLIED'
            )
            RETURNING id
        """

        cur.execute(sql, {
            "origen": payload["origen"],
            "codigo_cliente": payload["codigo_cliente"],
            "nombre_cliente": payload["nombre_cliente"],
            "banco": payload["banco"],
            "documento": payload.get("documento"),
            "numero_referencia": payload.get("numero_referencia"),
            "fecha_pago": payload["fecha_pago"],
            "monto": payload["monto"]
        })

        new_id = cur.fetchone()["id"]
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        cur.close()

    return {
        "status": "success",
        "message": "Pago registrado correctamente",
        "incoming_payment_id": new_id
    }
