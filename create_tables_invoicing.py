import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def create_tables():
    sql = """

    CREATE TABLE IF NOT EXISTS factura (
        id SERIAL PRIMARY KEY,

        tipo_factura VARCHAR(20) NOT NULL,

        codigo_cliente VARCHAR(20) NOT NULL,

        numero_factura VARCHAR(50),
        clave_electronica VARCHAR(60),

        fecha_emision DATE NOT NULL,
        termino_pago VARCHAR(50),

        moneda VARCHAR(5) NOT NULL DEFAULT 'USD',
        total NUMERIC(14,2) NOT NULL DEFAULT 0,

        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',

        pdf_path TEXT,
        xml_path TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS factura_detalle (
        id SERIAL PRIMARY KEY,

        factura_id INT NOT NULL REFERENCES factura(id) ON DELETE CASCADE,

        descripcion TEXT NOT NULL,
        cantidad NUMERIC(10,2) NOT NULL DEFAULT 1,
        precio_unitario NUMERIC(14,2) NOT NULL DEFAULT 0,
        impuesto NUMERIC(14,2) DEFAULT 0,
        total_linea NUMERIC(14,2) NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS factura_servicio (
        id SERIAL PRIMARY KEY,

        factura_id INT NOT NULL REFERENCES factura(id) ON DELETE CASCADE,
        servicio_id INT NOT NULL,
        num_informe VARCHAR(50),

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()

    print("✔ Tablas de Invoicing creadas correctamente")

if __name__ == "__main__":
    create_tables()
