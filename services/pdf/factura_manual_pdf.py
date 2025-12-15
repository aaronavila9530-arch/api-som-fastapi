from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from datetime import datetime
import os


# ============================================================
# Ruta base donde se almacenan las facturas
# ============================================================
BASE_PATH = os.path.join("backend_api", "storage", "facturas")


def generar_factura_manual_pdf(factura: dict, detalles: list) -> str:
    """
    Genera un PDF de factura manual.

    factura: dict (registro de la tabla factura)
    detalles: list[dict] (registros de factura_detalle)
    """

    # Asegurar directorio
    os.makedirs(BASE_PATH, exist_ok=True)

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

    # Fecha formateada
    fecha = factura.get("fecha_emision")
    if isinstance(fecha, datetime):
        fecha = fecha.strftime("%Y-%m-%d")

    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(1 * inch, y, f"Date: {fecha}")
    y -= 12
    c.drawString(1 * inch, y, f"Client: {factura.get('codigo_cliente', '')}")
    y -= 12
    c.drawString(
        1 * inch,
        y,
        f"Terms of payment: {factura.get('termino_pago', '')}"
    )

    # ================= TABLE HEADER =================
    y -= 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(1 * inch, y, "DESCRIPTION")
    c.drawRightString(7.5 * inch, y, "TOTAL")

    c.line(1 * inch, y - 2, 7.5 * inch, y - 2)

    # ================= DETAIL =================
    y -= 15
    c.setFont("Helvetica", 9)

    total = 0.0

    for d in detalles:
        descripcion = d.get("descripcion", "")
        total_linea = float(d.get("total_linea", 0))

        c.drawString(1 * inch, y, descripcion)
        c.drawRightString(
            7.5 * inch,
            y,
            f"$ {total_linea:,.2f}"
        )

        total += total_linea
        y -= 14

        # Salto de página si se acaba el espacio
        if y < 1.5 * inch:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 1 * inch

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
