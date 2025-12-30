import psycopg2
from psycopg2 import sql

# ============================================================
# CONFIGURACIÓN DB (Railway)
# ============================================================

DB_URL = (
    "postgresql://postgres:"
    "LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)

# ============================================================
# SQL DEFINITIONS
# ============================================================

SQL_CREATE_CLOSING_BATCHES = """
CREATE TABLE IF NOT EXISTS closing_batches (
    id SERIAL PRIMARY KEY,

    batch_code VARCHAR(50) UNIQUE NOT NULL,
    batch_type VARCHAR(30) NOT NULL,

    company_code VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL,
    period INT NOT NULL,
    ledger VARCHAR(10) NOT NULL DEFAULT '0L',

    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    source_batch_id INT NULL REFERENCES closing_batches(id),

    description TEXT,

    posted_at TIMESTAMP NULL,
    posted_by VARCHAR(100) NULL,

    reversed_at TIMESTAMP NULL,
    reversed_by VARCHAR(100) NULL,
    reverse_reason TEXT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

SQL_CREATE_CLOSING_BATCHES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_closing_batches_scope
ON closing_batches(company_code, fiscal_year, period, ledger);
"""

SQL_CREATE_CLOSING_BATCH_LINES = """
CREATE TABLE IF NOT EXISTS closing_batch_lines (
    id SERIAL PRIMARY KEY,

    batch_id INT NOT NULL REFERENCES closing_batches(id) ON DELETE CASCADE,

    account_code VARCHAR(30) NOT NULL,
    account_name VARCHAR(255) NOT NULL,

    debit NUMERIC(18,2) NOT NULL DEFAULT 0,
    credit NUMERIC(18,2) NOT NULL DEFAULT 0,
    balance NUMERIC(18,2) NOT NULL DEFAULT 0,

    currency VARCHAR(10) NOT NULL,

    source_type VARCHAR(30) NOT NULL,
    source_reference VARCHAR(100),

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

SQL_CREATE_CLOSING_BATCH_LINES_INDEX_1 = """
CREATE INDEX IF NOT EXISTS idx_closing_batch_lines_batch
ON closing_batch_lines(batch_id);
"""

SQL_CREATE_CLOSING_BATCH_LINES_INDEX_2 = """
CREATE INDEX IF NOT EXISTS idx_closing_batch_lines_account
ON closing_batch_lines(account_code);
"""

SQL_CREATE_CLOSING_STATUS = """
CREATE TABLE IF NOT EXISTS closing_status (
    id SERIAL PRIMARY KEY,

    company_code VARCHAR(10) NOT NULL,
    fiscal_year INT NOT NULL,
    period INT NOT NULL,
    ledger VARCHAR(10) NOT NULL DEFAULT '0L',

    period_closed BOOLEAN NOT NULL DEFAULT FALSE,

    gl_closed BOOLEAN NOT NULL DEFAULT FALSE,
    tb_closed BOOLEAN NOT NULL DEFAULT FALSE,
    pnl_closed BOOLEAN NOT NULL DEFAULT FALSE,
    equity_closed BOOLEAN NOT NULL DEFAULT FALSE,
    fs_closed BOOLEAN NOT NULL DEFAULT FALSE,
    fy_opened BOOLEAN NOT NULL DEFAULT FALSE,

    last_batch_id INT NULL REFERENCES closing_batches(id),

    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(company_code, fiscal_year, period, ledger)
);
"""

# ============================================================
# EXECUTION
# ============================================================

def main():
    print("🔌 Conectando a PostgreSQL...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:
        print("📦 Creando tabla closing_batches...")
        cur.execute(SQL_CREATE_CLOSING_BATCHES)
        cur.execute(SQL_CREATE_CLOSING_BATCHES_INDEX)

        print("📦 Creando tabla closing_batch_lines...")
        cur.execute(SQL_CREATE_CLOSING_BATCH_LINES)
        cur.execute(SQL_CREATE_CLOSING_BATCH_LINES_INDEX_1)
        cur.execute(SQL_CREATE_CLOSING_BATCH_LINES_INDEX_2)

        print("📦 Creando tabla closing_status...")
        cur.execute(SQL_CREATE_CLOSING_STATUS)

        conn.commit()
        print("✅ Todas las tablas de cierre contable fueron creadas correctamente.")

    except Exception as e:
        conn.rollback()
        print("❌ Error creando las tablas:", e)

    finally:
        cur.close()
        conn.close()
        print("🔒 Conexión cerrada.")


if __name__ == "__main__":
    main()
