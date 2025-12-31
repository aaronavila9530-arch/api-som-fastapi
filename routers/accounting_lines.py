from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

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
def get_accounting_lines(conn=Depends(get_db)):
    """
    Retorna líneas contables DIRECTAMENTE desde accounting_lines.
    NO agrupa
    NO calcula
    NO inventa
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
                al.created_at
            FROM accounting_lines al
            ORDER BY
                al.created_at,
                al.entry_id,
                al.id
        """)

        return cur.fetchall()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
