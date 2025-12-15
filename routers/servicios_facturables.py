from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db

router = APIRouter(
    prefix="/servicios",
    tags=["Servicios - Facturación"]
)

# ============================================================
# GET /servicios/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(
    cliente: Optional[str] = Query(None),
    conn=Depends(get_db)
):
    if not conn:
        raise HTTPException(
            status_code=500,
            detail="No se pudo obtener conexión a la base de datos"
        )

    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ====================================================
        # QUERY BASE
        # ====================================================
        sql = """
            SELECT
                s.consec,
                s.tipo,
                s.estado,
                s.num_informe,
                s.buque_contenedor,
                s.cliente,
                s.detalle,
                s.continente,
                s.pais,
                s.puerto,
                s.operacion,
                s.fecha_inicio,
                s.hora_inicio,
                s.fecha_fin,
                s.hora_fin,
                s.demoras,
                s.duracion,
                s.honorarios,
                s.factura
            FROM servicios s
            WHERE
                s.estado = 'Finalizado'
                AND s.num_informe IS NOT NULL
                AND s.num_informe <> ''
                AND s.factura IS NULL
        """

        params = []

        # ====================================================
        # FILTRO POR CLIENTE (CÓDIGO)
        # ====================================================
        if cliente:
            sql += " AND s.cliente = %s"
            params.append(cliente)

        sql += " ORDER BY s.fecha_inicio NULLS LAST"

        cur.execute(sql, params)
        data = cur.fetchall()

        return {
            "total": len(data),
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error SQL servicios_facturables: {str(e)}"
        )

    finally:
        if cur:
            cur.close()
