import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def main():
    conn = None
    cur = None

    try:
        print("🔌 Conectando a PostgreSQL...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        print("🛠 Aplicando ALTER TABLE a disputa.created_at...")
        cur.execute("""
            ALTER TABLE disputa
            ALTER COLUMN created_at
            SET DEFAULT NOW();
        """)

        conn.commit()
        print("✅ ALTER TABLE ejecutado correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print("❌ Error ejecutando ALTER TABLE:")
        print(e)

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
        print("🔒 Conexión cerrada.")

if __name__ == "__main__":
    main()
