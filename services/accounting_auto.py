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
