import psycopg2

# ============================================================
# CONFIGURACIÓN DIRECTA (Railway)
# ============================================================

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

# ============================================================
# CREAR TABLA incoming_payments
# ============================================================

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS incoming_payments (
    id SERIAL PRIMARY KEY,

    origen VARCHAR(30) NOT NULL,
    codigo_cliente VARCHAR(50) NOT NULL,
    nombre_cliente VARCHAR(150) NOT NULL,

    banco VARCHAR(50) NOT NULL,
    documento VARCHAR(80),
    numero_referencia VARCHAR(80),

    fecha_pago DATE NOT NULL,
    monto NUMERIC(18,2) NOT NULL,

    razon_desaplicacion TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'UNAPPLIED',

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incoming_payments_cliente
    ON incoming_payments (codigo_cliente);

CREATE INDEX IF NOT EXISTS idx_incoming_payments_estado
    ON incoming_payments (estado);

CREATE INDEX IF NOT EXISTS idx_incoming_payments_fecha
    ON incoming_payments (fecha_pago);

CREATE INDEX IF NOT EXISTS idx_incoming_payments_banco
    ON incoming_payments (banco);
"""

def main():
    print("🔧 Conectando a PostgreSQL (Railway)...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("📦 Creando tabla incoming_payments...")
    cur.execute(SQL_CREATE_TABLE)

    conn.commit()
    cur.close()
    conn.close()

    print("✅ Tabla incoming_payments creada correctamente.")

if __name__ == "__main__":
    main()
