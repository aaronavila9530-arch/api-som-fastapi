from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header
)
from psycopg2.extras import RealDictCursor
from datetime import date

from database import get_db
from backend_api.rbac_service import has_permission


router = APIRouter(
    prefix="/accounting/adjustments",
    tags=["Accounting - Adjustments"]
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


@router.post("/create")
def create_accounting_adjustment(payload: dict, conn=Depends(get_db)):
    """
    Crea un ASIENTO DE AJUSTE contable.

    payload esperado:
    {
        "original_entry_id": 7,
        "entry_date": "2025-12-27",
        "lines": [
            {
                "account_code": "4101",
                "account_name": "Ingresos por servicios",
                "debit": 0,
                "credit": 10000
            },
            {
                "account_code": "1101",
                "account_name": "Cuentas por cobrar",
                "debit": 10000,
                "credit": 0
            }
        ]
    }
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        original_entry_id = payload.get("original_entry_id")
        lines = payload.get("lines", [])
        entry_date = payload.get("entry_date") or date.today()

        if not original_entry_id:
            raise HTTPException(400, "original_entry_id es requerido")

        if not lines or len(lines) < 2:
            raise HTTPException(400, "El ajuste debe tener al menos 2 líneas")

        # ============================
        # Validar partida doble
        # ============================
        total_debit = round(sum(float(l.get("debit", 0)) for l in lines), 2)
        total_credit = round(sum(float(l.get("credit", 0)) for l in lines), 2)

        if abs(total_debit - total_credit) > 0.01:
            raise HTTPException(
                400,
                f"Asiento descuadrado. Debe={total_debit}, Haber={total_credit}"
            )

        period = str(entry_date)[:7]

        # ============================
        # Crear asiento cabecera
        # ============================
        cur.execute("""
            INSERT INTO accounting_entries (
                entry_date,
                period,
                description,
                origin,
                origin_id,
                created_by
            )
            VALUES (%s, %s, %s, 'ADJUSTMENT', %s, 'SYSTEM')
            RETURNING id
        """, (
            entry_date,
            period,
            f"Asiento de ajuste #{original_entry_id}",
            original_entry_id
        ))

        adjustment_entry_id = cur.fetchone()["id"]

        # ============================
        # Insertar líneas
        # ============================
        for l in lines:
            cur.execute("""
                INSERT INTO accounting_lines (
                    entry_id,
                    account_code,
                    account_name,
                    debit,
                    credit,
                    line_description
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                adjustment_entry_id,
                l["account_code"],
                l["account_name"],
                float(l.get("debit", 0)),
                float(l.get("credit", 0)),
                f"Ajuste de asiento #{original_entry_id}"
            ))

        conn.commit()

        return {
            "status": "ok",
            "adjustment_entry_id": adjustment_entry_id
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
