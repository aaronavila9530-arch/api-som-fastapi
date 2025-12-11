# backend_api/routers/clientes.py
from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/clientes", tags=["Clientes"])

@router.post("/add")
def add_cliente(data: dict):
    sql = """
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
            '' , -- valor temporal
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
    """
    try:
        database.sql(sql, data)
        return {"status": "OK", "msg": "Cliente registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# LISTAR CLIENTES — PAGINADO
# ============================================================
@router.get("")
def get_clientes(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql("""
        SELECT
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
        FROM cliente
        ORDER BY codigo ASC
        LIMIT %s OFFSET %s
    """, (page_size, offset), fetch=True)

    total = database.sql("SELECT COUNT(*) FROM cliente", fetch=True)[0][0]

    data = [
        {
            "codigo": r[0],
            "nombrejuridico": r[1],
            "nombrecomercial": r[2],
            "pais": r[3],
            "correo": r[4],
            "telefono": r[5],
            "cedulajuridicavat": r[6],
            "actividad_economica": r[7],
            "comentarios": r[8],
            "provincia": r[9],
            "canton": r[10],
            "distrito": r[11],
            "direccionexacta": r[12],
            "fecha_pago": r[13],
            "prefijo": r[14],
            "contacto_principal": r[15],
            "contacto_secundario": r[16],
        }
        for r in rows
    ]

    return {"total": total, "data": data}


# ============================================================
# OBTENER UN CLIENTE POR CÓDIGO
# ============================================================
@router.get("/{codigo}")
def get_cliente(codigo: str):
    row = database.sql("""
        SELECT
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
        FROM cliente
        WHERE codigo = %s
    """, (codigo,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    r = row[0]
    return {
        "codigo": r[0],
        "nombrejuridico": r[1],
        "nombrecomercial": r[2],
        "pais": r[3],
        "correo": r[4],
        "telefono": r[5],
        "cedulajuridicavat": r[6],
        "actividad_economica": r[7],
        "comentarios": r[8],
        "provincia": r[9],
        "canton": r[10],
        "distrito": r[11],
        "direccionexacta": r[12],
        "fecha_pago": r[13],
        "prefijo": r[14],
        "contacto_principal": r[15],
        "contacto_secundario": r[16],
    }


@router.put("/update")
def update_cliente(data: dict):
    sql = """
        UPDATE cliente SET
            nombrejuridico = %(NombreJuridico)s,
            nombrecomercial = %(NombreComercial)s,
            pais = %(Pais)s,
            correo = %(Correo)s,
            telefono = %(Telefono)s,
            cedulajuridicavat = %(CedulaJuridicaVAT)s,
            comentarios = %(Comentarios)s,
            provincia = %(Provincia)s,
            canton = %(Canton)s,
            distrito = %(Distrito)s,
            direccionexacta = %(DireccionExacta)s,
            fecha_pago = %(FechaDePago)s,
            prefijo = %(Prefijo)s,
            contacto_principal = %(ContactoPrincipal)s,
            contacto_secundario = %(ContactoSecundario)s
        WHERE codigo = %(Codigo)s
    """
    try:
        database.sql(sql, data)
        return {"status": "OK", "msg": "Cliente actualizado ✔"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ELIMINAR CLIENTE
# ============================================================
@router.delete("/{codigo}")
def delete_cliente(codigo: str):
    database.sql("DELETE FROM cliente WHERE codigo = %s", (codigo,))
    return {"status": "OK", "msg": "Cliente eliminado 🗑️"}


# ============================================================
# OBTENER ÚLTIMO CÓDIGO CORRELATIVO
# ============================================================
@router.get("/ultimo")
def get_ultimo_cliente():
    sql = """
        SELECT MAX(CAST(SUBSTRING(codigo FROM 5 FOR 4) AS INTEGER))
        FROM cliente;
    """
    result = database.sql(sql, fetch=True)
    ultimo = result[0][0] if result and result[0][0] is not None else 0
    return {"ultimo": ultimo}
