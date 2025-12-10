import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

sql = "SELECT * FROM surveyor ORDER BY id DESC LIMIT 5;"

print("🔎 Consultando últimos registros de SURVEYOR...\n")

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute(sql)
rows = cur.fetchall()

for r in rows:
    print(r)

cur.close()
conn.close()

print("\n✔ Finalizado")
