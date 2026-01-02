from fastapi import APIRouter, Depends, HTTPException, Header
from psycopg2.extras import RealDictCursor
from datetime import datetime
from fastapi.responses import FileResponse
import os

from database import get_db
from backend_api.rbac_service import has_permission

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


@router.post("/electronica")
def crear_factura_electronica(
    xml_path: str,
    codigo_cliente: str,
    nombre_cliente: str,
    conn=Depends(get_db)
):
    from services.factura_electronica_parser import parse_factura_electronica

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        data = parse_factura_electronica(xml_path)

        numero_documento = data["numero_factura"]
        fecha_emision = data["fecha_emision"]
        moneda = data["moneda"]
        total = data["total"]

        pdf_path = None

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
                NOW()
            )
        """, (
            numero_documento,
            codigo_cliente,
            nombre_cliente,
            fecha_emision,
            moneda,
            total,
            pdf_path
        ))

        conn.commit()
        return {"status": "ok"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()

