from psycopg2.extras import RealDictCursor
from datetime import date

def create_accounting_entry(
    conn,
    entry_date,
    period,
    description,
    origin,
    origin_id,
    lines,
    created_by="SYSTEM"
):
    """
    Crea un asiento contable con validación de partida doble
    """

    total_debit = sum(l["debit"] for l in lines)
    total_credit = sum(l["credit"] for l in lines)

    if round(total_debit, 2) != round(total_credit, 2):
        raise ValueError("Partida no balanceada")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Insert entry
    cur.execute("""
        INSERT INTO accounting_entries
            (entry_date, period, description, origin, origin_id, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        entry_date,
        period,
        description,
        origin,
        origin_id,
        created_by
    ))

    entry_id = cur.fetchone()["id"]

    # 2️⃣ Insert lines
    for line in lines:
        cur.execute("""
            INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            entry_id,
            line["account_code"],
            line["account_name"],
            line["debit"],
            line["credit"],
            line.get("description")
        ))

    # 🔥🔥🔥 ESTA ES LA LÍNEA QUE FALTABA 🔥🔥🔥
    conn.commit()

    return entry_id


def sync_collections_to_accounting(conn):

    from psycopg2.extras import RealDictCursor
    from datetime import date

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # OBTENER TC DEL DÍA (OBLIGATORIO)
    # ============================================================
    today = date.today()

    cur.execute("""
        SELECT rate
        FROM exchange_rate
        WHERE rate_date = %s
        LIMIT 1
    """, (today,))

    row_tc = cur.fetchone()
    if not row_tc:
        raise Exception("Tipo de cambio del día no encontrado. No se puede contabilizar Collections.")

    tc = float(row_tc["rate"])

    # ============================================================
    # COLLECTIONS SIN ASIENTO
    # ============================================================
    cur.execute("""
        SELECT c.*
        FROM collections c
        WHERE NOT EXISTS (
            SELECT 1
            FROM accounting_entries ae
            WHERE ae.origin = 'COLLECTIONS'
              AND ae.origin_id = c.id
        )
    """)

    rows = cur.fetchall()

    for c in rows:

        numero = c["numero_documento"]

        # ------------------------------
        # MONTO ORIGINAL
        # ------------------------------
        total = float(c["total"] or 0)
        if total <= 0:
            continue

        # 🔥 APLICAR TC
        total = round(total * tc, 2)

        fecha = c["fecha_emision"] or date.today()
        period = fecha.strftime("%Y-%m")

        # ==============================
        # País desde servicios
        # ==============================
        cur.execute("""
            SELECT pais
            FROM servicios
            WHERE factura = %s
            LIMIT 1
        """, (numero,))

        srv = cur.fetchone()
        pais = (srv["pais"] if srv else "").lower()

        if pais == "costa rica":
            subtotal = round(total / 1.13, 2)
            iva = round(total - subtotal, 2)
        else:
            subtotal = total
            iva = 0

        # ==============================
        # Crear ENTRY (cabecera)
        # ==============================
        cur.execute("""
            INSERT INTO accounting_entries (
                entry_date,
                period,
                description,
                origin,
                origin_id,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s, 'SYSTEM')
            RETURNING id
        """, (
            fecha,
            period,
            f"From Collections {numero}",
            "COLLECTIONS",
            c["id"]
        ))

        entry_id = cur.fetchone()["id"]

        # ==============================
        # Líneas contables
        # ==============================
        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            entry_id, "1101", "Cuentas por cobrar",
            total, 0, f"From Collections {numero}"
        ))

        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            entry_id, "4101", "Ingresos por servicios",
            0, subtotal, f"From Collections {numero}"
        ))

        if iva > 0:
            cur.execute("""
                INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                entry_id, "2108", "IVA por pagar",
                0, iva, f"From Collections {numero}"
            ))

    conn.commit()



def sync_itp_to_accounting(conn):
    """
    Sincroniza payment_obligations → accounting

    Reglas:
    - TODOS los montos ya vienen en CRC
    - NO se convierte moneda
    - Genera asiento Gasto vs CxP (origin='ITP') siempre que no exista,
      o corrige si ya existe pero está sin detalle o con monto incorrecto.
    - Si status='PAID' y balance=0 => genera asiento CxP vs Bancos (origin='ITP_PAYMENT')
      o corrige si ya existe pero está sin detalle o con monto incorrecto.
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # 1) Traer obligaciones activas
    # ============================================================
    cur.execute("""
        SELECT
            p.id,
            p.payee_name,
            p.obligation_type,
            p.reference,
            p.issue_date,
            p.last_payment_date,
            p.currency,
            p.total,
            p.balance,
            p.status,
            p.active
        FROM payment_obligations p
        WHERE p.active = TRUE
        ORDER BY p.id ASC
    """)
    obligations = cur.fetchall()

    # ============================================================
    # 2) Procesar una por una (SIN CONVERSIÓN)
    # ============================================================
    for ob in obligations:
        obligation_id = ob["id"]
        payee_name = (ob.get("payee_name") or "").strip() or "N/A"

        total = float(ob.get("total") or 0)
        balance = float(ob.get("balance") or 0)

        status = (ob.get("status") or "").upper()
        reference = ob.get("reference")

        issue_date = ob.get("issue_date") or date.today()
        period = issue_date.strftime("%Y-%m")

        # ------------------------------------------------------------
        # Cuentas
        # ------------------------------------------------------------
        expense_account = "5101"
        expense_name = "Gastos de servicios"
        if ob.get("obligation_type") == "SURVEYOR_FEE":
            expense_account = "5102"
            expense_name = "Honorarios surveyor"

        ap_account = "2101"
        ap_name = "Cuentas por pagar"

        bank_account = "1102"
        bank_name = "Bancos"

        # ============================================================
        # A) ASIENTO GASTO vs CxP (origin = 'ITP')
        # ============================================================
        detail_text = f"From ITP {payee_name}"

        cur.execute("""
            SELECT id
            FROM accounting_entries
            WHERE origin = 'ITP'
              AND origin_id = %s
            LIMIT 1
        """, (obligation_id,))
        row_itp = cur.fetchone()
        itp_entry_id = row_itp["id"] if row_itp else None

        if not itp_entry_id:
            from services.accounting_auto import create_accounting_entry

            lines = [
                {
                    "account_code": expense_account,
                    "account_name": expense_name,
                    "debit": total,
                    "credit": 0,
                    "line_description": detail_text
                },
                {
                    "account_code": ap_account,
                    "account_name": ap_name,
                    "debit": 0,
                    "credit": total,
                    "line_description": detail_text
                }
            ]

            create_accounting_entry(
                conn=conn,
                entry_date=issue_date,
                period=period,
                description=detail_text,
                origin="ITP",
                origin_id=obligation_id,
                lines=lines
            )

        else:
            cur.execute("""
                SELECT id, account_code, debit, credit, COALESCE(line_description,'') AS line_description
                FROM accounting_lines
                WHERE entry_id = %s
                ORDER BY id
            """, (itp_entry_id,))
            existing_lines = cur.fetchall()

            current_debit = 0.0
            for l in existing_lines:
                if str(l["account_code"]) == str(expense_account):
                    current_debit = float(l["debit"] or 0)
                    break

            needs_amount_fix = abs(round(current_debit, 2) - total) > 0.01

            cur.execute("""
                UPDATE accounting_lines
                SET line_description = %s
                WHERE entry_id = %s
                  AND (line_description IS NULL OR BTRIM(line_description) = '')
            """, (detail_text, itp_entry_id))

            if needs_amount_fix:
                cur.execute("""
                    UPDATE accounting_lines
                    SET debit = %s, credit = 0
                    WHERE entry_id = %s
                      AND account_code = %s
                """, (total, itp_entry_id, expense_account))

                cur.execute("""
                    UPDATE accounting_lines
                    SET debit = 0, credit = %s
                    WHERE entry_id = %s
                      AND account_code = %s
                """, (total, itp_entry_id, ap_account))

        # ============================================================
        # B) ASIENTO DE PAGO (origin='ITP_PAYMENT')
        # ============================================================
        if status == "PAID" and balance == 0:
            payment_date = ob.get("last_payment_date") or issue_date
            payment_period = payment_date.strftime("%Y-%m")
            payment_detail = f"From ITP Payment done to {payee_name}"

            cur.execute("""
                SELECT id
                FROM accounting_entries
                WHERE origin = 'ITP_PAYMENT'
                  AND origin_id = %s
                LIMIT 1
            """, (obligation_id,))
            row_pay = cur.fetchone()
            pay_entry_id = row_pay["id"] if row_pay else None

            if not pay_entry_id:
                from services.accounting_auto import create_accounting_entry

                pay_lines = [
                    {
                        "account_code": ap_account,
                        "account_name": ap_name,
                        "debit": total,
                        "credit": 0,
                        "line_description": payment_detail
                    },
                    {
                        "account_code": bank_account,
                        "account_name": bank_name,
                        "debit": 0,
                        "credit": total,
                        "line_description": payment_detail
                    }
                ]

                create_accounting_entry(
                    conn=conn,
                    entry_date=payment_date,
                    period=payment_period,
                    description=payment_detail,
                    origin="ITP_PAYMENT",
                    origin_id=obligation_id,
                    lines=pay_lines
                )

            else:
                cur.execute("""
                    SELECT id, account_code, debit, credit, COALESCE(line_description,'') AS line_description
                    FROM accounting_lines
                    WHERE entry_id = %s
                    ORDER BY id
                """, (pay_entry_id,))
                existing_pay_lines = cur.fetchall()

                current_debit_ap = 0.0
                for l in existing_pay_lines:
                    if str(l["account_code"]) == str(ap_account):
                        current_debit_ap = float(l["debit"] or 0)
                        break

                needs_amount_fix = abs(round(current_debit_ap, 2) - total) > 0.01

                cur.execute("""
                    UPDATE accounting_lines
                    SET line_description = %s
                    WHERE entry_id = %s
                      AND (line_description IS NULL OR BTRIM(line_description) = '')
                """, (payment_detail, pay_entry_id))

                if needs_amount_fix:
                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = %s, credit = 0
                        WHERE entry_id = %s
                          AND account_code = %s
                    """, (total, pay_entry_id, ap_account))

                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = 0, credit = %s
                        WHERE entry_id = %s
                          AND account_code = %s
                    """, (total, pay_entry_id, bank_account))

    conn.commit()
