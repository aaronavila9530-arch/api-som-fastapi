import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

sql = """
CREATE TABLE IF NOT EXISTS accounting_ledger (
    id SERIAL PRIMARY KEY,

    account_code VARCHAR(20) NOT NULL,
    account_name TEXT NOT NULL,
    account_level INT NOT NULL,
    account_type VARCHAR(20) NOT NULL,
    parent_account VARCHAR(20),

    entry_date DATE,
    description TEXT,

    debit NUMERIC(18,2) DEFAULT 0,
    credit NUMERIC(18,2) DEFAULT 0,

    source_module VARCHAR(30),
    source_id INT,
    entry_group UUID,
    is_reversal BOOLEAN DEFAULT FALSE,
    reversed_entry_id INT,

    period VARCHAR(7),
    fiscal_year INT,

    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute(sql)
conn.commit()
cur.close()
conn.close()

print("✅ Tabla accounting_ledger creada correctamente")
