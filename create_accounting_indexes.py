import psycopg2

# ============================================================
# CONFIGURACIÓN DE CONEXIÓN (Railway PostgreSQL)
# ============================================================
DATABASE_URL = (
    "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)

# ============================================================
# SQL: ÍNDICES OBLIGATORIOS
# ============================================================
SQL_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS idx_accounting_entries_period_origin
    ON accounting_entries (period, origin);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_accounting_lines_entry_id
    ON accounting_lines (entry_id);
    """
]

def main():
    conn = None
    try:
        print("🔌 Conectando a PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True

        cur = conn.cursor()

        for sql in SQL_STATEMENTS:
            print("▶ Ejecutando índice...")
            cur.execute(sql)

        cur.close()
        print("✅ Índices creados/verificados correctamente")

    except Exception as e:
        print("❌ Error creando índices:")
        print(e)

    finally:
        if conn:
            conn.close()
            print("🔒 Conexión cerrada")

if __name__ == "__main__":
    main()
