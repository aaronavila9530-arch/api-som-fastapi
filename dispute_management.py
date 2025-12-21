# ============================================================
# dispute_management.py
# Crear tablas de gestión de disputas - ERP-SOM
# Ejecutar desde CMD
# ============================================================

import psycopg2
from psycopg2.extras import RealDictCursor

# ============================================================
# DATABASE URL (Railway)
# ============================================================
DATABASE_URL = (
    "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)


def main():
    conn = None
    cur = None

    try:
        print("Conectando a PostgreSQL (Railway)...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ====================================================
        # TABLE: dispute_management
        # ====================================================
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dispute_management (
                id SERIAL PRIMARY KEY,
                dispute_id INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'New',
                disputed_amount NUMERIC(14,2) NOT NULL,
                dispute_closed_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_dispute
                    FOREIGN KEY (dispute_id)
                    REFERENCES disputa(id)
                    ON DELETE CASCADE
            );
        """)

        # ====================================================
        # TABLE: dispute_history (log de comentarios)
        # ====================================================
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dispute_history (
                id SERIAL PRIMARY KEY,
                dispute_management_id INTEGER NOT NULL,
                comentario TEXT NOT NULL,
                created_by VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_dispute_management
                    FOREIGN KEY (dispute_management_id)
                    REFERENCES dispute_management(id)
                    ON DELETE CASCADE
            );
        """)

        conn.commit()
        print("✔ Tablas dispute_management y dispute_history creadas correctamente.")

    except Exception as e:
        if conn:
            conn.rollback()
        print("✖ Error creando tablas:", e)

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
        print("Conexión cerrada.")


if __name__ == "__main__":
    main()
