import psycopg2

# ===========================================
# 🔌 CONEXIÓN A RAILWAY (usa tus credenciales)
# ===========================================
conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

try:
    cur = conn.cursor()
    
    query = """
        SELECT column_name 
        FROM information_schema.columns
        WHERE table_name = 'empleados'
        ORDER BY ordinal_position;
    """
    cur.execute(query)
    columnas = cur.fetchall()

    print("\n📌 Columnas de la tabla EMPLEADOS:\n")
    for col in columnas:
        print("➡", col[0])

    print("\n✔ Consulta completada.")

except Exception as e:
    print("❌ Error:", e)

finally:
    cur.close()
    conn.close()
