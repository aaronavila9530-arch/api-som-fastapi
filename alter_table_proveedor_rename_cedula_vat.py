import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

print("📡 Conectado a PostgreSQL ✔")

sql = """
ALTER TABLE proveedor
RENAME COLUMN cedula_juridica TO cedula_vat;
"""

cursor.execute(sql)
conn.commit()

print("🔄 Columna renombrada correctamente:")
print("➡ cedula_juridica  👉  cedula_vat ✔")

cursor.close()
conn.close()
print("🔌 Conexión cerrada ✔")
