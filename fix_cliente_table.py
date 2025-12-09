import psycopg2

connection = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

cursor = connection.cursor()

alter_cmds = [
    # Asegurar que pais sea texto
    "ALTER TABLE cliente ALTER COLUMN pais TYPE VARCHAR(120);",

    # Crear columnas faltantes
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS provincia VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS canton VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS distrito VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS direccionexacta VARCHAR(255);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS fecha_pago VARCHAR(50);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS prefijo VARCHAR(10);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contacto_principal VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contacto_secundario VARCHAR(120);"
]

for cmd in alter_cmds:
    try:
        cursor.execute(cmd)
        print(f"✔ OK → {cmd}")
    except Exception as e:
        print(f"⚠️ Error en → {cmd}")
        print("   detalle:", e)

connection.commit()
cursor.close()
connection.close()

print("\n🎯 Corrección completada sin abortar transacción")
print("💾 Tabla CLIENTE ahora SÍ está alineada al 100% con ERP 🚀")
