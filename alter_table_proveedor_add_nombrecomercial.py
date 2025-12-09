import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

print("📡 Conectado a PostgreSQL ✔")

sql = """
ALTER TABLE proveedor
ADD COLUMN IF NOT EXISTS nombrecomercial VARCHAR(200);
"""

cursor.execute(sql)
conn.commit()

print("🏷️ Columna 'nombrecomercial' agregada correctamente ✔")

cursor.close()
conn.close()
print("🔌 Conexión cerrada ✔")
