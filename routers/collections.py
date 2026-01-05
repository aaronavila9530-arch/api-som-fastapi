from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header
)
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date, datetime, timedelta

from database import get_db
from rbac_service import has_permission


router = APIRouter(
    prefix="/collections",
    tags=["Collections"]
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
# POST /collections/sync-from-invoicing
# Sincroniza facturas EMITIDAS → Collections
# ============================================================
@router.post("/sync-from-invoicing")
def sync_collections_from_invoicing(conn=Depends(get_db)):

    cur = conn.cursor(cursor_factory=RealDictCursor)

    inserted = 0
    skipped = 0
    errors = []

    try:
        cur.execute("""
            SELECT *
            FROM invoicing i
            WHERE i.tipo_documento = 'FACTURA'
              AND i.estado = 'EMITIDA'
              AND i.total > 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM collections c
                  WHERE c.numero_documento = i.numero_documento
                    AND c.codigo_cliente = i.codigo_cliente
              )
        """)

        facturas = cur.fetchall()
        hoy = date.today()
        procesadas = set()

        for f in facturas:

            key = (f.get("numero_documento"), f.get("codigo_cliente"))
            if key in procesadas:
                skipped += 1
                continue
            procesadas.add(key)

            try:
                # SAVEPOINT POR FACTURA
                cur.execute("SAVEPOINT sp_factura")

                # ---------- fecha_emision ----------
                fe = f.get("fecha_emision")
                if isinstance(fe, datetime):
                    fe = fe.date()
                elif isinstance(fe, date):
                    pass
                elif isinstance(fe, str):
                    fe = datetime.fromisoformat(fe).date()
                else:
                    raise ValueError("fecha_emision inválida")

                # ---------- dias_credito ----------
                try:
                    dias_credito = int(f.get("termino_pago"))
                except Exception:
                    dias_credito = 0

                fecha_vencimiento = fe + timedelta(days=dias_credito)
                aging_dias = (hoy - fecha_vencimiento).days

                if aging_dias <= 0:
                    bucket = "CURRENT"
                elif aging_dias <= 30:
                    bucket = "1-30"
                elif aging_dias <= 60:
                    bucket = "31-60"
                elif aging_dias <= 90:
                    bucket = "61-90"
                else:
                    bucket = "90+"

                total = float(f.get("total") or 0)

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
                        disputada,
                        saldo_pendiente,
                        created_at
                    ) VALUES (
                        %(numero_documento)s,
                        %(codigo_cliente)s,
                        %(nombre_cliente)s,
                        %(tipo_factura)s,
                        %(tipo_documento)s,
                        %(fecha_emision)s,
                        %(fecha_vencimiento)s,
                        %(moneda)s,
                        %(total)s,
                        %(dias_credito)s,
                        %(aging_dias)s,
                        %(bucket)s,
                        %(num_informe)s,
                        %(buque)s,
                        %(operacion)s,
                        %(periodo)s,
                        %(descripcion)s,
                        'PENDIENTE_PAGO',
                        FALSE,
                        %(saldo)s,
                        NOW()
                    )
                """, {
                    "numero_documento": f.get("numero_documento"),
                    "codigo_cliente": f.get("codigo_cliente"),
                    "nombre_cliente": f.get("nombre_cliente"),
                    "tipo_factura": f.get("tipo_factura"),
                    "tipo_documento": f.get("tipo_documento"),
                    "fecha_emision": fe,
                    "fecha_vencimiento": fecha_vencimiento,
                    "moneda": f.get("moneda"),
                    "total": total,
                    "dias_credito": dias_credito,
                    "aging_dias": aging_dias,
                    "bucket": bucket,
                    "num_informe": f.get("num_informe"),
                    "buque": f.get("buque_contenedor"),
                    "operacion": f.get("operacion"),
                    "periodo": f.get("periodo_operacion"),
                    "descripcion": f.get("descripcion_servicio"),
                    "saldo": total
                })

                cur.execute("RELEASE SAVEPOINT sp_factura")
                inserted += 1

            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp_factura")
                skipped += 1
                errors.append({
                    "numero_documento": f.get("numero_documento"),
                    "codigo_cliente": f.get("codigo_cliente"),
                    "error": str(e)
                })

        conn.commit()

        return {
            "status": "ok",
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors[:5]  # no saturar respuesta
        }

    finally:
        cur.close()
# ============================================================
# POST /collections/post-to-accounting
# Genera asientos contables para facturas existentes (y futuras que caigan a collections)
# ============================================================
@router.post("/post-to-accounting")
def post_collections_to_accounting(conn=Depends(get_db)) -> dict:
    """
    Sincroniza collections → accounting:
    - Inserta accounting_entries + accounting_lines
    - IVA para Costa Rica (total/1.13)
    - No duplica: valida por origin='COLLECTIONS' y origin_id=collections.id
    """
    try:
        from services.accounting_auto import sync_collections_to_accounting

        # Ejecuta sincronización real
        sync_collections_to_accounting(conn)

        return {
            "status": "ok",
            "message": "Collections posteadas a Accounting (entries + lines)"
        }

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(500, repr(e))
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




