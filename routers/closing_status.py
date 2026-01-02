from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Query
)
from psycopg2.extras import RealDictCursor

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/closing/period",
    tags=["Closing - Period"]
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


@router.get("/status")
def get_period_status(
    company_code: str = Query(...),
    fiscal_year: int = Query(...),
    period: int = Query(...),
    ledger: str = Query("0L"),
    conn=Depends(get_db)
):
    """
    Retorna el estado del período contable.
    NO modifica datos.
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT
            company_code,
            fiscal_year,
            period,
            ledger,
            period_closed,
            gl_closed,
            tb_closed,
            pnl_closed,
            fs_closed,
            fy_opened,
            last_batch_id,
            updated_at
        FROM closing_status
        WHERE company_code = %s
          AND fiscal_year = %s
          AND period = %s
          AND ledger = %s
        """,
        (company_code, fiscal_year, period, ledger)
    )

    row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="No existe estado de cierre para el período solicitado"
        )

    return row
