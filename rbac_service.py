import psycopg2

DATABASE_URL = (
    "postgresql://postgres:"
    "LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)


def has_permission(role_code: str, module: str, action: str) -> bool:
    """
    Devuelve True si el rol tiene permiso para module/action.
    Soporta wildcards (*).
    """

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Orden de prioridad:
    # 1) módulo + acción exactos
    # 2) módulo + *
    # 3) * + *
    cur.execute("""
        SELECT allowed
        FROM rbac_permissions
        WHERE role_code = %s
          AND (
                (module = %s AND action = %s) OR
                (module = %s AND action = '*') OR
                (module = '*' AND action = '*')
          )
        ORDER BY
            CASE
                WHEN module = %s AND action = %s THEN 1
                WHEN module = %s AND action = '*' THEN 2
                WHEN module = '*' AND action = '*' THEN 3
            END
        LIMIT 1
    """, (
        role_code,
        module, action,
        module,
        module, action,
        module
    ))

    row = cur.fetchone()

    cur.close()
    conn.close()

    # Si no existe permiso explícito → DENEGAR
    return bool(row[0]) if row else False
