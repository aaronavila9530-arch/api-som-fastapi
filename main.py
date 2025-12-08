# main.py — API backend ERP-SOM (FASTAPI)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import database  # Tu conexión a Railway

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
    data = database.sql(
        "SELECT nombre FROM continentes ORDER BY nombre;",
        fetch=True
    )
    return [row[0] for row in data]


# ======================================
# ENDPOINT: Países por continente
# ======================================
@app.get("/paises")
def get_paises(continente: str):
    data = database.sql("""
        SELECT p.nombre
        FROM paises p
        JOIN continentes c ON c.id_continente = p.continente_id
        WHERE c.nombre = %s
        ORDER BY p.nombre;
    """, (continente,), fetch=True)

    return [row[0] for row in data]


# ======================================
# ENDPOINT: Puertos por país
# ======================================
@app.get("/puertos")
def get_puertos(pais: str):
    data = database.sql("""
        SELECT p.nombre
        FROM puertos p
        JOIN paises pa ON pa.id_pais = p.pais_id
        WHERE pa.nombre = %s
        ORDER BY p.nombre;
    """, (pais,), fetch=True)

    return [row[0] for row in data]


# ======================================
# EJECUCIÓN LOCAL (no Railway)
# ======================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=True)
