import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS collections (
    id SERIAL PRIMARY KEY,
    numero_documento VARCHAR,
    codigo_cliente VARCHAR,
    nombre_cliente VARCHAR,
    tipo_factura VARCHAR,
    tipo_documento VARCHAR,
    fecha_emision DATE,
    fecha_vencimiento DATE,
    moneda VARCHAR,
    total NUMERIC(14,2),
    dias_credito INTEGER,
    aging_dias INTEGER,
    bucket_aging VARCHAR,
    num_informe VARCHAR,
    buque_contenedor VARCHAR,
    operacion VARCHAR,
    periodo_operacion VARCHAR,
    descripcion_servicio TEXT,
    estado_factura VARCHAR,
    disputada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS disputa (
    id SERIAL PRIMARY KEY,
    dispute_case VARCHAR UNIQUE,
    numero_documento VARCHAR,
    codigo_cliente VARCHAR,
    nombre_cliente VARCHAR,
    fecha_factura DATE,
    fecha_vencimiento DATE,
    monto NUMERIC(14,2),
    motivo VARCHAR,
    comentario TEXT,
    buque_contenedor VARCHAR,
    operacion VARCHAR,
    periodo_operacion VARCHAR,
    descripcion_servicio TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cash_app (
    id SERIAL PRIMARY KEY,
    numero_documento VARCHAR,
    codigo_cliente VARCHAR,
    nombre_cliente VARCHAR,
    banco VARCHAR,
    fecha_pago DATE,
    comision NUMERIC(14,2),
    referencia VARCHAR,
    monto_pagado NUMERIC(14,2),
    tipo_aplicacion VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

conn.commit()
cur.close()
conn.close()

print("✅ Tablas Collections, Disputa y Cash_App creadas")
