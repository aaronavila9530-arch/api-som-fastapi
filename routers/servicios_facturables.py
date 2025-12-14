from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

from database import get_db

router = APIRouter(
    prefix="/servicios",
    tags=["Servicios - Facturación"]
)

# ============================================================
# GET /servicios/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(conn=Depends(get_db)):
    """
    Retorna los servicios que:
    - están FINALIZADOS
    - tienen num_informe
    - NO han sido facturados
    """
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        sql = """
        SELECT
            s.id,
            s.codigo,
            s.cliente,
            s.descripcion,
            s.estado,
            s.num_informe,
            s.fecha,
            s.monto
        FROM servicios s
        WHERE
            s.estado = 'FINALIZADO'
            AND s.num_informe IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM factura_servicio fs
                WHERE fs.servicio_id = s.id
            )
        ORDER BY s.fecha ASC
        """

        cur.execute(sql)
        data = cur.fetchall()
        cur.close()

        return {
            "total": len(data),
            "data": data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
