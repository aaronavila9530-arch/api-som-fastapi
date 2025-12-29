from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date

from database import get_db

router = APIRouter(
    prefix="/accounting",
    tags=["Accounting"]
)


@router.get("/ledger")
def get_accounting_ledger(
    period: str | None = None,
    origin: str | None = None,
    conn=Depends(get_db)
):
    """
    Devuelve asientos contables agrupados por entry_id,
    con sus líneas (debe / haber)
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    conditions = []
    params = []

    if origin and not period:
        raise HTTPException(
            status_code=400,
            detail="period es obligatorio cuando se filtra por origin"
        )

    if period:
        conditions.append("e.period = %s")
        params.append(period)

    if origin:
        conditions.append("e.origin = %s")
        params.append(origin)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

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
        ORDER BY e.entry_date DESC, e.id DESC, l.id ASC
    """

    cur.execute(query, params)
    rows = cur.fetchall()

    # ======================================================
    # AGRUPAR POR entry_id
    # ======================================================
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

    cur.execute(
        "SELECT * FROM accounting_entries WHERE id = %s AND reversed = FALSE",
        (entry_id,)
    )
    entry = cur.fetchone()
    if not entry:
        raise HTTPException(404, "Entry not found or already reversed")

    cur.execute(
        "SELECT * FROM accounting_lines WHERE entry_id = %s",
        (entry_id,)
    )
    lines = cur.fetchall()

    # Crear asiento inverso
    cur.execute("""
        INSERT INTO accounting_entries
        (entry_date, period, description, origin, reversed)
        VALUES (CURRENT_DATE, %s, %s, 'REVERSAL', TRUE)
        RETURNING id
    """, (
        entry["period"],
        f"Reversal of entry {entry_id}"
    ))

    reversal_id = cur.fetchone()["id"]

    for l in lines:
        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            reversal_id,
            l["account_code"],
            l["account_name"],
            l["credit"],
            l["debit"],
            f"Reversal of {l['id']}"
        ))

    cur.execute("""
        UPDATE accounting_entries
        SET reversed = TRUE,
            reversal_entry_id = %s
        WHERE id = %s
    """, (reversal_id, entry_id))

    conn.commit()
    return {"status": "reversed", "reversal_entry_id": reversal_id}




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
def sync_cash_app_to_accounting(conn=Depends(get_db)):

    from services.accounting_auto import create_accounting_entry
    from psycopg2.extras import RealDictCursor
    from datetime import date, datetime
    from fastapi import HTTPException

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ============================================================
        # 1️⃣ TRAER TODOS LOS PAGOS (CON O SIN ASIENTO)
        #    - Si NO existe asiento: crear
        #    - Si YA existe asiento: corregir (montos + comisión)
        # ============================================================
        cur.execute("""
            SELECT
                c.id,
                c.numero_documento,
                c.fecha_pago,
                c.monto_pagado,
                c.comision,
                a.id AS entry_id
            FROM cash_app c
            LEFT JOIN accounting_entries a
              ON a.origin = 'CASH_APP'
             AND a.origin_id = c.id
            ORDER BY c.id ASC
        """)

        pagos = cur.fetchall()
        creados = 0
        corregidos = 0

        # ============================================================
        # 2️⃣ PROCESAR UNO A UNO
        # ============================================================
        for p in pagos:
            cash_id = p["id"]
            numero = p.get("numero_documento") or ""
            fecha_pago = p.get("fecha_pago")
            entry_id = p.get("entry_id")

            if not fecha_pago:
                continue

            # fecha_pago puede venir datetime o date
            if isinstance(fecha_pago, datetime):
                tc_date = fecha_pago.date()
                entry_date = fecha_pago.date()
            else:
                tc_date = fecha_pago
                entry_date = fecha_pago

            # ---- Montos ----
            monto_raw = float(p.get("monto_pagado") or 0)
            comision_raw = float(p.get("comision") or 0)

            if monto_raw <= 0:
                continue

            if comision_raw < 0:
                comision_raw = abs(comision_raw)

            # ============================================================
            # 3️⃣ OBTENER TC SEGÚN FECHA DEL PAGO (NO HOY)
            # ============================================================
            cur.execute("""
                SELECT rate
                FROM exchange_rate
                WHERE rate_date = %s
                LIMIT 1
            """, (tc_date,))
            tc_row = cur.fetchone()

            if not tc_row:
                raise Exception(
                    f"Tipo de cambio no encontrado para la fecha {tc_date}. "
                    "Primero obtenga el TC del día en Accounting."
                )

            tc = float(tc_row["rate"])

            # ============================================================
            # 4️⃣ CONVERSIÓN A CRC (monto y comisión)
            # ============================================================
            monto_crc = round(monto_raw * tc, 2)
            comision_crc = round(comision_raw * tc, 2)
            banco_crc = round(monto_crc - comision_crc, 2)

            if banco_crc < 0:
                raise Exception(
                    f"Comisión mayor al monto en cash_app id={cash_id}. "
                    f"monto_pagado={monto_raw}, comision={comision_raw}"
                )

            period = entry_date.strftime("%Y-%m")
            detail = f"Pago factura {numero}"

            # ============================================================
            # 5️⃣ SI NO EXISTE ASIENTO → CREAR
            # ============================================================
            if not entry_id:
                lines = []

                # 1) Bancos (neto)
                if banco_crc > 0:
                    lines.append({
                        "account_code": "1010",
                        "account_name": "Bancos",
                        "debit": banco_crc,
                        "credit": 0,
                        "line_description": detail
                    })

                # 2) Comisión (si existe)
                if comision_crc > 0:
                    lines.append({
                        "account_code": "5203",  # ajusta si tu catálogo usa otro
                        "account_name": "Comisiones bancarias",
                        "debit": comision_crc,
                        "credit": 0,
                        "line_description": f"Comisión bancaria - {detail}"
                    })

                # 3) CxC (total pagado)
                lines.append({
                    "account_code": "1101",
                    "account_name": "Cuentas por cobrar",
                    "debit": 0,
                    "credit": monto_crc,
                    "line_description": detail
                })

                # Validación partida doble
                total_debit = round(sum(float(x.get("debit") or 0) for x in lines), 2)
                total_credit = round(sum(float(x.get("credit") or 0) for x in lines), 2)
                if abs(total_debit - total_credit) > 0.01:
                    raise Exception(
                        f"Asiento descuadrado CASH_APP id={cash_id}. "
                        f"Debe={total_debit} Haber={total_credit} "
                        f"(monto_crc={monto_crc}, comision_crc={comision_crc}, banco_crc={banco_crc})"
                    )

                create_accounting_entry(
                    conn=conn,
                    entry_date=entry_date,
                    period=period,
                    description=f"{detail} (TC {tc})",
                    origin="CASH_APP",
                    origin_id=cash_id,
                    lines=lines
                )

                creados += 1
                continue

            # ============================================================
            # 6️⃣ SI YA EXISTE → CORREGIR (montos + agregar/quitar comisión)
            # ============================================================

            # 6.1) Asegurar descripción y fecha/periodo en cabecera
            cur.execute("""
                UPDATE accounting_entries
                SET entry_date = %s,
                    period = %s,
                    description = %s
                WHERE id = %s
            """, (entry_date, period, f"{detail} (TC {tc})", entry_id))

            # 6.2) Traer líneas actuales
            cur.execute("""
                SELECT id, account_code, debit, credit, COALESCE(line_description,'') AS line_description
                FROM accounting_lines
                WHERE entry_id = %s
                ORDER BY id
            """, (entry_id,))
            existing_lines = cur.fetchall()

            # Helpers para localizar líneas
            def _find_line(code: str):
                for ln in existing_lines:
                    if str(ln.get("account_code")) == str(code):
                        return ln
                return None

            bank_line = _find_line("1010")
            ar_line = _find_line("1101")
            fee_line = _find_line("5203")

            # 6.3) Asegurar/crear línea Bancos (1010)
            if banco_crc > 0:
                if bank_line:
                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = %s, credit = 0,
                            account_name = %s,
                            line_description = %s
                        WHERE id = %s
                    """, (banco_crc, "Bancos", detail, bank_line["id"]))
                else:
                    cur.execute("""
                        INSERT INTO accounting_lines
                        (entry_id, account_code, account_name, debit, credit, line_description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (entry_id, "1010", "Bancos", banco_crc, 0, detail))
            else:
                # Si por alguna razón neto quedara 0, eliminar línea de banco si existiera
                if bank_line:
                    cur.execute("""
                        DELETE FROM accounting_lines
                        WHERE id = %s
                    """, (bank_line["id"],))

            # 6.4) Asegurar/crear línea CxC (1101) por el total pagado
            if ar_line:
                cur.execute("""
                    UPDATE accounting_lines
                    SET debit = 0, credit = %s,
                        account_name = %s,
                        line_description = %s
                    WHERE id = %s
                """, (monto_crc, "Cuentas por cobrar", detail, ar_line["id"]))
            else:
                cur.execute("""
                    INSERT INTO accounting_lines
                    (entry_id, account_code, account_name, debit, credit, line_description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (entry_id, "1101", "Cuentas por cobrar", 0, monto_crc, detail))

            # 6.5) Comisión: si comision_crc > 0 debe existir 5203, si no debe eliminarse
            if comision_crc > 0:
                fee_desc = f"Comisión bancaria - {detail}"
                if fee_line:
                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = %s, credit = 0,
                            account_name = %s,
                            line_description = %s
                        WHERE id = %s
                    """, (comision_crc, "Comisiones bancarias", fee_desc, fee_line["id"]))
                else:
                    cur.execute("""
                        INSERT INTO accounting_lines
                        (entry_id, account_code, account_name, debit, credit, line_description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (entry_id, "5203", "Comisiones bancarias", comision_crc, 0, fee_desc))
            else:
                # Si ya no hay comisión, borrar línea si existía (limpia históricos)
                if fee_line:
                    cur.execute("""
                        DELETE FROM accounting_lines
                        WHERE id = %s
                    """, (fee_line["id"],))

            # 6.6) Validación final de partida doble (re-leer totales)
            cur.execute("""
                SELECT
                    COALESCE(SUM(debit),0) AS total_debit,
                    COALESCE(SUM(credit),0) AS total_credit
                FROM accounting_lines
                WHERE entry_id = %s
            """, (entry_id,))
            sums = cur.fetchone() or {}
            td = round(float(sums.get("total_debit") or 0), 2)
            tc_sum = round(float(sums.get("total_credit") or 0), 2)

            if abs(td - tc_sum) > 0.01:
                raise Exception(
                    f"Asiento CASH_APP descuadrado luego de corrección. "
                    f"entry_id={entry_id} cash_id={cash_id} Debe={td} Haber={tc_sum} "
                    f"(monto_crc={monto_crc}, comision_crc={comision_crc}, banco_crc={banco_crc})"
                )

            corregidos += 1

        conn.commit()

        return {
            "status": "ok",
            "entries_created": creados,
            "entries_updated": corregidos
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))

    finally:
        cur.close()


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

