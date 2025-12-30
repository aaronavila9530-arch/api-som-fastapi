import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


NORMALIZATION_RULES = [
    {
        "name": "Bancos",
        "target_code": "1.1.02",
        "target_name": "Bancos",
        "where": "account_name = 'Bancos' AND account_code <> '1.1.02'"
    },
    {
        "name": "Cuentas por cobrar",
        "target_code": "1101",
        "target_name": "Cuentas por cobrar",
        "where": "account_name = 'Cuentas por cobrar' AND account_code <> '1101'"
    }
]


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("\n🔍 Normalizando cuentas contables...\n")

    for rule in NORMALIZATION_RULES:
        print(f"➡ Revisando {rule['name']}...")

        cur.execute(f"""
            SELECT id, entry_id, account_code
            FROM accounting_lines
            WHERE {rule['where']}
            ORDER BY id
        """)

        rows = cur.fetchall()

        if not rows:
            print(f"   ✅ {rule['name']}: sin registros a corregir\n")
            continue

        print(f"   ⚠️ {len(rows)} registros a corregir:")

        for r in rows:
            print(
                f"      ID {r['id']} | Entry {r['entry_id']} | "
                f"{r['account_code']} → {rule['target_code']}"
            )

        cur.execute(f"""
            UPDATE accounting_lines
            SET account_code = %s,
                account_name = %s
            WHERE {rule['where']}
        """, (rule["target_code"], rule["target_name"]))

        conn.commit()
        print(f"   ✏️ {rule['name']} corregido correctamente\n")

    conn.close()
    print("✅ Normalización contable finalizada.\n")


if __name__ == "__main__":
    main()
