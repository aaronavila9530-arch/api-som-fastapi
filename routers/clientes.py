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
                correo,
                telefono,
                cedulajuridicavat,
                actividad_economica,
                comentarios,
                provincia,
                canton,
                distrito,
                direccionexacta,
                fecha_pago,
                prefijo,
                contacto_principal,
                contacto_secundario
            )
            VALUES (
                %(Codigo)s,
                %(NombreJuridico)s,
                %(NombreComercial)s,
                %(Pais)s,
                %(Correo)s,
                %(Telefono)s,
                %(CedulaJuridicaVAT)s,
                '' , -- aún no se usa este dato
                %(Comentarios)s,
                %(Provincia)s,
                %(Canton)s,
                %(Distrito)s,
                %(DireccionExacta)s,
                %(FechaDePago)s,
                %(Prefijo)s,
                %(ContactoPrincipal)s,
                %(ContactoSecundario)s
            )
        """, data, commit=True)

        return {"status": "OK", "msg": "Cliente registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
