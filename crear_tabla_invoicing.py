import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


def crear_tabla_invoicing():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    sql = """
    CREATE TABLE IF NOT EXISTS invoicing (
        id SERIAL PRIMARY KEY,
        factura_id INTEGER,
        tipo_factura VARCHAR(20) NOT NULL,
        tipo_documento VARCHAR(20) NOT NULL,
        numero_documento VARCHAR(50) NOT NULL,
        codigo_cliente VARCHAR(50) NOT NULL,
        nombre_cliente VARCHAR(150) NOT NULL,
        fecha_emision DATE NOT NULL,
        moneda VARCHAR(10) NOT NULL,
        total NUMERIC(14,2) NOT NULL,
        estado VARCHAR(20) DEFAULT 'EMITIDA',
        pdf_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    cur.execute(sql)
    conn.commit()

    cur.close()
    conn.close()

    print("✅ Tabla 'invoicing' creada correctamente en Railway")


if __name__ == "__main__":
    crear_tabla_invoicing()
