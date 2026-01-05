# ============================================================
# main.py — API backend ERP-SOM (FASTAPI)
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Conexión SQL
import database

# ============================================================
# Routers
# ============================================================

from routers.empleados import router as empleados_router
from routers.surveyores import router as surveyores_router
from routers.clientes import router as clientes_router
from routers.proveedores import router as proveedores_router
from routers.servicios_md import router as servicios_md_router
from routers.servicios_op import router as servicios_router
from routers.continentes_paises_puertos import router as cpp_router
from routers.version import router as version_router
from routers.cliente_credito import router as cliente_credito_router
from routers.factura import router as factura_router
from routers.invoicing import router as invoicing_router
from routers.billing import router as billing_router
from routers.collections import router as collections_router
from routers.bank_reconciliation import router as bank_reconciliation_router
from routers.incoming_payments import router as incoming_payments_router
from routers.dispute_management import router as dispute_management_router
from routers.dispute_notes import router as dispute_notes_router
from routers.disputa import router as disputa_router
from routers.invoice_to_pay import router as invoice_to_pay_router

# Accounting
from routers.accounting import router as accounting_router
from routers.accounting_adjustments import router as accounting_adjustments_router
from routers.closing import router as closing_router
from routers.closing_reports import router as closing_reports_router
from routers.closing_status import router as closing_status_router
from routers.accounting_lines import router as accounting_lines_router

from routers.exchange_rate import router as exchange_rate_router


# ============================================================
# CONFIGURACIÓN FASTAPI
# ============================================================
app = FastAPI(
    title="ERP-SOM API",
    version="1.0",
    description="API para Continentes, Países, Puertos y Empleados — ERP SOM"
    
)

# ============================================================
# CORS — Permite que el ERP Tkinter acceda sin restricciones
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # luego lo puedes restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DEBUG: IMPRIMIR RUTAS REGISTRADAS EN STARTUP (SOLO /collections)
# ============================================================
@app.on_event("startup")
def _debug_routes_collections():
    try:
        paths = []
        for r in app.router.routes:
            path = getattr(r, "path", "")
            methods = getattr(r, "methods", None)

            if isinstance(path, str) and path.startswith("/collections"):
                paths.append((path, sorted(list(methods)) if methods else []))

        print("\n=== ROUTES /collections REGISTRADAS ===")
        if not paths:
            print("NO HAY RUTAS /collections REGISTRADAS (CRÍTICO)")
        else:
            for p, m in sorted(paths):
                print(f"{p}  {m}")
        print("=== FIN ROUTES ===\n")

    except Exception as e:
        print("\n=== ERROR DEBUG ROUTES ===")
        print(str(e))
        print("=== FIN ERROR ===\n")


# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/")
def home():
    return {"status": "API Online ✔"}

# ============================================================
# ENDPOINT: Continentes
# ============================================================
@app.get("/continentes")
def get_continentes():
    data = database.sql("""
        SELECT nombre
        FROM continente
        ORDER BY nombre;
    """, fetch=True)
    return [row[0] for row in data]

# ============================================================
# ENDPOINT: Países por continente
# ============================================================
@app.get("/paises")
def get_paises(continente: str):
    data = database.sql("""
        SELECT p.nombre
        FROM pais p
        JOIN continente c ON c.id = p.continente_id
        WHERE unaccent(c.nombre) ILIKE unaccent(%s)
        ORDER BY p.nombre;
    """, (continente,), fetch=True)
    return [row[0] for row in data]

# ============================================================
# ENDPOINT: Puertos por país
# ============================================================
@app.get("/puertos")
def get_puertos(pais: str):
    data = database.sql("""
        SELECT pu.nombre
        FROM puerto pu
        JOIN pais pa ON pa.id = pu.pais_id
        WHERE unaccent(pa.nombre) ILIKE unaccent(%s)
        ORDER BY pu.nombre;
    """, (pais,), fetch=True)
    return [row[0] for row in data]

# ============================================================
# Include Routers
# ============================================================

app.include_router(empleados_router)
app.include_router(surveyores_router)
app.include_router(clientes_router)
app.include_router(proveedores_router)
app.include_router(servicios_router)
app.include_router(servicios_md_router)
app.include_router(cpp_router)
app.include_router(version_router, tags=["Version"])
app.include_router(cliente_credito_router)
app.include_router(factura_router)
app.include_router(invoicing_router)
app.include_router(billing_router)
app.include_router(collections_router)
app.include_router(bank_reconciliation_router)
app.include_router(incoming_payments_router)
app.include_router(dispute_management_router)
app.include_router(dispute_notes_router)
app.include_router(disputa_router)
app.include_router(invoice_to_pay_router)

app.include_router(accounting_router)
app.include_router(accounting_adjustments_router)
app.include_router(closing_router)
app.include_router(closing_reports_router)
app.include_router(closing_status_router)
app.include_router(accounting_lines_router)

app.include_router(exchange_rate_router)

# ============================================================
# EJECUCIÓN LOCAL
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
