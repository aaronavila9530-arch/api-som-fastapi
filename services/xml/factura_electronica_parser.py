import xml.etree.ElementTree as ET
from io import BytesIO

NS = {
    "fe": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
}

# ============================================================
# PARSER ORIGINAL (POR PATH – NO SE TOCA)
# ============================================================
def parse_factura_electronica(xml_path: str) -> dict:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer el XML desde path: {e}")

    return _parse_root(root)


# ============================================================
# NUEVO PARSER (PARA UploadFile / BYTES)
# ============================================================
def parse_factura_electronica_from_bytes(xml_bytes: bytes) -> dict:
    try:
        tree = ET.parse(BytesIO(xml_bytes))
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer el XML desde bytes: {e}")

    return _parse_root(root)


# ============================================================
# LÓGICA COMÚN (UNA SOLA FUENTE DE VERDAD)
# ============================================================
def _parse_root(root) -> dict:

    def get_text(path, default=None):
        el = root.find(path, NS)
        if el is None or el.text is None:
            return default
        return el.text.strip()

    def get_float(path, default=0.0):
        try:
            return float(get_text(path))
        except (TypeError, ValueError):
            return default

    fecha_raw = get_text("fe:FechaEmision")
    fecha_emision = fecha_raw[:10] if fecha_raw else None

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

        data["detalles"].append({
            "descripcion": line_text("fe:Detalle", ""),
            "cantidad": line_float("fe:Cantidad", 0),
            "precio_unitario": line_float("fe:PrecioUnitario", 0),
            "impuesto": line_float("fe:Impuesto/fe:Monto", 0),
            "total_linea": line_float("fe:MontoTotalLinea", 0)
        })

    return data
