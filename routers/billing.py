from fastapi import APIRouter, Depends, Query, HTTPException
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date

from database import get_db


router = APIRouter(
    prefix="/billing",
    tags=["Billing"]
)

# ============================================================
# GET /billing/search
# Búsqueda de documentos de facturación (emitidos)
# ============================================================
@router.get("/search")
def buscar_billing(
    cliente: Optional[str] = Query(
        None,
        description="Nombre del cliente o ALL para todos"
    ),
    fecha_desde: Optional[date] = Query(
        None,
        description="Fecha inicio (YYYY-MM-DD)"
    ),
    fecha_hasta: Optional[date] = Query(
        None,
        description="Fecha fin (YYYY-MM-DD)"
    ),
    tipo_factura: Optional[str] = Query(
        None,
        description="MANUAL | ELECTRONICA"
    ),
    tipo_documento: Optional[str] = Query(
        None,
        description="FACTURA | NOTA_CREDITO"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_db)
):
    """
    Devuelve documentos de facturación emitidos (facturas / notas de crédito)
    usando filtros opcionales y paginación.
    """

    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=RealDictCursor)

    filtros = []
    params = {}

    # ================= FILTROS =================
    if cliente and cliente.upper() != "ALL":
        filtros.append("nombre_cliente ILIKE %(cliente)s")
        params["cliente"] = f"%{cliente}%"

    if tipo_factura:
        filtros.append("tipo_factura = %(tipo_factura)s")
        params["tipo_factura"] = tipo_factura

    if tipo_documento:
        filtros.append("tipo_documento = %(tipo_documento)s")
        params["tipo_documento"] = tipo_documento

    if fecha_desde:
        filtros.append("fecha_emision >= %(fecha_desde)s")
        params["fecha_desde"] = fecha_desde

    if fecha_hasta:
        filtros.append("fecha_emision <= %(fecha_hasta)s")
        params["fecha_hasta"] = fecha_hasta

    where_sql = "WHERE " + " AND ".join(filtros) if filtros else ""

    # ================= TOTAL =================
    cur.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM factura
        {where_sql}
        """,
        params
    )
    total = cur.fetchone()["total"]

    # ================= DATA =================
    cur.execute(
        f"""
        SELECT
            id,
            tipo_factura,
            tipo_documento,
            numero_factura        AS numero_documento,
            nombre_cliente,
            fecha_emision,
            moneda,
            total,
            estado
        FROM factura
        {where_sql}
        ORDER BY fecha_emision DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            **params,
            "limit": page_size,
            "offset": offset
        }
    )

    data = cur.fetchall()
    cur.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": data
    }


# ============================================================
# GET /billing/{numero_factura}
# Devuelve factura completa para Preview (Billing / Invoicing)
# ============================================================
@router.get("/{numero_factura}")
def get_factura(
    numero_factura: str,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT *
        FROM factura
        WHERE numero_factura = %s
    """, (numero_factura,))

    factura = cur.fetchone()
    cur.close()

    if not factura:
        raise HTTPException(
            status_code=404,
            detail="Factura no encontrada"
        )

    return factura


# ============================================================
# GET /billing/pdf/{numero_factura}
# Devuelve ruta del PDF
# ============================================================
@router.get("/pdf/{numero_factura}")
def obtener_pdf_factura(
    numero_factura: str,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT pdf_path
        FROM factura
        WHERE numero_factura = %s
    """, (numero_factura,))

    row = cur.fetchone()
    cur.close()

    if not row or not row.get("pdf_path"):
        raise HTTPException(
            status_code=404,
            detail="PDF no encontrado"
        )

    return {"pdf_path": row["pdf_path"]}
