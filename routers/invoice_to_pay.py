from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from datetime import date
from typing import Optional


import os
import shutil
from fastapi import UploadFile, File, Form
from datetime import datetime


from database import get_db

router = APIRouter(
    prefix="/invoice-to-pay",
    tags=["Finance - Invoice to Pay"]
)

# ============================================================
# 🔁 SYNC SERVICIOS → PAYMENT OBLIGATIONS
# ============================================================
def _sync_servicios_to_itp(cur):
    """
    Inserta honorarios de surveyores desde servicios
    usando SOLO columnas válidas del modelo ITP
    """
    cur.execute("""
        INSERT INTO payment_obligations (
            record_type,
            payee_type,
            payee_name,
            obligation_type,
            reference,
            vessel,
            country,
            operation,
            service_id,
            currency,
            total,
            balance,
            status,
            origin,
            notes,
            created_at
        )
        SELECT
            'OBLIGATION',
            'SURVEYOR',
            s.surveyor,
            'SURVEYOR_FEE',
            s.consec,
            s.buque_contenedor,
            s.pais,
            s.operacion,
            s.consec,
            'USD',
            s.honorarios,
            s.honorarios,
            'PENDING',
            'SERVICIOS',
            s.detalle,
            NOW()
        FROM servicios s
        WHERE
            s.surveyor IS NOT NULL
            AND s.honorarios IS NOT NULL
            AND s.honorarios > 0
            AND NOT EXISTS (
                SELECT 1
                FROM payment_obligations po
                WHERE po.service_id = s.consec
                  AND po.origin = 'SERVICIOS'
            )
    """)

@router.get("/search")
def search_invoice_to_pay(
    obligation_type: Optional[str] = Query(None),
    payee: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    issue_date_from: Optional[date] = Query(None),
    issue_date_to: Optional[date] = Query(None),
    payment_date_from: Optional[date] = Query(None),
    payment_date_to: Optional[date] = Query(None),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 🔁 Sync servicios → ITP
    _sync_servicios_to_itp(cur)
    conn.commit()

    filters = []
    params = []

    # =========================
    # DEFAULT: excluir PAID
    # =========================
    if not status:
        filters.append("status <> 'PAID'")
    else:
        filters.append("status = %s")
        params.append(status)

    # =========================
    # OBLIGATION TYPE
    # =========================
    if obligation_type:
        if obligation_type == "SURVEYOR":
            filters.append("origin = 'SERVICIOS'")
        elif obligation_type == "FACTURA_ELECTRONICA":
            filters.append("origin = 'XML'")
        elif obligation_type == "MANUAL":
            filters.append("origin = 'MANUAL'")

    # =========================
    # PAYEE
    # =========================
    if payee:
        filters.append("payee_name ILIKE %s")
        params.append(f"%{payee}%")

    # =========================
    # ISSUE DATE RANGE
    # =========================
    if issue_date_from:
        filters.append("issue_date >= %s")
        params.append(issue_date_from)

    if issue_date_to:
        filters.append("issue_date <= %s")
        params.append(issue_date_to)

    # =========================
    # PAYMENT DATE RANGE
    # =========================
    if payment_date_from:
        filters.append("last_payment_date >= %s")
        params.append(payment_date_from)

    if payment_date_to:
        filters.append("last_payment_date <= %s")
        params.append(payment_date_to)

    where_clause = " AND ".join(filters)
    if where_clause:
        where_clause = "WHERE " + where_clause

    sql = f"""
        SELECT
            id,
            payee_name,

            -- 🧠 OBLIGATION
            CASE
                WHEN origin = 'SERVICIOS' THEN 'SURVEYOR'
                WHEN origin = 'XML' THEN 'FACTURA_ELECTRONICA'
                WHEN origin = 'MANUAL' THEN 'MANUAL'
                ELSE obligation_type
            END AS obligation_type,

            -- 📌 REFERENCIA
            CASE
                WHEN origin = 'SERVICIOS' THEN notes
                ELSE reference
            END AS reference,

            vessel,

            -- 🌍 PAÍS
            CASE
                WHEN origin = 'XML' THEN 'Costa Rica'
                ELSE country
            END AS country,

            operation,
            currency,
            total,
            balance,
            status,
            last_payment_date,

            -- 📅 ISSUE DATE
            issue_date,

            -- ⏳ DUE DATE
            due_date

        FROM payment_obligations
        {where_clause}
        ORDER BY issue_date DESC
    """

    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"InvoiceToPay search error: {str(e)}"
        )

    return {"data": rows}

# ============================================================
# 2️⃣ KPIs
# ============================================================
@router.get("/kpis")
def invoice_to_pay_kpis(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status IN ('PENDING','PARTIAL') THEN balance END), 0) AS pending,
            COALESCE(SUM(CASE WHEN status IN ('PARTIAL','PAID') THEN (total - balance) END), 0) AS paid,
            ROUND(
                AVG(
                    CASE
                        WHEN status = 'PAID'
                        AND last_payment_date IS NOT NULL
                        AND issue_date IS NOT NULL
                        THEN (last_payment_date - issue_date)
                    END
                ), 2
            ) AS dpo,
            COUNT(
                CASE
                    WHEN balance > 0
                    AND due_date IS NOT NULL
                    AND due_date < CURRENT_DATE
                    THEN 1
                END
            ) AS overdue
        FROM payment_obligations
        WHERE record_type = 'OBLIGATION'
    """)

    pending, paid, dpo, overdue = cur.fetchone()

    return {
        "pending": pending,
        "paid": paid,
        "dpo": dpo,
        "overdue": overdue
    }

# ============================================================
# 3️⃣ APPLY PAYMENT
# ============================================================
@router.post("/apply-payment")
def apply_payment(
    obligation_id: int,
    amount: float,
    payment_date: date,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

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

# ============================================================
# 4️⃣ MANUAL OBLIGATION
# ============================================================
@router.post("/manual")
def create_manual_obligation(
    payee_name: str,
    obligation_type: str,
    total: float,
    currency: str,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
    payee_type: str = "OTHER",
    conn=Depends(get_db)
):
    if total <= 0:
        raise HTTPException(
            status_code=400,
            detail="Total must be greater than zero"
        )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                payee_type,
                payee_name,
                obligation_type,
                reference,
                currency,
                total,
                balance,
                status,
                origin,
                notes,
                active,
                created_at
            )
            VALUES (
                'OBLIGATION',
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'PENDING',
                'MANUAL',
                %s,
                TRUE,
                NOW()
            )
            RETURNING id
        """, (
            payee_type,
            payee_name,
            obligation_type,
            reference,
            currency,
            total,
            total,
            notes
        ))

        new_id = cur.fetchone()["id"]
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating manual obligation: {str(e)}"
        )

    return {
        "message": "Manual obligation created successfully",
        "id": new_id
    }

# ============================================================
# 5️⃣ UPLOAD XML (FACTURA ELECTRÓNICA)
# ============================================================
@router.post("/upload/xml")
def upload_invoice_xml(
    file: UploadFile = File(...),
    payee_name: str = Form(...),
    reference: str = Form(...),
    currency: str = Form(...),
    total: float = Form(...),
    notes: Optional[str] = Form(None),
    conn=Depends(get_db)
):
    if total <= 0:
        raise HTTPException(status_code=400, detail="Invalid total amount")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    os.makedirs("storage/invoice_to_pay/xml", exist_ok=True)
    filename = f"{reference}_{int(datetime.now().timestamp())}.xml"
    filepath = os.path.join("storage/invoice_to_pay/xml", filename)

    try:
        # Guardar archivo
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Insertar obligación
        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                payee_type,
                payee_name,
                obligation_type,
                reference,
                currency,
                total,
                balance,
                status,
                origin,
                file_xml,
                notes,
                active,
                created_at
            )
            VALUES (
                'OBLIGATION',
                'SUPPLIER',
                %s,
                'SUPPLIER_INVOICE',
                %s,
                %s,
                %s,
                %s,
                'PENDING',
                'UPLOAD',
                %s,
                %s,
                TRUE,
                NOW()
            )
        """, (
            payee_name,
            reference,
            currency,
            total,
            total,
            filepath,
            notes
        ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"XML upload error: {str(e)}"
        )

    return {"message": "XML invoice uploaded successfully"}


# ============================================================
# 6️⃣ UPLOAD PDF (ADJUNTO)
# ============================================================
@router.post("/upload/pdf")
def upload_invoice_pdf(
    file: UploadFile = File(...),
    reference: str = Form(...),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    os.makedirs("storage/invoice_to_pay/pdf", exist_ok=True)
    filename = f"{reference}_{int(datetime.now().timestamp())}.pdf"
    filepath = os.path.join("storage/invoice_to_pay/pdf", filename)

    try:
        # Guardar archivo
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Insertar obligación mínima
        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                obligation_type,
                reference,
                status,
                origin,
                file_pdf,
                active,
                created_at
            )
            VALUES (
                'OBLIGATION',
                'PDF_ONLY',
                %s,
                'PENDING',
                'UPLOAD',
                %s,
                TRUE,
                NOW()
            )
        """, (
            reference,
            filepath
        ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"PDF upload error: {str(e)}"
        )

    return {"message": "PDF uploaded successfully"}

