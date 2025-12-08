# main.py — API backend ERP-SOM (FASTAPI)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import database  # Tu conexión a Railway
from psycopg2.extensions import register_adapter, AsIs

app = FastAPI(
    title="ERP-SOM API",
    version="1.0",
    description="API para Continentes, Países y Puertos — ERP SOM"
)

# ======================================
# CORS (permite llamadas desde el ERP)
# ======================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # luego se puede restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================
# HEALTH CHECK
# ======================================
@app.get("/")
def home():
    return {"status": "API Online ✔"}


# ======================================
# ENDPOINT: Continentes
# ======================================
@app.get("/continentes")
def get_continentes():
    data = database.sql("""
        SELECT nombre
        FROM continente
        ORDER BY nombre;
    """, fetch=True)
    return [row[0] for row in data]


# ======================================
# ENDPOINT: Países por continente
# ======================================
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


# ======================================
# ENDPOINT: Puertos por país
# ======================================
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


# ======================================
# EJECUCIÓN LOCAL (no Railway)
# ======================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=True)
