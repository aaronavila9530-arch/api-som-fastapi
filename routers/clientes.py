# backend_api/routers/clientes.py
from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/clientes", tags=["Clientes"])

@router.post("/add")
def add_cliente(data: dict):
    try:
        database.sql("""
            INSERT INTO cliente (
                codigo,
                nombrejuridico,
                nombrecomercial,
                pais,
                cedulajuridicavat,
                provincia,
                canton,
                distrito,
                direccionexacta,
                fechadepago,
                correo,
                prefijo,
                telefono,
                contactoprincipal,
                contactosecundario,
                comentarios
            )
            VALUES (
                %(Codigo)s,
                %(NombreJuridico)s,
                %(NombreComercial)s,
                %(Pais)s,
                %(CedulaJuridicaVAT)s,
                %(Provincia)s,
                %(Canton)s,
                %(Distrito)s,
                %(DireccionExacta)s,
                %(FechaDePago)s,
                %(Correo)s,
                %(Prefijo)s,
                %(Telefono)s,
                %(ContactoPrincipal)s,
                %(ContactoSecundario)s,
                %(Comentarios)s
            )
        """, data, commit=True)

        return {"status": "OK", "msg": "Cliente registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
