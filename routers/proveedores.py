from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])


# ============================================================
# INSERTAR NUEVO PROVEEDOR EN BD
# ============================================================
@router.post("/add")
def add_proveedor(data: dict):
    try:
        sql = """
        INSERT INTO proveedor (
            codigo,
            nombre,
            apellidos,
            nombrecomercial,
            cedula_vat,
            pais,
            provincia,
            canton,
            distrito,
            direccionexacta,
            prefijo,
            telefono,
            correo,
            terminospago,
            banco,
            cuenta_iban,
            swiftcode,
            uid,
            direccionbanco,
            tipoproveeduria,
            comentarios
        )
        VALUES (
            %(Codigo)s,
            %(Nombre)s,
            %(Apellidos)s,
            %(NombreComercial)s,
            %(Cedula)s,
            %(Pais)s,
            %(Provincia)s,
            %(Canton)s,
            %(Distrito)s,
            %(DireccionExacta)s,
            %(Prefijo)s,
            %(Telefono)s,
            %(Correo)s,
            %(TerminosPago)s,
            %(Banco)s,
            %(CuentaIBAN)s,
            %(SwiftCode)s,
            %(UID)s,
            %(DireccionBanco)s,
            %(TipoProveeduria)s,
            %(Comentarios)s
        )
        """
        database.sql(sql, data)
        return {"status": "OK", "msg": "Proveedor registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# OBTENER ÚLTIMO CÓDIGO CORRELATIVO
# ============================================================
@router.get("/ultimo_codigo")
def ultimo_codigo():
    try:
        res = database.sql(
            """
            SELECT codigo
            FROM proveedor
            ORDER BY CAST(split_part(codigo, '-', 2) AS INTEGER) DESC
            LIMIT 1;
            """,
            fetch=True
        )
        if res:
            return {"codigo": res[0]["codigo"]}
        return {"codigo": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
