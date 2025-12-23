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
    usando SOLO columnas válidas del modelo ITP.
    Se asignan también issue_date y due_date:
      - issue_date = fecha_fin
      - due_date = fecha_fin + 15 días
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
            issue_date,
            due_date,
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
            s.fecha_fin AS issue_date,
            (s.fecha_fin + INTERVAL '15 days') AS due_date,
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
            AND s.fecha_fin IS NOT NULL
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

    # =================
    # FILTRO POR ESTADO
    # =================
    # Si no se especifica, excluir PAID
    if status:
        filters.append("status = %s")
        params.append(status)
    else:
        filters.append("status <> 'PAID'")

    # =================================
    # FILTRO POR TIPO DE OBLIGACIÓN
    # =================================
    if obligation_type:
        if obligation_type.upper() == "SURVEYOR":
            filters.append("origin = 'SERVICIOS'")
        elif obligation_type.upper() == "FACTURA_ELECTRONICA":
            filters.append("origin = 'XML'")
        elif obligation_type.upper() == "MANUAL":
            filters.append("origin = 'MANUAL'")

    # ================
    # FILTRO BENEFICIARIO
    # ================
    if payee:
        filters.append("payee_name ILIKE %s")
        params.append(f"%{payee}%")

    # ================================
    # FILTROS POR RANGOS DE FECHA
    # ================================
    if issue_date_from:
        filters.append("issue_date >= %s")
        params.append(issue_date_from)

    if issue_date_to:
        filters.append("issue_date <= %s")
        params.append(issue_date_to)

    if payment_date_from:
        filters.append("last_payment_date >= %s")
        params.append(payment_date_from)

    if payment_date_to:
        filters.append("last_payment_date <= %s")
        params.append(payment_date_to)

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    # ========================================
    # SELECT FINAL NORMALIZADO
    # ========================================
    sql = f"""
        SELECT
            id,
            payee_name,

            -- 🧠 obligation_type normalizado
            CASE
                WHEN origin = 'SERVICIOS' THEN 'SURVEYOR'
                WHEN origin = 'XML' THEN 'FACTURA_ELECTRONICA'
                WHEN origin = 'MANUAL' THEN 'MANUAL'
                ELSE obligation_type
            END AS obligation_type,

            -- 📌 reference limpio
            CASE
                WHEN origin = 'SERVICIOS' THEN notes
                ELSE reference
            END AS reference,

            vessel,

            -- 🌍 País (Costa Rica si XML)
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
            issue_date,
            due_date,
            notes

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
# 2️⃣ KPIs — CONVERSIÓN CRC → USD (TC = 500)
# ============================================================
@router.get("/kpis")
def invoice_to_pay_kpis(conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute("""
        SELECT
            -- =========================
            -- PENDING (USD normalizado)
            -- =========================
            COALESCE(
                SUM(
                    CASE
                        WHEN status IN ('PENDING','PARTIAL') THEN
                            CASE
                                WHEN currency = 'CRC' THEN balance / 500.0
                                ELSE balance
                            END
                    END
                ), 0
            ) AS pending_usd,

            -- =========================
            -- PAID (USD normalizado)
            -- =========================
            COALESCE(
                SUM(
                    CASE
                        WHEN status IN ('PARTIAL','PAID') THEN
                            CASE
                                WHEN currency = 'CRC' THEN (total - balance) / 500.0
                                ELSE (total - balance)
                            END
                    END
                ), 0
            ) AS paid_usd,

            -- =========================
            -- DPO (NO requiere moneda)
            -- =========================
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

            -- =========================
            -- OVERDUE COUNT
            -- =========================
            COUNT(
                CASE
                    WHEN balance > 0
                    AND due_date IS NOT NULL
                    AND due_date < CURRENT_DATE
                    THEN 1
                END
            ) AS overdue,

            -- =========================
            -- OVERDUE AMOUNT (USD)
            -- =========================
            COALESCE(
                SUM(
                    CASE
                        WHEN balance > 0
                        AND due_date IS NOT NULL
                        AND due_date < CURRENT_DATE
                        THEN
                            CASE
                                WHEN currency = 'CRC' THEN balance / 500.0
                                ELSE balance
                            END
                    END
                ), 0
            ) AS overdue_amount_usd

        FROM payment_obligations
        WHERE record_type = 'OBLIGATION'
    """)

    pending, paid, dpo, overdue, overdue_amount = cur.fetchone()

    return {
        "pending": round(pending, 2),
        "paid": round(paid, 2),
        "dpo": dpo,
        "overdue": overdue,
        "overdue_amount": round(overdue_amount, 2),
        "currency": "USD",
        "exchange_rate": 500
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
# 📥 UPLOAD XML (FACTURA ELECTRÓNICA) — CON ISSUE_DATE / DUE_DATE
# ============================================================
@router.post("/upload/xml")
def upload_invoice_xml(
    file: UploadFile = File(...),
    conn=Depends(get_db)
):
    """
    Carga un XML de factura electrónica y lo inserta en payment_obligations
    con issue_date y due_date según reglas de negocio:
      - issue_date: FechaEmision del XML
      - due_date: FechaVencimiento si existe
                  si no, issue_date + 30 días
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Guardar el archivo
    os.makedirs("storage/invoice_to_pay/xml", exist_ok=True)
    timestamp = int(datetime.now().timestamp())
    filename = f"xml_{timestamp}_{file.filename}"
    filepath = os.path.join("storage/invoice_to_pay/xml", filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Leer XML
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        ns = {"fe": root.tag.split("}")[0].strip("{")}

        # ----------------------------
        # Campos del XML
        # ----------------------------
        clave = root.find(".//fe:Clave", ns).text
        fecha_emision = root.find(".//fe:FechaEmision", ns).text.split("T")[0]
        emisor = root.find(".//fe:Nombre", ns).text

        moneda = root.find(".//fe:CodigoMoneda", ns).text
        total = float(root.find(".//fe:TotalComprobante", ns).text)

        # Intentar leer término de pago si existe en XML
        termino = root.find(".//fe:PlazoCredito", ns)
        if termino is not None and termino.text.isdigit():
            term_days = int(termino.text)
        else:
            term_days = 30

        # ----------------------------
        # Fechas de emisión y vencimiento
        # ----------------------------
        issue_date_val = date.fromisoformat(fecha_emision)
        due_date_val = issue_date_val + timedelta(days=term_days)

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing XML: {str(e)}"
        )

    # ----------------------------
    # Insertar en la tabla
    # ----------------------------
    try:
        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                payee_type,
                payee_name,
                obligation_type,
                reference,
                issue_date,
                due_date,
                country,
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
                'FACTURA_ELECTRONICA',
                %s,
                %s,
                %s,
                'Costa Rica',
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
            emisor,
            clave,
            issue_date_val,
            due_date_val,
            moneda,
            total,
            total,
            filepath,
            f"Factura electrónica {clave}"
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error inserting obligation from XML: {str(e)}"
        )

    return {"message": "XML invoice uploaded and obligation created successfully"}


# ============================================================
# 📥 UPLOAD PDF (ADJUNTO) con issue_date y due_date
# ============================================================
@router.post("/upload/pdf")
def upload_invoice_pdf(
    file: UploadFile = File(...),
    reference: str = Form(...),
    issue_date: Optional[date] = Form(None),
    due_date: Optional[date] = Form(None),
    conn=Depends(get_db)
):
    """
    Carga un PDF y crea una obligación en payment_obligations
    Usará la lógica:
      - issue_date: si provisto por UI, si no, fecha actual
      - due_date: si provisto por UI, si no, same day (contado)
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Normalizar fechas
    issue_val = issue_date or date.today()
    due_val = due_date or issue_val

    os.makedirs("storage/invoice_to_pay/pdf", exist_ok=True)
    timestamp = int(datetime.now().timestamp())
    filename = f"pdf_{timestamp}_{file.filename}"
    filepath = os.path.join("storage/invoice_to_pay/pdf", filename)

    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                obligation_type,
                reference,
                issue_date,
                due_date,
                currency,
                total,
                balance,
                status,
                origin,
                file_pdf,
                notes,
                active,
                created_at
            )
            VALUES (
                'OBLIGATION',
                'PDF_ONLY',
                %s,
                %s,
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
            reference,
            issue_val,
            due_val,
            "USD",         # Por defecto USD (puedes ajustar luego)
            0.0,           # Sin monto explícito para PDF
            0.0,
            filepath,
            f"PDF adjunto para {reference}"
        ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"PDF upload error: {str(e)}"
        )

    return {"message": "PDF uploaded and obligation created successfully"}

