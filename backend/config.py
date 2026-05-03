"""
config.py — Trading Signal Bot v2 configuration.

SCAN SCHEDULE (free tier calculation):
  London:   07:00-16:00 UTC = 9h = 36 scans/day
  New York: 12:00-21:00 UTC = 9h = 36 scans/day
  Overlap counted once:      4h = 16 scans
  Total unique scans/day:   56 scans
  Credits: 6 pairs x 2 TF x 56 = 672/day (limit: 800) OK

SCORING MODEL v2 (max 10 points, min 6 to trade):
  +2  Market structure trend  (HH/HL or LH/LL)
  +1  RSI confirmation        (above/below midline)
  +2  Swing level proximity   (price near key level)
  +1  ATR volatility          (market is moving)
  +2  Liquidity sweep + ORB   (smart money signal)
  +2  MACD momentum           (momentum confirms direction)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────
_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.join(
    os.path.dirname(__file__), "data"
)
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH: str = os.path.join(_DATA_DIR, "signals.db")

# ── Watchlist ─────────────────────────────────────────────────────────────
# USD/CAD and EUR/JPY removed — replaced with cleaner pairs
WATCHLIST: list[str] = [
    "EUR/USD",   # Most liquid forex — benchmark pair
    "GBP/USD",   # Strong trends, clean structure
    "GBP/JPY",   # Volatile, excellent pip range
    "AUD/USD",   # Commodity-linked, reliable structure
    "XAU/USD",   # Gold — best performer historically
    "NZD/USD",   # Replaces USD/CAD — cleaner technical moves
]

ENTRY_INTERVAL: str = "15min"
HTF_INTERVAL:   str = "1h"
BARS_REQUIRED:  int = 300    # extra bars needed for MACD warm-up

# ── Scan schedule ─────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS: int = 900           # every 15 minutes
RESULT_CHECK_INTERVAL_SECONDS: int = 1800  # every 30 minutes

# Sessions — scanner ONLY runs during these UTC hours
ACTIVE_SESSION_HOURS: list[tuple[int, int]] = [
    (7, 16),   # London session
    (12, 21),  # New York session
]

# Opening range: minutes after session open used for ORB detection
ORB_MINUTES: int = 15

# ── Scoring model v2 (max 10) ─────────────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 6

SCORE_TREND_STRUCTURE: int = 2  # HH/HL (uptrend) or LH/LL (downtrend)
SCORE_RSI:             int = 1  # RSI on correct side of midline
SCORE_SWING_PROXIMITY: int = 2  # price near significant swing level
SCORE_ATR_VOLATILITY:  int = 1  # ATR above its rolling average
SCORE_LIQUIDITY_SWEEP: int = 2  # liquidity sweep / ORB reversal
SCORE_MACD:            int = 2  # MACD line + histogram momentum

# ── Indicators ────────────────────────────────────────────────────────────
# Trend structure detection
TREND_LOOKBACK: int = 5    # number of swing points to confirm trend

# RSI — widened to just "correct side of midline"
RSI_PERIOD:          int   = 14
RSI_BUY_THRESHOLD:   float = 55.0   # BUY: RSI < 55
RSI_SELL_THRESHOLD:  float = 45.0   # SELL: RSI > 45

# ATR (stable rolling method)
ATR_PERIOD:     int = 14
ATR_AVG_PERIOD: int = 50

# MACD
MACD_FAST:   int = 12
MACD_SLOW:   int = 26
MACD_SIGNAL: int = 9

# Swing level proximity
SWING_LOOKBACK:      int   = 30
SWING_PROXIMITY_PCT: float = 0.003  # 0.3% for forex pairs
GOLD_PROXIMITY_PCT:  float = 0.008  # 0.8% for XAU/USD

# Liquidity sweep window
LIQUIDITY_SWEEP_BARS: int = 5

# Candle confirmation — last N candles must close in signal direction
CANDLE_CONFIRM_COUNT: int = 2

# ── Risk management ───────────────────────────────────────────────────────
# SL/TP based on market structure; ATR used as fallback + buffer
ATR_SL_MULTIPLIER: float = 1.5
ATR_TP_MULTIPLIER: float = 2.5
ATR_BUFFER:        float = 0.3   # push SL slightly beyond swing level

# Minimum SL distance (prevents spread noise killing trades)
MIN_SL_PIPS_FOREX: float = 15.0
MIN_SL_PIPS_JPY:   float = 20.0
MIN_SL_PIPS_GOLD:  float = 150.0

MIN_RISK_REWARD: float = 1.5

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600
MAX_SIGNALS_PER_HOUR:   int = 6

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
