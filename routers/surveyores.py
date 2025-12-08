# backend_api/routers/surveyores.py
from fastapi import APIRouter
import database

router = APIRouter(prefix="/surveyores", tags=["Surveyores"])


@router.post("/add")
def add_surveyor(data: dict):
    sql = """
        INSERT INTO Surveyores (
            Codigo, Nombre, Apellidos, EstadoCivil, Genero,
            Nacionalidad, Prefijo, Telefono, Provincia, Canton,
            Distrito, Direccion, Jornada, Pago, Banco,
            CuentaIBAN, Moneda, swiftCode, uID,
            Enfermedades, ContactoEmergencia, TelEmergencia,
            Activo1, Marca1, Serial1,
            Activo2, Marca2, Serial2,
            Activo3, Marca3, Serial3
        )
        VALUES (
            %(codigo)s, %(nombre)s, %(apellidos)s, %(estado_civil)s, %(genero)s,
            %(nacionalidad)s, %(prefijo)s, %(telefono)s, %(provincia)s, %(canton)s,
            %(distrito)s, %(direccion)s, %(jornada)s, %(pago)s, %(banco)s,
            %(cuenta_iban)s, %(moneda)s, %(swift_code)s, %(uid)s,
            %(enfermedades)s, %(contacto_emergencia)s, %(telefono_emergencia)s,
            %(activo1)s, %(marca1)s, %(serial1)s,
            %(activo2)s, %(marca2)s, %(serial2)s,
            %(activo3)s, %(marca3)s, %(serial3)s
        );
    """
    database.sql(sql, data, commit=True)
    return {"status": "OK", "msg": "Surveyor registrado 💾✔"}
