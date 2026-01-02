from fastapi import APIRouter, Depends, Query, HTTPException, Header
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db
from backend_api.rbac_service import has_permission


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
# GET /bank-reconciliation (LISTADO PAGINADO cash_app)
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
    # WHERE dinámico
    # -----------------------------
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

    # -----------------------------
    # QUERY PRINCIPAL (cash_app)
    # -----------------------------
    sql = f"""
        SELECT
            ca.id,
            ca.numero_documento,
            ca.codigo_cliente,
            ca.nombre_cliente,
            ca.banco,
            ca.fecha_pago,
            ca.comision,
            ca.referencia,
            ca.monto_pagado,
            ca.tipo_aplicacion,
            ca.created_at,

            -- Calculados solo para UI
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

    params["limit"] = page_size
    params["offset"] = offset

    cur.execute(sql, params)
    rows = cur.fetchall()

    # -----------------------------
    # TOTAL PARA PAGINACIÓN
    # -----------------------------
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM cash_app ca
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
