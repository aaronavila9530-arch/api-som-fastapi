import psycopg2

# ============================================================
# CONEXIÓN A POSTGRESQL (Railway)
# ============================================================
DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def ver_columnas_cliente_credito():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        sql = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'cliente_credito'
        ORDER BY ordinal_position;
        """

        cur.execute(sql)
        columnas = cur.fetchall()

        print("\n📄 COLUMNAS DE LA TABLA: cliente_credito\n")

        if not columnas:
            print("⚠️ La tabla no existe o no tiene columnas.")
        else:
            for col, tipo, nullable, default in columnas:
                print(f"• {col}")
                print(f"   ├─ Tipo       : {tipo}")
                print(f"   ├─ Nullable   : {nullable}")
                print(f"   └─ Default    : {default}")
                print()

        cur.close()
        conn.close()

    except Exception as e:
        print("❌ Error al consultar columnas:")
        print(e)


if __name__ == "__main__":
    ver_columnas_cliente_credito()
