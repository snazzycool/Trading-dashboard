"""
config.py — Trading Signal Bot v3 configuration.

KEY CHANGES from v2:
  - Scanner runs 24/7 (session is now a score BONUS not a hard gate)
  - BARS_REQUIRED reduced 300 → 250 (more reliable on free tier)
  - MIN_SCORE_TO_TRADE reduced 6 → 5
  - Added session_bonus score component (+1)

SCORING MODEL v3 (max 11 points, min 5 to trade):
  +2  Trend structure (HH/HL or LH/LL) — or +1 if EMA fallback
  +1  RSI on correct side of midline
  +2  Price near swing level
  +1  ATR above average
  +2  Liquidity sweep / ORB reversal
  +2  MACD line confirms direction
  +1  BONUS: signal during London or NY session

API CREDITS (free tier: 800/day):
  6 pairs x 2 TF x 96 scans/day (every 15 min, 24hr) = 1152/day
  NOTE: Because scanner now runs 24/7, monitor your credit usage.
  If you hit the limit, set SCAN_INTERVAL_SECONDS = 1800 (30 min)
  which gives 6 x 2 x 48 = 576/day — safely under 800.
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
    "EUR/USD",
    "GBP/USD",
    "GBP/JPY",
    "AUD/USD",
    "XAU/USD",
    "NZD/USD",
]

ENTRY_INTERVAL: str = "15min"
HTF_INTERVAL:   str = "1h"
BARS_REQUIRED:  int = 250    # reduced from 300 — more reliable on free tier

# ── Scan schedule ─────────────────────────────────────────────────────────
# Scanner now runs 24/7 — session adds score bonus instead of being a gate.
# IMPORTANT: 24/7 at 15min = ~1152 credits/day (over free tier of 800).
# If you hit the limit, change to 1800 (30 min) = 576 credits/day.
SCAN_INTERVAL_SECONDS: int = 1800          # 30 min — safe for free tier
RESULT_CHECK_INTERVAL_SECONDS: int = 1800  # 30 min

# Session hours for BONUS scoring (not hard gates)
# London: 07:00-16:00 UTC | New York: 12:00-21:00 UTC
ACTIVE_SESSION_HOURS: list[tuple[int, int]] = [
    (7, 16),   # London
    (12, 21),  # New York
]

# ORB window: minutes after session open for opening range bonus
ORB_MINUTES: int = 15

# ── Scoring model v3 (max 11) ─────────────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 5    # lowered from 6

SCORE_TREND_STRUCTURE: int = 2  # +2 structure, +1 EMA fallback
SCORE_RSI:             int = 1
SCORE_SWING_PROXIMITY: int = 2
SCORE_ATR_VOLATILITY:  int = 1
SCORE_LIQUIDITY_SWEEP: int = 2
SCORE_MACD:            int = 2
SCORE_SESSION_BONUS:   int = 1  # NEW: bonus for London/NY session

# ── Indicators ────────────────────────────────────────────────────────────

# EMA (fallback trend detection)
EMA_FAST: int = 50
EMA_SLOW: int = 200

# Trend structure
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
