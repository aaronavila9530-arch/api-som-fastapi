from fastapi import APIRouter
import database

router = APIRouter(prefix="/servicios", tags=["Servicios"])

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
