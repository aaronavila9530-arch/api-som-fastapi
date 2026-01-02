import psycopg2

DATABASE_URL = (
    "postgresql://postgres:"
    "LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX"
    "@shortline.proxy.rlwy.net:50018/railway"
)

PERMISSIONS = [

    # =====================================================
    # MASTER — ACCESO TOTAL
    # =====================================================
    ("master", "finanzas", "*", True),

    # =====================================================
    # ADMIN / USER — OPERACIÓN COMPLETA (SIN CIERRES)
    # =====================================================
    ("admin", "finanzas", "view", True),
    ("admin", "finanzas", "create", True),
    ("admin", "finanzas", "edit", True),
    ("admin", "finanzas", "apply", True),
    ("admin", "finanzas", "reverse", True),
    ("admin", "finanzas", "sync", True),
    ("admin", "finanzas", "generate", True),
    ("admin", "finanzas", "reports", True),
    ("admin", "finanzas", "delete", False),
    ("admin", "finanzas", "close_period", False),
    ("admin", "finanzas", "close_financial_module", False),

    ("user", "finanzas", "view", True),
    ("user", "finanzas", "create", True),
    ("user", "finanzas", "edit", True),
    ("user", "finanzas", "apply", True),
    ("user", "finanzas", "reverse", True),
    ("user", "finanzas", "sync", True),
    ("user", "finanzas", "generate", True),
    ("user", "finanzas", "reports", True),
    ("user", "finanzas", "delete", False),
    ("user", "finanzas", "close_period", False),
    ("user", "finanzas", "close_financial_module", False),

    # =====================================================
    # CONSULTOR — LECTURA + REPORTES + ACCOUNTING
    # =====================================================
    ("consultor", "finanzas", "view", True),
    ("consultor", "finanzas", "create", True),       # accounting
    ("consultor", "finanzas", "edit", True),         # accounting
    ("consultor", "finanzas", "reverse", True),      # accounting
    ("consultor", "finanzas", "generate", True),     # informes
    ("consultor", "finanzas", "reports", True),      # reportes

    ("consultor", "finanzas", "apply", False),
    ("consultor", "finanzas", "sync", False),
    ("consultor", "finanzas", "delete", False),
    ("consultor", "finanzas", "close_period", False),
    ("consultor", "finanzas", "close_financial_module", False),
]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("🔐 Insertando permisos RBAC — FINANZAS")

    for role, module, action, allowed in PERMISSIONS:
        cur.execute("""
            INSERT INTO rbac_permissions (role_code, module, action, allowed)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (role_code, module, action)
            DO UPDATE SET allowed = EXCLUDED.allowed
        """, (role, module, action, allowed))

    conn.commit()
    cur.close()
    conn.close()

    print("✅ Permisos de Finanzas insertados correctamente.")


if __name__ == "__main__":
    main()
