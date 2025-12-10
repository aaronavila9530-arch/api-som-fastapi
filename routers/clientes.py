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


from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/clientes", tags=["Clientes"])


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
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM cliente", fetch=True)[0][0]

    data = [
        {
            "Codigo": r[0],
            "NombreJuridico": r[1],
            "NombreComercial": r[2],
            "Pais": r[3],
            "Correo": r[4],
            "Telefono": r[5],
            "CedulaJuridicaVAT": r[6],
            "ActividadEconomica": r[7],
            "Comentarios": r[8],
            "Provincia": r[9],
            "Canton": r[10],
            "Distrito": r[11],
            "DireccionExacta": r[12],
            "FechaDePago": r[13],
            "Prefijo": r[14],
            "ContactoPrincipal": r[15],
            "ContactoSecundario": r[16],
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
        "Codigo": r[0],
        "NombreJuridico": r[1],
        "NombreComercial": r[2],
        "Pais": r[3],
        "Correo": r[4],
        "Telefono": r[5],
        "CedulaJuridicaVAT": r[6],
        "ActividadEconomica": r[7],
        "Comentarios": r[8],
        "Provincia": r[9],
        "Canton": r[10],
        "Distrito": r[11],
        "DireccionExacta": r[12],
        "FechaDePago": r[13],
        "Prefijo": r[14],
        "ContactoPrincipal": r[15],
        "ContactoSecundario": r[16],
    }


# ============================================================
# ACTUALIZAR CLIENTE — nombres alineados con UI
# ============================================================
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
            actividad_economica = %(ActividadEconomica)s,
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
    database.sql(sql, data)
    return {"status": "OK", "msg": "Cliente actualizado ✔"}


# ============================================================
# ELIMINAR CLIENTE
# ============================================================
@router.delete("/{codigo}")
def delete_cliente(codigo: str):
    database.sql("DELETE FROM cliente WHERE codigo = %s", (codigo,))
    return {"status": "OK", "msg": "Cliente eliminado 🗑️"}
