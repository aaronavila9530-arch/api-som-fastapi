from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])

@router.post("/add")
def add_proveedor(data: dict):
    try:
        sql = """
        INSERT INTO proveedor (
            codigo, nombre, apellidos, nombrecomercial, cedula_vat,
            pais_id, provincia, canton, distrito, direccion,
            prefijo, telefono, email, terminos_pago, banco,
            cuenta_iban, swiftcode, uid, direccion_bancaria,
            tipo_producto, comentario
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
