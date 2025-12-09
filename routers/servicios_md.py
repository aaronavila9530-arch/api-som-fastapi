from fastapi import APIRouter
import database

router = APIRouter(prefix="/servicios", tags=["Servicios"])

@router.get("/ultimo")
def get_ultimo_codigo():
    data = database.sql("""
        SELECT MAX(CAST(SUBSTRING(codigo FROM 5 FOR 4) AS INTEGER)) 
        FROM ServiciosMD;
    """, fetch=True)
    
    ultimo = data[0][0] if data and data[0][0] else 0
    return {"ultimo": ultimo}
