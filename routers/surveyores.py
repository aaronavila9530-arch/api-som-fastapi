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
        database.sql(sql, data, commit=True)
        return {"status": "OK", "msg": "Surveyor registrado 💾✔"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
