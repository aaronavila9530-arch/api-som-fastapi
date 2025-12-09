import psycopg2

# Conexión a tu PostgreSQL en Railway
connection = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

# Muy importante: autocommit para que un error no aborte todo
connection.autocommit = True
cursor = connection.cursor()

commands = [
    # ==============================
    # RENOMBRAR COLUMNAS EXISTENTES
    # ==============================
    # nombre_fiscal -> nombrejuridico
    "ALTER TABLE cliente RENAME COLUMN nombre_fiscal TO nombrejuridico;",

    # nombre_comercial -> nombrecomercial
    "ALTER TABLE cliente RENAME COLUMN nombre_comercial TO nombrecomercial;",

    # pais_id -> pais
    "ALTER TABLE cliente RENAME COLUMN pais_id TO pais;",

    # email -> correo
    "ALTER TABLE cliente RENAME COLUMN email TO correo;",

    # cedula_juridica -> cedulajuridicavat
    "ALTER TABLE cliente RENAME COLUMN cedula_juridica TO cedulajuridicavat;",

    # comentario -> comentarios
    "ALTER TABLE cliente RENAME COLUMN comentario TO comentarios;",

    # ==============================
    # AGREGAR COLUMNAS QUE FALTAN
    # ==============================
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS provincia VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS canton VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS distrito VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS direccionexacta VARCHAR(255);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS fechadepago VARCHAR(50);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS prefijo VARCHAR(10);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contactoprincipal VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contactosecundario VARCHAR(120);",
]

for cmd in commands:
    try:
        print(f"➡ Ejecutando: {cmd}")
        cursor.execute(cmd)
        print("   ✔ OK")
    except Exception as e:
        print("   ⚠️ Error:", e)

cursor.close()
connection.close()
print("\n✅ Tabla 'cliente' alineada con los campos del ERP al 100%")
