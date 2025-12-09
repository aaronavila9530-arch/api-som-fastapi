import psycopg2

conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

ALTERS = [
    # Asegurar código único y texto
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS codigo VARCHAR(25) UNIQUE;",
    
    # Nombres popup
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS nombre VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS nombre_comercial VARCHAR(200);",
    
    # Dirección completa
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS pais VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS provincia VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS canton VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS distrito VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS direccionexacta VARCHAR(300);",
    
    # Contactos
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS prefijo VARCHAR(10);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS telefono VARCHAR(50);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS correo VARCHAR(200);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contacto_principal VARCHAR(120);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS contacto_secundario VARCHAR(120);",
    
    # Identificación / negocio
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS cedula_juridica_vat VARCHAR(100);",
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS fecha_pago VARCHAR(50);",
    
    # Extra
    "ALTER TABLE cliente ADD COLUMN IF NOT EXISTS comentarios TEXT;"
]

try:
    cur = conn.cursor()
    for sql in ALTERS:
        print("➡", sql)
        cur.execute(sql)
    conn.commit()
    print("\n✔ TABLA CLIENTE ACTUALIZADA CORRECTAMENTE")
except Exception as e:
    print("❌ ERROR:", e)
finally:
    cur.close()
    conn.close()
