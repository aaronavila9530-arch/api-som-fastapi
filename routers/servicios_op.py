from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import database

router = APIRouter(prefix="/servicios", tags=["Servicios"])

# ============================================
# MODELO PARA DEMORAS
# ============================================
class DemoraUpdate(BaseModel):
    total: str



# ============================================================
# MODELO DE INSERCIÓN DESDE POPUP
# ============================================================
class ServicioCreate(BaseModel):
    tipo: str
    buque_contenedor: str
    cliente: str
    contacto: str | None = None
    detalle: str | None = None
    continente: str
    pais: str
    puerto: str
    operacion: str
    surveyor: str
    honorarios: float | None = None
    costo_operativo: float | None = None
    fecha_inicio: str    # "YYYY-MM-DD"
    hora_inicio: str     # "HH:MM"


# ============================================================
# INSERTAR SERVICIO
# ============================================================
@router.post("/add")
def add_servicio(data: ServicioCreate):

    sql = """
        INSERT INTO servicios (
            tipo, estado, num_informe,
            buque_contenedor, cliente, contacto, detalle,
            continente, pais, puerto,
            operacion, surveyor, honorarios, costo_operativo,
            fecha_inicio, hora_inicio
        )
        VALUES (
            %(tipo)s, 'Buque por confirmar', '',
            %(buque_contenedor)s, %(cliente)s, %(contacto)s, %(detalle)s,
            %(continente)s, %(pais)s, %(puerto)s,
            %(operacion)s, %(surveyor)s, %(honorarios)s, %(costo_operativo)s,
            %(fecha_inicio)s, %(hora_inicio)s
        )
        RETURNING consec;
    """

    try:
        result = database.sql(sql, data.dict(), fetch=True)
        new_id = result[0][0]
        return {"status": "OK", "msg": "Servicio creado", "consec": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# LISTAR — PAGINADO
# ============================================================
@router.get("/")
def listar_servicios(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT
            consec, tipo, estado, num_informe,
            buque_contenedor, cliente, contacto, detalle,
            continente, pais, puerto,
            operacion, surveyor, honorarios, costo_operativo,
            fecha_inicio, hora_inicio,
            fecha_fin, hora_fin, demoras, duracion,
            factura, valor_factura, fecha_factura,
            terminos_pago, fecha_vencimiento, dias_vencido,
            razon_cancelacion, comentario_cancelacion
        FROM servicios
        ORDER BY consec DESC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM servicios", fetch=True)[0][0]

    columnas = [
        "consec", "tipo", "estado", "num_informe",
        "buque_contenedor", "cliente", "contacto", "detalle",
        "continente", "pais", "puerto",
        "operacion", "surveyor", "honorarios", "costo_operativo",
        "fecha_inicio", "hora_inicio",
        "fecha_fin", "hora_fin", "demoras", "duracion",
        "factura", "valor_factura", "fecha_factura",
        "terminos_pago", "fecha_vencimiento", "dias_vencido",
        "razon_cancelacion", "comentario_cancelacion"
    ]

    data = []
    for r in rows:
        item = {c: ("" if r[i] is None else str(r[i])) for i, c in enumerate(columnas)}
        data.append(item)

    return {"total": total, "data": data}


# ============================================================
# GET POR CONSEC
# ============================================================
@router.get("/{consec}")
def get_servicio(consec: int):
    row = database.sql("""
        SELECT
            consec, tipo, estado, num_informe,
            buque_contenedor, cliente, contacto, detalle,
            continente, pais, puerto,
            operacion, surveyor, honorarios, costo_operativo,
            fecha_inicio, hora_inicio,
            fecha_fin, hora_fin, demoras, duracion,
            factura, valor_factura, fecha_factura,
            terminos_pago, fecha_vencimiento, dias_vencido,
            razon_cancelacion, comentario_cancelacion
        FROM servicios
        WHERE consec = %s
    """, (consec,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    r = row[0]
    columnas = [
        "consec", "tipo", "estado", "num_informe",
        "buque_contenedor", "cliente", "contacto", "detalle",
        "continente", "pais", "puerto",
        "operacion", "surveyor", "honorarios", "costo_operativo",
        "fecha_inicio", "hora_inicio",
        "fecha_fin", "hora_fin", "demoras", "duracion",
        "factura", "valor_factura", "fecha_factura",
        "terminos_pago", "fecha_vencimiento", "dias_vencido",
        "razon_cancelacion", "comentario_cancelacion"
    ]

    return {c: ("" if r[i] is None else str(r[i])) for i, c in enumerate(columnas)}


@router.delete("/{consec}")
def eliminar_servicio(consec: int):
    try:
        sql = "DELETE FROM servicios WHERE consec = %s"
        database.sql(sql, (consec,))

        return {"status": "ok", "msg": f"Servicio {consec} eliminado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





@router.put("/cancelar/{consec}")
def cancelar_servicio(consec: int, data: dict):
    try:
        sql = """
            UPDATE servicios
            SET estado = %(estado)s,
                razon_cancelacion = %(razon_cancelacion)s,
                comentario_cancelacion = %(comentario_cancelacion)s
            WHERE consec = %(consec)s
        """

        params = {
            "estado": data.get("estado", "Cancelado"),
            "razon_cancelacion": data.get("razon_cancelacion", ""),
            "comentario_cancelacion": data.get("comentario_cancelacion", ""),
            "consec": consec
        }

        database.sql(sql, params)
        return {"status": "ok", "msg": f"Servicio {consec} cancelado"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.put("/por_confirmar/{consec}")
def marcar_por_confirmar(consec: int):
    try:
        sql = """
            UPDATE servicios
            SET estado = 'Por confirmar'
            WHERE consec = %s
        """
        database.sql(sql, (consec,))
        return {"status": "ok", "msg": f"Servicio {consec} marcado como 'Por confirmar'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/confirmar/{consec}")
def confirmar_servicio(consec: int, data: dict):
    try:
        sql = """
            UPDATE servicios
            SET fecha_inicio = %(fecha_inicio)s,
                hora_inicio = %(hora_inicio)s,
                estado = 'Confirmado'
            WHERE consec = %(consec)s
        """
        params = {
            "fecha_inicio": data.get("fecha_inicio"),
            "hora_inicio": data.get("hora_inicio"),
            "consec": consec
        }

        database.sql(sql, params)
        return {"status": "ok", "msg": f"Servicio {consec} confirmado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.put("/demoras/{consec}")
def actualizar_demoras(consec: int, payload: DemoraUpdate):

    total = payload.total

    try:
        database.sql(
            "UPDATE servicios SET demoras = %s WHERE consec = %s",
            (total, consec)
        )
        return {"status": "ok", "msg": "Demoras actualizadas", "total": total}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# EDITAR SERVICIO (SIN CAMBIAR ESTADO)
# ============================================================
@router.put("/editar/{consec}")
def editar_servicio(consec: int, data: dict):
    try:
        sql = """
            UPDATE servicios SET
                surveyor = %(surveyor)s,
                honorarios = %(honorarios)s,
                costo_operativo = %(costo_operativo)s,
                fecha_inicio = %(fecha_inicio)s,
                hora_inicio = %(hora_inicio)s
            WHERE consec = %(consec)s
        """

        params = {
            "surveyor": data.get("surveyor"),
            "honorarios": data.get("honorarios"),
            "costo_operativo": data.get("costo_operativo"),
            "fecha_inicio": data.get("fecha_inicio"),
            "hora_inicio": data.get("hora_inicio"),
            "consec": consec
        }

        database.sql(sql, params)
        return {"status": "ok", "msg": "Servicio actualizado"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================
# Generar informe
# ============================================================


@router.put("/cerrar/{consec}")
def cerrar_operacion(consec: int, data: dict):
    database.sql("""
        UPDATE servicios
        SET fecha_fin=%(f)s, hora_fin=%(h)s
        WHERE consec=%(c)s
    """, {
        "f": data["fecha_fin"],
        "h": data["hora_fin"],
        "c": consec
    })
    return {"status": "ok"}



@router.put("/generar_informe/{consec}")
def generar_informe(consec: int):
    try:
        # 1) Obtener fecha_inicio (puede venir como date o como str)
        row = database.sql(
            "SELECT fecha_inicio FROM servicios WHERE consec = %s",
            (consec,),
            fetch=True
        )
        if not row or not row[0][0]:
            raise HTTPException(status_code=400, detail="Servicio sin fecha_inicio.")

        fecha_inicio = row[0][0]
        if isinstance(fecha_inicio, str):
            # Si viene como "YYYY-MM-DD"
            fecha_inicio_dt = datetime.strptime(fecha_inicio[:10], "%Y-%m-%d")
        else:
            # Si viene como date/datetime
            fecha_inicio_dt = fecha_inicio

        ddmm = fecha_inicio_dt.strftime("%d%m")
        year = fecha_inicio_dt.strftime("%Y")

        # 2) Calcular consecutivo: max de la parte numérica antes del '-'
        # Solo toma registros que cumplan ^\d+-
        max_row = database.sql(
            r"""
            SELECT COALESCE(
                MAX( (regexp_match(num_informe, '^(\d+)-'))[1]::int ),
                0
            )
            FROM servicios
            WHERE num_informe ~ '^\d+-'
            """,
            fetch=True
        )
        ultimo = int(max_row[0][0] or 0)
        nuevo = ultimo + 1

        num_informe = f"{nuevo}-{ddmm}-{year}"

        # 3) Actualizar servicio: num_informe y estado finalizado
        database.sql(
            """
            UPDATE servicios
            SET num_informe = %s,
                estado = 'Finalizado'
            WHERE consec = %s
            """,
            (num_informe, consec)
        )

        return {"status": "ok", "num_informe": num_informe}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/fecha_fin/{consec}")
def actualizar_fecha_fin(consec: int, data: dict):
    database.sql(
        """
        UPDATE servicios
        SET fecha_fin = %(fecha_fin)s,
            hora_fin = %(hora_fin)s
        WHERE consec = %(consec)s
        """,
        {
            "fecha_fin": data["fecha_fin"],
            "hora_fin": data["hora_fin"],
            "consec": consec
        }
    )
    return {"status": "ok"}

