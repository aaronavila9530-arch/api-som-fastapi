import psycopg2

DATABASE_URL = (
    "postgresql://postgres:"
    "LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)

def run_migration():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print("🔌 Conectado a PostgreSQL")

    # -------------------------------------------------
    # 1️⃣ Agregar created_at si no existe
    # -------------------------------------------------
    cur.execute("""
        ALTER TABLE closing_status
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
    """)
    print("✅ Columna created_at verificada")

    # -------------------------------------------------
    # 2️⃣ Agregar closed_by si no existe
    # -------------------------------------------------
    cur.execute("""
        ALTER TABLE closing_status
        ADD COLUMN IF NOT EXISTS closed_by TEXT;
    """)
    print("✅ Columna closed_by verificada")

    # -------------------------------------------------
    # 3️⃣ Backfill created_at donde esté NULL
    # -------------------------------------------------
    cur.execute("""
        UPDATE closing_status
        SET created_at = updated_at
        WHERE created_at IS NULL;
    """)
    print("✅ created_at inicializado")

    # -------------------------------------------------
    # 4️⃣ Backfill closed_by donde esté NULL
    # -------------------------------------------------
    cur.execute("""
        UPDATE closing_status
        SET closed_by = 'system'
        WHERE closed_by IS NULL;
    """)
    print("✅ closed_by inicializado")

    cur.close()
    conn.close()

    print("🚀 Migración closing_status completada correctamente")

if __name__ == "__main__":
    run_migration()
