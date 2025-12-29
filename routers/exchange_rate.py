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
# CONFIG BCCR — ÚNICO ENDPOINT VÁLIDO (XML)
# ============================================================
BCCR_URL = (
    "https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/"
    "wsindicadoreseconomicos.asmx/ObtenerIndicadoresEconomicos"
)

BCCR_EMAIL = "aaron.avila@hotmail.es"
BCCR_TOKEN = "S8L8LAT0VI"
BCCR_NOMBRE = "MSL"

# Indicadores oficiales BCCR
INDICADOR_COMPRA = "317"
INDICADOR_VENTA = "318"


# ============================================================
# HELPER: CONSULTA TC VENTA DESDE BCCR (XML)
# ============================================================
def _fetch_tc_venta_from_bccr() -> tuple[float, date]:
    """
    Consulta el Tipo de Cambio de VENTA (Indicador 318)
    usando SIEMPRE la fecha del día.
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

        # Namespace oficial del BCCR
        ns = {"ns": "http://ws.sdde.bccr.fi.cr"}

        value_node = root.find(".//ns:NUM_VALOR", ns)
        date_node = root.find(".//ns:DES_FECHA", ns)

        if value_node is None or date_node is None:
            raise ValueError("NUM_VALOR o DES_FECHA no encontrados en XML")

        rate = float(value_node.text)

        # ⚠️ CORRECCIÓN CRÍTICA:
        # BCCR devuelve fecha en formato DD/MM/YYYY
        rate_date = datetime.strptime(
            date_node.text.strip(),
            "%d/%m/%Y"
        ).date()

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
    Devuelve el Tipo de Cambio del día (VENTA).
    - Si ya existe en BD → NO consulta BCCR
    - Si no existe → consulta BCCR y guarda
    """

    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

    # --------------------------------------------------------
    # 1️⃣ Buscar TC del día en BD
    # --------------------------------------------------------
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

    # --------------------------------------------------------
    # 2️⃣ Consultar BCCR (VENTA)
    # --------------------------------------------------------
    rate, rate_date = _fetch_tc_venta_from_bccr()

    # --------------------------------------------------------
    # 3️⃣ Guardar en BD (sin sobreescribir)
    # --------------------------------------------------------
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
    Devuelve el último Tipo de Cambio registrado en BD
    (NO consulta al BCCR)
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
