from psycopg2.extras import RealDictCursor
from datetime import date

def create_accounting_entry(
    conn,
    entry_date,
    period,
    description,
    origin,
    origin_id,
    lines,
    created_by="SYSTEM"
):
    """
    Crea un asiento contable con validación de partida doble
    """

    total_debit = sum(l["debit"] for l in lines)
    total_credit = sum(l["credit"] for l in lines)

    if round(total_debit, 2) != round(total_credit, 2):
        raise ValueError("Partida no balanceada")

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ Insert entry
    cur.execute("""
        INSERT INTO accounting_entries
            (entry_date, period, description, origin, origin_id, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        entry_date,
        period,
        description,
        origin,
        origin_id,
        created_by
    ))

    entry_id = cur.fetchone()["id"]

    # 2️⃣ Insert lines
    for line in lines:
        cur.execute("""
            INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            entry_id,
            line["account_code"],
            line["account_name"],
            line["debit"],
            line["credit"],
            line.get("description")
        ))

    # 🔥🔥🔥 ESTA ES LA LÍNEA QUE FALTABA 🔥🔥🔥
    conn.commit()

    return entry_id


def sync_collections_to_accounting(conn):

    from psycopg2.extras import RealDictCursor
    from datetime import date

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # 1️⃣ OBTENER TC DEL DÍA (OBLIGATORIO)
    # ============================================================
    today = date.today()

    cur.execute("""
        SELECT rate
        FROM exchange_rate
        WHERE rate_date = %s
        LIMIT 1
    """, (today,))

    row_tc = cur.fetchone()
    if not row_tc:
        raise Exception(
            "Tipo de cambio del día no encontrado. "
            "No se puede contabilizar Collections."
        )

    tc = float(row_tc["rate"])

    # ============================================================
    # 2️⃣ TRAER COLLECTIONS (TODAS) PARA CREAR O CORREGIR
    #    - Si ya existe asiento: CORREGIR
    #    - Si no existe: CREAR
    # ============================================================
    cur.execute("""
        SELECT
            c.id,
            c.numero_documento,
            c.nombre_cliente,
            c.fecha_emision,
            c.moneda,
            c.total
        FROM collections c
        ORDER BY c.id ASC
    """)
    rows = cur.fetchall()

    for c in rows:

        collection_id = c["id"]
        numero = c["numero_documento"]

        nombre_cliente = (c.get("nombre_cliente") or "").strip()
        moneda = (c.get("moneda") or "").upper()

        total_raw = float(c.get("total") or 0)
        if total_raw <= 0:
            continue

        fecha = c.get("fecha_emision") or today
        period = fecha.strftime("%Y-%m")

        # ========================================================
        # 3️⃣ PAÍS DEL CLIENTE (cliente.nombrecomercial)
        # ========================================================
        cur.execute("""
            SELECT pais
            FROM cliente
            WHERE LOWER(nombrecomercial) = LOWER(%s)
            LIMIT 1
        """, (nombre_cliente,))
        cli = cur.fetchone()
        pais = (cli["pais"] if cli else "").strip().lower()

        # ========================================================
        # 4️⃣ CONVERSIÓN MONEDA
        # ========================================================
        if moneda == "USD":
            total_crc = round(total_raw * tc, 2)
        else:
            total_crc = round(total_raw, 2)

        # ========================================================
        # 5️⃣ IVA SOLO SI CLIENTE ES COSTA RICA
        # ========================================================
        if pais == "costa rica":
            subtotal = round(total_crc / 1.13, 2)
            iva = round(total_crc - subtotal, 2)
        else:
            subtotal = total_crc
            iva = 0.0

        # ========================================================
        # 6️⃣ ¿EXISTE YA EL ASIENTO?
        # ========================================================
        cur.execute("""
            SELECT id
            FROM accounting_entries
            WHERE origin = 'COLLECTIONS'
              AND origin_id = %s
            LIMIT 1
        """, (collection_id,))
        row_entry = cur.fetchone()
        entry_id = row_entry["id"] if row_entry else None

        detail_text = f"From Collections {numero}"

        # ========================================================
        # 7️⃣ SI NO EXISTE → CREAR
        # ========================================================
        if not entry_id:

            cur.execute("""
                INSERT INTO accounting_entries (
                    entry_date,
                    period,
                    description,
                    origin,
                    origin_id,
                    created_by
                )
                VALUES (%s, %s, %s, %s, %s, 'SYSTEM')
                RETURNING id
            """, (
                fecha,
                period,
                detail_text,
                "COLLECTIONS",
                collection_id
            ))
            entry_id = cur.fetchone()["id"]

            # CxC (debe)
            cur.execute("""
                INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                entry_id, "1101", "Cuentas por cobrar",
                total_crc, 0, detail_text
            ))

            # Ingresos (haber)
            cur.execute("""
                INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                entry_id, "4101", "Ingresos por servicios",
                0, subtotal, detail_text
            ))

            # IVA por pagar (haber)
            if iva > 0:
                cur.execute("""
                    INSERT INTO accounting_lines
                    (entry_id, account_code, account_name, debit, credit, line_description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    entry_id, "2108", "IVA por pagar",
                    0, iva, detail_text
                ))

        # ========================================================
        # 8️⃣ SI YA EXISTE → CORREGIR (ESTO ES LO QUE TE FALTABA)
        # ========================================================
        else:
            # Asegurar descripción si está vacía
            cur.execute("""
                UPDATE accounting_lines
                SET line_description = %s
                WHERE entry_id = %s
                  AND (line_description IS NULL OR BTRIM(line_description) = '')
            """, (detail_text, entry_id))

            # 8.1) CxC (1101) debe = total_crc
            cur.execute("""
                UPDATE accounting_lines
                SET debit = %s, credit = 0, account_name = 'Cuentas por cobrar'
                WHERE entry_id = %s
                  AND account_code = '1101'
            """, (total_crc, entry_id))

            # 8.2) Ingresos (4101) haber = subtotal
            cur.execute("""
                UPDATE accounting_lines
                SET debit = 0, credit = %s, account_name = 'Ingresos por servicios'
                WHERE entry_id = %s
                  AND account_code = '4101'
            """, (subtotal, entry_id))

            # 8.3) IVA (2108) si aplica: crear o actualizar, si no aplica: eliminar
            if iva > 0:
                cur.execute("""
                    SELECT id
                    FROM accounting_lines
                    WHERE entry_id = %s
                      AND account_code = '2108'
                    LIMIT 1
                """, (entry_id,))
                row_iva = cur.fetchone()

                if row_iva:
                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = 0, credit = %s, account_name = 'IVA por pagar'
                        WHERE id = %s
                    """, (iva, row_iva["id"]))
                else:
                    cur.execute("""
                        INSERT INTO accounting_lines
                        (entry_id, account_code, account_name, debit, credit, line_description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (entry_id, "2108", "IVA por pagar", 0, iva, detail_text))
            else:
                cur.execute("""
                    DELETE FROM accounting_lines
                    WHERE entry_id = %s
                      AND account_code = '2108'
                """, (entry_id,))

    conn.commit()



def sync_cash_app_to_accounting(conn):

    from psycopg2.extras import RealDictCursor
    from datetime import date, datetime

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # 0️⃣ TRAER TODOS LOS PAGOS CASH_APP
    #    (con o sin asiento contable)
    # ============================================================
    cur.execute("""
        SELECT
            c.id,
            c.numero_documento,
            c.fecha_pago,
            c.monto_pagado,
            c.comision,
            a.id AS entry_id
        FROM cash_app c
        LEFT JOIN accounting_entries a
          ON a.origin = 'CASH_APP'
         AND a.origin_id = c.id
        ORDER BY c.id
    """)
    pagos = cur.fetchall()

    for p in pagos:

        cash_id = p["id"]
        numero = p.get("numero_documento") or ""
        fecha_pago = p.get("fecha_pago")

        if not fecha_pago:
            continue

        # Normalizar fecha
        if isinstance(fecha_pago, datetime):
            fecha = fecha_pago.date()
        else:
            fecha = fecha_pago

        monto = float(p.get("monto_pagado") or 0)
        comision = abs(float(p.get("comision") or 0))

        if monto <= 0:
            continue

        # ============================================================
        # 1️⃣ OBTENER TC POR FECHA DEL PAGO
        #     → fallback al último TC disponible
        # ============================================================
        cur.execute("""
            SELECT rate
            FROM exchange_rate
            WHERE rate_date = %s
            LIMIT 1
        """, (fecha,))
        row_tc = cur.fetchone()

        if not row_tc:
            # 🔁 Fallback: último TC disponible
            cur.execute("""
                SELECT rate
                FROM exchange_rate
                ORDER BY rate_date DESC
                LIMIT 1
            """)
            row_tc = cur.fetchone()

            if not row_tc:
                raise Exception(
                    "No existe ningún Tipo de Cambio registrado en el sistema."
                )

        tc = float(row_tc["rate"])

        # ============================================================
        # 2️⃣ CONVERSIÓN A CRC
        # ============================================================
        monto_crc = round(monto * tc, 2)
        comision_crc = round(comision * tc, 2)
        banco_crc = round(monto_crc - comision_crc, 2)

        if banco_crc < 0:
            raise Exception(
                f"Comisión mayor al monto en cash_app id={cash_id}"
            )

        period = fecha.strftime("%Y-%m")
        detail = f"Pago factura {numero}"

        # ============================================================
        # 3️⃣ ¿EXISTE ASIENTO?
        # ============================================================
        entry_id = p.get("entry_id")

        # ============================================================
        # 4️⃣ CREAR ASIENTO SI NO EXISTE
        # ============================================================
        if not entry_id:
            cur.execute("""
                INSERT INTO accounting_entries
                (entry_date, period, description, origin, origin_id, created_by)
                VALUES (%s, %s, %s, 'CASH_APP', %s, 'SYSTEM')
                RETURNING id
            """, (fecha, period, detail, cash_id))
            entry_id = cur.fetchone()["id"]
        else:
            # Asegurar cabecera actualizada
            cur.execute("""
                UPDATE accounting_entries
                SET entry_date = %s,
                    period = %s,
                    description = %s
                WHERE id = %s
            """, (fecha, period, detail, entry_id))

        # ============================================================
        # 5️⃣ LIMPIAR LÍNEAS EXISTENTES (CLAVE)
        # ============================================================
        cur.execute("""
            DELETE FROM accounting_lines
            WHERE entry_id = %s
        """, (entry_id,))

        # ============================================================
        # 6️⃣ RECREAR LÍNEAS CONTABLES
        # ============================================================

        # Bancos (neto)
        if banco_crc > 0:
            cur.execute("""
                INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
                VALUES (%s, '1010', 'Bancos', %s, 0, %s)
            """, (entry_id, banco_crc, detail))

        # Comisión bancaria
        if comision_crc > 0:
            cur.execute("""
                INSERT INTO accounting_lines
                (entry_id, account_code, account_name, debit, credit, line_description)
                VALUES (%s, '5203', 'Comisiones bancarias', %s, 0, %s)
            """, (entry_id, comision_crc, f"Comisión - {detail}"))

        # Cuentas por cobrar (total)
        cur.execute("""
            INSERT INTO accounting_lines
            (entry_id, account_code, account_name, debit, credit, line_description)
            VALUES (%s, '1101', 'Cuentas por cobrar', 0, %s, %s)
        """, (entry_id, monto_crc, detail))

    conn.commit()



def sync_itp_to_accounting(conn):
    """
    Sincroniza payment_obligations → accounting

    Reglas:
    - Si currency = 'USD' => multiplica por TC del día
    - Si currency = 'CRC' => NO convierte
    - Si payee_type = 'SUPPLIER' => el total incluye IVA (13%)
      → divide entre 1.13 para gasto (subtotal)
      → diferencia es IVA crédito fiscal
    - Genera asiento Gasto vs CxP (origin='ITP')
      - Si no existe: lo crea
      - Si ya existe: lo corrige (incluye/actualiza línea IVA)
    - Si status='PAID' y balance=0 => genera asiento CxP vs Bancos (origin='ITP_PAYMENT')
    """

    from psycopg2.extras import RealDictCursor
    from datetime import date

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ============================================================
    # 0️⃣ OBTENER TC DEL DÍA
    # ============================================================
    today = date.today()

    cur.execute("""
        SELECT rate
        FROM exchange_rate
        WHERE rate_date = %s
        LIMIT 1
    """, (today,))

    tc_row = cur.fetchone()
    if not tc_row:
        raise Exception("Tipo de cambio del día no encontrado. No se puede contabilizar ITP.")

    tc = float(tc_row["rate"])

    # ============================================================
    # 1️⃣ Traer obligaciones activas
    # ============================================================
    cur.execute("""
        SELECT
            p.id,
            p.payee_name,
            p.payee_type,
            p.obligation_type,
            p.reference,
            p.issue_date,
            p.last_payment_date,
            p.currency,
            p.total,
            p.balance,
            p.status,
            p.active
        FROM payment_obligations p
        WHERE p.active = TRUE
        ORDER BY p.id ASC
    """)
    obligations = cur.fetchall()

    # ============================================================
    # 2️⃣ Procesar una por una
    # ============================================================
    for ob in obligations:
        obligation_id = ob["id"]
        payee_name = (ob.get("payee_name") or "").strip() or "N/A"
        payee_type = (ob.get("payee_type") or "").upper()
        currency = (ob.get("currency") or "").upper()

        total_raw = float(ob.get("total") or 0)
        balance_raw = float(ob.get("balance") or 0)

        # -------------------------------
        # Conversión por moneda
        # -------------------------------
        if currency == "USD":
            total_crc = round(total_raw * tc, 2)
            balance_crc = round(balance_raw * tc, 2)
        else:
            total_crc = total_raw
            balance_crc = balance_raw

        # -------------------------------
        # IVA SOLO PARA SUPPLIER
        # -------------------------------
        if payee_type == "SUPPLIER":
            subtotal = round(total_crc / 1.13, 2)
            iva = round(total_crc - subtotal, 2)
        else:
            subtotal = total_crc
            iva = 0.0

        status = (ob.get("status") or "").upper()

        issue_date = ob.get("issue_date") or date.today()
        period = issue_date.strftime("%Y-%m")

        # ------------------------------------------------------------
        # Cuentas
        # ------------------------------------------------------------
        expense_account = "5101"
        expense_name = "Gastos de servicios"
        if ob.get("obligation_type") == "SURVEYOR_FEE":
            expense_account = "5102"
            expense_name = "Honorarios surveyor"

        ap_account = "2101"
        ap_name = "Cuentas por pagar"

        iva_account = "1131"
        iva_name = "IVA crédito fiscal"

        bank_account = "1102"
        bank_name = "Bancos"

        # ============================================================
        # A) ASIENTO GASTO vs CxP (origin='ITP')
        # ============================================================
        detail_text = f"From ITP {payee_name}"

        cur.execute("""
            SELECT id
            FROM accounting_entries
            WHERE origin = 'ITP'
              AND origin_id = %s
            LIMIT 1
        """, (obligation_id,))
        row_itp = cur.fetchone()
        itp_entry_id = row_itp["id"] if row_itp else None

        if not itp_entry_id:
            # --------------------------
            # Crear asiento
            # --------------------------
            from services.accounting_auto import create_accounting_entry

            lines = [
                {
                    "account_code": expense_account,
                    "account_name": expense_name,
                    "debit": subtotal,
                    "credit": 0,
                    "line_description": detail_text
                }
            ]

            if iva > 0:
                lines.append({
                    "account_code": iva_account,
                    "account_name": iva_name,
                    "debit": iva,
                    "credit": 0,
                    "line_description": detail_text
                })

            lines.append({
                "account_code": ap_account,
                "account_name": ap_name,
                "debit": 0,
                "credit": total_crc,
                "line_description": detail_text
            })

            create_accounting_entry(
                conn=conn,
                entry_date=issue_date,
                period=period,
                description=detail_text,
                origin="ITP",
                origin_id=obligation_id,
                lines=lines
            )

        else:
            # --------------------------
            # Corregir asiento existente
            # (aquí estaba el fallo: no se agregaba IVA)
            # --------------------------

            # 1) Asegurar detalle si está vacío
            cur.execute("""
                UPDATE accounting_lines
                SET line_description = %s
                WHERE entry_id = %s
                  AND (line_description IS NULL OR BTRIM(line_description) = '')
            """, (detail_text, itp_entry_id))

            # 2) Asegurar valores correctos en Gasto y CxP
            cur.execute("""
                UPDATE accounting_lines
                SET debit = %s, credit = 0
                WHERE entry_id = %s
                  AND account_code = %s
            """, (subtotal, itp_entry_id, expense_account))

            cur.execute("""
                UPDATE accounting_lines
                SET debit = 0, credit = %s
                WHERE entry_id = %s
                  AND account_code = %s
            """, (total_crc, itp_entry_id, ap_account))

            # 3) IVA: si es SUPPLIER debe existir línea 1131
            if iva > 0:
                cur.execute("""
                    SELECT id
                    FROM accounting_lines
                    WHERE entry_id = %s
                      AND account_code = %s
                    LIMIT 1
                """, (itp_entry_id, iva_account))
                iva_line = cur.fetchone()

                if iva_line:
                    cur.execute("""
                        UPDATE accounting_lines
                        SET debit = %s, credit = 0, account_name = %s
                        WHERE id = %s
                    """, (iva, iva_name, iva_line["id"]))
                else:
                    cur.execute("""
                        INSERT INTO accounting_lines
                        (entry_id, account_code, account_name, debit, credit, line_description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (itp_entry_id, iva_account, iva_name, iva, 0, detail_text))

            else:
                # Si NO es supplier, eliminar IVA si existiera (evita basura histórica)
                cur.execute("""
                    DELETE FROM accounting_lines
                    WHERE entry_id = %s
                      AND account_code = %s
                """, (itp_entry_id, iva_account))

        # ============================================================
        # B) ASIENTO DE PAGO (origin='ITP_PAYMENT')
        # ============================================================
        if status == "PAID" and balance_crc == 0:
            payment_date = ob.get("last_payment_date") or issue_date
            payment_period = payment_date.strftime("%Y-%m")
            payment_detail = f"From ITP Payment done to {payee_name}"

            cur.execute("""
                SELECT id
                FROM accounting_entries
                WHERE origin = 'ITP_PAYMENT'
                  AND origin_id = %s
                LIMIT 1
            """, (obligation_id,))
            row_pay = cur.fetchone()
            pay_entry_id = row_pay["id"] if row_pay else None

            if not pay_entry_id:
                from services.accounting_auto import create_accounting_entry

                pay_lines = [
                    {
                        "account_code": ap_account,
                        "account_name": ap_name,
                        "debit": total_crc,
                        "credit": 0,
                        "line_description": payment_detail
                    },
                    {
                        "account_code": bank_account,
                        "account_name": bank_name,
                        "debit": 0,
                        "credit": total_crc,
                        "line_description": payment_detail
                    }
                ]

                create_accounting_entry(
                    conn=conn,
                    entry_date=payment_date,
                    period=payment_period,
                    description=payment_detail,
                    origin="ITP_PAYMENT",
                    origin_id=obligation_id,
                    lines=pay_lines
                )

            else:
                # Corrige detalle y monto si existiera (se deja como en tu lógica original)
                cur.execute("""
                    UPDATE accounting_lines
                    SET line_description = %s
                    WHERE entry_id = %s
                      AND (line_description IS NULL OR BTRIM(line_description) = '')
                """, (payment_detail, pay_entry_id))

                cur.execute("""
                    UPDATE accounting_lines
                    SET debit = %s, credit = 0
                    WHERE entry_id = %s
                      AND account_code = %s
                """, (total_crc, pay_entry_id, ap_account))

                cur.execute("""
                    UPDATE accounting_lines
                    SET debit = 0, credit = %s
                    WHERE entry_id = %s
                      AND account_code = %s
                """, (total_crc, pay_entry_id, bank_account))

    conn.commit()
