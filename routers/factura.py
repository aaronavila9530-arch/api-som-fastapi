from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    UploadFile,
    File,
    Form,
    Query
)

from psycopg2.extras import RealDictCursor
from datetime import datetime
from fastapi.responses import FileResponse
import os
import uuid

from database import get_db
from rbac_service import has_permission

from services.xml.factura_electronica_parser import (
    parse_factura_electronica_from_bytes
)

from services.pdf.factura_preview_pdf import (
    generar_factura_preview_pdf
)

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
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
# OBTENER SIGUIENTE NÚMERO DE FACTURA (SEGURO CON RealDictCursor)
# ============================================================
def obtener_siguiente_numero_factura(cur):

    cur.execute("""
        SELECT COALESCE(
            MAX(numero_factura::int),
            2199
        ) AS ultimo
        FROM factura
        WHERE tipo_factura = 'MANUAL'
    """)

    row = cur.fetchone()

    if not row or row.get("ultimo") is None:
        return 2200

    return int(row["ultimo"]) + 1


# ============================================================
# CREAR FACTURA MANUAL
# ============================================================
@router.post("/manual")
def crear_factura_manual(payload: dict, conn=Depends(get_db)):

    try:
        from services.pdf.factura_manual_pdf import generar_factura_manual_pdf
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Módulo de generación de PDF no disponible"
        )

    cur = None

    try:
        servicio_id = payload.get("servicio_id")
        total = payload.get("total")

        if not servicio_id:
            raise HTTPException(status_code=400, detail="Servicio requerido")

        if total in (None, ""):
            raise HTTPException(status_code=400, detail="Total requerido")

        cur = conn.cursor(cursor_factory=RealDictCursor)


        # ====================================================
        # OBTENER SERVICIO
        # ====================================================
        cur.execute("""
            SELECT *
            FROM servicios
            WHERE consec = %s
        """, (servicio_id,))
        servicio = cur.fetchone()

        if not servicio:
            raise HTTPException(status_code=404, detail="Servicio no encontrado")

        if servicio.get("factura"):
            raise HTTPException(
                status_code=400,
                detail="Este servicio ya fue facturado"
            )

        # ====================================================
        # RESOLVER CÓDIGO DE CLIENTE DESDE NOMBRE
        # ====================================================
        cur.execute("""
            SELECT codigo
            FROM cliente  -- Modificado de 'clientes' a 'cliente'
            WHERE
                nombrecomercial = %s
                OR nombrejuridico = %s
        """, (
            servicio["cliente"],
            servicio["cliente"]
        ))

        cliente_row = cur.fetchone()

        if not cliente_row:
            raise HTTPException(
                status_code=400,
                detail="No se pudo resolver el código del cliente"
            )

        codigo_cliente = cliente_row["codigo"]

        # ====================================================
        # OBTENER TÉRMINO DE PAGO DESDE CLIENTE_CRÉDITO
        # ====================================================
        cur.execute("""
            SELECT termino_pago
            FROM cliente_credito
            WHERE codigo_cliente = %s
        """, (codigo_cliente,))

        credito = cur.fetchone()

        if not credito or credito.get("termino_pago") is None:
            raise HTTPException(
                status_code=400,
                detail="El cliente no tiene término de pago configurado"
            )

        termino_pago = int(credito["termino_pago"])

        # ====================================================
        # NÚMERO Y FECHA FACTURA
        # ====================================================
        numero_factura = obtener_siguiente_numero_factura(cur)
        fecha_factura = datetime.now()

        # ====================================================
        # INSERT FACTURA
        # ====================================================
        cur.execute("""
            INSERT INTO factura (
                tipo_factura,
                numero_factura,
                codigo_cliente,
                fecha_emision,
                termino_pago,
                moneda,
                total
            )
            VALUES (
                'MANUAL',
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        """, (
            numero_factura,
            codigo_cliente,
            fecha_factura,
            termino_pago,
            payload.get("moneda", "USD"),
            total
        ))

        factura_id = cur.fetchone()["id"]

        # ====================================================
        # DETALLE FACTURA
        # ====================================================
        cur.execute("""
            INSERT INTO factura_detalle (
                factura_id,
                descripcion,
                cantidad,
                precio_unitario,
                total_linea
            )
            VALUES (%s, %s, 1, %s, %s)
        """, (
            factura_id,
            payload.get("descripcion"),
            total,
            total
        ))

        # ====================================================
        # GENERAR PDF
        # ====================================================
        pdf_data = {
            "numero_factura": numero_factura,
            "fecha_factura": fecha_factura,
            "cliente": servicio["cliente"],  # nombre visible
            "buque": servicio["buque_contenedor"],
            "operacion": servicio["operacion"],
            "num_informe": servicio["num_informe"],
            "periodo": f"{servicio['fecha_inicio']} a {servicio['fecha_fin']}",
            "descripcion": payload.get("descripcion"),
            "moneda": payload.get("moneda", "USD"),
            "termino_pago": termino_pago,
            "total": total
        }

        pdf_path = generar_factura_manual_pdf(pdf_data)

        # ====================================================
        # ACTUALIZAR FACTURA CON PDF
        # ====================================================
        cur.execute("""
            UPDATE factura
            SET pdf_path = %s
            WHERE id = %s
        """, (pdf_path, factura_id))

        # ====================================================
        # INSERTAR EN TABLA INVOICING (MANUAL)
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
                created_at
            )
            VALUES (
                %s,
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
        """, (
            factura_id,
            numero_factura,
            codigo_cliente,
            servicio["cliente"],
            fecha_factura,
            payload.get("moneda", "USD"),
            total,
            pdf_path
        ))



        # ====================================================
        # BLOQUEAR SERVICIO
        # ====================================================
        cur.execute("""
            UPDATE servicios
            SET
                factura = %s,
                valor_factura = %s,
                fecha_factura = %s,
                terminos_pago = %s
            WHERE consec = %s
        """, (
            numero_factura,
            total,
            fecha_factura.date(),
            termino_pago,
            servicio_id
        ))

        conn.commit()

        return {
            "status": "ok",
            "factura_id": factura_id,
            "numero_factura": numero_factura,
            "pdf_path": pdf_path
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur:
            cur.close()




from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from psycopg2.extras import RealDictCursor
from datetime import datetime
import uuid

from database import get_db
from services.xml.factura_electronica_parser import (
    parse_factura_electronica_from_bytes
)
from services.pdf.factura_preview_pdf import generar_factura_preview_pdf

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
)


from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from psycopg2.extras import RealDictCursor
from datetime import datetime
import uuid

from database import get_db
from services.xml.factura_electronica_parser import (
    parse_factura_electronica_from_bytes
)
from services.pdf.factura_preview_pdf import generar_factura_preview_pdf

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
)


from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from psycopg2.extras import RealDictCursor
from datetime import datetime
import uuid

from database import get_db
from services.xml.factura_electronica_parser import (
    parse_factura_electronica_from_bytes
)
from services.pdf.factura_preview_pdf import generar_factura_preview_pdf

router = APIRouter(
    prefix="/factura",
    tags=["Facturación"]
)


@router.post("/electronica")
def crear_factura_electronica(
    file: UploadFile = File(...),
    servicio_id: int = Form(...),
    conn=Depends(get_db)
):
    # =========================================================
    # 0️⃣ VALIDACIONES BÁSICAS
    # =========================================================
    if not file.filename.lower().endswith(".xml"):
        raise HTTPException(400, "El archivo debe ser XML")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # =====================================================
        # 1️⃣ SERVICIO = FUENTE DE VERDAD OPERATIVA
        # =====================================================
        cur.execute("""
            SELECT
                s.consec,
                s.num_informe,
                s.buque_contenedor,
                s.operacion,
                s.fecha_inicio,
                s.fecha_fin,
                s.cliente,
                c.codigo AS codigo_cliente
            FROM servicios s
            JOIN cliente c
              ON c.nombrecomercial = s.cliente
              OR c.nombrejuridico = s.cliente
            WHERE s.consec = %s
        """, (servicio_id,))

        servicio = cur.fetchone()
        if not servicio:
            raise HTTPException(404, "Servicio no encontrado")

        # =====================================================
        # 2️⃣ VALIDAR CONTRA INVOICING (ÚNICA FUENTE DE VERDAD)
        # =====================================================
        cur.execute("""
            SELECT 1
            FROM invoicing
            WHERE
                num_informe = %s
                AND tipo_documento = 'FACTURA'
                AND estado <> 'ANULADA'
            LIMIT 1
        """, (servicio["num_informe"],))

        if cur.fetchone():
            raise HTTPException(
                400,
                "Este servicio ya tiene una factura registrada en Invoicing"
            )

        # =====================================================
        # 3️⃣ PARSEAR XML (FE / FEE – TOLERANTE)
        # =====================================================
        xml_bytes = file.file.read()
        data_xml = parse_factura_electronica_from_bytes(xml_bytes)

        numero_documento = (
            data_xml.get("numero_factura")
            or data_xml.get("clave_electronica")
        )

        if not numero_documento:
            raise HTTPException(
                400,
                "XML inválido: no se pudo obtener número ni clave"
            )

        moneda = data_xml.get("moneda") or "CRC"
        total = float(data_xml.get("total") or 0)

        fecha_emision = (
            data_xml.get("fecha_emision")
            or datetime.now().date()
        )

        try:
            termino_pago = int(float(data_xml.get("termino_pago") or 0))
        except (TypeError, ValueError):
            termino_pago = 0

        # =====================================================
        # 4️⃣ PDF PREVIEW (NO BLOQUEANTE)
        # =====================================================
        pdf_path = None
        try:
            tmp_pdf = f"/tmp/factura_preview_{uuid.uuid4().hex}.pdf"
            pdf_path = generar_factura_preview_pdf(
                {
                    "numero_documento": numero_documento,
                    "fecha_emision": fecha_emision,
                    "cliente": servicio["cliente"],
                    "buque_contenedor": servicio["buque_contenedor"],
                    "operacion": servicio["operacion"],
                    "periodo": (
                        f"{servicio['fecha_inicio']} a {servicio['fecha_fin']}"
                    ),
                    "moneda": moneda,
                    "total": total
                },
                output_path=tmp_pdf
            )
        except Exception:
            pdf_path = None  # preview es opcional

        # =====================================================
        # 5️⃣ INSERTAR EN INVOICING
        # =====================================================
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
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id
        """, (
            numero_documento,
            servicio["codigo_cliente"],
            servicio["cliente"],
            fecha_emision,
            moneda,
            total,
            pdf_path,
            servicio["num_informe"],
            termino_pago,
            servicio["buque_contenedor"],
            servicio["operacion"],
            f"{servicio['fecha_inicio']} a {servicio['fecha_fin']}",
            "Factura electrónica cargada desde XML"
        ))

        invoicing_id = cur.fetchone()["id"]

        # =====================================================
        # 6️⃣ BLOQUEAR SERVICIO (MISMO FLUJO QUE MANUAL)
        # =====================================================
        cur.execute("""
            UPDATE servicios
            SET
                factura = %s,
                valor_factura = %s,
                fecha_factura = %s,
                terminos_pago = %s
            WHERE consec = %s
        """, (
            numero_documento,
            total,
            fecha_emision,
            termino_pago,
            servicio_id
        ))

        conn.commit()

        return {
            "status": "ok",
            "invoicing_id": invoicing_id,
            "pdf_preview": pdf_path
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()



@router.get("/termino-pago")
def get_termino_pago_cliente(
    nombre_cliente: str = Query(..., description="nombrecomercial del cliente"),
    conn=Depends(get_db)
):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        nombre = nombre_cliente.strip()

        # 1️⃣ Resolver código desde cliente
        cur.execute("""
            SELECT codigo
            FROM cliente
            WHERE nombrecomercial = %s
               OR nombrejuridico = %s
            LIMIT 1
        """, (nombre, nombre))

        cliente = cur.fetchone()
        if not cliente:
            raise HTTPException(
                status_code=404,
                detail="Cliente no encontrado en tabla cliente"
            )

        codigo_cliente = cliente["codigo"]

        # 2️⃣ Obtener término de pago desde cliente_credito
        cur.execute("""
            SELECT termino_pago
            FROM cliente_credito
            WHERE codigo_cliente = %s
            LIMIT 1
        """, (codigo_cliente,))

        credito = cur.fetchone()
        if not credito or credito["termino_pago"] is None:
            raise HTTPException(
                status_code=404,
                detail="Cliente sin término de pago configurado"
            )

        return {
            "codigo_cliente": codigo_cliente,
            "termino_pago": int(credito["termino_pago"]),
            "fecha_emision": date.today().isoformat()
        }

    finally:
        cur.close()

# ============================================================
# DESCARGAR PDF DE FACTURA
# ============================================================
@router.get("/pdf/{factura_id}")
def descargar_pdf_factura(factura_id: int, conn=Depends(get_db)):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT pdf_path
        FROM factura
        WHERE id = %s
    """, (factura_id,))

    row = cur.fetchone()
    cur.close()

    if not row or not row.get("pdf_path"):
        raise HTTPException(
            status_code=404,
            detail="PDF de la factura no encontrado"
        )

    pdf_path = row["pdf_path"]

    if not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=404,
            detail="El archivo PDF no existe en el servidor"
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path)
    )

# ============================================================
# OBTENER FACTURA POR ID
# ============================================================
@router.get("/{factura_id}")
def get_factura(factura_id: int, conn=Depends(get_db)):
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM factura WHERE id = %s", (factura_id,))
    factura = cur.fetchone()

    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    cur.execute("""
        SELECT *
        FROM factura_detalle
        WHERE factura_id = %s
    """, (factura_id,))
    detalles = cur.fetchall()

    cur.close()

    return {
        "factura": factura,
        "detalles": detalles
    }
