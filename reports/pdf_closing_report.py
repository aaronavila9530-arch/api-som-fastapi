from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib import colors
from datetime import datetime


def generate_closing_batch_pdf(
    file_path: str,
    header: dict,
    lines: list,
    totals: dict
):
    """
    Genera PDF oficial de cierre contable por batch.
    """

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    styles["Title"].alignment = TA_CENTER

    elements = []

    # --------------------------------------------------
    # Título
    # --------------------------------------------------
    elements.append(Paragraph(
        f"<b>{header['title']}</b>",
        styles["Title"]
    ))
    elements.append(Spacer(1, 12))

    # --------------------------------------------------
    # Info general
    # --------------------------------------------------
    info = f"""
    <b>Empresa:</b> {header['company']}<br/>
    <b>Ejercicio:</b> {header['fiscal_year']}<br/>
    <b>Período:</b> {header['period']}<br/>
    <b>Ledger:</b> {header['ledger']}<br/>
    <b>Batch:</b> {header['batch_code']}<br/>
    <b>Usuario:</b> {header['posted_by']}<br/>
    <b>Fecha:</b> {header['posted_at']}
    """
    elements.append(Paragraph(info, styles["Normal"]))
    elements.append(Spacer(1, 15))

    # --------------------------------------------------
    # Tabla contable
    # --------------------------------------------------
    table_data = [
        ["Cuenta", "Nombre", "Debe", "Haber", "Saldo"]
    ]

    for r in lines:
        table_data.append([
            r["account_code"],
            r["account_name"],
            f"{r['debit']:,.2f}",
            f"{r['credit']:,.2f}",
            f"{r['balance']:,.2f}"
        ])

    table_data.append([
        "TOTAL", "",
        f"{totals['debit']:,.2f}",
        f"{totals['credit']:,.2f}",
        f"{totals['balance']:,.2f}"
    ])

    table = Table(table_data, colWidths=[70, 180, 70, 70, 70])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 15))

    # --------------------------------------------------
    # Footer legal
    # --------------------------------------------------
    footer = (
        "Este documento fue generado automáticamente por el sistema ERP-SOM. "
        "Constituye evidencia contable del cierre correspondiente."
    )
    elements.append(Paragraph(footer, styles["Italic"]))

    doc.build(elements)
