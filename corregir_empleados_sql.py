import psycopg2

# ====================================
# 🔌 Conexión Railway PostgreSQL
# ====================================
conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

cur = conn.cursor()

print("\n🛠️ Corrigiendo tabla EMPLEADOS...\n")

updates = [
    # ==== RENOMBRAR COLUMNAS PARA QUE COINCIDAN CON ERP ====
    ("ALTER TABLE empleados RENAME COLUMN estadocivil TO estado_civil;", "estado civil"),
    ("ALTER TABLE empleados RENAME COLUMN cuentaiban TO cuenta_iban;", "cuenta IBAN"),
    ("ALTER TABLE empleados RENAME COLUMN contactoemergencia TO contacto_emergencia;", "contacto emergencia"),
    ("ALTER TABLE empleados RENAME COLUMN telefonoemergencia TO telefono_emergencia;", "tel emergencia"),
]

for sql, desc in updates:
    try:
        cur.execute(sql)
        conn.commit()
        print(f"✔ Columna corregida: {desc}")
    except Exception as e:
        print(f"⚠ Ya estaba correcta o error en: {desc}")

# ====================================
# Confirmación final
# ====================================
print("\n🎯 Tabla EMPLEADOS alineada con tu ERP 💾🚀")

cur.close()
conn.close()
