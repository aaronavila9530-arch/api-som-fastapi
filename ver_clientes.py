import psycopg2
from psycopg2.extras import RealDictCursor

# 🔹 Usa tu misma cadena de conexión exacta
DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("\n🔎 Consultando últimos registros de CLIENTE...\n")

    cur.execute("""
        SELECT
            id,
            codigo,
            nombrejuridico,
            nombrecomercial,
            pais,
            correo,
            telefono,
            comentarios,
            creado_en
        FROM cliente
        ORDER BY id DESC
        LIMIT 10;
    """)

    rows = cur.fetchall()

    if not rows:
        print("⚠️ No hay registros en la tabla `cliente`")
    else:
        for row in rows:
            print(row)

    cur.close()
    conn.close()

    print("\n✔ Finalizado\n")

except Exception as e:
    print("\n❌ Error al consultar SQL:", str(e))
