import psycopg2

conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

conn.autocommit = True
cursor = conn.cursor()

drop_columns = [
    "nombre",
    "pais_id",
    "email",
    "comentario",
    "cedula_juridica_vat",
    "fechadepago",
    "contactoprincipal",
    "contactosecundario"
]

for col in drop_columns:
    try:
        print(f"➡ Eliminando columna: {col}")
        cursor.execute(f"ALTER TABLE cliente DROP COLUMN IF EXISTS {col};")
        print("   ✔ OK")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")

cursor.close()
conn.close()
print("\n🎯 Tabla cliente limpia y 100% lista para ERP 🚀")
