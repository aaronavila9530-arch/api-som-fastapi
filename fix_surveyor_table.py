import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

ALTERS = [
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS estado_civil VARCHAR(50);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS genero VARCHAR(50);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS nacionalidad VARCHAR(100);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS prefijo VARCHAR(10);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS provincia VARCHAR(100);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS canton VARCHAR(100);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS distrito VARCHAR(100);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS jornada VARCHAR(50);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS operacion VARCHAR(120);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS honorario VARCHAR(50);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS moneda VARCHAR(10);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS enfermedades VARCHAR(255);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS contacto_emergencia VARCHAR(120);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS telefono_emergencia VARCHAR(20);',
    'ALTER TABLE surveyor ADD COLUMN IF NOT EXISTS puerto VARCHAR(120);',
    # Renombrar terminos_pago → pago
    'ALTER TABLE surveyor RENAME COLUMN IF EXISTS terminos_pago TO pago;'
]

print("\n🛠️ Corrigiendo tabla SURVEYOR en Railway...\n")

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

for sql_cmd in ALTERS:
    try:
        print(f"⇒ {sql_cmd}")
        cur.execute(sql_cmd)
        conn.commit()
        print("   ✔ OK")
    except Exception as e:
        print(f"   ⚠️ ERROR: {e}")
        conn.rollback()

cur.close()
conn.close()

print("\n🎯 Tabla SURVEYOR alineada completamente con el ERP 💾🚀")
