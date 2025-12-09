# ============================================================
# main.py — API backend ERP-SOM (FASTAPI)
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Conexión SQL
import database

# Router de empleados (separado y limpio)
app.include_router(empleados_router, prefix="/empleados", tags=["Empleados"])
app.include_router(surveyores_router, prefix="/surveyores", tags=["Surveyores"])
app.include_router(clientes_router, prefix="/clientes", tags=["Clientes"])
app.include_router(proveedores_router, prefix="/proveedores", tags=["Proveedores"])
app.include_router(servicios_router, prefix="/servicios", tags=["Servicios"])


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
    allow_origins=["*"],  # luego se restringe a tu dominio
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
# INTEGRACIÓN DE ROUTERS
# ============================================================
app.include_router(empleados_router)   # 👈 Aquí se monta el CRUD de empleados
app.include_router(surveyores_router)
app.include_router(clientes_router)
app.include_router(proveedores.router)
app.include_router(servicios_md.router)



# ============================================================
# EJECUCIÓN LOCAL
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=True)
