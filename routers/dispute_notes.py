# ============================================================
# Dispute Notes API (NC/ND) - ERP-SOM
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
# Helpers
# ============================================================

def _calc_new_disputed_amount(old_amount: float, tipo: str, monto: float) -> float:
    return old_amount - monto if tipo == "NC" else old_amount + monto


def _ensure_disputed_amount(cur, management_id: int, monto_original: float):
    """
    Garantiza que disputed_amount nunca sea NULL
    """
    cur.execute("""
        UPDATE dispute_management
        SET disputed_amount = COALESCE(disputed_amount, %s)
        WHERE id = %s
    """, (monto_original, management_id))


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
        INSERT INTO dispute_history (dispute_management_id, comentario, created_by)
        VALUES (%s, %s, %s)
    """, (management_id, comentario, user))


def _get_context(cur, management_id: int):
    cur.execute("""
        SELECT
            dm.id,
            dm.disputed_amount,
            d.monto AS monto_original,
            d.dispute_case,
            d.numero_documento,
            d.codigo_cliente,
            d.nombre_cliente
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        WHERE dm.id = %s
    """, (management_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Disputa no encontrada")
    return row


# ============================================================
# Billing inserter (SEGURIDAD REAL)
# ============================================================

def _find_billing_table(cur):
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
    """)
    tables = {r["table_name"] for r in cur.fetchall()}
    for t in ("factura", "facturas", "billing_factura", "billing_facturas"):
        if t in tables:
            return t
    raise HTTPException(500, "No se encontró tabla de Billing")


def _get_columns(cur, table):
    cur.execute("""
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
    """, (table,))
    return {c["column_name"]: c for c in cur.fetchall()}


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
        # Identidad
        "tipo": tipo,
        "tipo_factura": tipo,
        "tipo_documento": tipo,
        "numero": dispute_case,
        "numero_documento": dispute_case,
        "consecutivo": dispute_case,

        # Cliente
        "cliente": nombre_cliente,
        "codigo_cliente": codigo_cliente,
        "nombre_cliente": nombre_cliente,

        # Importes
        "moneda": moneda,
        "total": monto,
        "monto": monto,
        "importe": monto,

        # Fechas (CRÍTICO)
        "fecha": today,
        "fecha_emision": today,
        "created_at": now,

        # Estado
        "estado": "CREATED",
        "status": "CREATED",

        # Referencias
        "referencia_externa": numero_documento,
        "numero_referencia": numero_documento,
        "comentario": f"{source} | Dispute {dispute_case} | Doc {numero_documento}",
        "detalle": f"{source} | Dispute {dispute_case} | Doc {numero_documento}",
        "observacion": f"{source} | Dispute {dispute_case} | Doc {numero_documento}",
    }

    if xml_raw:
        values["xml"] = xml_raw
        values["xml_raw"] = xml_raw
        values["xml_text"] = xml_raw

    insert_cols = []
    insert_vals = []

    for col, meta in cols.items():
        if col in values:
            insert_cols.append(col)
            insert_vals.append(values[col])
        else:
            # 🚨 Columna NOT NULL sin default → ERROR CONTROLADO
            if meta["is_nullable"] == "NO" and meta["column_default"] is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"Columna NOT NULL sin valor: '{col}' en tabla '{table}'"
                )

    if not insert_cols:
        raise HTTPException(500, "No hay columnas válidas para insertar en Billing")

    q = sql.SQL("""
        INSERT INTO {table} ({cols})
        VALUES ({vals})
        RETURNING id
    """).format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, insert_cols)),
        vals=sql.SQL(", ").join(sql.Placeholder() for _ in insert_cols),
    )

    try:
        cur.execute(q, insert_vals)
        return cur.fetchone()["id"]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error insertando en Billing ({table}): {str(e)}"
        )


# ============================================================
# NC / ND MANUAL
# ============================================================

@router.post("/{management_id}/notes/manual")
def create_note_manual(management_id: int, payload: dict, conn=Depends(get_db)):

    tipo = payload.get("tipo")
    monto = float(payload.get("monto", 0))
    moneda = payload.get("moneda", "USD")
    user = payload.get("user", "system")
    comentario = payload.get("comentario", "")

    if tipo not in ("NC", "ND") or monto <= 0:
        raise HTTPException(400, "Datos inválidos")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        ctx = _get_context(cur, management_id)

        _ensure_disputed_amount(cur, management_id, ctx["monto_original"])

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

        new_amount = _calc_new_disputed_amount(
            ctx["disputed_amount"] or ctx["monto_original"],
            tipo,
            monto
        )

        new_amount, resolved = _close_if_zero(cur, management_id, new_amount)

        _insert_history(
            cur,
            management_id,
            f"{tipo} manual creada (Billing {billing_id}). {comentario}",
            user
        )

        conn.commit()

        return {
            "status": "ok",
            "billing_id": billing_id,
            "new_disputed_amount": new_amount,
            "resolved": resolved
        }

    except Exception:
        conn.rollback()
        raise
