# database.py
import psycopg2

# =====================================================
# DATABASE URL (Railway)
# =====================================================
DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


# =====================================================
# CONEXIÓN DIRECTA (uso puntual)
# =====================================================
def connect():
    return psycopg2.connect(DATABASE_URL)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# =====================================================
# FUNCIÓN SQL GENÉRICA (legacy / utilitaria)
# =====================================================
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


# =====================================================
# ✅ FASTAPI DEPENDENCY (ESTO FALTABA)
# =====================================================
def get_db():
    """
    Dependency para FastAPI.
    Provee una conexión y la cierra automáticamente.
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()
