from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from datetime import datetime
import os


BASE_PATH = "backend_api/storage/facturas"


def generar_factura_manual_pdf(factura, detalles):
    """
    factura: dict (tabla factura)
    detalles: list (tabla factura_detalle)
    """

    if not os.path.exists(BASE_PATH):
        os.makedirs(BASE_PATH)

    filename = f"FACTURA_{factura['id']}.pdf"
    filepath = os.path.join(BASE_PATH, filename)

    c = canvas.Canvas(filepath, pagesize=LETTER)
    width, height = LETTER

    y = height - 1 * inch

    # ================= HEADER =================
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "MARINE SURVEYORS AND LOGISTICS S.A.")
    y -= 14

    c.setFont("Helvetica", 9)
    c.drawString(1 * inch, y, "San José, Costa Rica")
    y -= 12
    c.drawString(1 * inch, y, "Tel: +506 8814-0784")

    # ================= FACTURA INFO =================
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, f"INVOICE Nº {factura['id']}")

    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(1 * inch, y, f"Date: {factura['fecha_emision']}")
    y -= 12
    c.drawString(1 * inch, y, f"Client: {factura['codigo_cliente']}")
    y -= 12
    c.drawString(1 * inch, y, f"Terms of payment: {factura.get('termino_pago', '')}")

    # ================= TABLE HEADER =================
    y -= 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(1 * inch, y, "DESCRIPTION")
    c.drawString(5.5 * inch, y, "TOTAL")

    c.line(1 * inch, y - 2, 7.5 * inch, y - 2)

    # ================= DETAIL =================
    y -= 15
    c.setFont("Helvetica", 9)

    total = 0

    for d in detalles:
        c.drawString(1 * inch, y, d["descripcion"])
        c.drawRightString(
            7.5 * inch,
            y,
            f"$ {d['total_linea']:,.2f}"
        )
        total += d["total_linea"]
        y -= 14

    # ================= TOTAL =================
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(7.5 * inch, y, f"TOTAL $ {total:,.2f}")

    # ================= FOOTER =================
    y -= 40
    c.setFont("Helvetica", 8)
    c.drawString(
        1 * inch,
        y,
        "Payments to be drawn on C.R. bank free of all charges / in U.S. dollars"
    )

    y -= 12
    c.drawString(
        1 * inch,
        y,
        "IBAN: CR49015201308000025850 - BCR Banco de Costa Rica"
    )

    c.showPage()
    c.save()

    return filepath
