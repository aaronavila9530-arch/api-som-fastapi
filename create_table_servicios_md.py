import database

def crear_tabla_servicios():
    sql = """
    CREATE TABLE IF NOT EXISTS ServiciosMD (
        Id SERIAL PRIMARY KEY,
        Codigo VARCHAR(20),
        CodigoProd VARCHAR(50),
        Nombre VARCHAR(100),
        Costo VARCHAR(50)
    );
    """
    database.sql(sql)
    print("🎯 Tabla 'ServiciosMD' creada correctamente 🚀")

if __name__ == "__main__":
    crear_tabla_servicios()
