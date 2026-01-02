from fastapi import APIRouter, Depends, Query, HTTPException, Header
from psycopg2.extras import RealDictCursor
from typing import Optional

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/disputas",
    tags=["Disputas"]
)

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
# GET /disputas
# Listado base de disputas (TABLA PRINCIPAL)
# ============================================================
@router.get("")
def listar_disputas(
    codigo_cliente: Optional[str] = Query(None),
    page: int = 1,
    page_size: int = 50,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    offset = (page - 1) * page_size

    filtros = []
    params = []

    if codigo_cliente:
        filtros.append("d.codigo_cliente = %s")
        params.append(codigo_cliente)

    where_sql = f"WHERE {' AND '.join(filtros)}" if filtros else ""

    sql = f"""
        SELECT
            d.id,
            d.dispute_case,
            d.numero_documento,
            d.codigo_cliente,
            d.nombre_cliente,
            d.fecha_factura,
            d.fecha_vencimiento,
            d.monto,
            d.motivo,
            d.comentario,
            d.buque_contenedor,
            d.operacion,
            d.periodo_operacion,
            d.descripcion_servicio,
            d.created_at
        FROM disputa d
        {where_sql}
        ORDER BY d.created_at DESC
        LIMIT %s OFFSET %s
    """

    cur.execute(sql, params + [page_size, offset])
    data = cur.fetchall()

    return {
        "page": page,
        "page_size": page_size,
        "data": data
    }
