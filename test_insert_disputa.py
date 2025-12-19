import psycopg2

DB_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

try:
    cur.execute("""
        INSERT INTO disputa (
            dispute_case,
            numero_documento,
            codigo_cliente,
            nombre_cliente,
            fecha_factura,
            fecha_vencimiento,
            monto,
            motivo,
            comentario,
            buque_contenedor,
            operacion,
            periodo_operacion,
            descripcion_servicio
        ) VALUES (
            'DISP-TEST',
            'TEST-001',
            'CLI-TEST',
            'CLIENTE TEST',
            CURRENT_DATE,
            CURRENT_DATE,
            1000,
            'PRECIO',
            'TEST MANUAL',
            'BUQUE TEST',
            'OP TEST',
            '2025-01',
            'DESC TEST'
        )
    """)
    conn.commit()
    print("✅ INSERT directo OK")

except Exception as e:
    conn.rollback()
    print("❌ ERROR SQL REAL:")
    print(e)

finally:
    cur.close()
    conn.close()
