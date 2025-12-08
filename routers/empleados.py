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


@router.post("")
def agregar_empleado(emp: Empleado):
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO empleados (
                Codigo, Nombre, Apellidos, EstadoCivil, Genero, Nacionalidad,
                Prefijo, Telefono, Provincia, Canton, Distrito, Direccion,
                Jornada, Salario, Pago, Banco, CuentaIBAN, Moneda,
                Enfermedades, ContactoEmergencia, TelefonoEmergencia,
                Activo1, Marca1, Serial1,
                Activo2, Marca2, Serial2,
                Activo3, Marca3, Serial3
            ) VALUES (
                %(codigo)s, %(nombre)s, %(apellidos)s, %(estado_civil)s, %(genero)s, %(nacionalidad)s,
                %(prefijo)s, %(telefono)s, %(provincia)s, %(canton)s, %(distrito)s, %(direccion)s,
                %(jornada)s, %(salario)s, %(pago)s, %(banco)s, %(cuenta_iban)s, %(moneda)s,
                %(enfermedades)s, %(contacto_emergencia)s, %(telefono_emergencia)s,
                %(activo1)s, %(marca1)s, %(serial1)s,
                %(activo2)s, %(marca2)s, %(serial2)s,
                %(activo3)s, %(marca3)s, %(serial3)s
            )
        """, emp.dict())

        conn.commit()

        return {"status": "OK", "mensaje": "Empleado guardado correctamente"}

    except Exception as e:
        print("❌ Error API empleados:", e)
        raise HTTPException(status_code=500, detail="Error guardando empleado")

    finally:
        cursor.close()
        conn.close()
