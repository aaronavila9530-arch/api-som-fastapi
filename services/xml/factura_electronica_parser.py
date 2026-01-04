import xml.etree.ElementTree as ET
from io import BytesIO


# ============================================================
# PARSER DESDE PATH
# ============================================================
def parse_factura_electronica(xml_path: str) -> dict:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer el XML desde path: {e}")

    return _parse_root(root)


# ============================================================
# PARSER DESDE BYTES
# ============================================================
def parse_factura_electronica_from_bytes(xml_bytes: bytes) -> dict:
    try:
        tree = ET.parse(BytesIO(xml_bytes))
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer el XML desde bytes: {e}")

    return _parse_root(root)


# ============================================================
# LÓGICA ÚNICA – FE + FEE (SIN NAMESPACE FRÁGIL)
# ============================================================
def _parse_root(root) -> dict:

    # --------------------------------------------------------
    # Tipo documento
    # --------------------------------------------------------
    tag = root.tag.lower()
    if "facturaelectronicaexportacion" in tag:
        tipo_xml = "FEE"
    elif "facturaelectronica" in tag:
        tipo_xml = "FE"
    else:
        raise ValueError("XML no es FE ni FEE")

    # --------------------------------------------------------
    # Helpers robustos (ignoran namespace)
    # --------------------------------------------------------
    def get_text(tag_name, default=None):
        el = root.find(f".//{{*}}{tag_name}")
        if el is None or el.text is None:
            return default
        return el.text.strip()

    def get_float(tag_name, default=0.0):
        try:
            return float(get_text(tag_name))
        except (TypeError, ValueError):
            return default

    # --------------------------------------------------------
    # Campos principales (FE + FEE)
    # --------------------------------------------------------
    fecha_raw = get_text("FechaEmision")
    fecha_emision = fecha_raw[:10] if fecha_raw else None

    data = {
        "tipo_xml": tipo_xml,
        "clave_electronica": get_text("Clave"),
        "numero_factura": get_text("NumeroConsecutivo"),
        "fecha_emision": fecha_emision,
        "termino_pago": get_text("PlazoCredito") or get_text("CondicionVenta"),
        "moneda": get_text("CodigoMoneda", default="CRC"),
        "total": get_float("TotalComprobante"),
        "detalles": []
    }

    # --------------------------------------------------------
    # Detalle líneas (opcional, robusto)
    # --------------------------------------------------------
    for linea in root.findall(".//{*}LineaDetalle"):

        def line_text(tag_name, default=None):
            el = linea.find(f".//{{*}}{tag_name}")
            if el is None or el.text is None:
                return default
            return el.text.strip()

        def line_float(tag_name, default=0.0):
            try:
                return float(line_text(tag_name))
            except (TypeError, ValueError):
                return default

        data["detalles"].append({
            "descripcion": line_text("Detalle", ""),
            "cantidad": line_float("Cantidad", 0),
            "precio_unitario": line_float("PrecioUnitario", 0),
            "impuesto": line_float("Monto", 0),
            "total_linea": line_float("MontoTotalLinea", 0)
        })

    return data
