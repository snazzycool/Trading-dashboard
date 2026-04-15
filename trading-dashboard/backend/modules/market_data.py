"""
modules/market_data.py — TwelveData REST client with caching.
"""
import logging
import time
from typing import Optional
import requests
import pandas as pd
import config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.twelvedata.com/time_series"
_TIMEOUT   = 15
_MAX_RETRIES = 2
_RETRY_DELAY = 3
_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 60   # seconds

def get_candles(symbol: str, interval: str, bars: int = config.BARS_REQUIRED) -> Optional[pd.DataFrame]:
    key = (symbol, interval)
    now = time.monotonic()
    if key in _CACHE:
        ts, df = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return df
    df = _fetch(symbol, interval, bars)
    if df is not None:
        _CACHE[key] = (now, df)
    return df

def get_current_price(symbol: str) -> Optional[float]:
    df = get_candles(symbol, "1min", bars=1)
    if df is not None and not df.empty:
        return float(df["close"].iloc[-1])
    return None

def _fetch(symbol: str, interval: str, bars: int) -> Optional[pd.DataFrame]:
    params = {
        "symbol":     symbol,
        "interval":   interval,
        "outputsize": bars,
        "order":      "ASC",
        "apikey":     config.TWELVEDATA_API_KEY,
    }
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            resp = requests.get(_BASE_URL, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") == "error":
                logger.warning("TwelveData error %s/%s: %s", symbol, interval, payload.get("message"))
                return None
            return _parse(payload)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403, 429):
                break
            logger.warning("HTTP error %s/%s: %s", symbol, interval, e)
        except requests.exceptions.RequestException as e:
            logger.warning("Request error %s/%s: %s", symbol, interval, e)
        except Exception as e:
            logger.error("Unexpected error %s/%s: %s", symbol, interval, e)
            break
        if attempt <= _MAX_RETRIES:
            time.sleep(_RETRY_DELAY)
    return None

def _parse(payload: dict) -> Optional[pd.DataFrame]:
    try:
        values = payload.get("values", [])
        if not values:
            return None
        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.error("Parse error: %s", e)
        return None

def is_active_session() -> bool:
    if config.ACTIVE_SESSION_HOURS is None:
        return True
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in config.ACTIVE_SESSION_HOURS)
