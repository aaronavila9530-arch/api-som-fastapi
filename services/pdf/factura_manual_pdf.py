import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black
from reportlab.lib.units import cm
from datetime import datetime


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
BASE_DIR = os.path.join("backend_api", "storage", "pdf")
os.makedirs(BASE_DIR, exist_ok=True)

COLOR_PRINCIPAL = HexColor("#1F4E79")   # Azul corporativo
COLOR_GRIS = HexColor("#F2F2F2")


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def generar_factura_manual_pdf(data: dict) -> str:
    """
    data = {
        numero_factura,
        fecha_factura,
        cliente,
        buque,
        operacion,
        num_informe,
        periodo,
        descripcion,
        moneda,
        termino_pago,
        total
    }
    """

    nombre_pdf = f"Factura_{data['numero_factura']}.pdf"
    ruta_pdf = os.path.join(BASE_DIR, nombre_pdf)

    c = canvas.Canvas(ruta_pdf, pagesize=A4)
    width, height = A4

    # ========================================================
    # ENCABEZADO – EMISOR (1)
    # ========================================================
    c.setFillColor(COLOR_PRINCIPAL)
    c.rect(1.5 * cm, height - 3.5 * cm, width - 3 * cm, 2.5 * cm, fill=0)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, height - 2.2 * cm, "MSL MARINE SURVEYORS & LOGISTICS GROUP SRL")

    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, height - 2.9 * cm, "Cédula Jurídica: 3-102-XXXXXX")
    c.drawString(2 * cm, height - 3.4 * cm, "Correo: info@mslmarine.com | Tel: +506 XXXX-XXXX")

    # ========================================================
    # CLIENTE + FACTURA (2)
    # ========================================================
    y = height - 5 * cm

    c.setFillColor(COLOR_GRIS)
    c.rect(1.5 * cm, y, width - 3 * cm, 2.8 * cm, fill=1)
    c.setFillColor(black)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y + 2.1 * cm, f"FACTURA N° {data['numero_factura']}")
    c.drawString(2 * cm, y + 1.5 * cm, f"Cliente: {data['cliente']}")

    fecha = data["fecha_factura"]
    if isinstance(fecha, datetime):
        fecha = fecha.strftime("%d/%m/%Y")

    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, y + 0.9 * cm, f"Fecha factura: {fecha}")
    c.drawString(2 * cm, y + 0.3 * cm, f"N° Informe: {data['num_informe']}")

    # ========================================================
    # TÉRMINOS DE PAGO (3)
    # ========================================================
    y -= 2.2 * cm

    c.setFillColor(COLOR_GRIS)
    c.rect(1.5 * cm, y, width - 3 * cm, 1.5 * cm, fill=1)
    c.setFillColor(black)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y + 0.9 * cm, "Términos de pago")

    c.setFont("Helvetica", 9)
    c.drawString(
        2 * cm,
        y + 0.3 * cm,
        f"{data['termino_pago']} días | Moneda: {data['moneda']}"
    )

    # ========================================================
    # DESCRIPCIÓN (4)
    # ========================================================
    y -= 4.2 * cm

    c.setFillColor(COLOR_GRIS)
    c.rect(1.5 * cm, y, width - 3 * cm, 4 * cm, fill=1)
    c.setFillColor(black)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y + 3.2 * cm, "Descripción del servicio")

    c.setFont("Helvetica", 9)
    text = c.beginText(2 * cm, y + 2.6 * cm)
    text.textLine(f"Buque / Contenedor: {data['buque']}")
    text.textLine(f"Operación: {data['operacion']}")
    text.textLine(f"Periodo de operación: {data['periodo']}")
    text.textLine("")
    text.textLine(data["descripcion"])
    c.drawText(text)

    # ========================================================
    # TOTAL (5)
    # ========================================================
    y -= 2.2 * cm

    c.setFillColor(COLOR_PRINCIPAL)
    c.rect(1.5 * cm, y, width - 3 * cm, 1.5 * cm, fill=0)

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(
        width - 2 * cm,
        y + 0.5 * cm,
        f"TOTAL {data['moneda']} {float(data['total']):,.2f}"
    )

    # ========================================================
    # DATOS BANCARIOS (6)
    # ========================================================
    y -= 3.2 * cm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y + 1.8 * cm, "Datos bancarios")

    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, y + 1.2 * cm, "Banco: Banco Nacional de Costa Rica")
    c.drawString(2 * cm, y + 0.6 * cm, "IBAN: CR49015201308000025850")
    c.drawString(2 * cm, y, "SWIFT: BNCRCRSJ")

    # ========================================================
    # FOOTER
    # ========================================================
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(
        width / 2,
        1.2 * cm,
        "Este documento corresponde a una factura manual generada por ERP-SOM"
    )

    c.showPage()
    c.save()

    return ruta_pdf
