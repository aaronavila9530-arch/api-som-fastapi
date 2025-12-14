import psycopg2

DATABASE_URL = (
    "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@"
    "shortline.proxy.rlwy.net:50018/railway"
)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

print("🔌 Conectado a Railway PostgreSQL")

# ============================================================
# AJUSTE DE ROLES
# ============================================================
roles = {
    "Gerencia1": "admin",
    "Captain": "admin",
    "aaron01": "admin",
    "admin": "master",
}

for usuario, rol in roles.items():
    cur.execute(
        "UPDATE usuarios SET rol=%s WHERE usuario=%s",
        (rol, usuario)
    )
    print(f"✔ Rol actualizado → {usuario} = {rol}")

# ============================================================
# VERIFICACIÓN
# ============================================================
cur.execute("""
SELECT usuario, rol
FROM usuarios
ORDER BY usuario
""")

print("\n==============================")
print(" ✔ ROLES DEFINIDOS CORRECTAMENTE ")
print("==============================")

for u, r in cur.fetchall():
    print(f"• {u:10} → {r}")

cur.close()
conn.close()

print("\n🚀 Ajuste de roles completado")
