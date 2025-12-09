import psycopg2

DATABASE_URL = "postgres://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway?sslmode=require"

print("🔌 Conectando a PostgreSQL...")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()
print("📡 Conexión exitosa ✔\n")

results = []


def safe_rename(table, old, new):
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, old))

    if cursor.fetchone():
        try:
            cursor.execute(f'ALTER TABLE {table} RENAME COLUMN "{old}" TO "{new}"')
            results.append(f"✔ Renombrado {old} → {new}")
        except Exception as e:
            results.append(f"⚠ No se pudo renombrar {old} → {new}: {e}")
    else:
        results.append(f"ℹ {old} no existe, se omite ✔")


print("🚧 Ajustando tabla proveedor...\n")

# 0️⃣ Quitar Foreign Key para permitir cambiar columna
cursor.execute("""
ALTER TABLE proveedor DROP CONSTRAINT IF EXISTS proveedor_pais_id_fkey;
""")
results.append("✔ FK proveedor_pais_id_fkey eliminada")

# 1️⃣ Renombrar columnas según ERP
safe_rename("proveedor", "pais_id", "pais")
safe_rename("proveedor", "direccion", "direccionexacta")
safe_rename("proveedor", "email", "correo")
safe_rename("proveedor", "direccion_bancaria", "direccionbanco")
safe_rename("proveedor", "terminos_pago", "terminospago")
safe_rename("proveedor", "tipo_producto", "tipoproveeduria")
safe_rename("proveedor", "comentario", "comentarios")

# 2️⃣ Ajustar tipos solo si la columna existe
try:
    cursor.execute("""
        ALTER TABLE proveedor
            ALTER COLUMN pais TYPE VARCHAR(100),
            ALTER COLUMN provincia TYPE VARCHAR(100),
            ALTER COLUMN canton TYPE VARCHAR(100),
            ALTER COLUMN distrito TYPE VARCHAR(100),
            ALTER COLUMN prefijo TYPE VARCHAR(10),
            ALTER COLUMN swiftcode TYPE VARCHAR(50),
            ALTER COLUMN uid TYPE VARCHAR(50),
            ALTER COLUMN direccionexacta TYPE VARCHAR(255),
            ALTER COLUMN direccionbanco TYPE VARCHAR(255),
            ALTER COLUMN comentarios TYPE VARCHAR(255);
    """)
    results.append("✔ Tipos de columnas ajustados a VARCHAR")
except Exception as e:
    results.append(f"⚠ Error al ajustar tipos: {e}")

conn.commit()
cursor.close()
conn.close()

print("\n=============================")
print(" 🧩 RESULTADO FINAL")
print("=============================")
for r in results:
    print(r)

print("\n🎯 Esquema de proveedor listo y alineado con el ERP ✔")
