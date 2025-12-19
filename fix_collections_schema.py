import psycopg2
from psycopg2 import sql


DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


def main():
    conn = None
    try:
        print("🔌 Conectando a PostgreSQL...")
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()

        # ======================================================
        # 1️⃣ Crear UNIQUE constraint en numero_documento
        # ======================================================
        print("🔍 Verificando UNIQUE en collections.numero_documento...")

        cur.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'collections'
              AND constraint_type = 'UNIQUE'
              AND constraint_name = 'collections_numero_documento_uk'
        """)
        exists = cur.fetchone()

        if exists:
            print("✅ UNIQUE collections_numero_documento_uk ya existe")
        else:
            print("➕ Creando UNIQUE collections_numero_documento_uk...")
            cur.execute("""
                ALTER TABLE collections
                ADD CONSTRAINT collections_numero_documento_uk
                UNIQUE (numero_documento)
            """)
            print("✅ UNIQUE creado correctamente")

        # ======================================================
        # 2️⃣ Asegurar DEFAULT NOW() en created_at
        # ======================================================
        print("🔍 Verificando columna created_at...")

        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'collections'
              AND column_name = 'created_at'
        """)
        has_created_at = cur.fetchone()

        if not has_created_at:
            print("⚠️ La columna created_at NO existe — se omite")
        else:
            print("🔍 Verificando DEFAULT en created_at...")

            cur.execute("""
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'collections'
                  AND column_name = 'created_at'
            """)
            default = cur.fetchone()[0]

            if default and "now()" in default.lower():
                print("✅ created_at ya tiene DEFAULT now()")
            else:
                print("➕ Asignando DEFAULT now() a created_at...")
                cur.execute("""
                    ALTER TABLE collections
                    ALTER COLUMN created_at SET DEFAULT NOW()
                """)
                print("✅ DEFAULT now() aplicado a created_at")

        print("\n🎉 Esquema de collections verificado y corregido correctamente.")

    except Exception as e:
        print("❌ Error ejecutando el script:")
        print(e)

    finally:
        if conn:
            conn.close()
            print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    main()
