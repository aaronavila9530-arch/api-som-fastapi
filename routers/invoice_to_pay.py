from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header,
    UploadFile,
    File,
    Form
)
from psycopg2.extras import RealDictCursor
from datetime import date, datetime
from typing import Optional
import os
import shutil

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/invoice-to-pay",
    tags=["Finance - Invoice to Pay"]
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

    # 🔁 Sync servicios → Invoice To Pay
    _sync_servicios_to_itp(cur)
    conn.commit()

    filters = []
    params = []

    # =================
    # FILTRO POR ESTADO
    # =================
    if status:
        filters.append("status = %s")
        params.append(status)
    else:
        filters.append("status <> 'PAID'")

    # =================================
    # FILTRO POR TIPO DE OBLIGACIÓN
    # (basado en payee_type REAL)
    # =================================
    if obligation_type:
        if obligation_type.upper() == "SURVEYOR":
            filters.append("payee_type = 'SURVEYOR'")
        elif obligation_type.upper() == "SUPPLIER":
            filters.append("payee_type = 'SUPPLIER'")
        elif obligation_type.upper() == "MANUAL":
            filters.append("origin = 'MANUAL'")

    # =================
    # FILTRO BENEFICIARIO
    # =================
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
    # SELECT FINAL CORRECTO
    # ========================================
    sql = f"""
        SELECT
            id,
            payee_name,

            -- ✅ COLUMNA Obligación = payee_type REAL
            payee_type AS obligation_type,

            -- ✅ COLUMNA Referencia (regla de negocio)
            CASE
                WHEN origin = 'SERVICIOS' THEN notes
                ELSE reference
            END AS referencia,

            vessel,
            country,
            operation,
            currency,
            total,
            balance,
            status,
            last_payment_date,
            issue_date,
            due_date,
            origin

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
# 📥 UPLOAD XML (FACTURA ELECTRÓNICA) — ITP ROBUSTO / BLINDADO
# ============================================================
@router.post("/upload/xml")
def upload_invoice_xml(
    file: UploadFile = File(...),
    conn=Depends(get_db)
):
    """
    Carga un XML de Factura Electrónica (Costa Rica)
    y crea una obligación de pago (ITP) de forma tolerante
    a variaciones reales de XML (ATV / proveedores).
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # GUARDAR ARCHIVO
    # ============================================================
    os.makedirs("storage/invoice_to_pay/xml", exist_ok=True)

    timestamp = int(datetime.now().timestamp())
    safe_name = file.filename.replace(" ", "_")
    filename = f"{timestamp}_{safe_name}"
    filepath = os.path.join("storage/invoice_to_pay/xml", filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # ============================================================
    # PARSE XML (ULTRA ROBUSTO)
    # ============================================================
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # --------------------------------------------------------
        # Namespace dinámico (o sin namespace)
        # --------------------------------------------------------
        if "}" in root.tag:
            ns_uri = root.tag.split("}")[0].strip("{")
            ns = {"fe": ns_uri}
            p = "fe:"
        else:
            ns = {}
            p = ""

        def find_text(xpath, default=None):
            """
            Busca texto de forma segura.
            """
            try:
                node = root.find(xpath, ns)
                if node is not None and node.text:
                    return node.text.strip()
            except Exception:
                pass
            return default

        # --------------------------------------------------------
        # CLAVE (OBLIGATORIA)
        # --------------------------------------------------------
        clave = find_text(f".//{p}Clave")
        if not clave:
            raise ValueError("XML sin Clave")

        # --------------------------------------------------------
        # FECHA EMISIÓN
        # --------------------------------------------------------
        fecha_raw = find_text(f".//{p}FechaEmision")
        if not fecha_raw:
            raise ValueError("XML sin FechaEmision")

        # Limpieza ISO
        fecha_raw = fecha_raw.replace("Z", "")
        issue_date_val = date.fromisoformat(fecha_raw.split("T")[0])

        # --------------------------------------------------------
        # EMISOR (MUY VARIABLE)
        # --------------------------------------------------------
        emisor = (
            find_text(f".//{p}Emisor/{p}Nombre")
            or find_text(f".//{p}Nombre")
            or "PROVEEDOR DESCONOCIDO"
        )

        # --------------------------------------------------------
        # MONEDA (DEFAULT CRC)
        # --------------------------------------------------------
        moneda = find_text(f".//{p}CodigoMoneda", "CRC")

        # --------------------------------------------------------
        # TOTAL
        # --------------------------------------------------------
        total_raw = find_text(f".//{p}TotalComprobante")
        if not total_raw:
            raise ValueError("XML sin TotalComprobante")

        # Normalizar número
        total_raw = total_raw.replace(",", "")
        total = float(total_raw)

        # --------------------------------------------------------
        # PLAZO CRÉDITO
        # --------------------------------------------------------
        plazo_raw = find_text(f".//{p}PlazoCredito")
        term_days = int(plazo_raw) if plazo_raw and plazo_raw.isdigit() else 30

        due_date_val = issue_date_val + timedelta(days=term_days)

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"XML inválido o no compatible: {str(e)}"
        )

    # ============================================================
    # INSERTAR EN payment_obligations
    # ============================================================
    try:
        cur.execute("""
            INSERT INTO payment_obligations (
                record_type,
                payee_type,
                payee_id,
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
                file_pdf,
                file_xml,
                is_recurring,
                amount_type,
                fixed_amount,
                due_day,
                auto_generate,
                active,
                notes,
                created_at,
                updated_at
            )
            VALUES (
                'OBLIGATION',
                'SUPPLIER',
                NULL,
                %s,
                'SUPPLIER_INVOICE',
                %s,
                NULL,
                'Costa Rica',
                NULL,
                NULL,
                %s,
                %s,
                %s,
                %s,
                %s,
                'PENDING',
                'UPLOAD',
                NULL,
                %s,
                FALSE,
                NULL,
                NULL,
                NULL,
                FALSE,
                TRUE,
                %s,
                NOW(),
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
            f"Factura electrónica cargada por XML ({clave})"
        ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"DB error creando obligación: {str(e)}"
        )

    return {
        "message": "XML cargado correctamente",
        "reference": clave,
        "supplier": emisor,
        "total": total,
        "currency": moneda,
        "issue_date": issue_date_val,
        "due_date": due_date_val
    }


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


@router.delete("/{obligation_id}")
def delete_invoice_to_pay(obligation_id: int, conn=Depends(get_db)):
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM payment_obligations WHERE id = %s",
        (obligation_id,)
    )
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Obligation not found")

    cur.execute(
        "DELETE FROM payment_obligations WHERE id = %s",
        (obligation_id,)
    )

    conn.commit()

    return {"status": "ok"}
