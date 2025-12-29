from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date, datetime
import requests

from database import get_db

router = APIRouter(
    prefix="/exchange-rate",
    tags=["Exchange Rate"]
)

# ============================================================
# CONFIG BCCR (ÚNICO ENDPOINT VÁLIDO)
# ============================================================
BCCR_URL = (
    "https://centralenlinea.bccr.fi.cr/api/"
    "Bccr.GE.CPF.CMEP.Exportar.API/"
    "DatosPublicados/ObtengaDatosUltimoPeriodoPublicado"
)

BCCR_EMAIL = "aaron.avila@hotmail.es"
BCCR_TOKEN = "S8L8LAT0VI"


# ============================================================
# HELPER: CONSULTA TC DESDE BCCR (CSV)
# ============================================================
def _fetch_tc_from_bccr() -> tuple[float, date]:
    """
    Consulta el tipo de cambio más reciente al BCCR (CSV)
    Retorna: (rate, rate_date)
    """

    params = {
        "correo": BCCR_EMAIL,
        "token": BCCR_TOKEN
    }

    r = requests.get(BCCR_URL, params=params, timeout=15)
    r.raise_for_status()

    # CSV → líneas
    lines = r.text.strip().splitlines()

    if len(lines) < 2:
        raise HTTPException(
            status_code=500,
            detail="Respuesta inválida del BCCR (CSV vacío)"
        )

    headers = lines[0].split(",")
    values = lines[1].split(",")

    data = dict(zip(headers, values))

    try:
        rate = float(data["NUM_VALOR"])
        # DES_FECHA viene como dd/mm/yyyy
        rate_date = datetime.strptime(
            data["DES_FECHA"],
            "%d/%m/%Y"
        ).date()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error parseando respuesta BCCR: {e}"
        )

    return rate, rate_date


# ============================================================
# GET /exchange-rate/today
# ============================================================
@router.get("/today")
def get_today_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve el TC del día.
    Si ya existe en DB, NO consulta al BCCR.
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

    # 1️⃣ Buscar si ya existe
    cur.execute("""
        SELECT rate, rate_date
        FROM exchange_rate
        WHERE rate_date = %s
        LIMIT 1
    """, (today,))

    row = cur.fetchone()
    if row:
        return {
            "rate": float(row["rate"]),
            "date": row["rate_date"].isoformat()
        }

    # 2️⃣ Consultar BCCR
    rate, rate_date = _fetch_tc_from_bccr()

    # 3️⃣ Guardar en DB
    cur.execute("""
        INSERT INTO exchange_rate (rate, rate_date, source)
        VALUES (%s, %s, 'BCCR')
        ON CONFLICT (rate_date) DO NOTHING
    """, (rate, rate_date))

    conn.commit()

    return {
        "rate": rate,
        "date": rate_date.isoformat()
    }


# ============================================================
# GET /exchange-rate/latest
# ============================================================
@router.get("/latest")
def get_latest_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve el último TC registrado en la base de datos
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT rate, rate_date
        FROM exchange_rate
        ORDER BY rate_date DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No hay tipo de cambio registrado"
        )

    return {
        "rate": float(row["rate"]),
        "date": row["rate_date"].isoformat()
    }
