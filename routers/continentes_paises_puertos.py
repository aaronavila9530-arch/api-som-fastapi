# ============================================================
# ROUTER: Continentes / Países / Puertos desde una sola tabla
# Tabla: continentes_paises_puertos
# ============================================================

from fastapi import APIRouter
from database import sql

router = APIRouter(prefix="/cpp", tags=["Continentes / Países / Puertos"])

# ============================================================
# GET → Lista de continentes (únicos)
# ============================================================
@router.get("/continentes")
def get_continentes_cpp():
    rows = sql("""
        SELECT DISTINCT continente
        FROM continentes_paises_puertos
        WHERE continente IS NOT NULL AND continente <> ''
        ORDER BY continente;
    """, fetch=True)

    return [row[0] for row in rows]


# ============================================================
# GET → Lista de países según continente
# ============================================================
@router.get("/paises")
def get_paises_cpp(continente: str):
    rows = sql("""
        SELECT DISTINCT pais
        FROM continentes_paises_puertos
        WHERE continente = %s
          AND pais IS NOT NULL AND pais <> ''
        ORDER BY pais;
    """, (continente,), fetch=True)

    return [row[0] for row in rows]
