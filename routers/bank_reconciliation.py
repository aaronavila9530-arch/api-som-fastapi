from fastapi import APIRouter, Depends, Query, HTTPException, Header
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/bank-reconciliation",
    tags=["Bank Reconciliation"]
)

# ============================================================
# RBAC GUARD
# ============================================================
def require_permission(module: str, action: str):
    def checker(
        x_user_role: str = Header(..., alias="X-User-Role")
    ):
        if not has_permission(x_user_role, module, action):
            raise HTTPException(
                status_code=403,
                detail="No autorizado"
            )
    return checker

# ============================================================
# GET /bank-reconciliation
# LISTADO PAGINADO (cash_app + incoming_payments)
# ============================================================
@router.get("")
def get_bank_reconciliation(
    codigo_cliente: Optional[str] = Query(None),
    referencia: Optional[str] = Query(None),
    ver_todos: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_db)
):

    # -----------------------------
    # PROTECCIÓN ANTI-LAG
    # -----------------------------
    if not ver_todos and not codigo_cliente and not referencia:
        return {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "data": []
        }

    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # ===================== CASH_APP (NO TOCAR) ==================
    # ============================================================

    where_clauses = []
    params = {}

    if codigo_cliente:
        where_clauses.append("ca.codigo_cliente = %(codigo_cliente)s")
        params["codigo_cliente"] = codigo_cliente

    if referencia:
        where_clauses.append("ca.referencia ILIKE %(referencia)s")
        params["referencia"] = f"%{referencia}%"

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    cash_sql = f"""
        SELECT
            ca.id,
            'CASH_APP' AS origen,
            ca.numero_documento AS documento,
            ca.codigo_cliente,
            ca.nombre_cliente,
            ca.banco,
            ca.fecha_pago,
            ca.comision,
            ca.referencia AS numero_referencia,
            ca.monto_pagado AS monto,
            ca.tipo_aplicacion,
            ca.created_at,

            -- UI
            0::numeric AS monto_aplicado,
            ca.monto_pagado AS saldo,

            CASE
                WHEN ca.monto_pagado > 0 THEN 'APLICADO'
                ELSE 'DESAPLICADO'
            END AS estado
        FROM cash_app ca
        {where_sql}
        ORDER BY ca.fecha_pago DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    params_cash = params.copy()
    params_cash["limit"] = page_size
    params_cash["offset"] = offset

    cur.execute(cash_sql, params_cash)
    cash_rows = cur.fetchall()

    count_cash_sql = f"""
        SELECT COUNT(*) AS total
        FROM cash_app ca
        {where_sql}
    """
    cur.execute(count_cash_sql, params)
    total_cash = cur.fetchone()["total"]

    # ============================================================
    # ================= INCOMING_PAYMENTS (NUEVO) ================
    # ============================================================

    where_ip = []
    params_ip = {}

    if codigo_cliente:
        where_ip.append("ip.codigo_cliente = %(codigo_cliente)s")
        params_ip["codigo_cliente"] = codigo_cliente

    if referencia:
        where_ip.append("ip.numero_referencia ILIKE %(referencia)s")
        params_ip["referencia"] = f"%{referencia}%"

    where_ip_sql = ""
    if where_ip:
        where_ip_sql = "WHERE " + " AND ".join(where_ip)

    incoming_sql = f"""
        SELECT
            ip.id,
            ip.origen,
            ip.documento,
            ip.codigo_cliente,
            ip.nombre_cliente,
            ip.banco,
            ip.fecha_pago,
            NULL::numeric AS comision,
            ip.numero_referencia,
            ip.monto,
            NULL::text AS tipo_aplicacion,
            ip.created_at,

            -- UI
            0::numeric AS monto_aplicado,
            ip.monto AS saldo,
            ip.estado
        FROM incoming_payments ip
        {where_ip_sql}
        ORDER BY ip.fecha_pago DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    params_ip["limit"] = page_size
    params_ip["offset"] = offset

    cur.execute(incoming_sql, params_ip)
    incoming_rows = cur.fetchall()

    count_ip_sql = f"""
        SELECT COUNT(*) AS total
        FROM incoming_payments ip
        {where_ip_sql}
    """
    cur.execute(count_ip_sql, params_ip)
    total_ip = cur.fetchone()["total"]

    cur.close()

    # ============================================================
    # ======================= RESULTADO ==========================
    # ============================================================
    data = cash_rows + incoming_rows

    return {
        "page": page,
        "page_size": page_size,
        "total": total_cash + total_ip,
        "data": data
    }


# ============================================================
# POST /bank-reconciliation/{cash_app_id}/reverse
# REVERSA TOTAL (DELETE REAL)
# ============================================================
@router.post("/{cash_app_id}/reverse")
def reverse_cash_app(
    cash_app_id: int,
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado:
    {
        "reason": "WRONG_PAYMENT",
        "comment": "Payment registered incorrectly"
    }
    """

    reason = payload.get("reason")
    comment = payload.get("comment")

    if not reason or not comment:
        raise HTTPException(
            status_code=400,
            detail="Reason and comment are required."
        )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # -----------------------------
    # Verificar existencia
    # -----------------------------
    cur.execute("""
        SELECT id
        FROM cash_app
        WHERE id = %(id)s
    """, {"id": cash_app_id})

    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(
            status_code=404,
            detail="Payment not found in cash_app."
        )

    # -----------------------------
    # REVERSA REAL
    # -----------------------------
    cur.execute("""
        DELETE FROM cash_app
        WHERE id = %(id)s
    """, {"id": cash_app_id})

    conn.commit()
    cur.close()

    return {
        "status": "success",
        "message": "Payment reversed and removed from cash_app.",
        "cash_app_id": cash_app_id
    }
