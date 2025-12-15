import xml.etree.ElementTree as ET
from datetime import datetime


NS = {
    "fe": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
}


def parse_factura_electronica(xml_path: str) -> dict:
    """
    Parsea una Factura Electrónica de Costa Rica (v4.4)
    y devuelve un dict normalizado para Invoicing.
    """

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer el XML: {e}")

    def get_text(path, default=None):
        el = root.find(path, NS)
        if el is None or el.text is None:
            return default
        return el.text.strip()

    def get_float(path, default=0.0):
        val = get_text(path)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    # ================= CABECERA =================
    fecha_raw = get_text("fe:FechaEmision")
    fecha_emision = None
    if fecha_raw:
        try:
            fecha_emision = fecha_raw[:10]  # YYYY-MM-DD
        except Exception:
            fecha_emision = None

    data = {
        "clave_electronica": get_text("fe:Clave"),
        "numero_factura": get_text("fe:NumeroConsecutivo"),
        "fecha_emision": fecha_emision,
        "termino_pago": get_text("fe:PlazoCredito"),
        "moneda": get_text(
            "fe:ResumenFactura/fe:CodigoTipoMoneda/fe:CodigoMoneda",
            default="CRC"
        ),
        "total": get_float("fe:ResumenFactura/fe:TotalComprobante"),
        "detalles": []
    }

    # ================= DETALLES =================
    for linea in root.findall("fe:DetalleServicio/fe:LineaDetalle", NS):

        def line_text(path, default=None):
            el = linea.find(path, NS)
            if el is None or el.text is None:
                return default
            return el.text.strip()

        def line_float(path, default=0.0):
            try:
                return float(line_text(path))
            except (TypeError, ValueError):
                return default

        detalle = {
            "descripcion": line_text("fe:Detalle", ""),
            "cantidad": line_float("fe:Cantidad", 0),
            "precio_unitario": line_float("fe:PrecioUnitario", 0),
            "impuesto": line_float("fe:Impuesto/fe:Monto", 0),
            "total_linea": line_float("fe:MontoTotalLinea", 0)
        }

        data["detalles"].append(detalle)

    return data
