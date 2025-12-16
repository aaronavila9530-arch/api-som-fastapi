import psycopg2


DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


def main():
    conn = None
    cur = None

    try:
        print("🔌 Conectando a PostgreSQL...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        print("🛠️ Alterando tabla invoicing...")

        cur.execute("""
            ALTER TABLE invoicing
                ADD COLUMN IF NOT EXISTS num_informe           VARCHAR(50),
                ADD COLUMN IF NOT EXISTS termino_pago          INTEGER,
                ADD COLUMN IF NOT EXISTS buque_contenedor      VARCHAR(255),
                ADD COLUMN IF NOT EXISTS operacion             VARCHAR(255),
                ADD COLUMN IF NOT EXISTS periodo_operacion     VARCHAR(255),
                ADD COLUMN IF NOT EXISTS descripcion_servicio  TEXT;
        """)

        conn.commit()
        print("✅ Columnas agregadas correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print("❌ Error alterando la tabla invoicing:")
        print(e)

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
        print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    main()
