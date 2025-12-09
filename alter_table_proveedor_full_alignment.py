import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

print("📡 Conectado a PostgreSQL ✔")

# ===============================================================
# 1️⃣ Intentar renombrar columna si existe
# ===============================================================
try:
    cursor.execute(
        "ALTER TABLE proveedor RENAME COLUMN cedula_juridica TO cedula_vat;"
    )
    conn.commit()
    print("🔁 cedula_juridica → cedula_vat ✔")
except Exception:
    conn.rollback()
    print("ℹ cedula_juridica no existe, se continúa ✔")

# ===============================================================
# 2️⃣ Agregar TODAS las columnas que faltan
# ===============================================================
sql_add = """
ALTER TABLE proveedor
    ADD COLUMN IF NOT EXISTS nombre VARCHAR(100),
    ADD COLUMN IF NOT EXISTS apellidos VARCHAR(100),
    ADD COLUMN IF NOT EXISTS nombrecomercial VARCHAR(200),
    ADD COLUMN IF NOT EXISTS provincia VARCHAR(100),
    ADD COLUMN IF NOT EXISTS canton VARCHAR(100),
    ADD COLUMN IF NOT EXISTS distrito VARCHAR(100),
    ADD COLUMN IF NOT EXISTS prefijo VARCHAR(10),
    ADD COLUMN IF NOT EXISTS email VARCHAR(200),
    ADD COLUMN IF NOT EXISTS swiftcode VARCHAR(50),
    ADD COLUMN IF NOT EXISTS uid VARCHAR(100),
    ADD COLUMN IF NOT EXISTS terminos_pago VARCHAR(100),
    ADD COLUMN IF NOT EXISTS tipo_producto VARCHAR(100),
    ADD COLUMN IF NOT EXISTS direccion_bancaria VARCHAR(200),
    ADD COLUMN IF NOT EXISTS comentario TEXT,
    ADD COLUMN IF NOT EXISTS creado_en TIMESTAMP DEFAULT NOW();
"""

try:
    cursor.execute(sql_add)
    conn.commit()
    print("🧱 Nuevas columnas agregadas ✔")
except Exception as e:
    conn.rollback()
    print("❌ Error agregando columnas:", e)
    raise

# ===============================================================
# 3️⃣ Ajustar tipos de columnas
# ===============================================================
sql_alter = """
ALTER TABLE proveedor
    ALTER COLUMN codigo TYPE VARCHAR(20),
    ALTER COLUMN direccion TYPE VARCHAR(300),
    ALTER COLUMN cuenta_iban TYPE VARCHAR(100);
"""

try:
    cursor.execute(sql_alter)
    conn.commit()
    print("🧬 Tipos de columnas ajustados ✔")
except Exception as e:
    conn.rollback()
    print("❌ Error ajustando tipos:", e)
    raise

cursor.close()
conn.close()
print("🚀 Tabla proveedor totalmente alineada con UI + API ✔")
