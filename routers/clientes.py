# backend_api/routers/clientes.py
from fastapi import APIRouter
import database

router = APIRouter(prefix="/clientes", tags=["Clientes"])

@router.post("/add")
def add_cliente(data: dict):
    sql = """
        INSERT INTO "Clientes" (
            "Codigo", "NombreJuridico", "NombreComercial", "Pais",
            "CedulaJuridicaVAT",
            "Provincia", "Canton", "Distrito", "DireccionExacta",
            "FechaDePago", "Correo",
            "Prefijo", "Telefono",
            "ContactoPrincipal", "ContactoSecundario",
            "Comentarios"
        )
        VALUES (
            %(Codigo)s, %(NombreJuridico)s, %(NombreComercial)s, %(Pais)s,
            %(CedulaJuridicaVAT)s,
            %(Provincia)s, %(Canton)s, %(Distrito)s, %(DireccionExacta)s,
            %(FechaDePago)s, %(Correo)s,
            %(Prefijo)s, %(Telefono)s,
            %(ContactoPrincipal)s, %(ContactoSecundario)s,
            %(Comentarios)s
        )
    """

    database.sql(sql, data, commit=True)
    return {"status": "OK", "msg": "Cliente registrado 💾✔"}
