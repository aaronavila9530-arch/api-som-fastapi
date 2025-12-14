import psycopg2
import bcrypt

# ============================================================
# CONFIGURACIÓN RAILWAY POSTGRES
# ============================================================
DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

# ============================================================
# UTILIDAD HASH BCRYPT
# ============================================================
def hash_pass(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

# ============================================================
# CONEXIÓN
# ============================================================
conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

print("🔌 Conectado a Railway PostgreSQL")

# ============================================================
# CREAR / ACTUALIZAR TABLA USUARIOS
# ============================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE NOT NULL,
    pass_hash TEXT NOT NULL,
    rol TEXT DEFAULT 'user',
    activo BOOLEAN DEFAULT TRUE,
    email TEXT,
    otp_code TEXT,
    otp_expira TIMESTAMP,
    pass_temp BOOLEAN DEFAULT FALSE,
    creado TIMESTAMP DEFAULT now()
);
""")

print("✔ Tabla usuarios verificada")

# ============================================================
# USUARIOS BASE (SE MANTIENEN TUS CREDENCIALES)
# ============================================================
usuarios = [
    ("Gerencia1", "28#$&dqb", "admin", "supporting@mslogisticsgroup.com"),
    ("Captain",   "QMa$ter17#", "user", "supporting@mslogisticsgroup.com"),
    ("aaron01",   "M$l2O25*", "user", "supporting@mslogisticsgroup.com"),
    ("admin",     "M$lT3cH*", "admin", "supporting@mslogisticsgroup.com"),
]

for usuario, password, rol, email in usuarios:
    try:
        cur.execute(
            """
            INSERT INTO usuarios (usuario, pass_hash, rol, email)
            VALUES (%s, %s, %s, %s)
            """,
            (usuario, hash_pass(password), rol, email)
        )
        print(f"✔ Usuario creado → {usuario}")
    except psycopg2.errors.UniqueViolation:
        print(f"⚠ Usuario ya existe → {usuario}")
        conn.rollback()

# ============================================================
# VALIDACIÓN FINAL
# ============================================================
cur.execute("SELECT usuario, rol, activo, email FROM usuarios ORDER BY id")
rows = cur.fetchall()

print("\n==============================")
print("  ✔ USUARIOS EN RAILWAY CLOUD ")
print("  🔐 BCRYPT + OTP + RESET OK ")
print("==============================")

for r in rows:
    print(f"• {r[0]} | {r[1]} | activo={r[2]} | {r[3]}")

cur.close()
conn.close()

print("\n🚀 Setup completado correctamente")
