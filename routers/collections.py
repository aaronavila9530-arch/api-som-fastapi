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


# ============================================================
# POST /collections/sync
# Copia facturas emitidas desde invoicing a collections
# ============================================================
@router.post("/sync")
def sync_collections(
    cliente: Optional[str] = Query(
        None,
        description="ALL o filtro (código_cliente o nombre_cliente). Si no se envía, asume ALL."
    ),
    solo_pendientes: bool = Query(
        True,
        description="Si True, solo sincroniza facturas con estado != PAGADA (según invoicing)."
    ),
    conn=Depends(get_db)
):
    """
    Sincroniza (upsert) facturas desde 'invoicing' hacia 'collections'.

    - Si cliente = ALL o None -> procesa todas.
    - Si cliente se envía -> filtra por coincidencia exacta/ILIKE en codigo_cliente o nombre_cliente.
    - Calcula vencimiento y aging en el servidor.
    - No pisa disputada.
    - No pisa saldo_pendiente si ya hubo aplicaciones (pagos/NC).
    - Si no hay aplicaciones (saldo_pendiente == total anterior), ajusta saldo al nuevo total.
    - Nunca deja saldo_pendiente NULL.

    + FIX: Para facturas MANUAL (invoicing sin snapshots),
      trae num_informe/buque/operacion/periodo/descripcion desde servicios
      usando servicios.factura == numero_documento.
    """

    if not conn:
        raise HTTPException(status_code=500, detail="No se pudo obtener conexión a la base de datos")

    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        filtros = []
        params = {}

        # ---------------------------
        # Filtro cliente
        # ---------------------------
        if cliente and cliente.upper() != "ALL":
            filtros.append("(i.codigo_cliente = %(cliente_exact)s OR i.nombre_cliente ILIKE %(cliente_like)s)")
            params["cliente_exact"] = cliente.strip()
            params["cliente_like"] = f"%{cliente.strip()}%"

        # ---------------------------
        # Filtro pendientes (opcional)
        # ---------------------------
        if solo_pendientes:
            filtros.append("COALESCE(i.estado, 'EMITIDA') <> 'PAGADA'")

        where_sql = "WHERE " + " AND ".join(filtros) if filtros else ""

        # ---------------------------
        # Traer facturas desde invoicing
        # ---------------------------
        cur.execute(
            f"""
            SELECT
                i.tipo_factura,
                i.tipo_documento,
                i.numero_documento,
                i.codigo_cliente,
                i.nombre_cliente,
                i.fecha_emision,
                i.moneda,
                i.total,
                i.estado,

                i.num_informe,
                i.termino_pago,
                i.buque_contenedor,
                i.operacion,
                i.periodo_operacion,
                i.descripcion_servicio
            FROM invoicing i
            {where_sql}
            ORDER BY i.fecha_emision DESC
            """,
            params
        )
        facturas = cur.fetchall()

        if not facturas:
            return {
                "status": "ok",
                "synced": 0,
                "message": "No hay facturas para sincronizar con los filtros actuales"
            }

        hoy = date.today()
        synced = 0

        for f in facturas:
            numero = str(f.get("numero_documento", "")).strip()
            if not numero:
                continue

            codigo_cliente = (f.get("codigo_cliente") or "").strip()
            nombre_cliente = (f.get("nombre_cliente") or "").strip()

            # ---------- total robusto ----------
            try:
                total_nuevo = float(f.get("total") or 0)
            except Exception:
                total_nuevo = 0.0

            # 1) Obtener días de crédito desde cliente_credito (si existe)
            cur.execute("""
                SELECT termino_pago, limite_credito
                FROM cliente_credito
                WHERE codigo_cliente = %s
                LIMIT 1
            """, (codigo_cliente,))
            cc = cur.fetchone() or {}
            dias_credito = cc.get("termino_pago")

            if dias_credito is None:
                dias_credito = f.get("termino_pago")

            dias_credito = _safe_int(dias_credito, default=0)

            # 2) Fechas
            fecha_emision = f.get("fecha_emision")
            if isinstance(fecha_emision, str):
                try:
                    fecha_emision = date.fromisoformat(fecha_emision)
                except Exception:
                    fecha_emision = None

            if not fecha_emision:
                fecha_venc = None
                aging = 0
                bucket = "CURRENT"
            else:
                fecha_venc = fecha_emision + timedelta(days=dias_credito)
                aging = (hoy - fecha_venc).days
                bucket = _bucket_aging(aging)

            # ====================================================
            # ✅ FIX: Traer info desde SERVICIOS por factura
            # ====================================================
            cur.execute("""
                SELECT
                    num_informe,
                    buque_contenedor,
                    operacion,
                    fecha_inicio,
                    fecha_fin,
                    detalle
                FROM servicios
                WHERE TRIM(COALESCE(factura::text, '')) = %s
                ORDER BY consec DESC
                LIMIT 1
            """, (numero,))
            svc = cur.fetchone() or {}

            # periodo desde servicios (fecha_inicio / fecha_fin)
            periodo_servicio = ""
            if svc.get("fecha_inicio") and svc.get("fecha_fin"):
                periodo_servicio = f"{svc['fecha_inicio']} → {svc['fecha_fin']}"

            # Fallback snapshots: primero invoicing, si viene NULL usar servicios
            snap_num_informe = f.get("num_informe") or svc.get("num_informe")
            snap_buque = f.get("buque_contenedor") or svc.get("buque_contenedor")
            snap_operacion = f.get("operacion") or svc.get("operacion")
            snap_periodo = f.get("periodo_operacion") or periodo_servicio
            snap_descripcion = f.get("descripcion_servicio")
            if not snap_descripcion:
                snap_descripcion = svc.get("detalle") or ""

            # 3) Ver si existe en collections (y traer saldo/total previo)
            cur.execute("""
                SELECT
                    estado_factura,
                    disputada,
                    saldo_pendiente,
                    total
                FROM collections
                WHERE numero_documento = %s
                LIMIT 1
            """, (numero,))
            existente = cur.fetchone()

            estado_invoicing = (f.get("estado") or "").strip().upper()

            if existente:
                disputada = bool(existente.get("disputada"))
                estado_factura_actual = (existente.get("estado_factura") or "").strip().upper()
                total_anterior = existente.get("total")
                saldo_actual = existente.get("saldo_pendiente")

                try:
                    total_anterior = float(total_anterior or 0)
                except Exception:
                    total_anterior = 0.0

                try:
                    if saldo_actual in (None, "", "None"):
                        saldo_actual_num = None
                    else:
                        saldo_actual_num = float(saldo_actual)
                except Exception:
                    saldo_actual_num = None

                # --------- Determinar saldo final (NO PISAR APLICACIONES) ----------
                if saldo_actual_num is None:
                    saldo_final = total_nuevo
                else:
                    if abs(saldo_actual_num - total_anterior) < 0.0001:
                        saldo_final = total_nuevo
                    else:
                        saldo_final = saldo_actual_num

                # --------- Determinar estado_factura final ----------
                if estado_factura_actual in ("DISPUTADA", "WRITE_OFF", "PAGADA"):
                    estado_factura_final = estado_factura_actual
                else:
                    estado_factura_final = "PAGADA" if saldo_final <= 0 else "PENDIENTE_PAGO"

                if estado_invoicing == "PAGADA" and saldo_final <= 0:
                    estado_factura_final = "PAGADA"

                # 4) UPDATE
                cur.execute("""
                    UPDATE collections
                    SET
                        codigo_cliente = %s,
                        nombre_cliente = %s,
                        tipo_factura = %s,
                        tipo_documento = %s,
                        fecha_emision = %s,
                        fecha_vencimiento = %s,
                        moneda = %s,
                        total = %s,
                        saldo_pendiente = %s,
                        dias_credito = %s,
                        aging_dias = %s,
                        bucket_aging = %s,
                        num_informe = %s,
                        buque_contenedor = %s,
                        operacion = %s,
                        periodo_operacion = %s,
                        descripcion_servicio = %s,
                        estado_factura = %s
                    WHERE numero_documento = %s
                """, (
                    codigo_cliente,
                    nombre_cliente,
                    f.get("tipo_factura"),
                    f.get("tipo_documento"),
                    fecha_emision,
                    fecha_venc,
                    f.get("moneda"),
                    total_nuevo,
                    saldo_final,
                    dias_credito,
                    aging,
                    bucket,
                    snap_num_informe,
                    snap_buque,
                    snap_operacion,
                    snap_periodo,
                    snap_descripcion,
                    estado_factura_final,
                    numero
                ))

            else:
                # --------- Nuevo registro ----------
                disputada = False

                if estado_invoicing == "PAGADA":
                    estado_factura = "PAGADA"
                    saldo_inicial = 0.0
                else:
                    estado_factura = "PENDIENTE_PAGO"
                    saldo_inicial = total_nuevo

                cur.execute("""
                    INSERT INTO collections (
                        numero_documento,
                        codigo_cliente,
                        nombre_cliente,
                        tipo_factura,
                        tipo_documento,
                        fecha_emision,
                        fecha_vencimiento,
                        moneda,
                        total,
                        saldo_pendiente,
                        dias_credito,
                        aging_dias,
                        bucket_aging,
                        num_informe,
                        buque_contenedor,
                        operacion,
                        periodo_operacion,
                        descripcion_servicio,
                        estado_factura,
                        disputada
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    )
                """, (
                    numero,
                    codigo_cliente,
                    nombre_cliente,
                    f.get("tipo_factura"),
                    f.get("tipo_documento"),
                    fecha_emision,
                    fecha_venc,
                    f.get("moneda"),
                    total_nuevo,
                    saldo_inicial,
                    dias_credito,
                    aging,
                    bucket,
                    snap_num_informe,
                    snap_buque,
                    snap_operacion,
                    snap_periodo,
                    snap_descripcion,
                    estado_factura,
                    disputada
                ))

            synced += 1

        conn.commit()

        return {
            "status": "ok",
            "synced": synced,
            "cliente": cliente or "ALL",
            "solo_pendientes": solo_pendientes
        }

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error sync collections: {str(e)}")

    finally:
        if cur:
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



