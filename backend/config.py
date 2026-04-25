"""
config.py — Trading signal engine configuration.

FREE TIER MATHS (TwelveData: 800 credits/day)
  7 pairs × 2 timeframes = 14 credits per scan
  Scan every 30 min = 48 scans/day
  Total: 14 × 48 = 672 credits/day  ✅ within the 800 limit
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

# ── Scanner ───────────────────────────────────────────────────────────────
# 30-minute scan interval keeps daily API usage well within free tier
SCAN_INTERVAL_SECONDS: int         = 1800
RESULT_CHECK_INTERVAL_SECONDS: int = 1800

# ── Watchlist ─────────────────────────────────────────────────────────────
# 7 pairs × 2 timeframes × 48 scans/day = 672 credits/day (limit: 800) ✅
WATCHLIST: list[str] = [
    "EUR/USD",   # Most liquid forex pair
    "GBP/USD",   # High volatility, strong trends
    "GBP/JPY",   # Very volatile, excellent ATR-based signals
    "EUR/JPY",   # Active London/Tokyo overlap
    "AUD/USD",   # Commodity-linked, reliable trends
    "USD/CAD",   # Oil-linked, solid structure
    "XAU/USD",   # Gold — volatile, trending, high-quality signals
]

ENTRY_INTERVAL: str = "15min"
HTF_INTERVAL:   str = "1h"
BARS_REQUIRED:  int = 250

# ── Strategy scoring ──────────────────────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 5   # Signal fires only if score >= 5 out of 8

SCORE_TREND_CONFIRMATION: int = 2
SCORE_RSI_PULLBACK:       int = 1
SCORE_MARKET_STRUCTURE:   int = 2
SCORE_ATR_VOLATILITY:     int = 1
SCORE_LIQUIDITY_SWEEP:    int = 2

# ── Indicators ────────────────────────────────────────────────────────────
EMA_FAST:             int   = 50
EMA_SLOW:             int   = 200
RSI_PERIOD:           int   = 14
RSI_BUY_THRESHOLD:    float = 40.0
RSI_SELL_THRESHOLD:   float = 60.0
ATR_PERIOD:           int   = 14
ATR_AVG_PERIOD:       int   = 50
SWING_LOOKBACK:       int   = 20
SWING_PROXIMITY_PCT:  float = 0.003   # 0.3% for all forex pairs
GOLD_PROXIMITY_PCT:   float = 0.008   # 0.8% for XAU/USD (wider range)
LIQUIDITY_SWEEP_BARS: int   = 5

# ── Risk management ───────────────────────────────────────────────────────
ATR_SL_MULTIPLIER: float = 1.5   # Stop Loss   = entry ± 1.5 × ATR
ATR_TP_MULTIPLIER: float = 2.5   # Take Profit = entry ± 2.5 × ATR
MIN_RISK_REWARD:   float = 1.5   # Reject trade if RR < 1.5

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600  # Max 1 signal per pair per hour
MAX_SIGNALS_PER_HOUR:   int = 6     # Hard cap across all pairs per hour

# ── Session filter (UTC hours) ────────────────────────────────────────────
# London: 07:00–16:00 UTC  |  New York: 12:00–21:00 UTC
# Set to None to scan 24/7
ACTIVE_SESSION_HOURS: list[tuple[int, int]] | None = [
    (7, 16),   # London session
    (12, 21),  # New York session
]

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
