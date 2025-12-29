from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from datetime import date, datetime
import requests
import xml.etree.ElementTree as ET

from database import get_db

router = APIRouter(
    prefix="/exchange-rate",
    tags=["Exchange Rate"]
)

# ============================================================
# CONFIG BCCR — ENDPOINT OFICIAL
# ============================================================
BCCR_URL = (
    "https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/"
    "wsindicadoreseconomicos.asmx/ObtenerIndicadoresEconomicos"
)

BCCR_EMAIL = "aaron.avila@hotmail.es"
BCCR_TOKEN = "S8L8LAT0VI"
BCCR_NOMBRE = "MSL"

INDICADOR_VENTA = "318"


# ============================================================
# HELPER: TC VENTA DESDE BCCR (XML)
# ============================================================
def _fetch_tc_venta_from_bccr() -> tuple[float, date]:
    """
    Consulta TC de VENTA (Indicador 318)
    Retorna: (rate, rate_date)
    """

    today_str = date.today().strftime("%d/%m/%Y")

    params = {
        "Indicador": INDICADOR_VENTA,
        "FechaInicio": today_str,
        "FechaFinal": today_str,
        "Nombre": BCCR_NOMBRE,
        "SubNiveles": "N",
        "CorreoElectronico": BCCR_EMAIL,
        "Token": BCCR_TOKEN
    }

    r = requests.get(BCCR_URL, params=params, timeout=20)
    r.raise_for_status()

    try:
        root = ET.fromstring(r.text)
        ns = {"ns": "http://ws.sdde.bccr.fi.cr"}

        value_node = root.find(".//ns:NUM_VALOR", ns)
        date_node = root.find(".//ns:DES_FECHA", ns)

        if value_node is None or date_node is None:
            raise ValueError("NUM_VALOR o DES_FECHA no encontrados")

        rate = float(value_node.text)
        raw_date = date_node.text.strip()

        # ✅ SOPORTA AMBOS FORMATOS DEL BCCR
        try:
            rate_date = datetime.fromisoformat(raw_date).date()
        except ValueError:
            rate_date = datetime.strptime(raw_date, "%d/%m/%Y").date()

        return rate, rate_date

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error parseando XML del BCCR: {e}"
        )


# ============================================================
# GET /exchange-rate/today
# ============================================================
@router.get("/today")
def get_today_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve TC del día (VENTA)
    - Si existe en BD → CACHE
    - Si no existe → BCCR → INSERT
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

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
            "date": row["rate_date"].isoformat(),
            "source": "CACHE"
        }

    rate, rate_date = _fetch_tc_venta_from_bccr()

    cur.execute("""
        INSERT INTO exchange_rate (rate, rate_date, source)
        VALUES (%s, %s, 'BCCR')
        ON CONFLICT (rate_date) DO NOTHING
    """, (rate, rate_date))

    conn.commit()

    return {
        "rate": rate,
        "date": rate_date.isoformat(),
        "source": "BCCR"
    }


# ============================================================
# GET /exchange-rate/latest
# ============================================================
@router.get("/latest")
def get_latest_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve el último TC registrado
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT rate, rate_date, source
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
        "date": row["rate_date"].isoformat(),
        "source": row.get("source", "BCCR")
    }
