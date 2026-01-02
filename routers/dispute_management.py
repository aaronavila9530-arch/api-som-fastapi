# ============================================================
# Dispute Management API - ERP-SOM
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import datetime

from database import get_db
from backend_api.rbac_service import has_permission

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
# CONSTANTES
# ============================================================

DISPUTE_STATUSES = [
    "New",
    "In process",
    "Process by Sales",
    "Process by RTR",
    "Process by Invoicing",
    "Process by Collections",
    "Process by Bank",
    "Process by Disputes",
    "Written Off",
    "Resolved"
]

# ============================================================
# GET /dispute-management
# LISTADO DE GESTIONES (SOLO LAS EXISTENTES)
# ============================================================

@router.get("")
def list_dispute_management(
    cliente: Optional[str] = Query(None),
    page: int = 1,
    page_size: int = 50,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    offset = (page - 1) * page_size

    where = ""
    params = []

    if cliente:
        where = "WHERE d.codigo_cliente = %s"
        params.append(cliente)

    sql = f"""
        SELECT
            dm.id               AS management_id,
            dm.status,
            dm.disputed_amount,
            dm.dispute_closed_at,
            d.id                AS dispute_id,
            d.dispute_case,
            d.numero_documento,
            d.codigo_cliente,
            d.nombre_cliente,
            d.fecha_factura,
            d.fecha_vencimiento,
            d.monto,
            d.created_at,
            (
                SELECT comentario
                FROM dispute_history h
                WHERE h.dispute_management_id = dm.id
                ORDER BY h.created_at DESC
                LIMIT 1
            ) AS ultimo_comentario
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        {where}
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

# ============================================================
# POST /dispute-management/{management_id}/status
# CAMBIO DE ESTATUS + HISTORIAL
# ============================================================

@router.post("/{management_id}/status")
def update_status(
    management_id: int,
    payload: dict,
    conn=Depends(get_db)
):
    status = payload.get("status")
    comentario = payload.get("comentario")
    user = payload.get("user", "SYSTEM")

    if status not in DISPUTE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    closed_at = None
    if status == "Resolved":
        closed_at = datetime.now()

    cur.execute("""
        UPDATE dispute_management
        SET status = %s,
            dispute_closed_at = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id
    """, (status, closed_at, management_id))

    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Dispute management not found")

    if comentario:
        cur.execute("""
            INSERT INTO dispute_history
            (dispute_management_id, comentario, created_by)
            VALUES (%s, %s, %s)
        """, (management_id, comentario, user))

    conn.commit()
    return {"status": "ok"}

# ============================================================
# GET /dispute-management/{management_id}/history
# ============================================================

@router.get("/{management_id}/history")
def get_history(
    management_id: int,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT comentario, created_by, created_at
        FROM dispute_history
        WHERE dispute_management_id = %s
        ORDER BY created_at DESC
    """, (management_id,))

    return cur.fetchall()

# ============================================================
# GET /dispute-management/kpis/summary
# ============================================================

@router.get("/kpis/summary")
def get_kpis(conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ADO
    cur.execute("""
        SELECT AVG(CURRENT_DATE - d.created_at::date) AS ado
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        WHERE dm.status != 'Resolved'
    """)
    ado = cur.fetchone()["ado"]

    # DDO
    cur.execute("""
        SELECT AVG(dm.dispute_closed_at::date - d.created_at::date) AS ddo
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        WHERE dm.status = 'Resolved'
    """)
    ddo = cur.fetchone()["ddo"]

    # Incoming Volume (mes actual)
    cur.execute("""
        SELECT COUNT(*) AS incoming_volume
        FROM disputa
        WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
    """)
    incoming = cur.fetchone()["incoming_volume"]

    # Disputed Amount
    cur.execute("""
        SELECT SUM(disputed_amount) AS disputed_amount
        FROM dispute_management
        WHERE status != 'Resolved'
    """)
    amount = cur.fetchone()["disputed_amount"]

    return {
        "ADO": round(ado or 0, 2),
        "DDO": round(ddo or 0, 2),
        "IncomingVolume": incoming,
        "DisputedAmount": float(amount or 0)
    }

# ============================================================
# POST /dispute-management/from-dispute/{dispute_id}
# CREA GESTIÓN DESDE DISPUTA (✔ FIX CRÍTICO)
# ============================================================

@router.post("/from-dispute/{dispute_id}")
def create_or_get_management_from_dispute(
    dispute_id: int,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Validar disputa
    cur.execute("""
        SELECT id, monto
        FROM disputa
        WHERE id = %s
    """, (dispute_id,))
    disputa = cur.fetchone()

    if not disputa:
        raise HTTPException(status_code=404, detail="Disputa no encontrada")

    # 2️⃣ Ver si ya existe gestión
    cur.execute("""
        SELECT id, status
        FROM dispute_management
        WHERE dispute_id = %s
    """, (dispute_id,))
    management = cur.fetchone()

    if management:
        return {
            "management_id": management["id"],
            "status": management["status"],
            "created": False
        }

    # 3️⃣ CREAR gestión correctamente (✔ disputed_amount)
    cur.execute("""
        INSERT INTO dispute_management (
            dispute_id,
            status,
            disputed_amount,
            created_at
        )
        VALUES (%s, %s, %s, NOW())
        RETURNING id
    """, (
        dispute_id,
        "New",
        disputa["monto"]
    ))

    management_id = cur.fetchone()["id"]

    # 4️⃣ Crear historial inicial
    cur.execute("""
        INSERT INTO dispute_history (
            dispute_management_id,
            comentario,
            created_by
        )
        VALUES (%s, %s, %s)
    """, (
        management_id,
        "Gestión iniciada desde disputa",
        "SYSTEM"
    ))

    conn.commit()

    return {
        "management_id": management_id,
        "status": "New",
        "created": True
    }
