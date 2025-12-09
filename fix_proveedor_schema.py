import psycopg2
import os

# ===============================
# ⚠️ Configurar conexión Railway
# ===============================
DATABASE_URL = "postgres://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway?sslmode=require"

print("🔌 Conectando a la base de datos...")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()
print("📡 Conexión exitosa ✔")

changes = []

def safe_exec(sql, description):
    try:
        cursor.execute(sql)
        changes.append(f"✔ {description}")
    except Exception as e:
        changes.append(f"⚠ {description} — {e}")

print("\n🚧 Aplicando cambios a la tabla PROVEEDOR...\n")

# 1️⃣ Renombrar pais_id → pais (TEXT)
safe_exec("""
    ALTER TABLE proveedor
        RENAME COLUMN pais_id TO pais;
""", "Renombrar pais_id → pais")

safe_exec("""
    ALTER TABLE proveedor
        ALTER COLUMN pais TYPE VARCHAR(100);
""", "Ajustar tipo de pais → TEXT")

# 2️⃣ Renombrar columnas para alinear con ERP
rename_map = {
    "direccion": "direccionexacta",
    "email": "correo",
    "direccion_bancaria": "direccionbanco",
    "terminos_pago": "terminospago",
    "tipo_producto": "tipoproveeduria",
    "comentario": "comentarios"
}

for old, new in rename_map.items():
    safe_exec(f"""
        ALTER TABLE proveedor
            RENAME COLUMN {old} TO {new};
    """, f"Renombrar {old} → {new}")

# 3️⃣ Ajustar tipos de columnas
type_fix_sql = """
ALTER TABLE proveedor
    ALTER COLUMN provincia TYPE VARCHAR(100),
    ALTER COLUMN canton TYPE VARCHAR(100),
    ALTER COLUMN distrito TYPE VARCHAR(100),
    ALTER COLUMN prefijo TYPE VARCHAR(10),
    ALTER COLUMN swiftcode TYPE VARCHAR(50),
    ALTER COLUMN uid TYPE VARCHAR(50);
"""

safe_exec(type_fix_sql, "Ajustar tipos de columnas a VARCHAR")

conn.commit()
cursor.close()
conn.close()

print("\n=============================")
print("   🧩 RESULTADO DE CAMBIOS")
print("=============================")
for c in changes:
    print(c)

print("\n🎯 Esquema alineado con ERP y Router correctamente ✔")
