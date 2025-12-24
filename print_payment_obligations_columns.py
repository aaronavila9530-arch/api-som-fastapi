import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

def print_table_columns(table_name: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            ordinal_position,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))

    rows = cur.fetchall()

    print(f"\n📋 Column order for table: {table_name}\n")
    print("Pos | Column name               | Data type")
    print("-" * 60)

    for r in rows:
        print(
            f"{r['ordinal_position']:>3} | "
            f"{r['column_name']:<25} | "
            f"{r['data_type']}"
        )

    cur.close()
    conn.close()


if __name__ == "__main__":
    print_table_columns("payment_obligations")
