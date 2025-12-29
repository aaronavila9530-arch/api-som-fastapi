import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


def create_exchange_rate_table():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rate (
            id SERIAL PRIMARY KEY,
            rate NUMERIC(12,6) NOT NULL,
            rate_date DATE NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'BCCR',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (rate_date)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("✅ Tabla exchange_rate creada correctamente.")


if __name__ == "__main__":
    create_exchange_rate_table()
