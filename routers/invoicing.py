from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header,
    Form,
    File,
    UploadFile
)
from psycopg2.extras import RealDictCursor
from datetime import date
from typing import Optional
import os
import requests

from database import get_db
from rbac_service import has_permission

from services.xml.electronic_documents_parser import (
    parse_electronic_document
)



router = APIRouter(
    prefix="/invoicing",
    tags=["Invoicing & Billing"]
)

# ============================================================
# RBAC GUARD
# ============================================================
def require_permission(module: str, action: str):
    def checker(
        x_user_role: str = Header(..., alias="X-User-Role")
    ):
        if not has_permission(x_user_role, module, action):
            raise HTTPException(
                status_code=403,
                detail="No autorizado"
            )
    return checker

# ============================================================
# GET /invoicing/facturables
# ============================================================
@router.get("/facturables")
def get_servicios_facturables(
    cliente: str = Query(..., min_length=1),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT
                s.consec,
                s.tipo,
                s.buque_contenedor,
                s.num_informe,
                s.detalle,
                s.cliente,
                s.continente,
                s.pais,
                s.puerto,
                s.operacion,
                s.fecha_inicio,
                s.hora_inicio,
                s.fecha_fin,
                s.hora_fin,
                s.demoras,
                s.duracion,
                s.factura
            FROM servicios s
            WHERE
                s.cliente = %s
                AND s.estado = 'Finalizado'
                AND s.num_informe IS NOT NULL
                AND s.factura IS NULL
            ORDER BY s.fecha_inicio
        """, (cliente,))

        data = cur.fetchall()

        return {
            "total": len(data),
            "data": data
        }

    finally:
        cur.close()


# ============================================================
# POST /invoicing/anticipada
# FACTURA ANTICIPADA (MANUAL / XML)
# ============================================================
@router.post("/anticipada")
def emitir_factura_anticipada(payload: dict, conn=Depends(get_db)):

    from datetime import date
    from psycopg2.extras import RealDictCursor

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        tipo = payload.get("tipo_factura")

        if tipo not in ("MANUAL", "XML"):
            raise HTTPException(400, "tipo_factura inválido")

        codigo_cliente = payload.get("codigo_cliente")
        nombre_cliente = payload.get("nombre_cliente")

        if not codigo_cliente or not nombre_cliente:
            raise HTTPException(400, "Cliente requerido")

        # ====================================================
        # FACTURA MANUAL ANTICIPADA
        # ====================================================
        if tipo == "MANUAL":

            descripcion = payload.get("descripcion")
            total = payload.get("total")

            if not descripcion:
                raise HTTPException(400, "Descripción requerida")

            try:
                total = float(total)
                if total <= 0:
                    raise ValueError
            except Exception:
                raise HTTPException(400, "Total inválido")

            moneda = payload.get("moneda", "USD")
            termino_pago = int(payload.get("termino_pago", 0))
            fecha_emision = date.today()

            # ====================================================
            # NUMERACIÓN CORRECTA
            # → SOLO FACTURAS MANUALES
            # → SI NO HAY REGISTROS → 2201
            # ====================================================
            cur.execute("""
                SELECT COALESCE(
                    MAX(numero_documento::int),
                    2200
                ) AS ultimo
                FROM invoicing
                WHERE
                    tipo_documento = 'FACTURA'
                    AND tipo_factura = 'MANUAL'
                    AND numero_documento ~ '^[0-9]+$'
            """)

            ultimo = cur.fetchone()["ultimo"]
            numero_factura = int(ultimo) + 1

            # ====================================================
            # GENERAR PDF (SNAPSHOT COMPLETO)
            # ====================================================
            from services.pdf.factura_manual_pdf import generar_factura_manual_pdf

            pdf_data = {
                "numero_factura": numero_factura,
                "fecha_factura": fecha_emision,
                "cliente": nombre_cliente,
                "buque": payload.get("buque"),
                "operacion": payload.get("operacion"),
                "num_informe": payload.get("num_informe"),
                "periodo": payload.get("periodo_operacion"),
                "descripcion": descripcion,
                "moneda": moneda,
                "termino_pago": termino_pago,
                "total": total
            }

            pdf_path = generar_factura_manual_pdf(pdf_data)

            # ====================================================
            # INSERT → SOLO CAMPOS EXISTENTES EN invoicing
            # ====================================================
            cur.execute("""
                INSERT INTO invoicing (
                    factura_id,
                    tipo_factura,
                    tipo_documento,
                    numero_documento,
                    codigo_cliente,
                    nombre_cliente,
                    fecha_emision,
                    moneda,
                    total,
                    estado,
                    pdf_path,
                    created_at,
                    num_informe,
                    termino_pago,
                    buque_contenedor,
                    operacion,
                    periodo_operacion,
                    descripcion_servicio
                )
                VALUES (
                    NULL,
                    'MANUAL',
                    'FACTURA',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'EMITIDA',
                    %s,
                    NOW(),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id
            """, (
                str(numero_factura),
                codigo_cliente,
                nombre_cliente,
                fecha_emision,
                moneda,
                total,
                pdf_path,
                payload.get("num_informe"),
                termino_pago,
                payload.get("buque"),
                payload.get("operacion"),
                payload.get("periodo_operacion"),
                descripcion
            ))

            factura_id = cur.fetchone()["id"]
            conn.commit()

            return {
                "status": "ok",
                "factura_id": factura_id,
                "numero_documento": numero_factura,
                "pdf_path": pdf_path
            }

        # ====================================================
        # FACTURA XML ANTICIPADA (SIN NUMERACIÓN MANUAL)
        # ====================================================
        else:

            xml_path = payload.get("xml_path")
            if not xml_path:
                raise HTTPException(400, "xml_path requerido")

            from services.factura_electronica_parser import parse_factura_electronica
            data = parse_factura_electronica(xml_path)

            cur.execute("""
                INSERT INTO invoicing (
                    factura_id,
                    tipo_factura,
                    tipo_documento,
                    numero_documento,
                    codigo_cliente,
                    nombre_cliente,
                    fecha_emision,
                    moneda,
                    total,
                    estado,
                    created_at,
                    num_informe,
                    termino_pago,
                    buque_contenedor,
                    operacion,
                    periodo_operacion,
                    descripcion_servicio
                )
                VALUES (
                    NULL,
                    'ELECTRONICA',
                    'FACTURA',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'EMITIDA',
                    NOW(),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                data["numero_factura"],   # STRING
                codigo_cliente,
                nombre_cliente,
                data["fecha_emision"],
                data["moneda"],
                data["total"],
                data.get("num_informe"),
                data.get("termino_pago"),
                data.get("buque"),
                data.get("operacion"),
                data.get("periodo_operacion"),
                "Factura electrónica cargada desde XML"
            ))

            conn.commit()
            return {"status": "ok"}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error facturación anticipada: {str(e)}")
    finally:
        cur.close()


# ============================================================
# POST /invoicing/nota-credito
# NOTA DE CRÉDITO INDEPENDIENTE (NO LIGADA A SERVICIO)
# ============================================================
@router.post("/nota-credito")
def emitir_nota_credito(
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado (MANUAL):
    {
        tipo_factura: "MANUAL",
        codigo_cliente,
        nombre_cliente,
        num_informe,
        buque,
        operacion,
        periodo_operacion,
        descripcion,
        moneda,
        total
    }

    payload esperado (XML):
    {
        tipo_factura: "XML",
        codigo_cliente,
        nombre_cliente,
        xml_path
    }
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        tipo = payload.get("tipo_factura")

        if tipo not in ("MANUAL", "XML"):
            raise HTTPException(400, "tipo_factura inválido")

        codigo_cliente = payload.get("codigo_cliente")
        nombre_cliente = payload.get("nombre_cliente")

        if not codigo_cliente or not nombre_cliente:
            raise HTTPException(400, "Cliente requerido")

        # ====================================================
        # NC MANUAL
        # ====================================================
        if tipo == "MANUAL":

            descripcion = payload.get("descripcion")
            total = payload.get("total")

            if not descripcion:
                raise HTTPException(400, "Descripción requerida")

            try:
                total = float(total)
                if total <= 0:
                    raise ValueError
            except Exception:
                raise HTTPException(400, "Total inválido")

            moneda = payload.get("moneda", "USD")

            # ================= NÚMERO NC =================
            cur.execute("""
                SELECT COALESCE(
                    MAX(numero_documento::int),
                    9000
                ) AS ultimo
                FROM invoicing
                WHERE tipo_documento = 'NOTA_CREDITO'
            """)
            numero_nc = int(cur.fetchone()["ultimo"]) + 1

            fecha_emision = date.today()

            # ================= GENERAR PDF =================
            from services.pdf.factura_manual_pdf import generar_factura_manual_pdf

            pdf_data = {
                "numero_factura": numero_nc,
                "fecha_factura": fecha_emision,
                "cliente": nombre_cliente,
                "buque": payload.get("buque"),
                "operacion": payload.get("operacion"),
                "num_informe": payload.get("num_informe"),
                "periodo": payload.get("periodo_operacion"),
                "descripcion": f"NOTA DE CRÉDITO\n{descripcion}",
                "moneda": moneda,
                "termino_pago": 0,
                "total": total
            }

            pdf_path = generar_factura_manual_pdf(pdf_data)

            # ================= INSERT INVOICING =================
            cur.execute("""
                INSERT INTO invoicing (
                    factura_id,
                    tipo_factura,
                    tipo_documento,
                    numero_documento,
                    codigo_cliente,
                    nombre_cliente,
                    fecha_emision,
                    moneda,
                    total,
                    estado,
                    pdf_path,
                    created_at
                )
                VALUES (
                    NULL,
                    'MANUAL',
                    'NOTA_CREDITO',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'EMITIDA',
                    %s,
                    NOW()
                )
                RETURNING id
            """, (
                numero_nc,
                codigo_cliente,
                nombre_cliente,
                fecha_emision,
                moneda,
                total,
                pdf_path
            ))

            nc_id = cur.fetchone()["id"]
            conn.commit()

            return {
                "status": "ok",
                "nota_credito_id": nc_id,
                "numero_documento": numero_nc,
                "pdf_path": pdf_path
            }

        # ====================================================
        # NC XML (NACIONAL / EXPORTACIÓN)
        # ====================================================
        else:

            xml_path = payload.get("xml_path")
            if not xml_path:
                raise HTTPException(400, "xml_path requerido")

            # ------------------------------------------------
            # Parse XML REAL (NC / NCE)
            # ------------------------------------------------
            data = parse_electronic_document(xml_path)

            # data esperado:
            # {
            #   "tipo_documento": "NC" | "NCE",
            #   "numero_documento": str,
            #   "fecha_emision": date,
            #   "moneda": str,
            #   "total": float
            # }

            tipo_documento = data.get("tipo_documento")

            if tipo_documento not in ("NC", "NCE"):
                raise HTTPException(
                    400,
                    "El XML no corresponde a una Nota de Crédito electrónica"
                )

            # ------------------------------------------------
            # Validaciones duras
            # ------------------------------------------------
            for field in ("numero_documento", "fecha_emision", "moneda", "total"):
                if not data.get(field):
                    raise HTTPException(
                        400,
                        f"XML inválido: falta {field}"
                    )

            try:
                total = float(data["total"])
                if total <= 0:
                    raise ValueError
            except Exception:
                raise HTTPException(400, "Total inválido en XML")

            # ------------------------------------------------
            # INSERT INVOICING
            # ------------------------------------------------
            cur.execute("""
                INSERT INTO invoicing (
                    factura_id,
                    tipo_factura,
                    tipo_documento,
                    numero_documento,
                    codigo_cliente,
                    nombre_cliente,
                    fecha_emision,
                    moneda,
                    total,
                    estado,
                    created_at
                )
                VALUES (
                    NULL,
                    'ELECTRONICA',
                    'NOTA_CREDITO',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'EMITIDA',
                    NOW()
                )
                RETURNING id
            """, (
                str(data["numero_documento"]),
                codigo_cliente,
                nombre_cliente,
                data["fecha_emision"],
                data["moneda"],
                total
            ))

            nc_id = cur.fetchone()["id"]
            conn.commit()

            return {
                "status": "ok",
                "nota_credito_id": nc_id,
                "numero_documento": data["numero_documento"],
                "tipo_xml": tipo_documento
            }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error emitiendo nota de crédito: {str(e)}"
        )
    finally:
        cur.close()

@router.post("/anticipada/xml")
def emitir_factura_anticipada_xml(
    codigo_cliente: str = Form(...),
    nombre_cliente: str = Form(...),
    file: UploadFile = File(...),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1️⃣ Validaciones
        if not file or not file.filename:
            raise HTTPException(400, "Archivo XML requerido")

        if not file.filename.lower().endswith(".xml"):
            raise HTTPException(400, "El archivo debe ser XML")

        # 2️⃣ Leer bytes
        xml_bytes = file.file.read()
        if not xml_bytes:
            raise HTTPException(400, "Archivo XML vacío")

        # 3️⃣ Parsear XML (RUTA REAL)
        from services.xml.factura_electronica_parser import (
            parse_factura_electronica_from_bytes
        )

        data = parse_factura_electronica_from_bytes(xml_bytes)

        # 4️⃣ Validar campos
        for field in ("numero_factura", "fecha_emision", "moneda", "total"):
            if not data.get(field):
                raise HTTPException(
                    400,
                    f"XML inválido: falta {field}"
                )

        # 5️⃣ Generar PDF (IMPORT CORRECTO)
        from services.pdf.factura_xml_pdf import generar_factura_xml_pdf

        pdf_path = generar_factura_xml_pdf({
            "numero_factura": data["numero_factura"],
            "fecha_emision": data["fecha_emision"],
            "nombre_cliente": nombre_cliente,
            "moneda": data["moneda"],
            "total": data["total"]
        })

        # 6️⃣ Insert DB
        cur.execute("""
            INSERT INTO invoicing (
                factura_id,
                tipo_factura,
                tipo_documento,
                numero_documento,
                codigo_cliente,
                nombre_cliente,
                fecha_emision,
                moneda,
                total,
                estado,
                pdf_path,
                created_at,
                descripcion_servicio
            )
            VALUES (
                NULL,
                'ELECTRONICA',
                'FACTURA',
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'EMITIDA',
                %s,
                NOW(),
                'Factura electrónica cargada desde XML'
            )
            RETURNING id
        """, (
            str(data["numero_factura"]),
            codigo_cliente,
            nombre_cliente,
            data["fecha_emision"],
            data["moneda"],
            float(data["total"]),
            pdf_path
        ))

        factura_id = cur.fetchone()["id"]
        conn.commit()

        return {
            "status": "ok",
            "factura_id": factura_id,
            "numero_documento": data["numero_factura"],
            "pdf_path": pdf_path
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error XML anticipada: {str(e)}"
        )

    finally:
        cur.close()
