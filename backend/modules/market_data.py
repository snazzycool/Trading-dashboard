"""
modules/market_data.py — TwelveData REST client.

Fixes applied:
  1. Rate limiter — enforces max 8 calls/minute (free tier limit)
     by adding a delay between requests so all 14 calls across
     7 pairs × 2 timeframes never exceed 8/minute.
  2. Volume handling — volume column is optional. XAU/USD and
     most forex pairs don't return volume from TwelveData.
     Parser now works with or without it.
"""
import logging
import time
import threading
from typing import Optional
import requests
import pandas as pd
import config

logger = logging.getLogger(__name__)

_BASE_URL    = "https://api.twelvedata.com/time_series"
_TIMEOUT     = 15
_MAX_RETRIES = 2
_RETRY_DELAY = 3

# ── Cache ─────────────────────────────────────────────────────────────────
_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 120  # increased to 2 minutes for better API efficiency

# ── Per-minute rate limiter ───────────────────────────────────────────────
# TwelveData free tier: max 8 calls per minute + 800 per day.
# We enforce a minimum gap of 8 seconds between any two API calls
# (60s / 8 calls = 7.5s per call → we use 8s to be safe).
# Smart caching reduces API calls by reusing data across scans.
_RATE_LOCK        = threading.Lock()
_LAST_CALL_TIME   = 0.0
_MIN_CALL_GAP     = 8.0  # seconds between calls
_DAILY_CALL_COUNT = 0
_DAILY_RESET_DAY  = None


def _rate_limited_get(params: dict) -> Optional[requests.Response]:
    """Make a GET request, respecting per-minute and daily rate limits."""
    global _LAST_CALL_TIME, _DAILY_CALL_COUNT, _DAILY_RESET_DAY

    with _RATE_LOCK:
        now = time.time()
        elapsed = now - _LAST_CALL_TIME

        # Enforce minimum gap between calls
        if elapsed < _MIN_CALL_GAP:
            wait = _MIN_CALL_GAP - elapsed
            logger.debug("Rate limiter: sleeping %.1fs", wait)
            time.sleep(wait)

        # Track daily usage
        today = time.strftime("%Y-%m-%d")
        if _DAILY_RESET_DAY != today:
            _DAILY_RESET_DAY = today
            _DAILY_CALL_COUNT = 0

        # Check daily limit (leave 50 credit buffer)
        if _DAILY_CALL_COUNT >= 750:
            logger.warning("Daily API limit reached (750/800 credits used)")
            return None

        _LAST_CALL_TIME = time.time()
        _DAILY_CALL_COUNT += 1

    return requests.get(_BASE_URL, params=params, timeout=_TIMEOUT)


# ── Public API ────────────────────────────────────────────────────────────

def get_candles(
    symbol: str,
    interval: str,
    bars: int = config.BARS_REQUIRED,
    force_refresh: bool = False,
) -> Optional[pd.DataFrame]:
    """
    Fetch candles with intelligent caching.

    Args:
        symbol: Trading pair symbol
        interval: Time interval (e.g., '15min', '1h')
        bars: Number of bars to fetch
        force_refresh: Bypass cache if True

    Returns:
        DataFrame with OHLCV data or None if error
    """
    key = (symbol, interval)
    now = time.monotonic()

    # Check cache (unless force refresh)
    if not force_refresh and key in _CACHE:
        ts, df = _CACHE[key]
        # Return cached data if still fresh
        if now - ts < _CACHE_TTL:
            logger.debug("Cache hit: %s/%s (age: %.0fs)", symbol, interval, now - ts)
            return df

    # Fetch new data
    df = _fetch(symbol, interval, bars)
    if df is not None:
        _CACHE[key] = (now, df)
        logger.debug("Fetched fresh data: %s/%s", symbol, interval)
    return df


def get_current_price(symbol: str) -> Optional[float]:
    df = get_candles(symbol, "1min", bars=1)
    if df is not None and not df.empty:
        return float(df["close"].iloc[-1])
    return None


# ── Internal ──────────────────────────────────────────────────────────────

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
            resp = _rate_limited_get(params)
            resp.raise_for_status()
            payload = resp.json()

            if payload.get("status") == "error":
                logger.warning(
                    "TwelveData error %s/%s: %s",
                    symbol, interval, payload.get("message")
                )
                return None

            return _parse(payload, symbol, interval)

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (401, 403, 429):
                logger.warning("Auth/rate error %s/%s: %s", symbol, interval, e)
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


def _parse(payload: dict, symbol: str, interval: str) -> Optional[pd.DataFrame]:
    """
    Parse TwelveData JSON into a DataFrame.
    Volume is optional — XAU/USD and most forex pairs don't provide it.
    """
    try:
        values = payload.get("values", [])
        if not values:
            logger.warning("Empty values for %s/%s", symbol, interval)
            return None

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.set_index("datetime").sort_index()

        # Convert OHLC columns to numeric
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Volume is optional — not available for forex/gold
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        else:
            df["volume"] = 0.0  # fill with zero so downstream code doesn't break

        df = df.dropna(subset=["open", "high", "low", "close"])
        return df[["open", "high", "low", "close", "volume"]]

    except Exception as e:
        logger.error("Parse error %s/%s: %s", symbol, interval, e)
        return None


# ── Session filter ────────────────────────────────────────────────────────

def is_active_session() -> bool:
    """Check if current hour is within an active trading session."""
    if config.ACTIVE_SESSION_HOURS is None:
        return True
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in config.ACTIVE_SESSION_HOURS)


def get_api_usage() -> dict:
    """Return current API usage statistics."""
    global _DAILY_CALL_COUNT, _DAILY_RESET_DAY
    today = time.strftime("%Y-%m-%d")

    # Reset if new day
    if _DAILY_RESET_DAY != today:
        _DAILY_RESET_DAY = today
        _DAILY_CALL_COUNT = 0

    return {
        "daily_calls": _DAILY_CALL_COUNT,
        "daily_limit": 800,
        "remaining": 800 - _DAILY_CALL_COUNT,
        "percent_used": round(_DAILY_CALL_COUNT / 800 * 100, 1),
    }
