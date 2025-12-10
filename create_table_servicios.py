import database

sql = """
CREATE TABLE IF NOT EXISTS servicios (
    consec SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,
    estado VARCHAR(50) NOT NULL,
    num_informe VARCHAR(50),
    buque_contenedor VARCHAR(100) NOT NULL,
    cliente VARCHAR(50) NOT NULL,
    contacto VARCHAR(100),
    detalle VARCHAR(255),
    continente VARCHAR(50) NOT NULL,
    pais VARCHAR(50) NOT NULL,
    puerto VARCHAR(50) NOT NULL,
    operacion VARCHAR(100) NOT NULL,
    surveyor VARCHAR(50) NOT NULL,
    honorarios NUMERIC(12,2),
    costo_operativo NUMERIC(12,2),
    fecha_inicio DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    fecha_fin DATE,
    hora_fin TIME,
    demoras INTEGER,
    duracion INTEGER,
    factura VARCHAR(20),
    valor_factura NUMERIC(12,2),
    fecha_factura DATE,
    terminos_pago VARCHAR(50),
    fecha_vencimiento DATE,
    dias_vencido INTEGER,
    razon_cancelacion VARCHAR(255),
    comentario_cancelacion VARCHAR(255)
);
"""

database.sql(sql)
print("Tabla 'servicios' creada correctamente en Railway.")
