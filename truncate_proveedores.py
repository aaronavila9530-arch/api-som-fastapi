import psycopg2

# Conexión a Railway
conn = psycopg2.connect(
    host="shortline.proxy.rlwy.net",
    port="50018",
    database="railway",
    user="postgres",
    password="LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
)

try:
    cur = conn.cursor()
    cur.execute("DELETE FROM proveedor;")  # elimina todos los registros
    conn.commit()
    print("✔ Tabla proveedor limpiada correctamente")

except Exception as e:
    print("❌ Error:", e)

finally:
    cur.close()
    conn.close()
