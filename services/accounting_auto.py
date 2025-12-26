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
        total = float(c["total"] or 0)
        if total <= 0:
            continue

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
    Maneja:
    - Facturas por pagar (Gasto vs CxP)
    - Facturas pagadas (CxP vs Bancos)
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # 1️⃣ Traer obligaciones SIN asiento contable
    # ============================================================
    cur.execute("""
        SELECT p.*
        FROM payment_obligations p
        LEFT JOIN accounting_entries a
          ON a.origin = 'ITP'
         AND a.origin_id = p.id
        WHERE a.id IS NULL
          AND p.active = TRUE
    """)

    obligations = cur.fetchall()

    for ob in obligations:

        obligation_id = ob["id"]
        payee_name = ob["payee_name"]                # ✅ USAR ESTO
        total = float(ob["total"] or 0)
        balance = float(ob["balance"] or 0)
        status = ob["status"]

        issue_date = ob["issue_date"] or date.today()
        period = issue_date.strftime("%Y-%m")

        # ============================================================
        # CUENTAS CONTABLES (CATÁLOGO)
        # ============================================================
        expense_account = "5101"
        expense_name = "Gastos de servicios"

        if ob["obligation_type"] == "SURVEYOR_FEE":
            expense_account = "5102"
            expense_name = "Honorarios surveyor"

        # ============================================================
        # 2️⃣ ASIENTO DE GASTO / CUENTAS POR PAGAR
        # ============================================================
        detail_text = f"From ITP {payee_name}"

        lines = [
            {
                "account_code": expense_account,
                "account_name": expense_name,
                "debit": total,
                "credit": 0,
                "line_description": detail_text
            },
            {
                "account_code": "2101",
                "account_name": "Cuentas por pagar",
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

        # ============================================================
        # 3️⃣ SI YA ESTÁ PAGADA → ASIENTO DE PAGO
        # ============================================================
        if status == "PAID" and balance == 0:

            payment_date = ob["last_payment_date"] or issue_date
            payment_detail = f"From ITP Payment done to {payee_name}"

            pay_lines = [
                {
                    "account_code": "2101",
                    "account_name": "Cuentas por pagar",
                    "debit": total,
                    "credit": 0,
                    "line_description": payment_detail
                },
                {
                    "account_code": "1102",
                    "account_name": "Bancos",
                    "debit": 0,
                    "credit": total,
                    "line_description": payment_detail
                }
            ]

            create_accounting_entry(
                conn=conn,
                entry_date=payment_date,
                period=period,
                description=payment_detail,
                origin="ITP_PAYMENT",
                origin_id=obligation_id,
                lines=pay_lines
            )

    conn.commit()