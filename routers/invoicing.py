from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header
)
from psycopg2.extras import RealDictCursor
from datetime import date

from database import get_db
from rbac_service import has_permission


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
# POST /invoicing/emitir
# EMITE FACTURA Y GUARDA SNAPSHOT COMPLETO
# ============================================================
@router.post("/emitir")
def emitir_factura(
    payload: dict,
    conn=Depends(get_db)
):
    """
    payload esperado:
    {
        servicio_id,
        tipo_factura,
        numero_documento,
        moneda,
        total,
        termino_pago,
        descripcion
    }
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1️⃣ Obtener servicio
        cur.execute("""
            SELECT *
            FROM servicios
            WHERE consec = %s
        """, (payload["servicio_id"],))

        servicio = cur.fetchone()
        if not servicio:
            raise HTTPException(404, "Servicio no encontrado")

        # 2️⃣ Calcular periodo operación
        periodo = ""
        if servicio.get("fecha_inicio") and servicio.get("fecha_fin"):
            periodo = f"{servicio['fecha_inicio']} → {servicio['fecha_fin']}"

        # 3️⃣ INSERT SNAPSHOT EN INVOICING
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
                num_informe,
                termino_pago,
                buque_contenedor,
                operacion,
                periodo_operacion,
                descripcion_servicio
            ) VALUES (
                %(factura_id)s,
                %(tipo_factura)s,
                'FACTURA',
                %(numero_documento)s,
                %(codigo_cliente)s,
                %(nombre_cliente)s,
                NOW(),
                %(moneda)s,
                %(total)s,
                %(num_informe)s,
                %(termino_pago)s,
                %(buque_contenedor)s,
                %(operacion)s,
                %(periodo_operacion)s,
                %(descripcion_servicio)s
            )
            RETURNING id
        """, {
            "factura_id": servicio["consec"],
            "tipo_factura": payload["tipo_factura"],
            "numero_documento": payload["numero_documento"],
            "codigo_cliente": servicio["cliente"],
            "nombre_cliente": servicio["cliente"],
            "moneda": payload["moneda"],
            "total": payload["total"],
            "num_informe": servicio["num_informe"],
            "termino_pago": payload["termino_pago"],
            "buque_contenedor": servicio.get("buque_contenedor"),
            "operacion": servicio.get("operacion"),
            "periodo_operacion": periodo,
            "descripcion_servicio": payload.get("descripcion", "")
        })

        factura_id = cur.fetchone()["id"]

        # 4️⃣ Marcar servicio como facturado
        cur.execute("""
            UPDATE servicios
            SET factura = %s
            WHERE consec = %s
        """, (payload["numero_documento"], servicio["consec"]))

        conn.commit()

        return {
            "status": "ok",
            "factura_id": factura_id,
            "numero_documento": payload["numero_documento"]
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error emitiendo factura: {str(e)}")

    finally:
        cur.close()

# ============================================================
# POST /invoicing/anticipada
# FACTURA ANTICIPADA (NO LIGADA A SERVICIO)
# ============================================================
@router.post("/anticipada")
def emitir_factura_anticipada(
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
        termino_pago,
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
        # FACTURA ANTICIPADA MANUAL
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

            # ================= NÚMERO DE FACTURA =================
            cur.execute("""
                SELECT COALESCE(
                    MAX(numero_documento::int),
                    2200
                ) AS ultimo
                FROM invoicing
                WHERE tipo_documento = 'FACTURA'
            """)
            numero_factura = int(cur.fetchone()["ultimo"]) + 1

            fecha_emision = date.today()

            # ================= GENERAR PDF =================
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
                    'FACTURA',
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
                numero_factura,
                codigo_cliente,
                nombre_cliente,
                fecha_emision,
                moneda,
                total,
                pdf_path
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
        # FACTURA ANTICIPADA XML
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
                    created_at
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
                    NOW()
                )
            """, (
                data["numero_factura"],
                codigo_cliente,
                nombre_cliente,
                data["fecha_emision"],
                data["moneda"],
                data["total"]
            ))

            conn.commit()
            return {"status": "ok"}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            500,
            f"Error facturación anticipada: {str(e)}"
        )
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
        # NC XML
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
            """, (
                data["numero_factura"],
                codigo_cliente,
                nombre_cliente,
                data["fecha_emision"],
                data["moneda"],
                data["total"]
            ))

            conn.commit()
            return {"status": "ok"}

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

