from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date

from database import get_db

router = APIRouter(
    prefix="/accounting",
    tags=["Accounting"]
)


@router.post("/manual-entry")
def create_manual_entry(payload: dict, conn=Depends(get_db)):
    """
    payload:
    {
        entry_date,
        description,
        lines: [
            {account_code, account_name, debit, credit, line_description}
        ]
    }
    """

    lines = payload.get("lines", [])
    if not lines:
        raise HTTPException(400, "No accounting lines provided")

    total_debit = sum(l.get("debit", 0) for l in lines)
    total_credit = sum(l.get("credit", 0) for l in lines)

    if round(total_debit, 2) != round(total_credit, 2):
        raise HTTPException(400, "Entry does not balance")

    entry_date = date.fromisoformat(payload["entry_date"])
    period = entry_date.strftime("%Y-%m")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        INSERT INTO accounting_entries
        (entry_date, period, description, origin)
        VALUES (%s, %s, %s, 'MANUAL')
        RETURNING id
    """, (
        entry_date,
        period,
        payload.get("description")
    ))

    entry_id = cur.fetchone()["id"]

    for l in lines:
        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            entry_id,
            l["account_code"],
            l["account_name"],
            l.get("debit", 0),
            l.get("credit", 0),
            l.get("line_description")
        ))

    conn.commit()
    return {"status": "ok", "entry_id": entry_id}



@router.post("/reverse/{entry_id}")
def reverse_entry(entry_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Validar asiento original
    cur.execute("""
        SELECT *
        FROM accounting_entries
        WHERE id = %s
          AND COALESCE(reversed, FALSE) = FALSE
    """, (entry_id,))
    entry = cur.fetchone()

    if not entry:
        raise HTTPException(
            status_code=400,
            detail="El asiento no existe o ya fue revertido"
        )

    # 2️⃣ Traer líneas originales
    cur.execute("""
        SELECT *
        FROM accounting_lines
        WHERE entry_id = %s
    """, (entry_id,))
    lines = cur.fetchall()

    if not lines:
        raise HTTPException(400, "El asiento no tiene líneas")

    # 3️⃣ Crear asiento de reverso (NO marcado como reversed)
    cur.execute("""
        INSERT INTO accounting_entries
        (entry_date, period, description, origin, origin_id, reversed)
        VALUES (CURRENT_DATE, %s, %s, 'REVERSAL', %s, FALSE)
        RETURNING id
    """, (
        entry["period"],
        f"Asiento de reversa del asiento {entry_id}",
        entry_id
    ))
    reversal_id = cur.fetchone()["id"]

    # 4️⃣ Insertar líneas INVERTIDAS
    for l in lines:
        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            reversal_id,
            l["account_code"],
            l["account_name"],
            l["credit"],   # 👈 INVERTIDO
            l["debit"],    # 👈 INVERTIDO
            f"Reverso de línea {l['id']}"
        ))

    # 5️⃣ Marcar SOLO el original como revertido
    cur.execute("""
        UPDATE accounting_entries
        SET reversed = TRUE,
            reversal_entry_id = %s
        WHERE id = %s
    """, (reversal_id, entry_id))

    conn.commit()

    return {
        "status": "ok",
        "original_entry_id": entry_id,
        "reversal_entry_id": reversal_id
    }




# ============================================================
# CHART OF ACCOUNTS (Catalogo Contable)
# ============================================================
@router.get("/accounts")
def get_accounting_accounts(conn=Depends(get_db)):
    """
    Devuelve el catálogo contable desde accounting_ledger
    para uso en combobox (UI / Popup de ajustes)
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT DISTINCT
            account_code,
            account_name,
            account_type,
            account_level,
            parent_account
        FROM accounting_ledger
        WHERE account_code IS NOT NULL
        ORDER BY account_code
    """

    cur.execute(query)
    rows = cur.fetchall()

    return {
        "data": rows
    }


# ============================================================
# GET SINGLE ACCOUNTING ENTRY (FOR POPUP EDIT)
# ============================================================
@router.get("/entry/{entry_id}")
def get_accounting_entry(
    entry_id: int,
    conn=Depends(get_db)
):
    """
    Devuelve un asiento contable completo (cabecera + líneas)
    para edición en popup
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # --------------------------------------------------------
    # 1. Traer cabecera
    # --------------------------------------------------------
    cur.execute("""
        SELECT
            id AS entry_id,
            entry_date,
            period,
            description,
            origin,
            origin_id
        FROM accounting_entries
        WHERE id = %s
    """, (entry_id,))

    entry = cur.fetchone()

    if not entry:
        raise HTTPException(status_code=404, detail="Asiento no encontrado")

    # --------------------------------------------------------
    # 2. Traer líneas
    # --------------------------------------------------------
    cur.execute("""
        SELECT
            id AS line_id,
            account_code,
            account_name,
            debit,
            credit,
            line_description
        FROM accounting_lines
        WHERE entry_id = %s
        ORDER BY id
    """, (entry_id,))

    lines = cur.fetchall()

    # --------------------------------------------------------
    # 3. Respuesta final
    # --------------------------------------------------------
    return {
        "entry_id": entry["entry_id"],
        "entry_date": entry["entry_date"],
        "period": entry["period"],
        "description": entry["description"],
        "origin": entry["origin"],
        "origin_id": entry["origin_id"],
        "lines": [
            {
                "line_id": l["line_id"],
                "account_code": l["account_code"],
                "account_name": l["account_name"],
                "debit": float(l["debit"] or 0),
                "credit": float(l["credit"] or 0),
                "line_description": l["line_description"]
            }
            for l in lines
        ]
    }


# ============================================================
# UPDATE ACCOUNTING ENTRY (POPUP EDIT)
# ============================================================
@router.put("/entry/{entry_id}")
def update_accounting_entry(
    entry_id: int,
    payload: dict,
    conn=Depends(get_db)
):
    """
    Actualiza descripción del asiento y líneas contables.
    Valida partida doble.
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    description = payload.get("description")
    lines = payload.get("lines", [])

    if not lines:
        raise HTTPException(status_code=400, detail="No se enviaron líneas")

    # --------------------------------------------------------
    # 1. VALIDACIONES CONTABLES
    # --------------------------------------------------------
    total_debit = 0
    total_credit = 0

    for line in lines:
        debit = float(line.get("debit") or 0)
        credit = float(line.get("credit") or 0)

        if debit > 0 and credit > 0:
            raise HTTPException(
                status_code=400,
                detail="Una línea no puede tener Debe y Haber simultáneamente"
            )

        if debit < 0 or credit < 0:
            raise HTTPException(
                status_code=400,
                detail="Valores negativos no permitidos"
            )

        total_debit += debit
        total_credit += credit

    if round(total_debit, 2) != round(total_credit, 2):
        raise HTTPException(
            status_code=400,
            detail="La partida no está balanceada (Debe ≠ Haber)"
        )

    # --------------------------------------------------------
    # 2. VALIDAR QUE EL ASIENTO EXISTE
    # --------------------------------------------------------
    cur.execute(
        "SELECT id FROM accounting_entries WHERE id = %s",
        (entry_id,)
    )
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Asiento no encontrado")

    # --------------------------------------------------------
    # 3. ACTUALIZAR CABECERA
    # --------------------------------------------------------
    if description is not None:
        cur.execute("""
            UPDATE accounting_entries
            SET description = %s
            WHERE id = %s
        """, (description, entry_id))

    # --------------------------------------------------------
    # 4. ACTUALIZAR LÍNEAS
    # --------------------------------------------------------
    for line in lines:
        line_id = line.get("line_id")

        if not line_id:
            raise HTTPException(
                status_code=400,
                detail="line_id es obligatorio"
            )

        # validar cuenta contable
        cur.execute("""
            SELECT account_name
            FROM accounting_ledger
            WHERE account_code = %s
            LIMIT 1
        """, (line["account_code"],))

        acc = cur.fetchone()
        if not acc:
            raise HTTPException(
                status_code=400,
                detail=f"Cuenta contable inválida: {line['account_code']}"
            )

        cur.execute("""
            UPDATE accounting_lines
            SET
                account_code = %s,
                account_name = %s,
                debit = %s,
                credit = %s,
                line_description = %s
            WHERE id = %s
              AND entry_id = %s
        """, (
            line["account_code"],
            acc["account_name"],
            line.get("debit", 0),
            line.get("credit", 0),
            line.get("line_description"),
            line_id,
            entry_id
        ))

    conn.commit()

    return {
        "status": "ok",
        "message": "Asiento actualizado correctamente"
    }


@router.post("/sync/collections")
def sync_collections(conn=Depends(get_db)):
    from services.accounting_auto import sync_collections_to_accounting

    sync_collections_to_accounting(conn)

    return {
        "status": "ok",
        "message": "Collections sincronizadas con Accounting"
    }



@router.post("/sync/cash-app")
def sync_cash_app(conn=Depends(get_db)):
    try:
        from services.accounting_auto import sync_cash_app_to_accounting
        sync_cash_app_to_accounting(conn)

        return {
            "status": "ok",
            "message": "Cash App sincronizado a Accounting"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, repr(e))




@router.post("/sync/itp")
def sync_itp(conn=Depends(get_db)):
    try:
        from services.accounting_auto import sync_itp_to_accounting
        sync_itp_to_accounting(conn)

        return {
            "status": "ok",
            "message": "Invoice to Pay sincronizado a Accounting"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, repr(e))



@router.get("/ledger")
def get_accounting_ledger(
    period: str | None = None,
    origin: str | None = None,
    account_code: str | None = None,   # ✅ NUEVO FILTRO
    conn=Depends(get_db)
):
    """
    Devuelve asientos contables agrupados por entry_id,
    con sus líneas (debe / haber)

    Filtros soportados:
    - period (YYYY-MM)
    - origin (COLLECTIONS, ITP, CASH_APP, MANUAL, etc.)
    - account_code (1101, 2101, 5101, etc.)
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    conditions = []
    params = []

    # -----------------------------
    # VALIDACIONES
    # -----------------------------
    if origin and not period:
        raise HTTPException(
            status_code=400,
            detail="period es obligatorio cuando se filtra por origin"
        )

    # -----------------------------
    # FILTROS
    # -----------------------------
    if period:
        conditions.append("e.period = %s")
        params.append(period)

    if origin:
        conditions.append("e.origin = %s")
        params.append(origin)

    if account_code:
        conditions.append("l.account_code = %s")
        params.append(account_code)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # -----------------------------
    # QUERY PRINCIPAL
    # -----------------------------
    query = f"""
        SELECT
            e.id AS entry_id,
            e.entry_date,
            e.period,
            e.description AS entry_description,
            e.origin,
            e.origin_id,

            l.id AS line_id,
            l.account_code,
            l.account_name,
            l.debit,
            l.credit,
            l.line_description

        FROM accounting_entries e
        JOIN accounting_lines l ON l.entry_id = e.id
        {where_clause}
        ORDER BY
            e.entry_date DESC,
            e.id DESC,
            l.id ASC
    """

    cur.execute(query, params)
    rows = cur.fetchall()

    # -----------------------------
    # AGRUPAR POR entry_id
    # -----------------------------
    entries = {}

    for row in rows:
        entry_id = row["entry_id"]

        if entry_id not in entries:
            entries[entry_id] = {
                "entry_id": entry_id,
                "entry_date": row["entry_date"],
                "period": row["period"],
                "description": row["entry_description"],
                "origin": row["origin"],
                "origin_id": row["origin_id"],
                "lines": []
            }

        entries[entry_id]["lines"].append({
            "line_id": row["line_id"],
            "account_code": row["account_code"],
            "account_name": row["account_name"],
            "debit": float(row["debit"] or 0),
            "credit": float(row["credit"] or 0),
            "line_description": row["line_description"]
        })

    return {
        "data": list(entries.values())
    }



@router.get("/iva")
def get_accounting_iva(
    company_code: str,
    period: str,
    conn=Depends(get_db)
):
    """
    Calcula IVA del período (SAP-like):
    - IVA por pagar
    - IVA crédito fiscal
    - Arrastre de saldo a favor
    """

    if not conn:
        raise HTTPException(status_code=500, detail="No DB connection")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # -------------------------------------------------
        # 1️⃣ IVA DEL PERÍODO
        # -------------------------------------------------
        cur.execute("""
            SELECT
                SUM(
                    CASE
                        WHEN l.account_name ILIKE '%IVA por pagar%'
                        THEN COALESCE(l.credit, 0) - COALESCE(l.debit, 0)
                        ELSE 0
                    END
                ) AS iva_por_pagar,

                SUM(
                    CASE
                        WHEN l.account_name ILIKE '%IVA crédito%'
                        THEN COALESCE(l.debit, 0) - COALESCE(l.credit, 0)
                        ELSE 0
                    END
                ) AS iva_credito

            FROM accounting_lines l
            JOIN accounting_entries e ON e.id = l.entry_id
            WHERE e.company_code = %s
              AND e.period = %s
        """, (company_code, period))

        row = cur.fetchone() or {}

        iva_por_pagar = float(row.get("iva_por_pagar") or 0)
        iva_credito = float(row.get("iva_credito") or 0)

        # -------------------------------------------------
        # 2️⃣ SALDO A FAVOR DEL PERÍODO ANTERIOR
        # -------------------------------------------------
        cur.execute("""
            SELECT
                SUM(COALESCE(l.debit, 0) - COALESCE(l.credit, 0)) AS saldo_favor
            FROM accounting_lines l
            JOIN accounting_entries e ON e.id = l.entry_id
            WHERE e.company_code = %s
              AND e.period < %s
              AND l.account_name ILIKE '%IVA crédito%'
        """, (company_code, period))

        row_prev = cur.fetchone() or {}
        saldo_favor_anterior = float(row_prev.get("saldo_favor") or 0)

        # Solo se arrastra si hay saldo a favor
        if saldo_favor_anterior > 0:
            saldo_favor_anterior = saldo_favor_anterior
        else:
            saldo_favor_anterior = 0.0

        # -------------------------------------------------
        # 3️⃣ IVA FINAL A DECLARAR
        # -------------------------------------------------
        iva_total = iva_por_pagar - iva_credito - saldo_favor_anterior

        return {
            "company_code": company_code,
            "period": period,
            "iva_por_pagar": round(iva_por_pagar, 2),
            "iva_credito": round(iva_credito, 2),
            "saldo_favor_anterior": round(saldo_favor_anterior, 2),
            "iva_total": round(iva_total, 2)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

