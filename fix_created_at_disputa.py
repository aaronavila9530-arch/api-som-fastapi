import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def main():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        print("Conectado a la base de datos")

        sql = """
        ALTER TABLE disputa
        ALTER COLUMN created_at
        SET DEFAULT NOW();
        """

        cur.execute(sql)
        conn.commit()

        print("OK: DEFAULT now() agregado a disputa.created_at")

        cur.close()
        conn.close()

    except Exception as e:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
