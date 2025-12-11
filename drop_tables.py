import psycopg2

# ==============================================
# CADENA DE CONEXIÓN A RAILWAY (TAL COMO LA ENVIASTE)
# ==============================================
CONN_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

# ==============================================
# LISTA DE TABLAS A ELIMINAR
# ==============================================
tables = [
    "disputes",
    "empleado",
    "proveedores",
    "servicio",
    "surveyor_puerto",
    "surveyor_servicio",
    "surveyores"
]

# ==============================================
# EJECUTAR DROP TABLE
# ==============================================
def drop_tables():
    try:
        conn = psycopg2.connect(CONN_URL)
        cur = conn.cursor()

        print("\n===== INICIANDO ELIMINACIÓN DE TABLAS =====\n")

        for table in tables:
            try:
                print(f"Eliminando tabla: {table} ...")
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                conn.commit()
                print(f"✔ Tabla '{table}' eliminada correctamente.\n")
            except Exception as e:
                print(f"❌ Error eliminando '{table}': {e}\n")

        cur.close()
        conn.close()

        print("===== PROCESO FINALIZADO CORRECTAMENTE =====")

    except Exception as e:
        print("❌ Error conectando a PostgreSQL:", e)


if __name__ == "__main__":
    drop_tables()
