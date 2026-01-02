from fastapi import APIRouter, HTTPException, Depends, Header
import database

from backend_api.rbac_service import has_permission

router = APIRouter(prefix="/servicios_md", tags=["ServiciosMD"])

# ============================================================
# RBAC GUARD
# ============================================================
def require_permission(module: str, action: str):
    def checker(
        x_user_role: str = Header(..., alias="X-User-Role")
    ):
        if not has_permission(x_user_role, module, action):
            raise HTTPException(
                status_code=403,
                detail="No autorizado"
            )
    return checker



# ============================================================
# INSERTAR NUEVO SERVICIO EN ServiciosMD
# ============================================================
@router.post("/add")
def add_servicio(data: dict):
    sql = """
        INSERT INTO ServiciosMD (
            Codigo, CodigoProd, Nombre, Costo
        )
        VALUES (
            %(codigo)s, %(codigo_prod)s, %(nombre)s, %(costo)s
        )
    """
    database.sql(sql, data)
    return {"status": "OK", "msg": "Servicio registrado 💾✔"}


# ============================================================
# OBTENER ÚLTIMO CÓDIGO CORRELATIVO
# ============================================================
@router.get("/ultimo")
def get_ultimo_codigo():
    data = database.sql("""
        SELECT MAX(CAST(SUBSTRING(codigo FROM 5 FOR 4) AS INTEGER)) 
        FROM ServiciosMD;
    """, fetch=True)

    ultimo = data[0][0] if data and data[0][0] else 0
    return {"ultimo": ultimo}

# ============================================================
# LISTAR SERVICIOS — PAGINADO
# ============================================================
@router.get("/")
def get_servicios(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT Codigo, CodigoProd, Nombre, Costo
        FROM ServiciosMD
        ORDER BY Codigo ASC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    # total para paginación
    total = database.sql("""
        SELECT COUNT(*) FROM ServiciosMD
    """, fetch=True)[0][0]

    data = [
        {
            "codigo": r[0],
            "codigo_prod": r[1],
            "nombre": r[2],
            "costo": r[3],
        }
        for r in rows
    ]

    return {"data": data, "total": total}


# ============================================================
# OBTENER UN SERVICIO POR CÓDIGO
# ============================================================
@router.get("/{codigo}")
def get_servicio(codigo: str):
    row = database.sql("""
        SELECT Codigo, CodigoProd, Nombre, Costo
        FROM ServiciosMD
        WHERE Codigo = %s
    """, (codigo,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    r = row[0]
    return {
        "codigo": r[0],
        "codigo_prod": r[1],
        "nombre": r[2],
        "costo": r[3],
    }

# ============================================================
# ACTUALIZAR SERVICIO
# ============================================================
@router.put("/update")
def update_servicio(data: dict):
    sql = """
        UPDATE ServiciosMD SET
            CodigoProd = %(codigo_prod)s,
            Nombre = %(nombre)s,
            Costo = %(costo)s
        WHERE Codigo = %(codigo)s
    """
    database.sql(sql, data)
    return {"status": "OK", "msg": "Servicio actualizado ✔"}


# ============================================================
# ELIMINAR SERVICIO
# ============================================================
@router.delete("/{codigo}")
def delete_servicio(codigo: str):
    database.sql("""
        DELETE FROM ServiciosMD WHERE Codigo = %s
    """, (codigo,))
    return {"status": "OK", "msg": "Servicio eliminado 🗑️"}
