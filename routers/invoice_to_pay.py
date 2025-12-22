from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from datetime import date
from typing import Optional

from database import get_db


router = APIRouter(
    prefix="/invoice-to-pay",
    tags=["Finance - Invoice to Pay"]
)

# ============================================================
# 1️⃣ SEARCH PAYMENT OBLIGATIONS
# ============================================================
@router.get("/search")
def search_invoice_to_pay(
    obligation_type: Optional[str] = Query(None),
    payee: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    filters = []
    params = []

    if obligation_type:
        filters.append("obligation_type = %s")
        params.append(obligation_type)

    if payee:
        filters.append("payee_name ILIKE %s")
        params.append(f"%{payee}%")

    if status:
        filters.append("status = %s")
        params.append(status)

    where_clause = " AND " + " AND ".join(filters) if filters else ""

    sql = f"""
        SELECT
            id,
            payee_name,
            obligation_type,
            reference,
            vessel,
            country,
            operation,
            currency,
            total,
            balance,
            last_payment_date,
            status,
            due_date
        FROM payment_obligations
        WHERE record_type = 'OBLIGATION'
        {where_clause}
        ORDER BY due_date ASC
    """

    cur.execute(sql, params)
    rows = cur.fetchall()

    return {"data": rows}


@router.get("/kpis")
def invoice_to_pay_kpis(
    conn=Depends(get_db)
):
    cur = conn.cursor()

    sql = """
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('PENDING','PARTIAL') THEN balance END), 0) AS pending,
            COALESCE(SUM(CASE WHEN status IN ('PARTIAL','PAID') THEN (total - balance) END), 0) AS paid,
            ROUND(AVG(CASE WHEN status = 'PAID' THEN (last_payment_date - issue_date) END), 2) AS dpo,
            COUNT(CASE WHEN balance > 0 AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '5 days' THEN 1 END) AS upcoming,
            COUNT(CASE WHEN balance > 0 AND due_date < CURRENT_DATE THEN 1 END) AS overdue
        FROM payment_obligations
        WHERE record_type = 'OBLIGATION'
    """

    cur.execute(sql)
    pending, paid, dpo, upcoming, overdue = cur.fetchone()

    return {
        "pending": pending,
        "paid": paid,
        "dpo": dpo,
        "upcoming": upcoming,
        "overdue": overdue
    }
@router.post("/apply-payment")
def apply_payment(
    obligation_id: int,
    amount: float,
    payment_date: date,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Obtener obligación
    cur.execute("""
        SELECT id, balance
        FROM payment_obligations
        WHERE id = %s
          AND record_type = 'OBLIGATION'
    """, (obligation_id,))

    obligation = cur.fetchone()
    if not obligation:
        raise HTTPException(status_code=404, detail="Obligation not found")

    balance = obligation["balance"]

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    if amount > balance:
        raise HTTPException(status_code=400, detail="Payment exceeds outstanding balance")

    new_balance = balance - amount
    new_status = "PAID" if new_balance == 0 else "PARTIAL"

    # 2️⃣ Actualizar obligación
    cur.execute("""
        UPDATE payment_obligations
        SET
            balance = %s,
            status = %s,
            last_payment_date = %s,
            updated_at = NOW()
        WHERE id = %s
    """, (
        new_balance,
        new_status,
        payment_date,
        obligation_id
    ))

    conn.commit()

    return {
        "message": "Payment applied successfully",
        "new_balance": new_balance,
        "status": new_status
    }




