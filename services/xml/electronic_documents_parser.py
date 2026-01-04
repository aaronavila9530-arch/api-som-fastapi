import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime


# ============================================================
# PARSER DESDE PATH
# ============================================================
def parse_electronic_document(xml_path: str) -> dict:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer XML: {e}")

    return _parse_root(root)


# ============================================================
# PARSER DESDE BYTES (UploadFile)
# ============================================================
def parse_electronic_document_from_bytes(xml_bytes: bytes) -> dict:
    try:
        tree = ET.parse(BytesIO(xml_bytes))
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"No se pudo leer XML: {e}")

    return _parse_root(root)


# ============================================================
# CORE PARSER – FE | FEE | NC | NCE
# ============================================================
def _parse_root(root) -> dict:

    tag = root.tag.lower()

    if "facturaelectronicaexportacion" in tag:
        tipo = "FEE"
    elif "facturaelectronica" in tag:
        tipo = "FE"
    elif "notacreditoelectronicaexportacion" in tag:
        tipo = "NCE"
    elif "notacreditoelectronica" in tag:
        tipo = "NC"
    else:
        raise ValueError("Documento electrónico no soportado")

    # --------------------------------------------------------
    # Helpers SIN namespace
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

    fecha_raw = get_text("FechaEmision")
    fecha_emision = None
    if fecha_raw:
        try:
            fecha_emision = datetime.fromisoformat(
                fecha_raw.replace("Z", "")
            ).date()
        except Exception:
            fecha_emision = fecha_raw[:10]

    data = {
        "tipo_documento": tipo,
        "clave_electronica": get_text("Clave"),
        "numero_documento": get_text("NumeroConsecutivo"),
        "fecha_emision": fecha_emision,
        "termino_pago": get_text("PlazoCredito") or get_text("CondicionVenta"),
        "moneda": get_text("CodigoMoneda", "CRC"),
        "total": get_float("TotalComprobante"),
        "detalles": []
    }

    for linea in root.findall(".//{*}LineaDetalle"):

        def lt(tag, default=None):
            el = linea.find(f".//{{*}}{tag}")
            if el is None or el.text is None:
                return default
            return el.text.strip()

        def lf(tag, default=0.0):
            try:
                return float(lt(tag))
            except (TypeError, ValueError):
                return default

        data["detalles"].append({
            "descripcion": lt("Detalle", ""),
            "cantidad": lf("Cantidad"),
            "precio_unitario": lf("PrecioUnitario"),
            "impuesto": lf("Monto"),
            "total_linea": lf("MontoTotalLinea")
        })

    return data
