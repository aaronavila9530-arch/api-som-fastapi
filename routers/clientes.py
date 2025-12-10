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
# OBTENER ÚLTIMO CÓDIGO CORRELATIVO
# ============================================================
@router.get("/ultimo")
def get_ultimo_codigo():
    res = database.sql("""
        SELECT MAX(CAST(split_part(codigo, '-', 2) AS INTEGER))
        FROM cliente;
    """, fetch=True)

    ultimo = res[0][0] if res and res[0][0] else 0
    return {"ultimo": ultimo}

# ============================================================
# LISTAR CLIENTES — PAGINADO
# ============================================================
@router.get("/")
def get_clientes(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT
            codigo,
            nombrejuridico,
            nombrecomercial,
            pais,
            correo,
            telefono
        FROM cliente
        ORDER BY codigo ASC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM cliente", fetch=True)[0][0]

    data = [
        {
            "codigo": r[0],
            "nombre_juridico": r[1],
            "nombre_comercial": r[2],
            "pais": r[3],
            "correo": r[4],
            "telefono": r[5],
        }
        for r in rows
    ]

    return {"data": data, "total": total}


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
            provincia,
            canton,
            distrito,
            direccionexacta,
            fecha_pago,
            prefijo,
            contacto_principal,
            contacto_secundario,
            comentarios
        FROM cliente
        WHERE codigo = %s
    """, (codigo,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    r = row[0]
    return {
        "codigo": r[0],
        "nombre_juridico": r[1],
        "nombre_comercial": r[2],
        "pais": r[3],
        "correo": r[4],
        "telefono": r[5],
        "cedula_juridica_vat": r[6],
        "provincia": r[7],
        "canton": r[8],
        "distrito": r[9],
        "direccion_exacta": r[10],
        "fecha_de_pago": r[11],
        "prefijo": r[12],
        "contacto_principal": r[13],
        "contacto_secundario": r[14],
        "comentarios": r[15]
    }


# ============================================================
# ACTUALIZAR CLIENTE
# ============================================================
@router.put("/update")
def update_cliente(data: dict):
    sql = """
        UPDATE cliente SET
            nombrejuridico = %(nombre_juridico)s,
            nombrecomercial = %(nombre_comercial)s,
            pais = %(pais)s,
            correo = %(correo)s,
            telefono = %(telefono)s,
            cedulajuridicavat = %(cedula_juridica_vat)s,
            comentarios = %(comentarios)s,
            provincia = %(provincia)s,
            canton = %(canton)s,
            distrito = %(distrito)s,
            direccionexacta = %(direccion_exacta)s,
            fecha_pago = %(fecha_de_pago)s,
            prefijo = %(prefijo)s,
            contacto_principal = %(contacto_principal)s,
            contacto_secundario = %(contacto_secundario)s
        WHERE codigo = %(codigo)s
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
    try:
        database.sql("DELETE FROM cliente WHERE codigo = %s", (codigo,))
        return {"status": "OK", "msg": "Cliente eliminado 🗑️"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))