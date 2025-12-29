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

INDICADOR_COMPRA = "317"
INDICADOR_VENTA = "318"


# ============================================================
# HELPER: PARSE FECHA BCCR (ROBUSTO)
# ============================================================
def _parse_bccr_date(raw: str) -> date:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("DES_FECHA vacío")

    # Caso 1: ISO con timezone (ej: 2025-12-29T00:00:00-06:00)
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass

    # Caso 2: DD/MM/YYYY
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        pass

    # Caso 3: ISO sin timezone (por si acaso)
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Formato DES_FECHA no soportado: {raw}")


# ============================================================
# HELPER: CONSULTA TC VENTA DESDE BCCR (XML)
# ============================================================
def _fetch_tc_venta_from_bccr() -> tuple[float, date]:
    """
    Consulta TC de VENTA (Indicador 318) del día actual
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

    r = requests.get(BCCR_URL, params=params, timeout=30)
    r.raise_for_status()

    try:
        root = ET.fromstring(r.text)

        # Namespace típico del BCCR (pero a veces cambia)
        ns = {"ns": "http://ws.sdde.bccr.fi.cr"}

        value_node = root.find(".//ns:NUM_VALOR", ns)
        date_node = root.find(".//ns:DES_FECHA", ns)

        # Fallback sin namespace si viniera distinto
        if value_node is None:
            value_node = root.find(".//NUM_VALOR")
        if date_node is None:
            date_node = root.find(".//DES_FECHA")

        if value_node is None or date_node is None:
            # Esto te deja el XML en el error para diagnóstico rápido en Railway
            raise ValueError(f"NUM_VALOR/DES_FECHA no encontrados. XML snippet: {r.text[:300]}")

        rate = float((value_node.text or "").strip())
        rate_date = _parse_bccr_date(date_node.text)

        return rate, rate_date

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error parseando XML del BCCR: {repr(e)}"
        )


# ============================================================
# GET /exchange-rate/today
# ============================================================
@router.get("/today")
def get_today_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve el TC del día (VENTA).
    Si ya existe en BD, NO consulta al BCCR.
    """

    if not conn:
        raise HTTPException(500, "No DB connection")

    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

    # 1) Buscar en BD
    cur.execute("""
        SELECT rate, rate_date, source
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

    # 2) Consultar BCCR
    rate, rate_date = _fetch_tc_venta_from_bccr()

    # 3) Guardar en BD (sin depender de UNIQUE; si existe, mejor)
    try:
        cur.execute("""
            INSERT INTO exchange_rate (rate, rate_date, source)
            VALUES (%s, %s, 'BCCR')
        """, (rate, rate_date))
        conn.commit()

    except Exception as e:
        # Si falla por duplicado / falta de UNIQUE / carrera, no matamos el endpoint.
        conn.rollback()

        # Intentar leer lo que haya quedado guardado (si lo insertó otro proceso)
        cur.execute("""
            SELECT rate, rate_date, source
            FROM exchange_rate
            WHERE rate_date = %s
            LIMIT 1
        """, (rate_date,))
        row2 = cur.fetchone()
        if row2:
            return {
                "rate": float(row2["rate"]),
                "date": row2["rate_date"].isoformat(),
                "source": "CACHE"
            }

        # Si no hay nada, entonces sí devolvemos error real con detalle
        raise HTTPException(
            status_code=500,
            detail=f"Error insertando exchange_rate: {repr(e)}"
        )

    return {
        "rate": float(rate),
        "date": rate_date.isoformat(),
        "source": "BCCR"
    }


# ============================================================
# GET /exchange-rate/latest
# ============================================================
@router.get("/latest")
def get_latest_exchange_rate(conn=Depends(get_db)):
    """
    Devuelve el último TC registrado en la base de datos
    """

    if not conn:
        raise HTTPException(500, "No DB connection")

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
        "source": row.get("source") or "BCCR"
    }
