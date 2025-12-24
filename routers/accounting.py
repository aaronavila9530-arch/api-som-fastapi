from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date

from database import get_db

router = APIRouter(
    prefix="/accounting",
    tags=["Accounting"]
)


@router.get("/ledger")
def search_ledger(
    period: str | None = None,
    origin: str | None = None,
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    filters = []
    params = []

    if period:
        filters.append("e.period = %s")
        params.append(period)

    if origin:
        filters.append("e.origin = %s")
        params.append(origin)

    where = "WHERE " + " AND ".join(filters) if filters else ""

    sql = f"""
        SELECT
            e.id AS entry_id,
            e.entry_date,
            e.description,
            e.origin,
            e.origin_id,
            l.account_code,
            l.account_name,
            l.debit,
            l.credit,
            l.line_description
        FROM accounting_entries e
        JOIN accounting_lines l ON l.entry_id = e.id
        {where}
        ORDER BY e.entry_date DESC, e.id, l.id
    """

    cur.execute(sql, params)
    return {"data": cur.fetchall()}


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
