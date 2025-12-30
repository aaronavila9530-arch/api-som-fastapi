import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def main():
    conn = None
    try:
        print("🔌 Conectando a la base de datos...")
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = False

        cur = conn.cursor(cursor_factory=RealDictCursor)

        print("🧹 Eliminando líneas del asiento 11...")
        cur.execute("""
            DELETE FROM accounting_lines
            WHERE entry_id = %s
        """, (11,))

        print("🗑️ Eliminando asiento 11...")
        cur.execute("""
            DELETE FROM accounting_entries
            WHERE id = %s
        """, (11,))

        print("♻️ Restaurando estado del asiento 10...")
        cur.execute("""
            UPDATE accounting_entries
            SET reversed = FALSE,
                reversal_entry_id = NULL
            WHERE id = %s
        """, (10,))

        conn.commit()
        print("✅ Corrección aplicada correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print("❌ Error ejecutando corrección:")
        print(e)

    finally:
        if conn:
            conn.close()
            print("🔒 Conexión cerrada.")

if __name__ == "__main__":
    main()
