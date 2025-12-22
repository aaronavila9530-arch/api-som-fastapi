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


# ============================================================
# GET /cliente-credito/exposure/{codigo_cliente}
# EXPOSICIÓN CREDITICIA CONSOLIDADA (ALINEADA A DB REAL)
# ============================================================
@router.get("/exposure/{codigo_cliente}")
def get_credit_exposure(
    codigo_cliente: str,
    conn=Depends(get_db)
):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ====================================================
        # 1️⃣ CREDIT CONFIG (TABLA REAL)
        # ====================================================
        cur.execute("""
            SELECT
                limite_credito,
                termino_pago,
                moneda,
                estado_credito,
                hold_manual
            FROM cliente_credito
            WHERE codigo_cliente = %s
        """, (codigo_cliente,))

        credit = cur.fetchone()

        if not credit:
            raise HTTPException(
                404,
                "Cliente sin configuración de crédito"
            )

        limite_credito = float(credit.get("limite_credito") or 0)
        termino_pago = int(credit.get("termino_pago") or 0)

        # ====================================================
        # 2️⃣ TOTAL FACTURAS (INVOICING)
        # ====================================================
        cur.execute("""
            SELECT
                COALESCE(SUM(total), 0) AS total_facturas
            FROM invoicing
            WHERE
                codigo_cliente = %s
                AND tipo_documento = 'FACTURA'
                AND estado = 'EMITIDA'
        """, (codigo_cliente,))

        total_facturas = float(cur.fetchone()["total_facturas"] or 0)

        # ====================================================
        # 3️⃣ TOTAL NOTAS DE CRÉDITO
        # ====================================================
        cur.execute("""
            SELECT
                COALESCE(SUM(total), 0) AS total_nc
            FROM invoicing
            WHERE
                codigo_cliente = %s
                AND tipo_documento = 'NOTA_CREDITO'
                AND estado = 'EMITIDA'
        """, (codigo_cliente,))

        total_nc = float(cur.fetchone()["total_nc"] or 0)

        # ====================================================
        # 4️⃣ EXPOSICIÓN REAL
        # ====================================================
        exposicion_real = total_facturas - total_nc

        # ====================================================
        # 5️⃣ DISPONIBLE
        # ====================================================
        disponible = limite_credito - exposicion_real

        # ====================================================
        # 6️⃣ SEMÁFORO + ESTADO EXPOSICIÓN
        # ====================================================
        porcentaje_disponible = (
            disponible / limite_credito
            if limite_credito > 0 else -1
        )

        if disponible <= 0:
            semaforo = "ROJO"
            exposicion_estado = "OVERLIMIT"
        elif porcentaje_disponible <= 0.20:
            semaforo = "AMARILLO"
            exposicion_estado = "CRITICO"
        else:
            semaforo = "VERDE"
            exposicion_estado = "NORMAL"

        # ====================================================
        # 7️⃣ PAYMENT TREND (INCOMING PAYMENTS)
        # ====================================================
        avg_days = None
        trend = "SIN_DATOS"

        cur.execute("""
            SELECT
                AVG(
                    DATE_PART(
                        'day',
                        p.fecha_pago - i.fecha_emision
                    )
                ) AS avg_days
            FROM incoming_payments p
            JOIN invoicing i
                ON i.numero_documento = p.documento
            WHERE
                p.codigo_cliente = %s
                AND p.estado = 'APPLIED'
                AND p.fecha_pago IS NOT NULL
                AND i.fecha_emision IS NOT NULL
        """, (codigo_cliente,))

        row = cur.fetchone()

        if row and row["avg_days"] is not None:
            avg_days = round(row["avg_days"])

            if avg_days <= termino_pago:
                trend = "BUENO"
            elif avg_days <= termino_pago + 15:
                trend = "MEDIO"
            else:
                trend = "LENTO"

        # ====================================================
        # RESPONSE
        # ====================================================
        return {
            "codigo_cliente": codigo_cliente,
            "limite_credito": limite_credito,
            "total_facturado": exposicion_real,
            "disponible": disponible,
            "exposicion": exposicion_estado,
            "semaforo": semaforo,
            "payment_trend": {
                "avg_days_to_pay": avg_days,
                "trend": trend
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            500,
            f"Error calculando exposición crediticia: {str(e)}"
        )
    finally:
        cur.close()
