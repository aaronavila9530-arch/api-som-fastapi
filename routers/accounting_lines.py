from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from typing import List

from database import get_db

router = APIRouter(
    prefix="/accounting-lines",
    tags=["Accounting"]
)

# ============================================================
# GET /accounting-lines
# Libro Diario – líneas contables REALES
# ============================================================
@router.get("")
def get_accounting_lines(
    company_code: str = Query(...),
    conn=Depends(get_db)
):
    """
    Retorna líneas contables DIRECTAMENTE desde accounting_lines.
    NO agrupa, NO calcula, NO inventa fechas.
    """

    if not conn:
        raise HTTPException(status_code=500, detail="No DB connection")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT
                al.id              AS line_id,
                al.entry_id,
                al.account_code,
                al.account_name,
                al.debit,
                al.credit,
                al.line_description,
                al.created_at,

                ae.origin,
                ae.fiscal_year,
                ae.period

            FROM accounting_lines al
            JOIN accounting_entries ae
              ON ae.id = al.entry_id

            WHERE ae.company_code = %s

            ORDER BY
                ae.fiscal_year,
                ae.period,
                al.entry_id,
                al.id
        """, (company_code,))

        rows = cur.fetchall()
        return rows

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
