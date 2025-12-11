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
@router.get("/ultimo")
def get_ultimo_proveedor():
    sql_query = """
        SELECT MAX(CAST(SUBSTRING(codigo FROM 5 FOR 4) AS INTEGER))
        FROM proveedor;
    """
    result = database.sql(sql_query, fetch=True)

    ultimo = result[0][0] if result and result[0][0] is not None else 0
    return {"ultimo": ultimo}

# ============================================================
# LISTAR PROVEEDORES — PAGINADO
# ============================================================
@router.get("/")
def get_proveedores(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT codigo, nombre, apellidos, nombrecomercial,
               cedula_vat, pais, provincia, canton, distrito,
               direccionexacta, prefijo, telefono, correo,
               terminospago, banco, cuenta_iban, swiftcode,
               uid, direccionbanco, tipoproveeduria, comentarios
        FROM proveedor
        ORDER BY codigo ASC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM proveedor", fetch=True)[0][0]

    data = [
        {
            "Codigo": r[0],
            "Nombre": r[1],
            "Apellidos": r[2],
            "NombreComercial": r[3],
            "Cedula": r[4],
            "Pais": r[5],
            "Provincia": r[6],
            "Canton": r[7],
            "Distrito": r[8],
            "DireccionExacta": r[9],
            "Prefijo": r[10],
            "Telefono": r[11],
            "Correo": r[12],
            "TerminosPago": r[13],
            "Banco": r[14],
            "CuentaIBAN": r[15],
            "SwiftCode": r[16],
            "UID": r[17],
            "DireccionBanco": r[18],
            "TipoProveeduria": r[19],
            "Comentarios": r[20]
        }
        for r in rows
    ]

    return {"data": data, "total": total}

# ============================================================
# OBTENER UN PROVEEDOR POR CÓDIGO
# ============================================================
@router.get("/{codigo}")
def get_proveedor(codigo: str):
    row = database.sql("""
        SELECT codigo, nombre, apellidos, nombrecomercial,
               cedula_vat, pais, provincia, canton, distrito,
               direccionexacta, prefijo, telefono, correo,
               terminospago, banco, cuenta_iban, swiftcode,
               uid, direccionbanco, tipoproveeduria, comentarios
        FROM proveedor
        WHERE codigo = %s
    """, (codigo,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    r = row[0]
    return {
        "Codigo": r[0],
        "Nombre": r[1],
        "Apellidos": r[2],
        "NombreComercial": r[3],
        "Cedula": r[4],
        "Pais": r[5],
        "Provincia": r[6],
        "Canton": r[7],
        "Distrito": r[8],
        "DireccionExacta": r[9],
        "Prefijo": r[10],
        "Telefono": r[11],
        "Correo": r[12],
        "TerminosPago": r[13],
        "Banco": r[14],
        "CuentaIBAN": r[15],
        "SwiftCode": r[16],
        "UID": r[17],
        "DireccionBanco": r[18],
        "TipoProveeduria": r[19],
        "Comentarios": r[20]
    }


# ============================================================
# ACTUALIZAR PROVEEDOR
# ============================================================
@router.put("/update")
def update_proveedor(data: dict):
    sql = """
        UPDATE proveedor SET
            nombre = %(Nombre)s,
            apellidos = %(Apellidos)s,
            nombrecomercial = %(NombreComercial)s,
            cedula_vat = %(Cedula)s,
            pais = %(Pais)s,
            provincia = %(Provincia)s,
            canton = %(Canton)s,
            distrito = %(Distrito)s,
            direccionexacta = %(DireccionExacta)s,
            prefijo = %(Prefijo)s,
            telefono = %(Telefono)s,
            correo = %(Correo)s,
            terminospago = %(TerminosPago)s,
            banco = %(Banco)s,
            cuenta_iban = %(CuentaIBAN)s,
            swiftcode = %(SwiftCode)s,
            uid = %(UID)s,
            direccionbanco = %(DireccionBanco)s,
            tipoproveeduria = %(TipoProveeduria)s,
            comentarios = %(Comentarios)s
        WHERE codigo = %(Codigo)s
    """
    database.sql(sql, data)
    return {"status": "OK", "msg": "Proveedor actualizado ✔"}


# ============================================================
# ELIMINAR PROVEEDOR
# ============================================================
@router.delete("/{codigo}")
def delete_proveedor(codigo: str):
    database.sql("DELETE FROM proveedor WHERE codigo = %s", (codigo,))
    return {"status": "OK", "msg": "Proveedor eliminado 🗑️"}

