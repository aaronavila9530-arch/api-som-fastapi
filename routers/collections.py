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
        description="Si True, solo sincroniza facturas con estado != PAGADA (según invoicing/collections)."
    ),
    conn=Depends(get_db)
):
    """
    Sincroniza (upsert) facturas desde 'invoicing' hacia 'collections'.

    - Si cliente = ALL o None -> procesa todas.
    - Si cliente se envía -> filtra por coincidencia exacta/ILIKE en codigo_cliente o nombre_cliente.
    - Calcula vencimiento y aging en el servidor.
    - No pisa disputada/estado_factura si ya existían (mantiene gestión de cobro).
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
            # Puede venir como código o nombre
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
        # Nota: Aquí leemos también las nuevas columnas snapshot si existen.
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

                -- snapshots (pueden existir o no según tu ALTER TABLE)
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

        # ---------------------------
        # Upsert por numero_documento
        # ---------------------------
        for f in facturas:
            numero = str(f.get("numero_documento", "")).strip()
            if not numero:
                continue

            codigo_cliente = (f.get("codigo_cliente") or "").strip()
            nombre_cliente = (f.get("nombre_cliente") or "").strip()

            # 1) Obtener días de crédito desde cliente_credito (si existe)
            cur.execute("""
                SELECT termino_pago, limite_credito
                FROM cliente_credito
                WHERE codigo_cliente = %s
                LIMIT 1
            """, (codigo_cliente,))
            cc = cur.fetchone() or {}
            dias_credito = cc.get("termino_pago")

            # fallback a lo que venga en invoicing (termino_pago)
            if dias_credito is None:
                dias_credito = f.get("termino_pago")

            dias_credito = _safe_int(dias_credito, default=0)

            # 2) Fechas
            fecha_emision = f.get("fecha_emision")
            # Si viene como string 'YYYY-MM-DD' convertir a date
            if isinstance(fecha_emision, str):
                try:
                    fecha_emision = date.fromisoformat(fecha_emision)
                except Exception:
                    fecha_emision = None

            if not fecha_emision:
                # Si falta fecha_emision no podemos calcular vencimiento
                # Igual podemos insertar algo mínimo
                fecha_venc = None
                aging = 0
                bucket = "CURRENT"
            else:
                fecha_venc = fecha_emision + timedelta(days=dias_credito)
                aging = (hoy - fecha_venc).days
                bucket = _bucket_aging(aging)

            # 3) Mantener disputada/estado_factura si ya existe
            cur.execute("""
                SELECT estado_factura, disputada
                FROM collections
                WHERE numero_documento = %s
                LIMIT 1
            """, (numero,))
            existente = cur.fetchone()

            if existente:
                estado_factura = existente.get("estado_factura") or f.get("estado") or "PENDIENTE_PAGO"
                disputada = bool(existente.get("disputada"))
            else:
                # Estado inicial: si invoicing trae estado, úsalo; si no, PENDIENTE_PAGO
                estado_invoicing = (f.get("estado") or "").strip().upper()
                if estado_invoicing == "PAGADA":
                    estado_factura = "PAGADA"
                else:
                    estado_factura = "PENDIENTE_PAGO"
                disputada = False

            # 4) Upsert
            if existente:
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
                    f.get("total"),
                    dias_credito,
                    aging,
                    bucket,
                    f.get("num_informe"),
                    f.get("buque_contenedor"),
                    f.get("operacion"),
                    f.get("periodo_operacion"),
                    f.get("descripcion_servicio"),
                    estado_factura,
                    numero
                ))
            else:
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
                    f.get("total"),
                    dias_credito,
                    aging,
                    bucket,
                    f.get("num_informe"),
                    f.get("buque_contenedor"),
                    f.get("operacion"),
                    f.get("periodo_operacion"),
                    f.get("descripcion_servicio"),
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

        # ====================================================
        # 1️⃣ Generar dispute_case secuencial (ROBUSTO)
        # ====================================================
        cur.execute("""
            SELECT COALESCE(
                MAX(
                    CAST(
                        SUBSTRING(dispute_case FROM '[0-9]+') AS INTEGER
                    )
                ),
                0
            ) AS last_num
            FROM disputa
        """)

        last_num = cur.fetchone()["last_num"]
        dispute_case = f"DISP-{last_num + 1:04d}"

        # ====================================================
        # 2️⃣ Obtener datos desde Collections (fuente de verdad)
        # ====================================================
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
        """, (payload["numero_documento"],))

        base = cur.fetchone()

        if not base:
            raise HTTPException(
                status_code=404,
                detail="Factura no encontrada en Collections"
            )

        if not base["fecha_emision"] or not base["fecha_vencimiento"]:
            raise HTTPException(
                status_code=400,
                detail="La factura no tiene fechas válidas para disputar"
            )

        if base["total"] is None:
            raise HTTPException(
                status_code=400,
                detail="La factura no tiene monto válido"
            )

        # ====================================================
        # 3️⃣ Insertar disputa
        # ====================================================
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
                descripcion_servicio
            ) VALUES (
                %(dispute_case)s,
                %(numero_documento)s,
                %(codigo_cliente)s,
                %(nombre_cliente)s,
                %(fecha_factura)s,
                %(fecha_vencimiento)s,
                %(monto)s,
                %(motivo)s,
                %(comentario)s,
                %(buque_contenedor)s,
                %(operacion)s,
                %(periodo_operacion)s,
                %(descripcion_servicio)s
            )
        """, {
            "dispute_case": dispute_case,
            "numero_documento": payload["numero_documento"],
            "codigo_cliente": payload["codigo_cliente"],
            "nombre_cliente": payload["nombre_cliente"],
            "fecha_factura": base["fecha_emision"],
            "fecha_vencimiento": base["fecha_vencimiento"],
            "monto": base["total"],
            "motivo": payload["motivo"],
            "comentario": payload["comentario"],
            "buque_contenedor": base["buque_contenedor"],
            "operacion": base["operacion"],
            "periodo_operacion": base["periodo_operacion"],
            "descripcion_servicio": base["descripcion_servicio"]
        })

        # ====================================================
        # 4️⃣ Marcar factura como disputada
        # ====================================================
        cur.execute("""
            UPDATE collections
            SET
                disputada = TRUE,
                estado_factura = 'DISPUTADA'
            WHERE numero_documento = %s
        """, (payload["numero_documento"],))

        conn.commit()

        return {
            "status": "ok",
            "dispute_case": dispute_case
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
            detail=f"Error creando disputa: {str(e)}"
        )

    finally:
        if cur:
            cur.close()


# ============================================================
# POST /collections/pago
# Aplicar pago o nota de crédito a una factura
# ============================================================
@router.post("/pago")
def aplicar_pago(payload: dict, conn=Depends(get_db)):
    """
    payload esperado:
    {
        numero_documento,
        codigo_cliente,
        nombre_cliente,
        tipo_aplicacion,   # PAGO | NOTA_CREDITO
        banco,
        fecha_pago,
        comision,
        referencia,
        monto_pagado
    }
    """

    cur = None

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # ================= VALIDACIONES =================
        if payload["tipo_aplicacion"] not in ("PAGO", "NOTA_CREDITO"):
            raise HTTPException(400, "Tipo de aplicación inválido")

        if float(payload["monto_pagado"]) <= 0:
            raise HTTPException(400, "El monto debe ser mayor a cero")

        # ================= INSERT CASH APP =================
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
                tipo_aplicacion
            ) VALUES (
                %(numero_documento)s,
                %(codigo_cliente)s,
                %(nombre_cliente)s,
                %(banco)s,
                %(fecha_pago)s,
                %(comision)s,
                %(referencia)s,
                %(monto_pagado)s,
                %(tipo_aplicacion)s
            )
        """, {
            "numero_documento": payload["numero_documento"],
            "codigo_cliente": payload["codigo_cliente"],
            "nombre_cliente": payload["nombre_cliente"],
            "banco": payload["banco"],
            "fecha_pago": payload["fecha_pago"],
            "comision": payload.get("comision", 0),
            "referencia": payload.get("referencia"),
            "monto_pagado": payload["monto_pagado"],
            "tipo_aplicacion": payload["tipo_aplicacion"]
        })

        # ================= ACTUALIZAR COLLECTIONS =================
        # En esta versión: pago completo = PAGADA
        # (parciales se pueden extender luego)
        cur.execute("""
            UPDATE collections
            SET estado_factura = 'PAGADA'
            WHERE numero_documento = %s
        """, (payload["numero_documento"],))

        conn.commit()

        return {
            "status": "ok",
            "message": f"{payload['tipo_aplicacion']} aplicado correctamente"
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
            detail=f"Error aplicando pago: {str(e)}"
        )

    finally:
        if cur:
            cur.close()



