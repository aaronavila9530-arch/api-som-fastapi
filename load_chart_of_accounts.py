import pandas as pd
import psycopg2

DATABASE_URL = "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"
EXCEL_PATH = "Catalogo contable.xlsx"

def get_account_type(code: str):
    if code.startswith("1"):
        return "ASSET"
    if code.startswith("2"):
        return "LIABILITY"
    if code.startswith("3"):
        return "EQUITY"
    if code.startswith("4"):
        return "INCOME"
    if code.startswith("5"):
        return "EXPENSE"
    return "OTHER"

df = pd.read_excel(EXCEL_PATH)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

for _, row in df.iterrows():
    account_code = str(row["Numero de cuenta"]).strip()
    account_name = str(row["Detalle"]).strip()

    level = account_code.count(".") + 1
    parent = ".".join(account_code.split(".")[:-1]) if "." in account_code else None
    acc_type = get_account_type(account_code)

    cur.execute("""
        INSERT INTO accounting_ledger (
            account_code,
            account_name,
            account_level,
            account_type,
            parent_account
        )
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, (
        account_code,
        account_name,
        level,
        acc_type,
        parent
    ))

conn.commit()
cur.close()
conn.close()

print("✅ Catálogo contable Costa Rica cargado correctamente")
