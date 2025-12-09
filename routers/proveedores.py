# backend_api/routers/proveedores.py
from fastapi import APIRouter
import database

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])


@router.post("/add")
def add_proveedor(data: dict):
    sql = """
    INSERT INTO Proveedores (
        Codigo, Nombre, Apellidos, NombreComercial, Cedula,
        Pais, Provincia, Canton, Distrito, DireccionExacta,
        Prefijo, Telefono, Correo, TerminosPago, Banco,
        CuentaIBAN, SwiftCode, UID, DireccionBanco,
        TipoProveeduria, Comentarios
    )
    VALUES (
        %(Codigo)s, %(Nombre)s, %(Apellidos)s, %(NombreComercial)s, %(Cedula)s,
        %(Pais)s, %(Provincia)s, %(Canton)s, %(Distrito)s, %(DireccionExacta)s,
        %(Prefijo)s, %(Telefono)s, %(Correo)s, %(TerminosPago)s, %(Banco)s,
        %(CuentaIBAN)s, %(SwiftCode)s, %(UID)s, %(DireccionBanco)s,
        %(TipoProveeduria)s, %(Comentarios)s
    );
    """
    database.sql(sql, data)
    return {"status": "OK", "msg": "Proveedor registrado 💾✔"}
