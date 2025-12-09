from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])


@router.get("/ultimo_codigo")
def ultimo_codigo():
    try:
        res = database.sql("SELECT codigo FROM proveedor ORDER BY id DESC LIMIT 1;", fetch=True)
        if res:
            return {"codigo": res[0]["codigo"]}
        return {"codigo": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
