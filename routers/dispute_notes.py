# ============================================================
# Dispute Notes API (NC / ND) - ERP-SOM
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from datetime import datetime, date
from typing import Optional, Dict, Any
import xml.etree.ElementTree as ET

from database import get_db

router = APIRouter(
    prefix="/dispute-management",
    tags=["Disputes - Notes (NC/ND)"]
)

# ============================================================
# HELPERS
# ============================================================

def _get_table_columns(cur, table_name: str) -> Dict[str, dict]:
    cur.execute("""
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return {r["column_name"]: r for r in cur.fetchall()}


def _find_billing_table(cur) -> str:
    candidates = [
        "factura",
        "facturas",
        "billing",
        "billing_factura",
        "billing_facturas",
    ]

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
    """)
    existing = {r["table_name"] for r in cur.fetchall()}

    for t in candidates:
        if t in existing:
            return t

    raise HTTPException(
        status_code=500,
        detail="No se encontró tabla de Billing (factura / facturas / billing)"
    )


def _calc_new_disputed_amount(old: float, tipo: str, monto: float) -> float:
    return old - monto if tipo == "NC" else old + monto


def _close_if_zero(cur, management_id: int, new_amount: float):
    if new_amount <= 0:
        cur.execute("""
            UPDATE dispute_management
            SET disputed_amount = 0,
                status = 'Resolved',
                dispute_closed_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (datetime.now(), management_id))
        return 0.0, True

    cur.execute("""
        UPDATE dispute_management
        SET disputed_amount = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (new_amount, management_id))
    return new_amount, False


def _insert_history(cur, management_id: int, comentario: str, user: str):
    cur.execute("""
        INSERT INTO dispute_history
        (dispute_management_id, comentario, created_by)
        VALUES (%s, %s, %s)
    """, (management_id, comentario, user))


def _get_dispute_context(cur, management_id: int) -> dict:
    cur.execute("""
        SELECT
            dm.id,
            dm.disputed_amount,
            dm.dispute_id,
            d.dispute_case,
            d.numero_documento,
            d.codigo_cliente,
            d.nombre_cliente,
            d.monto AS monto_original
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        WHERE dm.id = %s
    """, (management_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Disputa no encontrada")
    return row


# ============================================================
# BILLING INSERT
# ============================================================

def _crear_en_billing(
    cur,
    *,
    tipo: str,
    monto: float,
    moneda: str,
    dispute_case: str,
    numero_documento: str,
    codigo_cliente: str,
    nombre_cliente: str,
    source: str,
    xml_raw: Optional[str] = None
) -> int:

    table = _find_billing_table(cur)
    cols = _get_table_columns(cur, table)

    today = date.today()
    now = datetime.now()

    values = {
        "tipo": tipo,
        "tipo_factura": tipo,
        "tipo_documento": tipo,
        "numero": dispute_case,
        "numero_documento": dispute_case,
        "codigo_cliente": codigo_cliente,
        "cliente": nombre_cliente,
        "nombre_cliente": nombre_cliente,
        "moneda": moneda,
        "total": monto,
        "monto": monto,
        "estado": "CREATED",
        "status": "CREATED",
        "fecha": today,
        "fecha_emision": today,
        "created_at": now,
        "comentario": f"{source} | Dispute {dispute_case} | Doc {numero_documento}",
        "detalle": f"{source} | Dispute {dispute_case} | Doc {numero_documento}",
        "referencia_externa": numero_documento,
    }

    if xml_raw:
        values["xml"] = xml_raw
        values["xml_raw"] = xml_raw

    insert_cols = []
    insert_vals = []

    for col, meta in cols.items():
        if col in values:
            insert_cols.append(col)
            insert_vals.append(values[col])
        elif meta["is_nullable"] == "NO" and meta["column_default"] is None:
            raise HTTPException(
                500,
                f"Columna NOT NULL sin valor en '{table}': {col}"
            )

    q = sql.SQL("""
        INSERT INTO {table} ({cols})
        VALUES ({vals})
        RETURNING id
    """).format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, insert_cols)),
        vals=sql.SQL(", ").join(sql.Placeholder() for _ in insert_cols),
    )

    cur.execute(q, insert_vals)
    return cur.fetchone()["id"]


# ============================================================
# POST /notes/manual
# ============================================================

@router.post("/{management_id}/notes/manual")
def create_note_manual(management_id: int, payload: dict, conn=Depends(get_db)):

    tipo = payload.get("tipo")
    monto = payload.get("monto")
    moneda = payload.get("moneda", "USD")
    user = payload.get("user", "system")
    comentario_user = payload.get("comentario", "")

    if tipo not in ("NC", "ND"):
        raise HTTPException(400, "Tipo inválido")
    monto = float(monto)
    if monto <= 0:
        raise HTTPException(400, "Monto inválido")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    ctx = _get_dispute_context(cur, management_id)
    current = ctx["disputed_amount"] or ctx["monto_original"] or 0

    billing_id = _crear_en_billing(
        cur,
        tipo=tipo,
        monto=monto,
        moneda=moneda,
        dispute_case=ctx["dispute_case"],
        numero_documento=ctx["numero_documento"],
        codigo_cliente=ctx["codigo_cliente"],
        nombre_cliente=ctx["nombre_cliente"],
        source="DISPUTE-MANUAL"
    )

    new_amount = _calc_new_disputed_amount(current, tipo, monto)
    new_amount, resolved = _close_if_zero(cur, management_id, new_amount)

    hist = f"{tipo} MANUAL creada (Billing ID {billing_id}) por {monto:.2f} {moneda}"
    if comentario_user:
        hist += f" | {comentario_user}"

    _insert_history(cur, management_id, hist, user)

    conn.commit()

    return {
        "status": "ok",
        "billing_id": billing_id,
        "new_disputed_amount": new_amount,
        "resolved": resolved
    }
