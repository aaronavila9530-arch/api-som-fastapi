import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

SQL = """
CREATE TABLE IF NOT EXISTS accounting_journal (
    id SERIAL PRIMARY KEY,
    entry_id VARCHAR(30) NOT NULL,
    line_no INTEGER NOT NULL,

    entry_date DATE NOT NULL,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,

    account_code VARCHAR(20) NOT NULL,
    account_name TEXT NOT NULL,
    account_type VARCHAR(20) NOT NULL,

    debit NUMERIC(14,2) DEFAULT 0,
    credit NUMERIC(14,2) DEFAULT 0,

    currency VARCHAR(10) DEFAULT 'CRC',
    exchange_rate NUMERIC(10,4) DEFAULT 1,

    description TEXT,

    origin_module VARCHAR(30),
    origin_table VARCHAR(50),
    origin_id INTEGER,

    is_posted BOOLEAN DEFAULT TRUE,
    is_reversed BOOLEAN DEFAULT FALSE,
    reversed_entry_id VARCHAR(30),

    created_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_accounting_entry_id
    ON accounting_journal(entry_id);

CREATE INDEX IF NOT EXISTS idx_accounting_period
    ON accounting_journal(period_year, period_month);

CREATE INDEX IF NOT EXISTS idx_accounting_account
    ON accounting_journal(account_code);

CREATE INDEX IF NOT EXISTS idx_accounting_origin
    ON accounting_journal(origin_module, origin_id);
"""

def main():
    print("🔌 Conectando a PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("🛠️ Creando tabla accounting_journal...")
    cur.execute(SQL)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Tabla contable creada correctamente.")

if __name__ == "__main__":
    main()
