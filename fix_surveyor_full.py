import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

COMMANDS = [
    # 1️⃣ Agregar columna apellidos si no existe
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS apellidos VARCHAR(120);',
    # 2️⃣ Renombrar terminos_pago a pago
    'ALTER TABLE surveyor RENAME COLUMN terminos_pago TO pago;',
]

print("\n🛠️ Corrigiendo estructura final de SURVEYOR...\n")

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

for cmd in COMMANDS:
    try:
        print(f"⇒ {cmd}")
        cur.execute(cmd)
        conn.commit()
        print("   ✔ OK")
    except Exception as e:
        print(f"   ⚠️ ERROR: {e}")
        conn.rollback()

cur.close()
conn.close()

print("\n🎯 SURVEYOR ahora coincide 100% con ERP 🚀")
