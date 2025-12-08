# create_table_surveyores.py
import database

sql_script = """
CREATE TABLE IF NOT EXISTS "surveyores" (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL,

    nombre VARCHAR(100),
    apellidos VARCHAR(100),
    estado_civil VARCHAR(50),
    genero VARCHAR(50),
    nacionalidad VARCHAR(80),

    prefijo VARCHAR(10),
    telefono VARCHAR(30),
    provincia VARCHAR(80),
    canton VARCHAR(80),
    distrito VARCHAR(80),
    direccion VARCHAR(200),

    jornada VARCHAR(50),
    operacion VARCHAR(100),
    honorario VARCHAR(50),
    pago VARCHAR(50),
    banco VARCHAR(80),
    cuenta_iban VARCHAR(50),
    moneda VARCHAR(10),
    swift VARCHAR(50),
    uid VARCHAR(60),

    enfermedades VARCHAR(300),
    contacto_emergencia VARCHAR(120),
    telefono_emergencia VARCHAR(30),

    puerto VARCHAR(100)
);
"""

try:
    database.sql(sql_script)
    print("🎯 Tabla 'surveyores' creada correctamente en Railway 🚀")
except Exception as e:
    print("❌ Error creando tabla:")
    print(e)
