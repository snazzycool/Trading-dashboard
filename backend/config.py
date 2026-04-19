"""
config.py — All tunable parameters for the trading signal engine.

FREE TIER MATHS (TwelveData: 800 credits/day)
  Each scan fetches 2 timeframes per pair = 2 credits per pair per scan
  5 pairs × 2 = 10 credits per scan
  Scan every 30 min = 48 scans/day
  Total: 10 × 48 = 480 credits/day  ✅ well within the 800 limit
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
# Set to 1800 (30 min) to stay within TwelveData free tier (800 credits/day)
# Change back to 300 (5 min) only if you upgrade to a paid API plan
SCAN_INTERVAL_SECONDS: int = 1800          # 30 minutes
RESULT_CHECK_INTERVAL_SECONDS: int = 1800  # 30 minutes

# ── Watchlist ─────────────────────────────────────────────────────────────
# Kept to 5 pairs to stay safely within TwelveData free tier.
# 5 pairs × 2 timeframes × 48 scans/day = 480 credits/day (limit: 800)
# Add more pairs only if you upgrade to a paid TwelveData plan.
WATCHLIST: list[str] = [
    "EUR/USD",   # Most liquid forex pair
    "GBP/USD",   # High volatility forex
    "USD/JPY",   # Asian session coverage
    "BTC/USD",   # Crypto — high ATR, good signals
    "ETH/USD",   # Crypto — strong trend behaviour
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
SWING_PROXIMITY_PCT:  float = 0.003
LIQUIDITY_SWEEP_BARS: int   = 5

# ── Risk management ───────────────────────────────────────────────────────
ATR_SL_MULTIPLIER: float = 1.5   # Stop Loss   = entry ± 1.5 × ATR
ATR_TP_MULTIPLIER: float = 2.5   # Take Profit = entry ± 2.5 × ATR
MIN_RISK_REWARD:   float = 1.5   # Reject trade if RR < 1.5

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600  # Max 1 signal per pair per hour
MAX_SIGNALS_PER_HOUR:   int = 5     # Hard cap across all pairs per hour

# ── Session filter (UTC hours) ────────────────────────────────────────────
# Only scan during active trading sessions.
# London: 07:00–16:00 UTC  |  New York: 12:00–21:00 UTC
# Set to None to scan 24/7 (not recommended — wastes API credits overnight)
ACTIVE_SESSION_HOURS: list[tuple[int, int]] | None = [
    (7, 16),   # London session
    (12, 21),  # New York session
]

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
