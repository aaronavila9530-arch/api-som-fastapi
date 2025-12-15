from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from typing import Optional, List, Dict, Any

from database import get_db

router = APIRouter(
    prefix="/servicios",
    tags=["Servicios - Facturación"]
)

# ============================================================
# GET /servicios/facturables
# ============================================================
@router.get(
    "/facturables",
    response_model=Dict[str, Any]
)
def get_servicios_facturables(
    cliente: Optional[str] = Query(None),
    conn=Depends(get_db)
):
    """
    Retorna servicios facturables:
    - estado = FINALIZADO
    - num_informe IS NOT NULL
    - NO facturados
    - opcionalmente filtrados por cliente
    """

    if not conn:
        raise HTTPException(
            status_code=500,
            detail="No se pudo obtener conexión a la base de datos"
        )

    cur = None
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
        """

        params = []

        if cliente:
            sql += " AND s.cliente = %s"
            params.append(cliente)

        sql += " ORDER BY s.fecha ASC"

        cur.execute(sql, params)
        data = cur.fetchall()

        return {
            "total": len(data),
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener servicios facturables: {str(e)}"
        )

    finally:
        if cur:
            cur.close()
