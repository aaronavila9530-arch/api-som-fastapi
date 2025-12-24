import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS accounting_entries (
    id SERIAL PRIMARY KEY,
    entry_date DATE NOT NULL,
    period VARCHAR(7) NOT NULL,
    description TEXT,
    origin VARCHAR(30) NOT NULL,
    origin_id INTEGER,
    reversed BOOLEAN DEFAULT FALSE,
    reversal_entry_id INTEGER,
    created_by VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS accounting_lines (
    id SERIAL PRIMARY KEY,
    entry_id INTEGER NOT NULL
        REFERENCES accounting_entries(id)
        ON DELETE CASCADE,
    account_code VARCHAR(20) NOT NULL,
    account_name TEXT NOT NULL,
    debit NUMERIC(14,2) DEFAULT 0,
    credit NUMERIC(14,2) DEFAULT 0,
    line_description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
""")

conn.commit()
cur.close()
conn.close()

print("✅ Accounting tables created successfully")
