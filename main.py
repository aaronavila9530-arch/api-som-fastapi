# ============================================================
# main.py — API backend ERP-SOM (FASTAPI)
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Conexión SQL
import database

# Routers (todos viven en la carpeta routers/)
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
from routers import invoicing


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
# INTEGRACIÓN DE ROUTERS (CRUD maestros)
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
app.include_router(invoicing.router)

# ============================================================
# EJECUCIÓN LOCAL
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
