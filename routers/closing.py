from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from typing import List, Dict, Any
from datetime import date
from calendar import monthrange

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
def post_gl_closing(payload: dict, conn=Depends(get_db)):
    """
    Posteo del cierre de Libro Mayor.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2025,
        period: 12,
        ledger: "0L",
        posted_by: "aaron.avila"
    }
    """

    required_fields = ["company_code", "fiscal_year", "period", "posted_by"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = payload["fiscal_year"]
    period = payload["period"]
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

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
            raise HTTPException(
                400,
                "El período no está cerrado. No se puede postear el cierre de Libro Mayor."
            )

        if status["gl_closed"]:
            raise HTTPException(
                409,
                "El cierre de Libro Mayor ya fue posteado para este período."
            )

        # ----------------------------------------------------
        # 2️⃣ Recalcular preview (fuente única de verdad)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code,
                account_name,
                SUM(debit)  AS debit,
                SUM(credit) AS credit,
                SUM(debit - credit) AS balance
            FROM accounting_ledger
            WHERE company_code = %s
              AND fiscal_year = %s
              AND period <= %s
              AND ledger = %s
            GROUP BY account_code, account_name
            ORDER BY account_code
        """, (company, fiscal_year, period, ledger))

        rows = cur.fetchall()

        if not rows:
            raise HTTPException(404, "No existen movimientos contables para postear.")

        total_debit = sum(r["debit"] for r in rows)
        total_credit = sum(r["credit"] for r in rows)

        if round(total_debit - total_credit, 2) != 0:
            raise HTTPException(
                400,
                "El Libro Mayor no cuadra. No se puede postear el cierre."
            )

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
            f"Cierre de Libro Mayor {fiscal_year}-{period:02d}",
            posted_by
        ))

        batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 4️⃣ Insertar líneas del batch (snapshot por cuenta)
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'GL', NULL)
            """, (
                batch_id,
                r["account_code"],
                r["account_name"],
                r["debit"],
                r["credit"],
                r["balance"],
                "CRC"   # o moneda sociedad si ya la tienes parametrizada
            ))

        # ----------------------------------------------------
        # 5️⃣ Actualizar closing_status
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
        raise HTTPException(500, f"Error posteando cierre de Libro Mayor: {e}")


# ============================================================
# POST /closing/batch/{id}/reverse
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
        reversed_by: "aaron.avila",
        reason: "Ajuste requerido en asientos"
    }
    """

    if "reversed_by" not in payload:
        raise HTTPException(400, "Missing field: reversed_by")

    reversed_by = payload["reversed_by"]
    reason = payload.get("reason", "Reversa solicitada por el usuario")

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
                409,
                "Solo se pueden reversar batches en estado POSTED."
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
                409,
                f"No se puede reversar. Existen batches dependientes posteados: {codes}"
            )

        # ----------------------------------------------------
        # 3️⃣ Marcar batch como REVERSED
        # ----------------------------------------------------
        cur.execute("""
            UPDATE closing_batches
            SET status = 'REVERSED',
                reversed_at = NOW(),
                reversed_by = %s,
                reverse_reason = %s
            WHERE id = %s
        """, (reversed_by, reason, batch_id))

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
            raise HTTPException(500, "Estado de cierre no encontrado.")

        # Mapa batch_type → flag a revertir
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
                500,
                f"Batch type desconocido: {batch['batch_type']}"
            )

        cur.execute(f"""
            UPDATE closing_status
            SET {flag} = FALSE,
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
            500,
            f"Error al reversar batch de cierre: {e}"
        )




# ============================================================
# POST /closing/tb/preview
# Preview Balance de Comprobación (Trial Balance)
# ============================================================

@router.post("/tb/preview")
def preview_trial_balance(payload: dict, conn=Depends(get_db)):
    """
    Preview del Balance de Comprobación basado en GL_CLOSING.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2025,
        period: 12,
        ledger: "0L"
    }
    """

    required_fields = ["company_code", "fiscal_year", "period"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = payload["fiscal_year"]
    period = payload["period"]
    ledger = payload.get("ledger", "0L")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ----------------------------------------------------
    # 1️⃣ Obtener batch GL_CLOSING POSTED
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
            "No existe un cierre de Libro Mayor posteado para este período."
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

    response = {
        "source_batch": {
            "batch_id": gl_batch["id"],
            "batch_code": gl_batch["batch_code"],
            "batch_type": "GL_CLOSING"
        },

        "company_code": company,
        "fiscal_year": fiscal_year,
        "period": period,
        "ledger": ledger,

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

    return response


# ============================================================
# POST /closing/tb/post
# Postea el batch de Balance de Comprobación (TB_POST)
# ============================================================

@router.post("/tb/post")
def post_trial_balance(payload: dict, conn=Depends(get_db)):
    """
    Posteo del Balance de Comprobación.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2025,
        period: 12,
        ledger: "0L",
        posted_by: "aaron.avila"
    }
    """

    required_fields = ["company_code", "fiscal_year", "period", "posted_by"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = payload["fiscal_year"]
    period = payload["period"]
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Validar estado de cierre
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

        if not status or not status["gl_closed"]:
            raise HTTPException(
                400,
                "El cierre de Libro Mayor no está posteado. No se puede postear TB."
            )

        if status["tb_closed"]:
            raise HTTPException(
                409,
                "El Balance de Comprobación ya fue posteado para este período."
            )

        # ----------------------------------------------------
        # 2️⃣ Obtener batch GL_CLOSING (fuente única)
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
                "No se encontró batch GL_CLOSING posteado."
            )

        # ----------------------------------------------------
        # 3️⃣ Leer snapshot del mayor (closing_batch_lines)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code,
                account_name,
                debit,
                credit,
                balance,
                currency
            FROM closing_batch_lines
            WHERE batch_id = %s
            ORDER BY account_code
        """, (gl_batch["id"],))

        rows = cur.fetchall()

        if not rows:
            raise HTTPException(
                500,
                "El batch GL_CLOSING no contiene líneas."
            )

        total_debit = sum(r["debit"] for r in rows)
        total_credit = sum(r["credit"] for r in rows)

        if round(total_debit - total_credit, 2) != 0:
            raise HTTPException(
                400,
                "El Balance de Comprobación no cuadra. No se puede postear."
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
            VALUES (%s, 'TB_POST', %s, %s, %s, %s, 'POSTED',
                    %s, %s, NOW(), %s)
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
        # 5️⃣ Insertar líneas TB (snapshot)
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
            SET tb_closed = TRUE,
                last_batch_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (tb_batch_id, status["id"]))

        conn.commit()

        return {
            "message": "Balance de Comprobación posteado correctamente.",
            "batch_id": tb_batch_id,
            "batch_code": batch_code,
            "source_gl_batch": gl_batch["batch_code"],
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
    """
    Cierre automático del Estado de Resultados.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2025,
        period: 12,
        ledger: "0L",
        equity_account_code: "3XXX-RESULTADO_EJERCICIO",
        equity_account_name: "Resultado del Ejercicio",
        posted_by: "aaron.avila"
    }
    """

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
        # 2️⃣ Obtener batch TB_POST (fuente única)
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
                404,
                "No se encontró batch TB_POST posteado."
            )

        # ----------------------------------------------------
        # 3️⃣ Obtener cuentas de resultados (4xxx / 5xxx)
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code,
                account_name,
                balance,
                currency
            FROM closing_batch_lines
            WHERE batch_id = %s
              AND (account_code LIKE '4%%' OR account_code LIKE '5%%')
              AND balance <> 0
            ORDER BY account_code
        """, (tb_batch["id"],))

        pnl_accounts = cur.fetchall()

        if not pnl_accounts:
            raise HTTPException(
                400,
                "No existen cuentas de resultados con saldo."
            )

        # ----------------------------------------------------
        # 4️⃣ Calcular resultado neto
        # ----------------------------------------------------
        result_amount = sum(a["balance"] for a in pnl_accounts)
        # Resultado positivo = utilidad, negativo = pérdida

        # ----------------------------------------------------
        # 5️⃣ Crear batch CLOSE_PNL
        # ----------------------------------------------------
        batch_code = f"PNL-{fiscal_year}-{period:02d}-{int(datetime.utcnow().timestamp())}"

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
            VALUES (%s, 'CLOSE_PNL', %s, %s, %s, %s, 'POSTED',
                    %s, %s, NOW(), %s)
            RETURNING id
        """, (
            batch_code,
            company,
            fiscal_year,
            period,
            ledger,
            tb_batch["id"],
            f"Cierre Estado de Resultados {fiscal_year}-{period:02d}",
            posted_by
        ))

        pnl_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 6️⃣ Insertar líneas de cierre (cuentas P&L → 0)
        # ----------------------------------------------------
        for acc in pnl_accounts:
            debit = abs(acc["balance"]) if acc["balance"] < 0 else 0
            credit = acc["balance"] if acc["balance"] > 0 else 0

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
        # 7️⃣ Línea contra Patrimonio (resultado neto)
        # ----------------------------------------------------
        debit_eq = result_amount if result_amount < 0 else 0
        credit_eq = result_amount if result_amount > 0 else 0

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
            "batch_code": batch_code,
            "resultado_neto": float(result_amount),
            "equity_account": equity_code,
            "company_code": company,
            "fiscal_year": fiscal_year,
            "period": period
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error posteando cierre de Resultados: {e}"
        )


# ============================================================
# POST /closing/fs/post
# Postea Estados Financieros Finales (Balance General)
# ============================================================

@router.post("/fs/post")
def post_financial_statements(payload: dict, conn=Depends(get_db)):
    """
    Posteo de Estados Financieros Finales.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2025,
        period: 12,
        ledger: "0L",
        posted_by: "aaron.avila"
    }
    """

    required_fields = ["company_code", "fiscal_year", "period", "posted_by"]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    fiscal_year = payload["fiscal_year"]
    period = payload["period"]
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Validar estado
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

        if not status or not status["pnl_closed"]:
            raise HTTPException(
                400,
                "El cierre de Resultados no está completado."
            )

        if status["fs_closed"]:
            raise HTTPException(
                409,
                "Los Estados Financieros ya fueron posteados."
            )

        # ----------------------------------------------------
        # 2️⃣ Obtener último TB_POST
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
            raise HTTPException(404, "TB_POST no encontrado.")

        # ----------------------------------------------------
        # 3️⃣ Calcular Balance General
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                SUM(CASE WHEN account_code LIKE '1%%' THEN balance ELSE 0 END) AS activos,
                SUM(CASE WHEN account_code LIKE '2%%' THEN balance ELSE 0 END) AS pasivos,
                SUM(CASE WHEN account_code LIKE '3%%' THEN balance ELSE 0 END) AS patrimonio
            FROM closing_batch_lines
            WHERE batch_id = %s
        """, (tb_batch["id"],))

        bg = cur.fetchone()

        activos = bg["activos"] or 0
        pasivos = bg["pasivos"] or 0
        patrimonio = bg["patrimonio"] or 0

        if round(activos - (pasivos + patrimonio), 2) != 0:
            raise HTTPException(
                400,
                "El Balance General no cuadra (Activo ≠ Pasivo + Patrimonio)."
            )

        # ----------------------------------------------------
        # 4️⃣ Crear batch FS_FINAL
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
            company,
            fiscal_year,
            period,
            ledger,
            tb_batch["id"],
            f"Estados Financieros Finales {fiscal_year}",
            posted_by
        ))

        fs_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 5️⃣ Actualizar closing_status
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
            "activo": float(activos),
            "pasivo": float(pasivos),
            "patrimonio": float(patrimonio)
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error posteando EEFF: {e}")


# ============================================================
# POST /closing/fy/open
# Apertura de nuevo ejercicio fiscal (carryforward)
# ============================================================

@router.post("/fy/open")
def open_new_fiscal_year(payload: dict, conn=Depends(get_db)):
    """
    Apertura de nuevo ejercicio fiscal.

    Payload esperado:
    {
        company_code: "MSL-CR",
        fiscal_year: 2026,
        source_fiscal_year: 2025,
        ledger: "0L",
        posted_by: "aaron.avila"
    }
    """

    required_fields = [
        "company_code",
        "fiscal_year",
        "source_fiscal_year",
        "posted_by"
    ]

    for f in required_fields:
        if f not in payload:
            raise HTTPException(400, f"Missing field: {f}")

    company = payload["company_code"]
    new_year = payload["fiscal_year"]
    source_year = payload["source_fiscal_year"]
    ledger = payload.get("ledger", "0L")
    posted_by = payload["posted_by"]

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ----------------------------------------------------
        # 1️⃣ Validar cierre previo
        # ----------------------------------------------------
        cur.execute("""
            SELECT *
            FROM closing_status
            WHERE company_code = %s
              AND fiscal_year = %s
              AND ledger = %s
            ORDER BY period DESC
            LIMIT 1
            FOR UPDATE
        """, (company, source_year, ledger))

        status = cur.fetchone()

        if not status or not status["fs_closed"]:
            raise HTTPException(
                400,
                "Estados Financieros no están cerrados. No se puede abrir nuevo ejercicio."
            )

        # ----------------------------------------------------
        # 2️⃣ Obtener FS_FINAL
        # ----------------------------------------------------
        cur.execute("""
            SELECT id
            FROM closing_batches
            WHERE company_code = %s
              AND fiscal_year = %s
              AND batch_type = 'FS_FINAL'
              AND status = 'POSTED'
            ORDER BY posted_at DESC
            LIMIT 1
        """, (company, source_year))

        fs_batch = cur.fetchone()

        if not fs_batch:
            raise HTTPException(404, "FS_FINAL no encontrado.")

        # ----------------------------------------------------
        # 3️⃣ Crear batch OPEN_FY
        # ----------------------------------------------------
        batch_code = f"OPEN-{new_year}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
            INSERT INTO closing_batches (
                batch_code, batch_type, company_code,
                fiscal_year, period, ledger,
                status, source_batch_id,
                description, posted_at, posted_by
            )
            VALUES (%s, 'OPEN_FY', %s, %s, 1, %s,
                    'POSTED', %s, %s, NOW(), %s)
            RETURNING id
        """, (
            batch_code,
            company,
            new_year,
            ledger,
            fs_batch["id"],
            f"Apertura ejercicio {new_year}",
            posted_by
        ))

        open_batch_id = cur.fetchone()["id"]

        # ----------------------------------------------------
        # 4️⃣ Carryforward cuentas balance
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                account_code, account_name, balance, currency
            FROM closing_batch_lines
            WHERE batch_id = %s
              AND (account_code LIKE '1%%'
               OR account_code LIKE '2%%'
               OR account_code LIKE '3%%')
        """, (fs_batch["id"],))

        for r in cur.fetchall():
            cur.execute("""
                INSERT INTO closing_batch_lines (
                    batch_id, account_code, account_name,
                    debit, credit, balance,
                    currency, source_type, source_reference
                )
                VALUES (%s, %s, %s,
                        %s, %s, %s,
                        %s, 'OPEN', 'CARRY')
            """, (
                open_batch_id,
                r["account_code"],
                r["account_name"],
                r["balance"] if r["balance"] > 0 else 0,
                abs(r["balance"]) if r["balance"] < 0 else 0,
                r["balance"],
                r["currency"]
            ))

        conn.commit()

        return {
            "message": "Nuevo ejercicio fiscal abierto correctamente.",
            "batch_id": open_batch_id,
            "batch_code": batch_code,
            "new_fiscal_year": new_year
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error abriendo ejercicio fiscal: {e}")