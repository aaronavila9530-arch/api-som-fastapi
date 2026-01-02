from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header
)
from psycopg2.extras import RealDictCursor

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/accounting-lines",
    tags=["Accounting"]
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
