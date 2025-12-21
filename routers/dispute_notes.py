# ============================================================
# Dispute Notes API (NC/ND) - ERP-SOM
# NC/ND solo se crean si hay una disputa de por medio
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional
import xml.etree.ElementTree as ET

from database import get_db

router = APIRouter(
    prefix="/dispute-management",
    tags=["Disputes - Notes (NC/ND)"]
)

# -----------------------------
# Helpers de negocio
# -----------------------------

def _calc_new_disputed_amount(old_amount: float, tipo: str, monto: float) -> float:
    if tipo == "NC":
        return old_amount - monto
    if tipo == "ND":
        return old_amount + monto
    raise ValueError("Tipo inválido")


def _close_if_zero(cur, management_id: int, new_amount: float):
    """
    Si el monto llega a 0 -> status Resolved y fecha de cierre.
    """
    if new_amount <= 0:
        new_amount = 0.0
        cur.execute("""
            UPDATE dispute_management
            SET disputed_amount = %s,
                status = 'Resolved',
                dispute_closed_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_amount, datetime.now(), management_id))
        return new_amount, "Resolved"

    cur.execute("""
        UPDATE dispute_management
        SET disputed_amount = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (new_amount, management_id))
    return new_amount, None


def _insert_history(cur, management_id: int, comentario: str, created_by: str):
    cur.execute("""
        INSERT INTO dispute_history (dispute_management_id, comentario, created_by)
        VALUES (%s, %s, %s)
    """, (management_id, comentario, created_by))


def _get_dispute_context(cur, management_id: int):
    """
    Trae datos de disputa + management para referenciar en Billing
    """
    cur.execute("""
        SELECT
            dm.id AS management_id,
            dm.disputed_amount,
            dm.status,
            dm.dispute_id,
            d.dispute_case,
            d.numero_documento,
            d.codigo_cliente,
            d.nombre_cliente,
            d.monto AS monto_original,
            d.created_at AS dispute_created_at
        FROM dispute_management dm
        JOIN disputa d ON d.id = dm.dispute_id
        WHERE dm.id = %s
    """, (management_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Disputa no encontrada")
    return row


# ============================================================
# PUNTO CRÍTICO: creación en Billing (ajusta a tu tabla real)
# ============================================================

def _crear_en_billing(cur, *, tipo: str, monto: float, moneda: str,
                     dispute_case: str, numero_documento: str,
                     codigo_cliente: str, nombre_cliente: str,
                     source: str, xml_raw: Optional[str] = None) -> int:
    """
    IMPORTANTE:
    - Aquí debes alinear el INSERT a tu tabla real de Billing.
    - Esta implementación es un "template" seguro:
      1) Deja la referencia de la NC/ND al dispute_case
      2) Deja la referencia al documento disputado
      3) Guarda el monto/moneda
      4) (Opcional) guarda el XML si decides tener un campo
    """

    # ========= EJEMPLO GENERICO =========
    # Si tu tabla billing NO tiene estas columnas, AJUSTA este INSERT.
    # La idea es que Billing muestre este registro en su tabla.

    cur.execute("""
        INSERT INTO billing (
            tipo_factura,
            tipo_documento,
            numero,
            cliente,
            fecha,
            moneda,
            total,
            estado,
            referencia_externa,
            comentario
        )
        VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        tipo,                      # tipo_factura (NC/ND)
        tipo,                      # tipo_documento
        dispute_case,              # numero (para rastreo)
        nombre_cliente,            # cliente
        moneda,                    # moneda
        monto,                     # total
        "CREATED",                 # estado
        numero_documento,          # referencia_externa: documento disputado
        f"{source} | Dispute Case {dispute_case} | Doc {numero_documento}"
    ))

    return cur.fetchone()["id"]


# ============================================================
# POST /dispute-management/{management_id}/notes/manual
# Crear NC/ND MANUAL desde Disputes (obligatorio dispute)
# ============================================================

@router.post("/{management_id}/notes/manual")
def create_note_manual(management_id: int, payload: dict, conn=Depends(get_db)):
    """
    payload:
    {
      "tipo": "NC" | "ND",
      "monto": 123.45,
      "moneda": "USD",
      "comentario": "texto opcional",
      "user": "Aaroncito"
    }
    """

    tipo = payload.get("tipo")
    monto = payload.get("monto")
    moneda = payload.get("moneda", "USD")
    comentario_user = payload.get("comentario", "")
    user = payload.get("user", "system")

    if tipo not in ("NC", "ND"):
        raise HTTPException(400, "Tipo inválido (use NC o ND)")
    if monto is None:
        raise HTTPException(400, "Falta monto")
    try:
        monto = float(monto)
    except Exception:
        raise HTTPException(400, "Monto inválido")
    if monto <= 0:
        raise HTTPException(400, "Monto debe ser mayor a 0")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Contexto disputa
    ctx = _get_dispute_context(cur, management_id)

    # 1) Crear en Billing (obligatorio)
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

    # 2) Ajustar disputed_amount
    new_amount = _calc_new_disputed_amount(float(ctx["disputed_amount"]), tipo, monto)

    # 3) Cerrar si llega a 0
    new_amount, resolved_status = _close_if_zero(cur, management_id, new_amount)

    # 4) History
    hist = f"{tipo} MANUAL creada (Billing ID {billing_id}) por {monto:.2f} {moneda}."
    if comentario_user.strip():
        hist += f" Comentario: {comentario_user.strip()}"
    _insert_history(cur, management_id, hist, user)

    conn.commit()

    return {
        "status": "ok",
        "billing_id": billing_id,
        "new_disputed_amount": float(new_amount),
        "dispute_resolved": (resolved_status == "Resolved")
    }


# ============================================================
# POST /dispute-management/{management_id}/notes/xml
# Crear NC/ND ELECTRÓNICA (subir XML) desde Disputes
# ============================================================

@router.post("/{management_id}/notes/xml")
async def create_note_from_xml(
    management_id: int,
    tipo: str,
    moneda: str = "USD",
    user: str = "system",
    file: UploadFile = File(...),
    conn=Depends(get_db)
):
    """
    - tipo: NC | ND (se valida)
    - file: XML de nota electrónica
    - Se crea en Billing y se ajusta disputed_amount
    """

    if tipo not in ("NC", "ND"):
        raise HTTPException(400, "Tipo inválido (use NC o ND)")

    xml_bytes = await file.read()
    try:
        xml_text = xml_bytes.decode("utf-8", errors="ignore")
    except Exception:
        xml_text = str(xml_bytes)

    # 1) Extraer monto del XML (best-effort, ajustable a tu XML real)
    monto = None
    try:
        root = ET.fromstring(xml_text)

        # Heurística: busca nodos que contengan Total / Monto / TotalComprobante
        candidates = []
        for el in root.iter():
            tag = el.tag.lower()
            if any(k in tag for k in ["total", "monto", "totalcomprobante", "importe"]):
                if el.text:
                    candidates.append(el.text.strip())

        # Toma el último valor parseable
        for v in reversed(candidates):
            try:
                monto = float(v.replace(",", ""))
                if monto > 0:
                    break
            except Exception:
                continue

    except Exception:
        pass

    if monto is None:
        raise HTTPException(
            422,
            "No se pudo extraer el monto del XML. Ajuste el parser a su estructura real."
        )

    cur = conn.cursor(cursor_factory=RealDictCursor)
    ctx = _get_dispute_context(cur, management_id)

    # 2) Crear en Billing (obligatorio)
    billing_id = _crear_en_billing(
        cur,
        tipo=tipo,
        monto=monto,
        moneda=moneda,
        dispute_case=ctx["dispute_case"],
        numero_documento=ctx["numero_documento"],
        codigo_cliente=ctx["codigo_cliente"],
        nombre_cliente=ctx["nombre_cliente"],
        source=f"DISPUTE-XML:{file.filename}",
        xml_raw=xml_text  # si decides guardarlo, ajusta _crear_en_billing
    )

    # 3) Ajustar disputed_amount
    new_amount = _calc_new_disputed_amount(float(ctx["disputed_amount"]), tipo, float(monto))

    # 4) Cerrar si llega a 0
    new_amount, resolved_status = _close_if_zero(cur, management_id, new_amount)

    # 5) History
    _insert_history(
        cur,
        management_id,
        f"{tipo} XML creada (Billing ID {billing_id}) por {monto:.2f} {moneda}. File: {file.filename}",
        user
    )

    conn.commit()

    return {
        "status": "ok",
        "billing_id": billing_id,
        "xml_filename": file.filename,
        "extracted_amount": float(monto),
        "new_disputed_amount": float(new_amount),
        "dispute_resolved": (resolved_status == "Resolved")
    }
