from fastapi import APIRouter, HTTPException
import database

router = APIRouter(prefix="/surveyores", tags=["Surveyores"])


@router.post("/add")
def add_surveyor(data: dict):
    try:
        sql = """
        INSERT INTO surveyor (
            codigo,
            nombre,
            apellidos,
            estado_civil,
            genero,
            nacionalidad,
            prefijo,
            telefono,
            provincia,
            canton,
            distrito,
            direccion,
            jornada,
            operacion,
            honorario,
            pago,
            banco,
            cuenta_iban,
            moneda,
            swift,
            uid,
            enfermedades,
            contacto_emergencia,
            telefono_emergencia,
            puerto
        )
        VALUES (
            %(codigo)s,
            %(nombre)s,
            %(apellidos)s,
            %(estado_civil)s,
            %(genero)s,
            %(nacionalidad)s,
            %(prefijo)s,
            %(telefono)s,
            %(provincia)s,
            %(canton)s,
            %(distrito)s,
            %(direccion)s,
            %(jornada)s,
            %(operacion)s,
            %(honorario)s,
            %(pago)s,
            %(banco)s,
            %(cuenta_iban)s,
            %(moneda)s,
            %(swift)s,
            %(uid)s,
            %(enfermedades)s,
            %(contacto_emergencia)s,
            %(telefono_emergencia)s,
            %(puerto)s
        );
        """
        database.sql(sql, data)
        return {"status": "OK", "msg": "Surveyor registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# OBTENER ÚLTIMO CÓDIGO CORRELATIVO
# ============================================================
@router.get("/ultimo")
def get_ultimo_surveyor():
    sql = """
        SELECT MAX(CAST(SUBSTRING(codigo FROM 5 FOR 4) AS INTEGER))
        FROM surveyor;
    """
    result = database.sql(sql, fetch=True)
    ultimo = result[0][0] if result and result[0][0] is not None else 0
    return {"ultimo": ultimo}


# ============================================================
# LISTAR SURVEYORS — PAGINADO
# ============================================================
@router.get("/")
def get_surveyores(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT
            codigo,nombre,apellidos,estado_civil,genero,nacionalidad,
            prefijo,telefono,provincia,canton,distrito,direccion,
            jornada,operacion,honorario,pago,banco,cuenta_iban,
            moneda,swift,uid,enfermedades,contacto_emergencia,
            telefono_emergencia,puerto
        FROM surveyor
        ORDER BY codigo ASC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM surveyor", fetch=True)[0][0]

    data = [
        {
            "codigo": r[0],
            "nombre": r[1],
            "apellidos": r[2],
            "estado_civil": r[3],
            "genero": r[4],
            "nacionalidad": r[5],
            "prefijo": r[6],
            "telefono": r[7],
            "provincia": r[8],
            "canton": r[9],
            "distrito": r[10],
            "direccion": r[11],
            "jornada": r[12],
            "operacion": r[13],
            "honorario": r[14],
            "pago": r[15],
            "banco": r[16],
            "cuenta_iban": r[17],
            "moneda": r[18],
            "swift": r[19],
            "uid": r[20],
            "enfermedades": r[21],
            "contacto_emergencia": r[22],
            "telefono_emergencia": r[23],
            "puerto": r[24],
        }
        for r in rows
    ]

    return {"total": total, "data": data}


# ============================================================
# OBTENER UN SURVEYOR POR CÓDIGO
# ============================================================
@router.get("/{codigo}")
def get_surveyor(codigo: str):
    row = database.sql("""
        SELECT
            codigo,nombre,apellidos,estado_civil,genero,nacionalidad,
            prefijo,telefono,provincia,canton,distrito,direccion,
            jornada,operacion,honorario,pago,banco,cuenta_iban,
            moneda,swift,uid,enfermedades,contacto_emergencia,
            telefono_emergencia,puerto
        FROM surveyor
        WHERE codigo = %s
    """, (codigo,), fetch=True)

    if not row:
        raise HTTPException(status_code=404, detail="Surveyor no encontrado")

    r = row[0]
    return {
        "codigo": r[0],
        "nombre": r[1],
        "apellidos": r[2],
        "estado_civil": r[3],
        "genero": r[4],
        "nacionalidad": r[5],
        "prefijo": r[6],
        "telefono": r[7],
        "provincia": r[8],
        "canton": r[9],
        "distrito": r[10],
        "direccion": r[11],
        "jornada": r[12],
        "operacion": r[13],
        "honorario": r[14],
        "pago": r[15],
        "banco": r[16],
        "cuenta_iban": r[17],
        "moneda": r[18],
        "swift": r[19],
        "uid": r[20],
        "enfermedades": r[21],
        "contacto_emergencia": r[22],
        "telefono_emergencia": r[23],
        "puerto": r[24],
    }


# ============================================================
# ACTUALIZAR SURVEYOR
# ============================================================
@router.put("/update")
def update_surveyor(data: dict):
    sql = """
        UPDATE surveyor SET
            nombre = %(nombre)s,
            apellidos = %(apellidos)s,
            estado_civil = %(estado_civil)s,
            genero = %(genero)s,
            nacionalidad = %(nacionalidad)s,
            prefijo = %(prefijo)s,
            telefono = %(telefono)s,
            provincia = %(provincia)s,
            canton = %(canton)s,
            distrito = %(distrito)s,
            direccion = %(direccion)s,
            jornada = %(jornada)s,
            operacion = %(operacion)s,
            honorario = %(honorario)s,
            pago = %(pago)s,
            banco = %(banco)s,
            cuenta_iban = %(cuenta_iban)s,
            moneda = %(moneda)s,
            swift = %(swift)s,
            uid = %(uid)s,
            enfermedades = %(enfermedades)s,
            contacto_emergencia = %(contacto_emergencia)s,
            telefono_emergencia = %(telefono_emergencia)s,
            puerto = %(puerto)s
        WHERE codigo = %(codigo)s
    """
    try:
        database.sql(sql, data)
        return {"status": "OK", "msg": "Surveyor actualizado ✔"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ELIMINAR SURVEYOR
# ============================================================
@router.delete("/{codigo}")
def delete_surveyor(codigo: str):
    try:
        database.sql("DELETE FROM surveyor WHERE codigo = %s", (codigo,))
        return {"status": "OK", "msg": "Surveyor eliminado 🗑️"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
