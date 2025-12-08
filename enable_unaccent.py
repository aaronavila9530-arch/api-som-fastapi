from database import connect

def enable_unaccent():
    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
        conn.commit()
        print("✔ Extensión 'unaccent' habilitada correctamente.")
    except Exception as e:
        print("❌ Error habilitando unaccent:", e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    enable_unaccent()
