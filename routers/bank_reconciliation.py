from fastapi import APIRouter, Depends, Query
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db

router = APIRouter(
    prefix="/bank-reconciliation",
    tags=["Bank Reconciliation"]
)


# ============================================================
# GET /bank-reconciliation (paginado)
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

    # --------------------------------------------------------
    # Protección ANTI-LAG
    # --------------------------------------------------------
    if not ver_todos and not codigo_cliente and not referencia:
        return {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "data": []
        }

    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # --------------------------------------------------------
    # WHERE dinámico
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # QUERY PRINCIPAL (100% alineado a cash_app)
    # --------------------------------------------------------
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

            -- Campos calculados (NO persistidos)
            0::numeric AS monto_aplicado,
            ca.monto_pagado AS saldo,

            CASE
                WHEN ca.monto_pagado = 0 THEN 'APPLIED'
                ELSE 'UNAPPLIED'
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

    # --------------------------------------------------------
    # TOTAL PARA PAGINACIÓN
    # --------------------------------------------------------
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
# GET /bank-reconciliation/{cash_app_id}/applied
# ============================================================
@router.get("/{cash_app_id}/applied")
def get_cash_app_applied(
    cash_app_id: int,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    sql = """
        SELECT
            cad.id,
            cad.numero_documento_aplicado,
            cad.monto_aplicado,
            cad.origen,
            cad.created_at
        FROM cash_app_detail cad
        WHERE cad.cash_app_id = %(cash_app_id)s
          AND cad.is_reversed = FALSE
        ORDER BY cad.created_at ASC
    """

    cur.execute(sql, {"cash_app_id": cash_app_id})
    rows = cur.fetchall()
    cur.close()

    return {
        "cash_app_id": cash_app_id,
        "total_applied": sum(r["monto_aplicado"] for r in rows),
        "data": rows
    }

# ============================================================
# POST /bank-reconciliation/applied/{detail_id}/reverse
# ============================================================
@router.post("/applied/{detail_id}/reverse")
def reverse_cash_app_detail(
    detail_id: int,
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado:
    {
        "reason": "WRONG_APPLICATION",
        "comment": "Applied to incorrect invoice"
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

    # Verificar que exista y no esté revertido
    cur.execute("""
        SELECT id
        FROM cash_app_detail
        WHERE id = %(id)s
          AND is_reversed = FALSE
    """, {"id": detail_id})

    row = cur.fetchone()
    if not row:
        cur.close()
        raise HTTPException(
            status_code=404,
            detail="Applied record not found or already reversed."
        )

    # Reversa lógica
    cur.execute("""
        UPDATE cash_app_detail
        SET
            is_reversed = TRUE,
            reversed_at = NOW(),
            reversed_reason = %(reason)s,
            reversed_comment = %(comment)s
        WHERE id = %(id)s
    """, {
        "id": detail_id,
        "reason": reason,
        "comment": comment
    })

    conn.commit()
    cur.close()

    return {
        "status": "success",
        "message": "Application reversed successfully."
    }

