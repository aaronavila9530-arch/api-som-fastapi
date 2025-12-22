import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

DDL = """
CREATE TABLE IF NOT EXISTS payment_obligations (

    id SERIAL PRIMARY KEY,

    record_type VARCHAR(20) NOT NULL,
    payee_type VARCHAR(30) NOT NULL,
    payee_id INT,
    payee_name TEXT NOT NULL,

    obligation_type VARCHAR(50) NOT NULL,

    reference TEXT,
    vessel TEXT,
    country VARCHAR(50),
    operation TEXT,
    service_id INT,

    issue_date DATE,
    due_date DATE,
    last_payment_date DATE,

    currency VARCHAR(10) NOT NULL,
    total NUMERIC(14,2),
    balance NUMERIC(14,2),

    status VARCHAR(20),

    origin VARCHAR(20),
    file_pdf TEXT,
    file_xml TEXT,

    is_recurring BOOLEAN DEFAULT FALSE,
    amount_type VARCHAR(20),
    fixed_amount NUMERIC(14,2),
    due_day INT,
    auto_generate BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,

    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_payment_status
ON payment_obligations (status);

CREATE INDEX IF NOT EXISTS idx_payment_due_date
ON payment_obligations (due_date);

CREATE INDEX IF NOT EXISTS idx_payment_record_type
ON payment_obligations (record_type);

CREATE INDEX IF NOT EXISTS idx_payment_payee
ON payment_obligations (payee_type, payee_id);
"""

def main():
    conn = None
    try:
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        print("📄 Creating table payment_obligations...")
        cur.execute(DDL)

        print("⚡ Creating indexes...")
        cur.execute(INDEXES)

        conn.commit()
        print("✅ payment_obligations table created successfully.")

    except Exception as e:
        print("❌ Error:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
