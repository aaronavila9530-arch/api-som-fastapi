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
    """
    Crea asientos contables para todas las collections
    que aún no tienen asiento contable.
    """

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

    collections = cur.fetchall()

    for c in collections:

        entry_date = c["fecha_emision"]
        period = entry_date.strftime("%Y-%m")
        description = f"Factura cliente {c['nombre_cliente']} – {c['numero_documento']}"

        lines = [
            {
                "account_code": "103-01",
                "account_name": "Cuentas por cobrar",
                "debit": float(c["total"]),
                "credit": 0,
                "description": "Registro CxC"
            },
            {
                "account_code": "401-01",
                "account_name": "Ingresos por servicios",
                "debit": 0,
                "credit": float(c["total"]),
                "description": "Ingreso por servicios"
            }
        ]

        create_accounting_entry(
            conn=conn,
            entry_date=entry_date,
            period=period,
            description=description,
            origin="COLLECTIONS",
            origin_id=c["id"],
            lines=lines,
            created_by="SYSTEM"
        )

