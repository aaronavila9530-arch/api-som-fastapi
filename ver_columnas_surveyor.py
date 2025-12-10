import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

sql = """
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'surveyor'
ORDER BY ordinal_position;
"""

print("🧾 Columnas de la tabla SURVEYOR en Railway:\n")

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute(sql)
cols = cur.fetchall()

for c in cols:
    print("📌", c[0])

cur.close()
conn.close()

print("\n✔ Finalizado")
