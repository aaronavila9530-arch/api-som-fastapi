from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db

router = APIRouter(
    prefix="/servicios",
    tags=["Servicios - Facturación"]
)

# ============================================================
# ⚠️ ESTA RUTA DEBE IR PRIMERO
# GET /servicios/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(
    cliente: Optional[str] = Query(None),
    conn=Depends(get_db)
):
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
            detail=str(e)
        )

    finally:
        if cur:
            cur.close()


# ============================================================
# ⚠️ ESTA RUTA SIEMPRE AL FINAL
# GET /servicios/{servicio_id}
# ============================================================
@router.get("/{servicio_id}")
def get_servicio(
    servicio_id: int,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM servicios WHERE id = %s",
        (servicio_id,)
    )
    data = cur.fetchone()
    cur.close()

    if not data:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    return data
