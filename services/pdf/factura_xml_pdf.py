import os

def generar_factura_xml_pdf(data: dict) -> str:
    """
    Genera un PDF espejo SIMPLIFICADO para factura XML
    (stub inicial)
    """

    os.makedirs("/tmp/pdf", exist_ok=True)

    numero = data.get("numero_factura", "XML")
    path = f"/tmp/pdf/Factura_XML_{numero}.pdf"

    # PDF placeholder (luego lo mejoras)
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\n%Factura XML placeholder\n")

    return path
