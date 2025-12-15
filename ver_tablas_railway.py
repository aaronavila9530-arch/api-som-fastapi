import psycopg2

# ============================================================
# CONEXIÓN A POSTGRESQL (Railway)
# ============================================================
DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def listar_tablas():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        sql = """
        SELECT
            schemaname,
            tablename
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename;
        """

        cur.execute(sql)
        tablas = cur.fetchall()

        print("\n📦 TABLAS EXISTENTES EN RAILWAY:\n")

        if not tablas:
            print("⚠️ No se encontraron tablas.")
        else:
            esquema_actual = None
            for esquema, tabla in tablas:
                if esquema != esquema_actual:
                    print(f"\n📁 Esquema: {esquema}")
                    esquema_actual = esquema
                print(f"   └── {tabla}")

        cur.close()
        conn.close()

    except Exception as e:
        print("❌ Error al conectar o consultar la base de datos:")
        print(e)


if __name__ == "__main__":
    listar_tablas()
