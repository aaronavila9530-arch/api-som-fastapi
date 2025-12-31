from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any
from datetime import date, datetime
from calendar import monthrange
from typing import Dict
from fastapi import Depends
from security.auth import get_current_user


from database import get_db

router = APIRouter(
    prefix="/closing",
    tags=["Closing – Cierre Contable"]
)


@router.post("/period/close")
def close_period(payload: dict, conn=Depends(get_db)):
    required = ["company_code", "fiscal_year", "period", "ledger", "closed_by"]
    for f in required:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Intentar cerrar si existe
    cur.execute("""
        UPDATE closing_status
        SET period_closed = TRUE,
            closed_by = %s,
            updated_at = NOW()
        WHERE company_code = %s
          AND fiscal_year = %s
          AND period = %s
          AND ledger = %s
        RETURNING id
    """, (
        payload["closed_by"],
        payload["company_code"],
        payload["fiscal_year"],
        payload["period"],
        payload["ledger"]
    ))

    row = cur.fetchone()

    # 2️⃣ Si no existe, crearlo y cerrarlo
    if not row:
        cur.execute("""
            INSERT INTO closing_status (
                company_code,
                fiscal_year,
                period,
                ledger,
                period_closed,
                gl_closed,
                tb_closed,
                pnl_closed,
                equity_closed,
                fs_closed,
                fy_opened,
                closed_by,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s,
                TRUE,
                FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
                %s,
                NOW(), NOW()
            )
            RETURNING id
        """, (
            payload["company_code"],
            payload["fiscal_year"],
            payload["period"],
            payload["ledger"],
            payload["closed_by"]
        ))

    conn.commit()

    return {
        "status": "ok",
        "message": "Periodo cerrado correctamente"
    }


@router.post("/gl/preview")
def preview_gl_closing(payload: Dict[str, Any], conn=Depends(get_db)):
    required_fields = ["company_code", "fiscal_year", "period"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = int(payload["fiscal_year"])
    period = int(payload["period"])

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # --------------------------------------------------------
    # 1️⃣ Validar período cerrado (closing_status = fuente verdad)
    # --------------------------------------------------------
    cur.execute("""
        SELECT 1
        FROM closing_status
        WHERE company_code = %s
          AND fiscal_year = %s
          AND period = %s
          AND period_closed = TRUE
    """, (company, fiscal_year, period))

    if not cur.fetchone():
        raise HTTPException(
            400,
            "El período no está cerrado. No se puede generar preview."
        )

    # --------------------------------------------------------
    # 2️⃣ Calcular rango de fechas del período
    # --------------------------------------------------------
    start_date = date(fiscal_year, period, 1)
    end_day = monthrange(fiscal_year, period)[1]
    end_date = date(fiscal_year, period, end_day)

    # --------------------------------------------------------
    # 3️⃣ GL Preview desde accounting_lines (POR FECHA)
    # --------------------------------------------------------
    cur.execute("""
        SELECT
            l.account_code,
            l.account_name,
            SUM(l.debit)  AS debit,
            SUM(l.credit) AS credit,
            SUM(l.debit - l.credit) AS balance
        FROM accounting_lines l
        WHERE l.created_at::date BETWEEN %s AND %s
        GROUP BY l.account_code, l.account_name
        ORDER BY l.account_code
    """, (start_date, end_date))

    rows = cur.fetchall() or []

    # --------------------------------------------------------
    # 4️⃣ Respuesta segura
    # --------------------------------------------------------
    if not rows:
        return {
            "company_code": company,
            "fiscal_year": fiscal_year,
            "period": period,
            "totals": {
                "debit": 0.0,
                "credit": 0.0,
                "difference": 0.0
            },
            "is_balanced": True,
            "data": [],
            "message": "No existen movimientos contables para el período."
        }

    total_debit = sum(r["debit"] for r in rows)
    total_credit = sum(r["credit"] for r in rows)
    diff = round(total_debit - total_credit, 2)

    return {
        "company_code": company,
        "fiscal_year": fiscal_year,
        "period": period,
        "totals": {
            "debit": float(total_debit),
            "credit": float(total_credit),
            "difference": float(diff)
        },
        "is_balanced": diff == 0,
        "data": [
            {
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "debit": float(r["debit"]),
                "credit": float(r["credit"]),
                "balance": float(r["balance"])
            }
            for r in rows
        ]
    }
# ============================================================
# POST /closing/gl/post
# Postea el batch de cierre de Libro Mayor (GL_CLOSING)
# ============================================================

@router.post("/gl/post")
def post_gl_closing(payload: Dict, conn=Depends(get_db)):

    required_fields = ["company_code", "fiscal_year", "period", "posted_by"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = int(payload["fiscal_year"])
    period = int(payload["period"])
    posted_by = payload["posted_by"]
    ledger = payload.get("ledger", "0L")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Validar estado del período
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
            FOR UPDATE
        """, (company, fiscal_year, period, ledger))

        status = cur.fetchone()

        if not status or not status["period_closed"]:
            raise HTTPException(400, "El período no está cerrado.")

        if status["gl_closed"]:
            raise HTTPException(409, "El GL ya fue cerrado para este período.")

        # ----------------------------------------------------
        # 2️⃣ GL Snapshot (misma lógica que preview)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                l.account_code,
                l.account_name,
                SUM(l.debit)  AS debit,
                SUM(l.credit) AS credit,
                SUM(l.debit - l.credit) AS balance
            FROM accounting_lines l
            WHERE l.created_at::date <= (
                SELECT updated_at::date
                FROM closing_status
                WHERE company_code = %s
                  AND fiscal_year = %s
                  AND period = %s
                  AND ledger = %s
            )
            GROUP BY l.account_code, l.account_name
            ORDER BY l.account_code
        """, (company, fiscal_year, period, ledger))

        rows = cur.fetchall()

        if not rows:
            raise HTTPException(404, "No hay movimientos contables para cerrar.")

        total_debit = sum(r["debit"] or 0 for r in rows)
        total_credit = sum(r["credit"] or 0 for r in rows)

        if round(total_debit - total_credit, 2) != 0:
            raise HTTPException(400, "El Libro Mayor no cuadra.")

        # ----------------------------------------------------
        # 3️⃣ Crear batch GL_CLOSING
        # ----------------------------------------------------
        batch_code = f"GLCL-{fiscal_year}-{period:02d}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code,
                batch_type,
                company_code,
                fiscal_year,
                period,
                ledger,
                status,
                description,
                posted_at,
                posted_by
            )
            VALUES (%s, 'GL_CLOSING', %s, %s, %s, %s, 'POSTED',
                    %s, NOW(), %s)
            RETURNING id
        """, (
            batch_code,
            company,
            fiscal_year,
            period,
            ledger,
            f"Cierre Libro Mayor {fiscal_year}-{period:02d}",
            posted_by
        ))

        batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 4️⃣ Insertar líneas del batch
        # ----------------------------------------------------
        for r in rows:
            cur.execute("""
                INSERT INTO closing_batch_lines (
                    batch_id,
                    account_code,
                    account_name,
                    debit,
                    credit,
                    balance,
                    currency,
                    source_type,
                    source_reference
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'CRC', 'GL', NULL)
            """, (
                batch_id,
                r["account_code"],
                r["account_name"],
                r["debit"] or 0,
                r["credit"] or 0,
                r["balance"] or 0
            ))

        # ----------------------------------------------------
        # 5️⃣ Marcar GL como cerrado
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_status
            SET gl_closed = TRUE,
                last_batch_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (batch_id, status["id"]))

        conn.commit()

        return {
            "message": "Cierre de Libro Mayor posteado correctamente.",
            "batch_id": batch_id,
            "batch_code": batch_code,
            "company_code": company,
            "fiscal_year": fiscal_year,
            "period": period,
            "ledger": ledger
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error posteando GL: {e}")


# ============================================================
# POST /closing/batch/{batch_id}/reverse
# Reversa controlada de batch de cierre
# ============================================================

@router.post("/batch/{batch_id}/reverse")
def reverse_closing_batch(
    batch_id: int,
    payload: dict,
    conn=Depends(get_db)
):
    """
    Reversa un batch de cierre contable.

    Payload esperado:
    {
        reversed_by: "<usuario_logeado>",
        reason: "Motivo de la reversa"
    }
    """

    reversed_by = payload.get("reversed_by")
    if not reversed_by:
        raise HTTPException(
            status_code=400,
            detail="Missing field: reversed_by"
        )

    reason = payload.get(
        "reason",
        "Reversa solicitada por el usuario"
    )

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Obtener batch objetivo
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_batches
            WHERE id = %s
            FOR UPDATE
        """, (batch_id,))

        batch = cur.fetchone()

        if not batch:
            raise HTTPException(404, "Batch no encontrado.")

        if batch["status"] != "POSTED":
            raise HTTPException(
                status_code=409,
                detail="Solo se pueden reversar batches en estado POSTED."
            )

        # ----------------------------------------------------
        # 2️⃣ Verificar dependencias (hijos posteados)
        # ----------------------------------------------------
        cur.execute("""
            SELECT id, batch_code
            FROM closing_batches
            WHERE source_batch_id = %s
              AND status = 'POSTED'
        """, (batch_id,))

        dependents = cur.fetchall()

        if dependents:
            codes = ", ".join(d["batch_code"] for d in dependents)
            raise HTTPException(
                status_code=409,
                detail=(
                    "No se puede reversar. "
                    f"Existen batches dependientes posteados: {codes}"
                )
            )

        # ----------------------------------------------------
        # 3️⃣ Marcar batch como REVERSED
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_batches
            SET
                status = 'REVERSED',
                reversed_at = NOW(),
                reversed_by = %s,
                reverse_reason = %s
            WHERE id = %s
        """, (
            reversed_by,
            reason,
            batch_id
        ))

        # ----------------------------------------------------
        # 4️⃣ Rollback de flags en closing_status
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
            FOR UPDATE
        """, (
            batch["company_code"],
            batch["fiscal_year"],
            batch["period"],
            batch["ledger"]
        ))

        status = cur.fetchone()

        if not status:
            raise HTTPException(
                status_code=500,
                detail="Estado de cierre no encontrado."
            )

        flag_map = {
            "GL_CLOSING": "gl_closed",
            "TB_POST": "tb_closed",
            "CLOSE_PNL": "pnl_closed",
            "EQ_ADJ": "equity_closed",
            "FS_FINAL": "fs_closed",
            "OPEN_FY": "fy_opened"
        }

        flag = flag_map.get(batch["batch_type"])
        if not flag:
            raise HTTPException(
                status_code=500,
                detail=f"Batch type desconocido: {batch['batch_type']}"
            )

        cur.execute(f"""
            UPDATE closing_status
            SET
                {flag} = FALSE,
                last_batch_id = NULL,
                updated_at = NOW()
            WHERE id = %s
        """, (status["id"],))

        conn.commit()

        return {
            "message": "Batch reversado correctamente.",
            "batch_id": batch_id,
            "batch_code": batch["batch_code"],
            "batch_type": batch["batch_type"],
            "reversed_by": reversed_by
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al reversar batch de cierre: {e}"
        )




# ============================================================
# POST /closing/tb/preview
# Preview Balance de Comprobación (Trial Balance)
# ============================================================

@router.post("/tb/preview")
def preview_trial_balance(payload: dict, conn=Depends(get_db)):
    """
    Preview del Balance de Comprobación basado en el
    ÚLTIMO GL_CLOSING posteado.

    Payload esperado:
    {
        company_code: "MSL MARINE SURVEYORS AND LOGISTICS GROUP SRL",
        ledger: "0L"        # opcional
    }
    """

    company = payload.get("company_code")
    ledger = payload.get("ledger", "0L")

    if not company:
        raise HTTPException(400, "Missing field: company_code")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ----------------------------------------------------
    # 1️⃣ Obtener ÚLTIMO GL_CLOSING POSTED
    # ----------------------------------------------------
    cur.execute("""
        SELECT
            id,
            batch_code,
            fiscal_year,
            period,
            ledger
        FROM closing_batches
        WHERE company_code = %s
          AND ledger = %s
          AND batch_type = 'GL_CLOSING'
          AND status = 'POSTED'
        ORDER BY fiscal_year DESC, period DESC, posted_at DESC
        LIMIT 1
    """, (company, ledger))

    gl_batch = cur.fetchone()

    if not gl_batch:
        raise HTTPException(
            404,
            "No existe un cierre de Libro Mayor posteado."
        )

    # ----------------------------------------------------
    # 2️⃣ Obtener snapshot del batch (líneas por cuenta)
    # ----------------------------------------------------
    cur.execute("""
        SELECT
            account_code,
            account_name,
            debit,
            credit,
            balance
        FROM closing_batch_lines
        WHERE batch_id = %s
        ORDER BY account_code
    """, (gl_batch["id"],))

    rows = cur.fetchall()

    if not rows:
        raise HTTPException(
            500,
            "El batch de Libro Mayor no contiene líneas."
        )

    # ----------------------------------------------------
    # 3️⃣ Totales y validación
    # ----------------------------------------------------
    total_debit = sum(r["debit"] for r in rows)
    total_credit = sum(r["credit"] for r in rows)
    difference = round(total_debit - total_credit, 2)

    return {
        "source_batch": {
            "batch_id": gl_batch["id"],
            "batch_code": gl_batch["batch_code"],
            "batch_type": "GL_CLOSING"
        },

        "company_code": company,
        "fiscal_year": gl_batch["fiscal_year"],
        "period": gl_batch["period"],
        "ledger": gl_batch["ledger"],

        "totals": {
            "debit": float(total_debit),
            "credit": float(total_credit),
            "difference": float(difference)
        },

        "is_balanced": difference == 0,

        "data": [
            {
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "debit": float(r["debit"]),
                "credit": float(r["credit"]),
                "balance": float(r["balance"])
            }
            for r in rows
        ]
    }


# ============================================================
# POST /closing/tb/post
# Postea el batch de Balance de Comprobación (TB_POST)
# ============================================================

@router.post("/tb/post")
def post_trial_balance(
    payload: dict,
    conn=Depends(get_db)
):
    """
    Posteo del Balance de Comprobación (TB_POST)

    Payload esperado:
    {
        company_code: "MSL MARINE SURVEYORS AND LOGISTICS GROUP SRL",
        posted_by: "<usuario_logeado>"
    }
    """

    company = payload.get("company_code")
    posted_by = payload.get("posted_by")

    if not company:
        raise HTTPException(400, "Missing field: company_code")

    if not posted_by:
        raise HTTPException(400, "Missing field: posted_by")

    ledger = payload.get("ledger", "0L")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Obtener estado de cierre ACTIVO del periodo
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND ledger = %s
              AND gl_closed = TRUE
            ORDER BY fiscal_year DESC, period DESC
            LIMIT 1
            FOR UPDATE
        """, (company, ledger))

        status = cur.fetchone()

        if not status:
            raise HTTPException(
                404,
                "No existe un período con GL cerrado para postear TB."
            )

        if status["tb_closed"]:
            raise HTTPException(
                409,
                "El Balance de Comprobación ya fue posteado para este período."
            )

        fiscal_year = status["fiscal_year"]
        period = status["period"]

        # ----------------------------------------------------
        # 2️⃣ Obtener batch GL_CLOSING fuente
        # ----------------------------------------------------
        cur.execute("""
            SELECT id, batch_code
            FROM closing_batches
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
              AND batch_type = 'GL_CLOSING'
              AND status = 'POSTED'
            ORDER BY posted_at DESC
            LIMIT 1
        """, (company, fiscal_year, period, ledger))

        gl_batch = cur.fetchone()

        if not gl_batch:
            raise HTTPException(
                404,
                "No se encontró batch GL_CLOSING posteado para este período."
            )

        # ----------------------------------------------------
        # 3️⃣ Snapshot agregado del GL
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code,
                account_name,
                SUM(debit)   AS debit,
                SUM(credit)  AS credit,
                SUM(balance) AS balance,
                currency
            FROM closing_batch_lines
            WHERE batch_id = %s
            GROUP BY account_code, account_name, currency
            ORDER BY account_code
        """, (gl_batch["id"],))

        rows = cur.fetchall()

        if not rows or len(rows) < 3:
            raise HTTPException(
                500,
                "Snapshot del GL inválido o incompleto."
            )

        total_debit = sum(r["debit"] for r in rows)
        total_credit = sum(r["credit"] for r in rows)

        if round(total_debit - total_credit, 2) != 0:
            raise HTTPException(
                400,
                "El Balance de Comprobación no cuadra."
            )

        # ----------------------------------------------------
        # 4️⃣ Crear batch TB_POST
        # ----------------------------------------------------
        batch_code = f"TB-{fiscal_year}-{period:02d}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code,
                batch_type,
                company_code,
                fiscal_year,
                period,
                ledger,
                status,
                source_batch_id,
                description,
                posted_at,
                posted_by
            )
            VALUES (
                %s, 'TB_POST', %s, %s, %s, %s,
                'POSTED', %s, %s, NOW(), %s
            )
            RETURNING id
        """, (
            batch_code,
            company,
            fiscal_year,
            period,
            ledger,
            gl_batch["id"],
            f"Balance de Comprobación {fiscal_year}-{period:02d}",
            posted_by
        ))

        tb_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 5️⃣ Insertar líneas snapshot
        # ----------------------------------------------------
        for r in rows:
            cur.execute("""
                INSERT INTO closing_batch_lines (
                    batch_id,
                    account_code,
                    account_name,
                    debit,
                    credit,
                    balance,
                    currency,
                    source_type,
                    source_reference
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'TB', NULL)
            """, (
                tb_batch_id,
                r["account_code"],
                r["account_name"],
                r["debit"],
                r["credit"],
                r["balance"],
                r["currency"]
            ))

        # ----------------------------------------------------
        # 6️⃣ Actualizar closing_status
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_status
            SET
                tb_closed = TRUE,
                last_batch_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (tb_batch_id, status["id"]))

        conn.commit()

        return {
            "message": "Balance de Comprobación posteado correctamente.",
            "batch_id": tb_batch_id,
            "batch_code": batch_code,
            "company_code": company,
            "fiscal_year": fiscal_year,
            "period": period,
            "ledger": ledger
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error posteando Balance de Comprobación: {e}"
        )





# ============================================================
# POST /closing/pnl/post
# Cierre del Estado de Resultados (P&L → Patrimonio)
# ============================================================

@router.post("/pnl/post")
def post_pnl_closing(payload: dict, conn=Depends(get_db)):

    required_fields = [
        "company_code",
        "fiscal_year",
        "period",
        "posted_by",
        "equity_account_code",
        "equity_account_name"
    ]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = payload["fiscal_year"]
    period = payload["period"]
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

    equity_code = payload["equity_account_code"]
    equity_name = payload["equity_account_name"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Validar estado del cierre
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
            FOR UPDATE
        """, (company, fiscal_year, period, ledger))

        status = cur.fetchone()

        if not status or not status["tb_closed"]:
            raise HTTPException(
                400,
                "El Balance de Comprobación no está cerrado. No se puede cerrar P&L."
            )

        if status["pnl_closed"]:
            raise HTTPException(
                409,
                "El cierre de Resultados ya fue posteado para este período."
            )

        # ----------------------------------------------------
        # 2️⃣ Obtener batch TB_POST
        # ----------------------------------------------------
        cur.execute("""
            SELECT id
            FROM closing_batches
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
              AND batch_type = 'TB_POST'
              AND status = 'POSTED'
            ORDER BY posted_at DESC
            LIMIT 1
        """, (company, fiscal_year, period, ledger))

        tb_batch = cur.fetchone()
        if not tb_batch:
            raise HTTPException(404, "No se encontró batch TB_POST posteado.")

        # ----------------------------------------------------
        # 3️⃣ Obtener cuentas de resultados (4xxx / 5xxx)
        # ----------------------------------------------------
        cur.execute("""
            SELECT account_code, account_name, balance, currency
            FROM closing_batch_lines
            WHERE batch_id = %s
              AND (account_code LIKE '4%%' OR account_code LIKE '5%%')
              AND balance <> 0
        """, (tb_batch["id"],))

        pnl_accounts = cur.fetchall()
        if not pnl_accounts:
            raise HTTPException(400, "No existen cuentas de resultados con saldo.")

        # ----------------------------------------------------
        # 4️⃣ Calcular resultado neto
        # ----------------------------------------------------
        result_amount = sum(a["balance"] for a in pnl_accounts)

        # ----------------------------------------------------
        # 5️⃣ Crear batch CLOSE_PNL
        # ----------------------------------------------------
        batch_code = f"PNL-{fiscal_year}-{period:02d}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code, batch_type, company_code,
                fiscal_year, period, ledger,
                status, source_batch_id,
                description, posted_at, posted_by
            )
            VALUES (%s, 'CLOSE_PNL', %s, %s, %s, %s,
                    'POSTED', %s, %s, NOW(), %s)
            RETURNING id
        """, (
            batch_code, company, fiscal_year, period,
            ledger, tb_batch["id"],
            f"Cierre Estado de Resultados {fiscal_year}-{period:02d}",
            posted_by
        ))

        pnl_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 6️⃣ Cerrar cuentas P&L
        # ----------------------------------------------------
        for acc in pnl_accounts:
            debit = abs(acc["balance"]) if acc["balance"] < 0 else 0
            credit = acc["balance"] if acc["balance"] > 0 else 0

            cur.execute("""
                INSERT INTO closing_batch_lines (
                    batch_id, account_code, account_name,
                    debit, credit, balance,
                    currency, source_type, source_reference
                )
                VALUES (%s, %s, %s, %s, %s, 0, %s, 'PNL', 'CLOSE')
            """, (
                pnl_batch_id,
                acc["account_code"],
                acc["account_name"],
                debit,
                credit,
                acc["currency"]
            ))

        # ----------------------------------------------------
        # 7️⃣ Resultado contra Patrimonio
        # ----------------------------------------------------
        debit_eq = abs(result_amount) if result_amount < 0 else 0
        credit_eq = result_amount if result_amount > 0 else 0

        cur.execute("""
            INSERT INTO closing_batch_lines (
                batch_id, account_code, account_name,
                debit, credit, balance,
                currency, source_type, source_reference
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'PNL', 'RESULT')
        """, (
            pnl_batch_id,
            equity_code,
            equity_name,
            debit_eq,
            credit_eq,
            result_amount,
            pnl_accounts[0]["currency"]
        ))

        # ----------------------------------------------------
        # 8️⃣ Actualizar closing_status
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_status
            SET pnl_closed = TRUE,
                last_batch_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (pnl_batch_id, status["id"]))

        conn.commit()

        return {
            "message": "Cierre de Estado de Resultados posteado correctamente.",
            "batch_id": pnl_batch_id,
            "resultado_neto": float(result_amount)
        }

    except:
        conn.rollback()
        raise


# ============================================================
# POST /closing/fs/post
# Estados Financieros Finales (BLINDADO)
# - Corrige signo de pasivo/patrimonio (balances vienen negativos)
# - Valida existencia TB_POST
# - Opcional: incorpora efecto del CLOSE_PNL (RESULT) a patrimonio
# ============================================================

from fastapi import HTTPException, Depends
from psycopg2.extras import RealDictCursor
from datetime import datetime

@router.post("/fs/post")
def post_financial_statements(payload: dict, conn=Depends(get_db)):

    required_fields = ["company_code", "fiscal_year", "period", "posted_by"]
    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = int(payload["fiscal_year"])
    period = int(payload["period"])
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1) Validar estado de cierre (con lock)
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
            FOR UPDATE
        """, (company, fiscal_year, period, ledger))

        status = cur.fetchone()

        if not status:
            raise HTTPException(404, "No existe closing_status para ese período/ledger.")

        if not status.get("pnl_closed"):
            raise HTTPException(400, "El cierre de Resultados (P&L) no está completado.")

        if status.get("fs_closed"):
            raise HTTPException(409, "Los Estados Financieros ya fueron posteados.")

        # ----------------------------------------------------
        # 2) Obtener TB_POST (obligatorio)
        # ----------------------------------------------------
        cur.execute("""
            SELECT id, batch_code
            FROM closing_batches
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
              AND batch_type = 'TB_POST'
              AND status = 'POSTED'
            ORDER BY posted_at DESC
            LIMIT 1
        """, (company, fiscal_year, period, ledger))

        tb_batch = cur.fetchone()
        if not tb_batch:
            raise HTTPException(
                400,
                "No se encontró TB_POST posteado. No se pueden postear EEFF sin TB."
            )

        tb_batch_id = tb_batch["id"]

        # ----------------------------------------------------
        # 3) Calcular Activo / Pasivo / Patrimonio desde TB_POST
        #    IMPORTANTE:
        #    - balance = debit - credit
        #    - Activo (1xx) normalmente positivo
        #    - Pasivo (2xx) normalmente NEGATIVO -> se invierte a positivo
        #    - Patrimonio (3xx) normalmente NEGATIVO -> se invierte a positivo
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN account_code LIKE '1%%' THEN balance ELSE 0 END), 0) AS activos_signed,
                COALESCE(SUM(CASE WHEN account_code LIKE '2%%' THEN balance ELSE 0 END), 0) AS pasivos_signed,
                COALESCE(SUM(CASE WHEN account_code LIKE '3%%' THEN balance ELSE 0 END), 0) AS patrimonio_signed
            FROM closing_batch_lines
            WHERE batch_id = %s
        """, (tb_batch_id,))

        bg = cur.fetchone() or {}

        activos_signed = float(bg.get("activos_signed") or 0.0)
        pasivos_signed = float(bg.get("pasivos_signed") or 0.0)       # usualmente negativo
        patrimonio_signed = float(bg.get("patrimonio_signed") or 0.0) # usualmente negativo

        activos = activos_signed
        pasivos = -pasivos_signed
        patrimonio = -patrimonio_signed

        # ----------------------------------------------------
        # 4) (Opcional recomendado) Incorporar efecto del CLOSE_PNL a Patrimonio
        #    Tu línea RESULT en CLOSE_PNL puede tener 'balance' inconsistente.
        #    Por eso usamos (debit - credit) que es la contabilidad real.
        # ----------------------------------------------------
        cur.execute("""
            SELECT id
            FROM closing_batches
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period = %s
              AND ledger = %s
              AND batch_type = 'CLOSE_PNL'
              AND status = 'POSTED'
            ORDER BY posted_at DESC
            LIMIT 1
        """, (company, fiscal_year, period, ledger))

        pnl_batch = cur.fetchone()
        pnl_effect = 0.0

        if pnl_batch:
            cur.execute("""
                SELECT
                    COALESCE(SUM(debit - credit), 0) AS effect
                FROM closing_batch_lines
                WHERE batch_id = %s
                  AND source_type = 'PNL'
                  AND source_reference = 'RESULT'
            """, (pnl_batch["id"],))

            pnl_row = cur.fetchone() or {}
            pnl_effect = float(pnl_row.get("effect") or 0.0)

            # effect = debit-credit.
            # Si fue una ganancia, normalmente credit > debit => effect NEGATIVO.
            # Para patrimonio positivo, invertimos:
            patrimonio += (-pnl_effect)

        # ----------------------------------------------------
        # 5) Validación Balance General (con convención positiva)
        # ----------------------------------------------------
        diff = round(activos - (pasivos + patrimonio), 2)
        if diff != 0:
            raise HTTPException(
                400,
                f"El Balance General no cuadra. Activo={activos:.2f}, "
                f"Pasivo={pasivos:.2f}, Patrimonio={patrimonio:.2f}, Diff={diff:.2f}. "
                f"(TB_POST={tb_batch_id})"
            )

        # ----------------------------------------------------
        # 6) Crear batch FS_FINAL
        # ----------------------------------------------------
        batch_code = f"FS-{fiscal_year}-{period:02d}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code, batch_type, company_code,
                fiscal_year, period, ledger,
                status, source_batch_id,
                description, posted_at, posted_by
            )
            VALUES (%s, 'FS_FINAL', %s, %s, %s, %s,
                    'POSTED', %s, %s, NOW(), %s)
            RETURNING id
        """, (
            batch_code,
            company, fiscal_year, period, ledger,
            tb_batch_id,
            f"Estados Financieros Finales {fiscal_year}-{period:02d}",
            posted_by
        ))

        fs_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 7) Actualizar closing_status
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_status
            SET fs_closed = TRUE,
                last_batch_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (fs_batch_id, status["id"]))

        conn.commit()

        return {
            "message": "Estados Financieros Finales posteados correctamente.",
            "batch_id": fs_batch_id,
            "batch_code": batch_code,
            "source_tb_batch_id": tb_batch_id,
            "activo": float(round(activos, 2)),
            "pasivo": float(round(pasivos, 2)),
            "patrimonio": float(round(patrimonio, 2)),
            "pnl_effect_in_equity": float(round(pnl_effect, 2))
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error posteando EEFF: {e}")


# ============================================================
# POST /closing/fy/open
# Apertura automática de nuevo ejercicio fiscal (carryforward)
# ============================================================

@router.post("/fy/open")
def open_new_fiscal_year(
    payload: dict,
    conn=Depends(get_db),
    current_user=Depends(get_current_user)  # 👈 usuario logeado
):
    """
    Apertura automática de nuevo ejercicio fiscal.

    Payload esperado:
    {
        company_code: "MSL MARINE SURVEYORS AND LOGISTICS GROUP SRL",
        ledger: "0L"   # opcional
    }
    """

    company = payload.get("company_code")
    ledger = payload.get("ledger", "0L")

    if not company:
        raise HTTPException(400, "Missing field: company_code")

    posted_by = current_user["usuario"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Detectar último ejercicio cerrado (FS_FINAL)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                cb.id            AS fs_batch_id,
                cb.fiscal_year   AS source_year
            FROM closing_batches cb
            WHERE cb.company_code = %s
              AND cb.ledger = %s
              AND cb.batch_type = 'FS_FINAL'
              AND cb.status = 'POSTED'
            ORDER BY cb.fiscal_year DESC, cb.posted_at DESC
            LIMIT 1
            FOR UPDATE
        """, (company, ledger))

        fs = cur.fetchone()

        if not fs:
            raise HTTPException(
                400,
                "No existe un ejercicio fiscal cerrado (FS_FINAL)."
            )

        source_year = fs["source_year"]
        new_year = source_year + 1

        # ----------------------------------------------------
        # 2️⃣ Validar que el nuevo ejercicio no exista
        # ----------------------------------------------------
        cur.execute("""
            SELECT 1
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND ledger = %s
            LIMIT 1
        """, (company, new_year, ledger))

        if cur.fetchone():
            raise HTTPException(
                409,
                f"El ejercicio fiscal {new_year} ya existe."
            )

        # ----------------------------------------------------
        # 3️⃣ Crear batch OPEN_FY
        # ----------------------------------------------------
        batch_code = f"OPEN-{new_year}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code,
                batch_type,
                company_code,
                fiscal_year,
                period,
                ledger,
                status,
                source_batch_id,
                description,
                posted_at,
                posted_by
            )
            VALUES (
                %s, 'OPEN_FY', %s,
                %s, 1, %s,
                'POSTED', %s,
                %s, NOW(), %s
            )
            RETURNING id
        """, (
            batch_code,
            company,
            new_year,
            ledger,
            fs["fs_batch_id"],
            f"Apertura ejercicio fiscal {new_year}",
            posted_by
        ))

        open_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 4️⃣ Carryforward cuentas de balance (1,2,3)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code,
                account_name,
                balance,
                currency
            FROM closing_batch_lines
            WHERE batch_id = %s
              AND (
                    account_code LIKE '1%%'
                 OR account_code LIKE '2%%'
                 OR account_code LIKE '3%%'
              )
        """, (fs["fs_batch_id"],))

        for r in cur.fetchall():
            debit = r["balance"] if r["balance"] > 0 else 0
            credit = abs(r["balance"]) if r["balance"] < 0 else 0

            cur.execute("""
                INSERT INTO closing_batch_lines (
                    batch_id,
                    account_code,
                    account_name,
                    debit,
                    credit,
                    balance,
                    currency,
                    source_type,
                    source_reference
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, 'OPEN', 'CARRY'
                )
            """, (
                open_batch_id,
                r["account_code"],
                r["account_name"],
                debit,
                credit,
                r["balance"],
                r["currency"]
            ))

        # ----------------------------------------------------
        # 5️⃣ Crear closing_status del nuevo ejercicio
        # ----------------------------------------------------
        cur.execute("""
            INSERT INTO closing_status (
                company_code,
                fiscal_year,
                period,
                ledger,
                fy_opened,
                created_at,
                updated_at,
                closed_by
            )
            VALUES (%s, %s, 1, %s, TRUE, NOW(), NOW(), %s)
        """, (
            company,
            new_year,
            ledger,
            posted_by
        ))

        conn.commit()

        return {
            "message": "Nuevo ejercicio fiscal abierto correctamente.",
            "batch_id": open_batch_id,
            "batch_code": batch_code,
            "source_fiscal_year": source_year,
            "new_fiscal_year": new_year,
            "opened_by": posted_by
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error abriendo ejercicio fiscal: {e}"
        )
