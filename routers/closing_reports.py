from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from psycopg2.extras import RealDictCursor
import os
import tempfile

from database import get_db
from reports.pdf_closing_report import generate_closing_batch_pdf

router = APIRouter(
    prefix="/closing/reports",
    tags=["Closing – Reports"]
)


@router.get("/batch/{batch_id}/pdf")
def download_closing_batch_pdf(batch_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # --------------------------------------------------
    # 1️⃣ Batch
    # --------------------------------------------------
    cur.execute("""
        SELECT *
        FROM closing_batches
        WHERE id = %s
          AND status = 'POSTED'
    """, (batch_id,))
    batch = cur.fetchone()

    if not batch:
        raise HTTPException(404, "Batch no encontrado o no posteado.")

    # --------------------------------------------------
    # 2️⃣ Líneas
    # --------------------------------------------------
    cur.execute("""
        SELECT *
        FROM closing_batch_lines
        WHERE batch_id = %s
        ORDER BY account_code
    """, (batch_id,))
    lines = cur.fetchall()

    if not lines:
        raise HTTPException(500, "Batch sin líneas.")

    # --------------------------------------------------
    # 3️⃣ Totales
    # --------------------------------------------------
    totals = {
        "debit": sum(l["debit"] for l in lines),
        "credit": sum(l["credit"] for l in lines),
        "balance": sum(l["balance"] for l in lines)
    }

    # --------------------------------------------------
    # 4️⃣ Header
    # --------------------------------------------------
    titles = {
        "GL_CLOSING": "Cierre de Libro Mayor",
        "TB_POST": "Balance de Comprobación",
        "CLOSE_PNL": "Cierre de Estado de Resultados",
        "FS_FINAL": "Estados Financieros Finales",
        "OPEN_FY": "Apertura de Ejercicio Fiscal"
    }

    header = {
        "title": titles.get(batch["batch_type"], "Cierre Contable"),
        "company": batch["company_code"],
        "fiscal_year": batch["fiscal_year"],
        "period": batch["period"],
        "ledger": batch["ledger"],
        "batch_code": batch["batch_code"],
        "posted_by": batch["posted_by"],
        "posted_at": batch["posted_at"].strftime("%d/%m/%Y %H:%M")
    }

    # --------------------------------------------------
    # 5️⃣ Generar PDF
    # --------------------------------------------------
    tmp_dir = tempfile.gettempdir()
    file_path = os.path.join(tmp_dir, f"{batch['batch_code']}.pdf")

    generate_closing_batch_pdf(
        file_path=file_path,
        header=header,
        lines=lines,
        totals=totals
    )

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"{batch['batch_code']}.pdf"
    )
