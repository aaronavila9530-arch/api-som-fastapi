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
# ============================================================
@router.get("/search")
def buscar_billing(
    cliente: Optional[str] = Query(None),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    tipo_factura: Optional[str] = Query(None),
    tipo_documento: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_db)
):
    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=RealDictCursor)

    filtros = []
    params = {}

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

    # -------- TOTAL --------
    cur.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM invoicing
        {where_sql}
        """,
        params
    )
    total = cur.fetchone()["total"]

    # -------- DATA --------
    cur.execute(
        f"""
        SELECT
            id,
            tipo_factura,
            tipo_documento,
            numero_documento,
            nombre_cliente,
            fecha_emision,
            moneda,
            total,
            estado
        FROM invoicing
        {where_sql}
        ORDER BY fecha_emision DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {**params, "limit": page_size, "offset": offset}
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
# GET /billing/{numero_documento}
# Preview de factura (PopupPreviewFactura)
# ============================================================
@router.get("/{numero_documento}")
def get_factura(numero_documento: str, conn=Depends(get_db)):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT *
        FROM invoicing
        WHERE numero_documento = %s
    """, (numero_documento,))

    factura = cur.fetchone()
    cur.close()

    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    return factura


# ============================================================
# GET /billing/pdf/{numero_documento}
# ============================================================
@router.get("/pdf/{numero_documento}")
def obtener_pdf_factura(numero_documento: str, conn=Depends(get_db)):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT pdf_path
        FROM invoicing
        WHERE numero_documento = %s
    """, (numero_documento,))

    row = cur.fetchone()
    cur.close()

    if not row or not row["pdf_path"]:
        raise HTTPException(404, "PDF no encontrado")

    return {"pdf_path": row["pdf_path"]}
