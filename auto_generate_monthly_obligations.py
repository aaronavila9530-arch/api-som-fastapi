import psycopg2
from datetime import date
from calendar import monthrange

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


def get_first_and_last_day(year, month):
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def main():
    today = date.today()
    year = today.year
    month = today.month

    conn = None

    try:
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # ======================================================
        # 1️⃣ Obtener templates recurrentes activos
        # ======================================================
        cur.execute("""
            SELECT *
            FROM payment_obligations
            WHERE record_type = 'TEMPLATE'
              AND is_recurring = TRUE
              AND auto_generate = TRUE
              AND active = TRUE
        """)

        templates = cur.fetchall()
        print(f"📄 Templates found: {len(templates)}")

        for tpl in templates:

            (
                tpl_id,
                record_type,
                payee_type,
                payee_id,
                payee_name,
                obligation_type,
                reference,
                vessel,
                country,
                operation,
                service_id,
                issue_date,
                due_date,
                last_payment_date,
                currency,
                total,
                balance,
                status,
                origin,
                file_pdf,
                file_xml,
                is_recurring,
                amount_type,
                fixed_amount,
                due_day,
                auto_generate,
                active,
                notes,
                created_at,
                updated_at
            ) = tpl

            # ==================================================
            # 2️⃣ Verificar si ya existe obligación del mes
            # ==================================================
            cur.execute("""
                SELECT 1
                FROM payment_obligations
                WHERE record_type = 'OBLIGATION'
                  AND is_recurring = FALSE
                  AND reference = %s
                  AND DATE_TRUNC('month', due_date) = DATE_TRUNC('month', %s::date)
            """, (
                f"{tpl_id}-{year}-{month:02d}",
                today
            ))

            if cur.fetchone():
                print(f"⏭ Skipped (already exists): {payee_name} [{obligation_type}]")
                continue

            # ==================================================
            # 3️⃣ Calcular fechas
            # ==================================================
            due_day_safe = due_day if due_day and due_day <= 28 else 28
            due_date_new = date(year, month, due_day_safe)

            # ==================================================
            # 4️⃣ Montos y estado
            # ==================================================
            if amount_type == "FIXED":
                total_amount = fixed_amount
                balance_amount = fixed_amount
                status_new = "PENDING"
            else:
                total_amount = None
                balance_amount = None
                status_new = "DRAFT"

            # ==================================================
            # 5️⃣ Insertar obligación
            # ==================================================
            cur.execute("""
                INSERT INTO payment_obligations (
                    record_type,
                    payee_type,
                    payee_id,
                    payee_name,
                    obligation_type,
                    reference,
                    vessel,
                    country,
                    operation,
                    service_id,
                    issue_date,
                    due_date,
                    currency,
                    total,
                    balance,
                    status,
                    origin,
                    is_recurring,
                    notes
                )
                VALUES (
                    'OBLIGATION',
                    %s, %s, %s,
                    %s,
                    %s,
                    %s, %s, %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'RECURRING',
                    FALSE,
                    %s
                )
            """, (
                payee_type,
                payee_id,
                payee_name,
                obligation_type,
                f"{tpl_id}-{year}-{month:02d}",
                vessel,
                country,
                operation,
                service_id,
                today,
                due_date_new,
                currency,
                total_amount,
                balance_amount,
                status_new,
                f"Auto-generated from template ID {tpl_id}"
            ))

            print(f"✅ Created obligation: {payee_name} [{obligation_type}]")

        conn.commit()
        print("🎉 Monthly auto-generation completed successfully.")

    except Exception as e:
        print("❌ Error:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
