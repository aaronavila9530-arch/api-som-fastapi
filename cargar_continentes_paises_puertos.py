import psycopg2
import pandas as pd

# ============================================================
# CONFIGURACIÓN DE LA BD (TU URL EXACTA DE RAILWAY)
# ============================================================
DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

# ============================================================
# NOMBRE DEL EXCEL A LEER
# ============================================================
EXCEL_FILE = "continentes_paises_puertos.xlsx"

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def main():
    print("Leyendo archivo Excel...")
    try:
        df = pd.read_excel(EXCEL_FILE)
    except Exception as e:
        print("ERROR: No se pudo leer el archivo Excel:", e)
        return

    # Normalizar columnas
    df.columns = [col.strip().lower() for col in df.columns]

    required = ["continente", "pais", "puerto"]
    for col in required:
        if col not in df.columns:
            print(f"ERROR: La columna '{col}' no existe en el Excel.")
            return

    # Conexión a la BD
    print("Conectando a PostgreSQL...")
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
    except Exception as e:
        print("ERROR: No se pudo conectar a la BD:", e)
        return

    # Crear tabla
    print("Creando tabla si no existe...")
    create_table = """
    CREATE TABLE IF NOT EXISTS continentes_paises_puertos (
        id SERIAL PRIMARY KEY,
        continente VARCHAR(100) NOT NULL,
        pais VARCHAR(150) NOT NULL,
        puerto VARCHAR(200) NOT NULL
    );
    """
    cur.execute(create_table)
    conn.commit()

    # Insert SQL
    insert_sql = """
    INSERT INTO continentes_paises_puertos (continente, pais, puerto)
    VALUES (%s, %s, %s);
    """

    print("Insertando registros...")
    count = 0

    for _, row in df.iterrows():
        continente = str(row["continente"]).strip()
        pais = str(row["pais"]).strip()
        puerto = str(row["puerto"]).strip()

        if continente and pais and puerto:
            cur.execute(insert_sql, (continente, pais, puerto))
            count += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"PROCESO FINALIZADO: {count} registros insertados correctamente.")


# ============================================================
# EJECUCIÓN DESDE CMD
# ============================================================
if __name__ == "__main__":
    main()
