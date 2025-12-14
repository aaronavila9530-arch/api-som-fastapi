# database.py
import psycopg2


# =====================================================
# ⚠️ PEGA AQUÍ TU URL DE RAILWAY
# Ejemplo de formato:
# postgresql://usuario:clave@host:puerto/railway
# =====================================================
DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"  # 👈 REEMPLAZA ESTO


def connect():
    return psycopg2.connect(DATABASE_URL)


def sql(query, params=None, fetch=False):
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute(query, params)

        if fetch:
            data = cur.fetchall()
            conn.commit()
            return data

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("❌ Error SQL:", e)
        raise

    finally:
        cur.close()
        conn.close()


def get_conn():
    return psycopg2.connect(DATABASE_URL)
