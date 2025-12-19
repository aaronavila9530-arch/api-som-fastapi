import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    try:
        print("🔧 Asegurando columna saldo_pendiente...")
        cur.execute("""
            ALTER TABLE collections
            ADD COLUMN IF NOT EXISTS saldo_pendiente NUMERIC;
        """)

        print("🔄 Inicializando saldo_pendiente = total cuando está NULL o vacío...")
        cur.execute("""
            UPDATE collections
            SET saldo_pendiente = total
            WHERE saldo_pendiente IS NULL;
        """)

        conn.commit()
        print("✅ OK. saldo_pendiente inicializado.")
    except Exception as e:
        conn.rollback()
        print("❌ Error:", e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
