"""
config.py — Trading Signal Bot v2.1 configuration.

SCAN SCHEDULE (free tier calculation):
  London:   07:00-16:00 UTC = 9h = 36 scans/day
  New York: 12:00-21:00 UTC = 9h = 36 scans/day
  Overlap counted once:      4h = 16 scans
  Total unique scans/day:   56 scans
  Credits: 6 pairs x 2 TF x 56 = 672/day (limit: 800) OK

SCORING MODEL v2.1 (max 10 points, min 6 to trade):
  +2  Trend structure (HH/HL or LH/LL) — or +1 if EMA fallback used
  +1  RSI confirmation (correct side of midline)
  +2  Swing level proximity (price near key level)
  +1  ATR volatility (market is moving)
  +2  Liquidity sweep + ORB (smart money signal)
  +2  MACD momentum (confirms direction)
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
WATCHLIST: list[str] = [
    "EUR/USD",   # Most liquid forex — benchmark pair
    "GBP/USD",   # Strong trends, clean structure
    "GBP/JPY",   # Volatile, excellent pip range
    "AUD/USD",   # Commodity-linked, reliable structure
    "XAU/USD",   # Gold — best performer
    "NZD/USD",   # Replaces USD/CAD — cleaner moves
]

ENTRY_INTERVAL: str = "15min"
HTF_INTERVAL:   str = "1h"
BARS_REQUIRED:  int = 300

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

# ── Scoring model v2.1 (max 10) ───────────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 6

SCORE_TREND_STRUCTURE: int = 2  # full if structure, partial (+1) if EMA fallback
SCORE_RSI:             int = 1
SCORE_SWING_PROXIMITY: int = 2
SCORE_ATR_VOLATILITY:  int = 1
SCORE_LIQUIDITY_SWEEP: int = 2
SCORE_MACD:            int = 2

# ── Indicators ────────────────────────────────────────────────────────────

# EMA — used as fallback trend filter when structure is unclear
EMA_FAST: int = 50
EMA_SLOW: int = 200

# Trend structure detection
TREND_LOOKBACK: int = 5

# RSI
RSI_PERIOD:          int   = 14
RSI_BUY_THRESHOLD:   float = 55.0
RSI_SELL_THRESHOLD:  float = 45.0

# ATR
ATR_PERIOD:     int = 14
ATR_AVG_PERIOD: int = 50

# MACD
MACD_FAST:   int = 12
MACD_SLOW:   int = 26
MACD_SIGNAL: int = 9

# Swing levels
SWING_LOOKBACK:      int   = 30
SWING_PROXIMITY_PCT: float = 0.003
GOLD_PROXIMITY_PCT:  float = 0.008

# Liquidity sweep
LIQUIDITY_SWEEP_BARS: int = 5

# Candle confirmation
CANDLE_CONFIRM_COUNT: int = 2

# ── Risk management ───────────────────────────────────────────────────────
ATR_SL_MULTIPLIER: float = 1.5
ATR_TP_MULTIPLIER: float = 2.5
ATR_BUFFER:        float = 0.3

MIN_SL_PIPS_FOREX: float = 15.0
MIN_SL_PIPS_JPY:   float = 20.0
MIN_SL_PIPS_GOLD:  float = 150.0

MIN_RISK_REWARD: float = 1.5

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600
MAX_SIGNALS_PER_HOUR:   int = 6

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
