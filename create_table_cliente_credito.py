import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def create_table():
    sql = """
    CREATE TABLE IF NOT EXISTS cliente_credito (
        id SERIAL PRIMARY KEY,

        codigo_cliente VARCHAR(20) NOT NULL UNIQUE,

        termino_pago VARCHAR(50) NOT NULL,
        limite_credito NUMERIC(14,2) NOT NULL DEFAULT 0,
        moneda VARCHAR(5) NOT NULL DEFAULT 'USD',

        estado_credito VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        hold_manual BOOLEAN NOT NULL DEFAULT FALSE,

        observaciones TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT fk_cliente_credito
            FOREIGN KEY (codigo_cliente)
            REFERENCES cliente(codigo)
            ON DELETE CASCADE
    );
    """

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    cur.close()
    conn.close()

    print("✔ Tabla cliente_credito creada correctamente en Railway")

if __name__ == "__main__":
    create_table()
