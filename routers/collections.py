from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date, timedelta


from database import get_db

router = APIRouter(
    prefix="/collections",
    tags=["Collections"]
)


# ============================================================
# Helpers
# ============================================================
def _bucket_aging(aging_dias: int) -> str:
    if aging_dias <= 0:
        return "CURRENT"
    if 1 <= aging_dias <= 30:
        return "1-30"
    if 31 <= aging_dias <= 60:
        return "31-60"
    if 61 <= aging_dias <= 90:
        return "61-90"
    return "90+"


def _safe_int(v, default=0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


@router.post("/post-to-accounting")
def post_collections_to_accounting(conn=Depends(get_db)):

    from psycopg2.extras import RealDictCursor
    from datetime import date

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ====================================================
        # 1️⃣ Collections sin líneas contables
        # ====================================================
        cur.execute("""
            SELECT c.*
            FROM collections c
            WHERE NOT EXISTS (
                SELECT 1
                FROM accounting_lines al
                WHERE al.line_description = 'From Collections ' || c.numero_documento
            )
        """)

        collections = cur.fetchall()
        creados = 0

        for c in collections:

            numero = c["numero_documento"]
            total = float(c["total"] or 0)
            if total <= 0:
                continue

            fecha = c["fecha_emision"] or date.today()

            # ====================================================
            # 2️⃣ Buscar servicio para país
            # ====================================================
            cur.execute("""
                SELECT pais
                FROM servicios
                WHERE factura = %s
                LIMIT 1
            """, (numero,))

            srv = cur.fetchone()
            pais = (srv["pais"] if srv else "").strip().lower()

            # ====================================================
            # 3️⃣ Cálculo IVA
            # ====================================================
            if pais == "costa rica":
                subtotal = round(total / 1.13, 2)
                iva = round(total - subtotal, 2)
            else:
                subtotal = total
                iva = 0

            # ====================================================
            # 4️⃣ CxC
            # ====================================================
            cur.execute("""
                INSERT INTO accounting_lines
                    (account_code, account_name, debit, credit, line_description, created_at)
                VALUES (%s, %s, %s, 0, %s, NOW())
            """, (
                "1101",
                "Cuentas por cobrar",
                total,
                f"From Collections {numero}"
            ))

            # ====================================================
            # 5️⃣ Ingresos
            # ====================================================
            cur.execute("""
                INSERT INTO accounting_lines
                    (account_code, account_name, debit, credit, line_description, created_at)
                VALUES (%s, %s, 0, %s, %s, NOW())
            """, (
                "4101",
                "Ingresos por servicios",
                subtotal,
                f"From Collections {numero}"
            ))

            # ====================================================
            # 6️⃣ IVA por pagar (solo CR)
            # ====================================================
            if iva > 0:
                cur.execute("""
                    INSERT INTO accounting_lines
                        (account_code, account_name, debit, credit, line_description, created_at)
                    VALUES (%s, %s, 0, %s, %s, NOW())
                """, (
                    "2108",
                    "IVA por pagar",
                    iva,
                    f"From Collections {numero}"
                ))

            creados += 1

        conn.commit()

        return {
            "status": "ok",
            "lines_created": creados
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Error posting collections to accounting: {repr(e)}")

    finally:
        cur.close()
# ============================================================
# GET /collections/search
# Búsqueda de cuentas por cobrar (Collections)
# ============================================================
@router.get("/search")
def search_collections(
    cliente: Optional[str] = Query(
        None,
        description="ALL o código/nombre del cliente"
    ),
    bucket_aging: Optional[str] = Query(
        None,
        description="CURRENT | 1-30 | 31-60 | 61-90 | 90+"
    ),
    estado_factura: Optional[str] = Query(
        None,
        description="PENDIENTE_PAGO | PAGADA | DISPUTADA | WRITE_OFF"
    ),
    disputada: Optional[bool] = Query(
        None,
        description="True / False"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn=Depends(get_db)
):
    """
    Devuelve facturas en Collections con filtros y paginación.
    NO se ejecuta automáticamente en UI.
    """

    offset = (page - 1) * page_size
    cur = conn.cursor(cursor_factory=RealDictCursor)

    filtros = []
    params = {}

    # ================= FILTROS =================
    if cliente and cliente.upper() != "ALL":
        filtros.append("""
            (codigo_cliente = %(cliente_exact)s
             OR nombre_cliente ILIKE %(cliente_like)s)
        """)
        params["cliente_exact"] = cliente.strip()
        params["cliente_like"] = f"%{cliente.strip()}%"

    if bucket_aging:
        filtros.append("bucket_aging = %(bucket_aging)s")
        params["bucket_aging"] = bucket_aging

    if estado_factura:
        filtros.append("estado_factura = %(estado_factura)s")
        params["estado_factura"] = estado_factura

    if disputada is not None:
        filtros.append("disputada = %(disputada)s")
        params["disputada"] = disputada

    where_sql = "WHERE " + " AND ".join(filtros) if filtros else ""

    # ================= TOTAL =================
    cur.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM collections
        {where_sql}
        """,
        params
    )
    total = cur.fetchone()["total"]

    # ================= DATA =================
    cur.execute(
        f"""
        SELECT
            codigo_cliente,
            nombre_cliente,
            tipo_factura,
            tipo_documento,
            numero_documento,
            fecha_emision,
            fecha_vencimiento,
            aging_dias,
            bucket_aging,
            moneda,
            total,
            saldo_pendiente,
            num_informe,
            buque_contenedor,
            operacion,
            periodo_operacion,
            descripcion_servicio,
            estado_factura,
            disputada
        FROM collections
        {where_sql}
        ORDER BY
            disputada DESC,
            aging_dias DESC,
            fecha_vencimiento ASC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            **params,
            "limit": page_size,
            "offset": offset
        }
    )

    data = cur.fetchall()
    cur.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": data
    }

# ============================================================
# POST /collections/disputa
# Crear una disputa de factura
# ============================================================
@router.post("/disputa")
def crear_disputa(payload: dict, conn=Depends(get_db)):
    cur = None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ================================
        # VALIDAR PAYLOAD MÍNIMO
        # ================================
        numero_documento = str(payload.get("numero_documento") or "").strip()
        codigo_cliente = str(payload.get("codigo_cliente") or "").strip()
        nombre_cliente = str(payload.get("nombre_cliente") or "").strip()
        motivo = str(payload.get("motivo") or "").strip()
        comentario = str(payload.get("comentario") or "").strip()

        if not numero_documento:
            raise HTTPException(400, "numero_documento es requerido")
        if not motivo:
            raise HTTPException(400, "motivo es requerido")
        if not comentario:
            raise HTTPException(400, "comentario es requerido")

        # ================================
        # 1️⃣ dispute_case seguro
        # ================================
        cur.execute("""
            SELECT COALESCE(
                MAX(
                    CAST(SUBSTRING(dispute_case FROM '[0-9]+') AS INTEGER)
                ),
                0
            ) AS last_num
            FROM disputa
        """)
        dispute_case = f"DISP-{cur.fetchone()['last_num'] + 1:04d}"

        # ================================
        # 2️⃣ Fuente de verdad: collections
        # ================================
        cur.execute("""
            SELECT
                fecha_emision,
                fecha_vencimiento,
                total,
                buque_contenedor,
                operacion,
                periodo_operacion,
                descripcion_servicio
            FROM collections
            WHERE numero_documento = %s
            LIMIT 1
        """, (numero_documento,))
        base = cur.fetchone()

        if not base:
            raise HTTPException(404, "Factura no encontrada en Collections")

        # ================================
        # 3️⃣ INSERT limpio (SIN payload basura)
        # ================================
        cur.execute("""
            INSERT INTO disputa (
                dispute_case,
                numero_documento,
                codigo_cliente,
                nombre_cliente,
                fecha_factura,
                fecha_vencimiento,
                monto,
                motivo,
                comentario,
                buque_contenedor,
                operacion,
                periodo_operacion,
                descripcion_servicio,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, NOW()
            )
        """, (
            dispute_case,
            numero_documento,
            codigo_cliente,
            nombre_cliente,
            base["fecha_emision"],
            base["fecha_vencimiento"],
            base["total"],
            motivo,
            comentario,
            base["buque_contenedor"],
            base["operacion"],
            base["periodo_operacion"],
            base["descripcion_servicio"]
        ))

        # ================================
        # 4️⃣ Marcar disputada
        # ================================
        cur.execute("""
            UPDATE collections
            SET disputada = TRUE,
                estado_factura = 'DISPUTADA'
            WHERE numero_documento = %s
        """, (numero_documento,))

        conn.commit()

        return {"status": "ok", "dispute_case": dispute_case}

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, f"Error creando disputa: {repr(e)}")

    finally:
        if cur:
            cur.close()



# ============================================================
# POST /collections/pago
# Aplicar pago o nota de crédito (parcial o total)
# ============================================================
@router.post("/pago")
def aplicar_pago(payload: dict, conn=Depends(get_db)):

    cur = None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ================================
        # VALIDAR PAYLOAD MÍNIMO (BLINDADO)
        # ================================
        numero_documento = str(payload.get("numero_documento") or "").strip()
        codigo_cliente = str(payload.get("codigo_cliente") or "").strip()
        nombre_cliente = str(payload.get("nombre_cliente") or "").strip()
        tipo_aplicacion = str(payload.get("tipo_aplicacion") or "").strip().upper()
        banco = str(payload.get("banco") or "").strip()
        referencia = str(payload.get("referencia") or "").strip()

        try:
            monto_pagado = float(payload.get("monto_pagado", 0))
        except Exception:
            monto_pagado = 0

        comision = payload.get("comision") or 0
        fecha_pago = payload.get("fecha_pago")

        if not numero_documento:
            raise HTTPException(400, "numero_documento es requerido")

        if tipo_aplicacion not in ("PAGO", "NOTA_CREDITO"):
            raise HTTPException(400, "Tipo de aplicación inválido")

        if monto_pagado <= 0:
            raise HTTPException(400, "El monto debe ser mayor a cero")

        # ================================
        # OBTENER SALDO ACTUAL (LOCK)
        # ================================
        cur.execute("""
            SELECT saldo_pendiente
            FROM collections
            WHERE numero_documento = %s
            FOR UPDATE
        """, (numero_documento,))

        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Factura no encontrada en Collections")

        saldo_actual = float(row["saldo_pendiente"] or 0)

        if monto_pagado > saldo_actual:
            raise HTTPException(
                400,
                f"El monto aplicado ({monto_pagado}) excede el saldo pendiente ({saldo_actual})"
            )

        # ================================
        # INSERT CASH APP (LEDGER)
        # ================================
        cur.execute("""
            INSERT INTO cash_app (
                numero_documento,
                codigo_cliente,
                nombre_cliente,
                banco,
                fecha_pago,
                comision,
                referencia,
                monto_pagado,
                tipo_aplicacion,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, NOW()
            )
        """, (
            numero_documento,
            codigo_cliente,
            nombre_cliente,
            banco,
            fecha_pago,
            comision,
            referencia,
            monto_pagado,
            tipo_aplicacion
        ))

        # ================================
        # CALCULAR NUEVO SALDO
        # ================================
        nuevo_saldo = saldo_actual - monto_pagado

        if nuevo_saldo <= 0:
            nuevo_saldo = 0
            estado = "PAGADA"
        else:
            estado = "PENDIENTE_PAGO"

        # ================================
        # ACTUALIZAR COLLECTIONS
        # ================================
        cur.execute("""
            UPDATE collections
            SET
                saldo_pendiente = %s,
                estado_factura = %s
            WHERE numero_documento = %s
        """, (
            nuevo_saldo,
            estado,
            numero_documento
        ))

        conn.commit()

        return {
            "status": "ok",
            "message": f"{tipo_aplicacion} aplicado correctamente",
            "saldo_anterior": saldo_actual,
            "saldo_actual": nuevo_saldo,
            "estado_factura": estado
        }

    except HTTPException:
        if conn:
            conn.rollback()
        raise

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error aplicando pago: {repr(e)}"
        )

    finally:
        if cur:
            cur.close()




