from fastapi import APIRouter, Depends, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor

from database import get_db

router = APIRouter(
    prefix="/cliente-credito",
    tags=["Cliente Crédito"]
)

# ============================================================
# GET crédito por cliente
# ============================================================
@router.get("/{codigo_cliente}")
def get_credito_cliente(codigo_cliente: str, conn=Depends(get_db)):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                codigo_cliente,
                termino_pago,
                limite_credito,
                moneda,
                estado_credito,
                hold_manual,
                observaciones
            FROM cliente_credito
            WHERE codigo_cliente = %s
        """, (codigo_cliente,))

        data = cur.fetchone()
        cur.close()

        if not data:
            return {
                "exists": False,
                "message": "Cliente sin configuración crediticia"
            }

        return {
            "exists": True,
            "data": data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST crear crédito inicial por cliente
# ============================================================
@router.post("/")
def create_credito_cliente(payload: dict, conn=Depends(get_db)):
    """
    payload esperado:
    {
        codigo_cliente,
        termino_pago,
        limite_credito,
        moneda,
        observaciones
    }
    """
    try:
        cur = conn.cursor()

        # Verificar si ya existe
        cur.execute("""
            SELECT 1 FROM cliente_credito
            WHERE codigo_cliente = %s
        """, (payload["codigo_cliente"],))

        if cur.fetchone():
            raise HTTPException(
                status_code=400,
                detail="El cliente ya tiene configuración crediticia"
            )

        cur.execute("""
            INSERT INTO cliente_credito (
                codigo_cliente,
                termino_pago,
                limite_credito,
                moneda,
                observaciones
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            payload["codigo_cliente"],
            payload.get("termino_pago"),
            payload.get("limite_credito", 0),
            payload.get("moneda", "USD"),
            payload.get("observaciones")
        ))

        conn.commit()
        cur.close()

        return {"message": "Configuración crediticia creada"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PUT actualizar crédito del cliente
# ============================================================
@router.put("/{codigo_cliente}")
def update_credito_cliente(codigo_cliente: str, payload: dict, conn=Depends(get_db)):
    """
    payload posible:
    {
        termino_pago,
        limite_credito,
        estado_credito,
        hold_manual,
        observaciones
    }
    """
    try:
        cur = conn.cursor()

        cur.execute("""
            UPDATE cliente_credito SET
                termino_pago = COALESCE(%s, termino_pago),
                limite_credito = COALESCE(%s, limite_credito),
                estado_credito = COALESCE(%s, estado_credito),
                hold_manual = COALESCE(%s, hold_manual),
                observaciones = COALESCE(%s, observaciones),
                updated_at = CURRENT_TIMESTAMP
            WHERE codigo_cliente = %s
        """, (
            payload.get("termino_pago"),
            payload.get("limite_credito"),
            payload.get("estado_credito"),
            payload.get("hold_manual"),
            payload.get("observaciones"),
            codigo_cliente
        ))

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Cliente sin configuración crediticia"
            )

        conn.commit()
        cur.close()

        return {"message": "Configuración crediticia actualizada"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{codigo_cliente}")
def delete_credito_cliente(codigo_cliente: str, conn=Depends(get_db)):
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cliente_credito WHERE codigo_cliente = %s",
        (codigo_cliente,)
    )

    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="No existe configuración")

    conn.commit()
    cur.close()
    return {"message": "Configuración crediticia eliminada"}

