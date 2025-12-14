import xml.etree.ElementTree as ET


NS = {
    "fe": "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
}


def parse_factura_electronica(xml_path: str):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    def get(path):
        el = root.find(path, NS)
        return el.text if el is not None else None

    data = {
        "clave_electronica": get("fe:Clave"),
        "numero_factura": get("fe:NumeroConsecutivo"),
        "fecha_emision": get("fe:FechaEmision")[:10],
        "termino_pago": get("fe:PlazoCredito"),
        "moneda": get("fe:ResumenFactura/fe:CodigoTipoMoneda/fe:CodigoMoneda"),
        "total": float(get("fe:ResumenFactura/fe:TotalComprobante") or 0),
        "detalles": []
    }

    for linea in root.findall("fe:DetalleServicio/fe:LineaDetalle", NS):
        detalle = {
            "descripcion": linea.find("fe:Detalle", NS).text,
            "cantidad": float(linea.find("fe:Cantidad", NS).text),
            "precio_unitario": float(linea.find("fe:PrecioUnitario", NS).text),
            "impuesto": float(
                linea.find("fe:Impuesto/fe:Monto", NS).text
            ) if linea.find("fe:Impuesto/fe:Monto", NS) is not None else 0,
            "total_linea": float(linea.find("fe:MontoTotalLinea", NS).text)
        }
        data["detalles"].append(detalle)

    return data
