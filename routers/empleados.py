from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import os

router = APIRouter(prefix="/empleados", tags=["Empleados"])

DB_URL = os.getenv("DATABASE_URL") or \
         "postgresql://postgres:LjjyuIUsTSCdiwPVHSSwtIYPOsRQytGX@shortline.proxy.rlwy.net:50018/railway"


class Empleado(BaseModel):
    codigo: str
    nombre: str
    apellidos: str
    estado_civil: str | None = None
    genero: str | None = None
    nacionalidad: str | None = None
    prefijo: str | None = None
    telefono: str | None = None
    provincia: str | None = None
    canton: str | None = None
    distrito: str | None = None
    direccion: str | None = None
    jornada: str | None = None
    salario: str | None = None
    pago: str | None = None
    banco: str | None = None
    cuenta_iban: str | None = None
    moneda: str | None = None
    enfermedades: str | None = None
    contacto_emergencia: str | None = None
    telefono_emergencia: str | None = None
    activo1: str | None = None
    marca1: str | None = None
    serial1: str | None = None
    activo2: str | None = None
    marca2: str | None = None
    serial2: str | None = None
    activo3: str | None = None
    marca3: str | None = None
    serial3: str | None = None


@router.post("/add")
def agregar_empleado(emp: Empleado):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO empleados (
                codigo, nombre, apellidos, estado_civil, genero, nacionalidad,
                prefijo, telefono, provincia, canton, distrito, direccion,
                jornada, salario, pago, banco, cuenta_iban, moneda,
                enfermedades, contacto_emergencia, telefono_emergencia,
                activo1, marca1, serial1,
                activo2, marca2, serial2,
                activo3, marca3, serial3
            )
            VALUES (
                %(codigo)s, %(nombre)s, %(apellidos)s, %(estado_civil)s, %(genero)s, %(nacionalidad)s,
                %(prefijo)s, %(telefono)s, %(provincia)s, %(canton)s, %(distrito)s, %(direccion)s,
                %(jornada)s, %(salario)s, %(pago)s, %(banco)s, %(cuenta_iban)s, %(moneda)s,
                %(enfermedades)s, %(contacto_emergencia)s, %(telefono_emergencia)s,
                %(activo1)s, %(marca1)s, %(serial1)s,
                %(activo2)s, %(marca2)s, %(serial2)s,
                %(activo3)s, %(marca3)s, %(serial3)s
            );
        """, emp.dict())

        conn.commit()

        return {"status": "OK", "msg": "Empleado registrado 💾✔"}

    except Exception as e:
        print("❌ Error API empleados:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cursor.close()
        conn.close()


# ============================================================
# LISTAR EMPLEADOS — Paginado (Corregido)
# ============================================================
@router.get("/")
def get_empleados(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size

    rows = database.sql(f"""
        SELECT
            codigo, nombre, apellidos, estado_civil, genero, nacionalidad,
            prefijo, telefono, provincia, canton, distrito, direccion,
            jornada, salario, pago, banco, cuenta_iban, moneda,
            enfermedades, contacto_emergencia, telefono_emergencia,
            activo1, marca1, serial1,
            activo2, marca2, serial2,
            activo3, marca3, serial3
        FROM empleados
        ORDER BY codigo ASC
        LIMIT {page_size} OFFSET {offset}
    """, fetch=True)

    total = database.sql("SELECT COUNT(*) FROM empleados", fetch=True)[0][0]

    columnas = [
        "codigo","nombre","apellidos","estado_civil","genero","nacionalidad",
        "prefijo","telefono","provincia","canton","distrito","direccion",
        "jornada","salario","pago","banco","cuenta_iban","moneda",
        "enfermedades","contacto_emergencia","telefono_emergencia",
        "activo1","marca1","serial1",
        "activo2","marca2","serial2",
        "activo3","marca3","serial3",
    ]

    data = []
    for r in rows:
        fila = {}
        for i, col in enumerate(columnas):
            valor = r[i]
            fila[col] = "" if valor is None else str(valor)
        data.append(fila)

    return {"data": data, "total": total}


# ============================================================
# UPDATE — 100% alineado
# ============================================================
@router.put("/update")
def update_empleado(data: dict):
    sql = """
        UPDATE empleados SET
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
            salario = %(salario)s,
            pago = %(pago)s,
            banco = %(banco)s,
            cuenta_iban = %(cuenta_iban)s,
            moneda = %(moneda)s,
            enfermedades = %(enfermedades)s,
            contacto_emergencia = %(contacto_emergencia)s,
            telefono_emergencia = %(telefono_emergencia)s,
            activo1 = %(activo1)s,
            marca1 = %(marca1)s,
            serial1 = %(serial1)s,
            activo2 = %(activo2)s,
            marca2 = %(marca2)s,
            serial2 = %(serial2)s,
            activo3 = %(activo3)s,
            marca3 = %(marca3)s,
            serial3 = %(serial3)s
        WHERE codigo = %(codigo)s
    """
    try:
        database.sql(sql, data)
        return {"status": "OK", "msg": "Empleado actualizado ✔"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# DELETE — igual que Servicios
# ============================================================
@router.delete("/{codigo}")
def delete_empleado(codigo: str):
    try:
        database.sql("DELETE FROM empleados WHERE codigo = %s", (codigo,))
        return {"status": "OK", "msg": "Empleado eliminado 🗑️"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))