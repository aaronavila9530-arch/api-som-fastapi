import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("🔍 Verificando valores no numéricos en period...")

    cur.execute("""
        SELECT DISTINCT period
        FROM accounting_ledger
        WHERE period !~ '^[0-9]+$'
    """)
    bad_rows = cur.fetchall()

    if bad_rows:
        print("❌ Existen valores NO numéricos en period:")
        for r in bad_rows:
            print("   →", r[0])
        print("\n⛔ Corrige estos valores antes de cambiar el tipo.")
        return

    print("✅ Todos los valores son numéricos. Procediendo con ALTER TABLE...")

    cur.execute("""
        ALTER TABLE accounting_ledger
        ALTER COLUMN period
        TYPE INTEGER
        USING period::integer;
    """)

    print("🎉 Columna period convertida exitosamente a INTEGER.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
