# ============================================================
# ACCOUNTING - REVERSE ENTRY
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date
from database import get_db

router = APIRouter(
    prefix="/accounting",
    tags=["Accounting"]
)


@router.post("/reverse/{entry_id}")
def reverse_accounting_entry(entry_id: int, conn=Depends(get_db)):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ====================================================
        # 1️⃣ VALIDAR ASIENTO ORIGINAL
        # ====================================================
        cur.execute("""
            SELECT *
            FROM accounting_entries
            WHERE id = %s
            LIMIT 1
        """, (entry_id,))
        entry = cur.fetchone()

        if not entry:
            raise HTTPException(404, "Asiento contable no encontrado")

        if entry.get("reversed") is True:
            raise HTTPException(
                400,
                f"El asiento {entry_id} ya fue reversado"
            )

        # ====================================================
        # 2️⃣ TRAER LÍNEAS DEL ASIENTO ORIGINAL
        # ====================================================
        cur.execute("""
            SELECT *
            FROM accounting_lines
            WHERE entry_id = %s
            ORDER BY id
        """, (entry_id,))
        lines = cur.fetchall()

        if not lines:
            raise HTTPException(
                400,
                "El asiento no tiene líneas contables"
            )

        # ====================================================
        # 3️⃣ CREAR NUEVO ASIENTO DE REVERSO
        # ====================================================
        reverse_description = f"Reverso asiento {entry_id}"
        today = date.today()
        period = today.strftime("%Y-%m")

        cur.execute("""
            INSERT INTO accounting_entries (
                entry_date,
                period,
                description,
                origin,
                origin_id,
                created_by
            )
            VALUES (%s, %s, %s, %s, %s, 'SYSTEM')
            RETURNING id
        """, (
            today,
            period,
            reverse_description,
            "REVERSAL",
            entry_id
        ))

        reverse_entry_id = cur.fetchone()["id"]

        # ====================================================
        # 4️⃣ CREAR LÍNEAS INVERTIDAS (DEBE ↔ HABER)
        # ====================================================
        for ln in lines:
            debit = float(ln.get("debit") or 0)
            credit = float(ln.get("credit") or 0)

            cur.execute("""
                INSERT INTO accounting_lines (
                    entry_id,
                    account_code,
                    account_name,
                    debit,
                    credit,
                    line_description
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                reverse_entry_id,
                ln["account_code"],
                ln["account_name"],
                credit,   # 🔁 INVERTIDO
                debit,    # 🔁 INVERTIDO
                reverse_description
            ))

        # ====================================================
        # 5️⃣ MARCAR ASIENTO ORIGINAL COMO REVERSADO
        # ====================================================
        cur.execute("""
            UPDATE accounting_entries
            SET reversed = TRUE,
                reversal_entry_id = %s
            WHERE id = %s
        """, (reverse_entry_id, entry_id))

        conn.commit()

        return {
            "status": "ok",
            "message": f"Asiento {entry_id} reversado correctamente",
            "reversal_entry_id": reverse_entry_id
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))

    finally:
        cur.close()
