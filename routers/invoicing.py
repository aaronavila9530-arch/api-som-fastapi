from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db

router = APIRouter(
    prefix="/invoicing",
    tags=["Invoicing & Billing"]
)

# ============================================================
# GET /invoicing/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(
    cliente: str = Query(..., min_length=1, description="Código del cliente"),
    conn=Depends(get_db)
):
    """
    Devuelve los servicios de UN cliente que:
    - están FINALIZADOS
    - tienen número de informe
    - NO han sido facturados
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
                consec,
                tipo,
                estado,
                num_informe,
                buque_contenedor,
                cliente,
                contacto,
                detalle,
                continente,
                pais,
                puerto,
                operacion,
                surveyor,
                honorarios,
                costo_operativo,
                fecha_inicio,
                hora_inicio,
                fecha_fin,
                hora_fin,
                demoras,
                duracion,
                factura,
                valor_factura,
                fecha_factura,
                terminos_pago,
                fecha_vencimiento,
                dias_vencido
            FROM servicios
            WHERE
                cliente = %s
                AND estado = 'Finalizado'
                AND num_informe IS NOT NULL
                AND num_informe <> ''
                AND factura IS NULL
            ORDER BY fecha_inicio NULLS LAST
        """

        cur.execute(sql, (cliente,))
        data = cur.fetchall()

        return {
            "cliente": cliente,
            "total": len(data),
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error SQL Invoicing Facturables: {str(e)}"
        )

    finally:
        if cur:
            cur.close()
