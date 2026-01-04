# backend_api/services/pdf/factura_preview_pdf.py

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime
import os


def generar_factura_preview_pdf(data: dict, output_path: str) -> str:
    """
    Genera un PDF simple de PREVIEW (NO fiscal).
    Retorna el path generado.
    """

    # ===============================
    # Validaciones mínimas
    # ===============================
    if not output_path:
        raise ValueError("output_path requerido")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    y = height - 20 * mm

    def draw(text):
        nonlocal y
        c.drawString(20 * mm, y, str(text))
        y -= 7 * mm

    # ===============================
    # HEADER
    # ===============================
    c.setFont("Helvetica-Bold", 14)
    draw("FACTURA ELECTRÓNICA – PREVIEW")
    y -= 5 * mm

    c.setFont("Helvetica", 9)
    draw("Documento NO fiscal – Solo para visualización")
    y -= 10 * mm

    # ===============================
    # DATOS PRINCIPALES
    # ===============================
    c.setFont("Helvetica", 10)

    draw(f"Número documento: {data.get('numero_documento', '-')}")
    draw(f"Fecha emisión: {data.get('fecha_emision', '-')}")
    draw(f"Cliente: {data.get('cliente', '-')}")
    draw(f"Buque / Contenedor: {data.get('buque_contenedor', '-')}")
    draw(f"Operación: {data.get('operacion', '-')}")
    draw(f"Periodo: {data.get('periodo', '-')}")
    y -= 5 * mm

    # ===============================
    # TOTALES
    # ===============================
    c.setFont("Helvetica-Bold", 11)
    draw(
        f"Total: {data.get('moneda', '')} "
        f"{data.get('total', 0)}"
    )

    y -= 10 * mm

    # ===============================
    # FOOTER
    # ===============================
    c.setFont("Helvetica", 8)
    draw(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    draw("ERP-SOM – Preview automático")

    c.showPage()
    c.save()

    return output_path
