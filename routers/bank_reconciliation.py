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

    # -----------------------------
    # WHERE dinámico (compartido)
    # -----------------------------
    where_clauses = []
    params = {}

    if codigo_cliente:
        where_clauses.append("codigo_cliente = %(codigo_cliente)s")
        params["codigo_cliente"] = codigo_cliente

    if referencia:
        where_clauses.append("numero_referencia ILIKE %(referencia)s")
        params["referencia"] = f"%{referencia}%"

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # -----------------------------
    # QUERY UNIFICADO
    # -----------------------------
    sql = f"""
        SELECT *
        FROM (
            -- ===============================
            -- CASH APP
            -- ===============================
            SELECT
                ca.id,
                'CASH_APP' AS origen,
                ca.codigo_cliente,
                ca.nombre_cliente,
                ca.banco,
                ca.numero_documento AS documento,
                ca.referencia AS numero_referencia,
                ca.fecha_pago,
                ca.monto_pagado AS monto,
                ca.created_at,
                CASE
                    WHEN ca.monto_pagado > 0 THEN 'APLICADO'
                    ELSE 'DESAPLICADO'
                END AS estado
            FROM cash_app ca

            UNION ALL

            -- ===============================
            -- INCOMING PAYMENTS
            -- ===============================
            SELECT
                ip.id,
                ip.origen,
                ip.codigo_cliente,
                ip.nombre_cliente,
                ip.banco,
                ip.documento,
                ip.numero_referencia,
                ip.fecha_pago,
                ip.monto,
                ip.created_at,
                ip.estado
            FROM incoming_payments ip
        ) t
        {where_sql}
        ORDER BY fecha_pago DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    params["limit"] = page_size
    params["offset"] = offset

    cur.execute(sql, params)
    rows = cur.fetchall()

    # -----------------------------
    # TOTAL PARA PAGINACIÓN
    # -----------------------------
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT ca.id
            FROM cash_app ca

            UNION ALL

            SELECT ip.id
            FROM incoming_payments ip
        ) t
        {where_sql}
    """

    cur.execute(count_sql, params)
    total = cur.fetchone()["total"]

    cur.close()

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "data": rows
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
