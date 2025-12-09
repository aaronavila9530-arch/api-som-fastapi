import psycopg2

conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

cur = conn.cursor()

cur.execute("""
SELECT table_schema, column_name
FROM information_schema.columns
WHERE table_name = 'cliente'
ORDER BY table_schema, column_name;
""")

rows = cur.fetchall()

print("\n🧾 Columnas encontradas en la tabla 'cliente':\n")
for schema, col in rows:
    print(f"📌 Schema: {schema:<10} → Columna: {col}")

cur.close()
conn.close()
