"""
config.py — Trading Bot with Capital.com automation.

V1 strategy restored + Capital.com API + trailing stop + risk management.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")

# ── Capital.com credentials ───────────────────────────────────────────────
CAPITAL_API_KEY:    str = os.getenv("CAPITAL_API_KEY",    "")
CAPITAL_PASSWORD:   str = os.getenv("CAPITAL_PASSWORD",   "")
CAPITAL_IDENTIFIER: str = os.getenv("CAPITAL_IDENTIFIER", "")
CAPITAL_ENV:        str = os.getenv("CAPITAL_ENV", "demo")  # "demo" or "live"

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
BARS_REQUIRED:  int = 250

# ── Scan schedule ─────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS: int         = 1800  # 30 min (safe for free tier)
RESULT_CHECK_INTERVAL_SECONDS: int = 1800  # 30 min
TRAILING_CHECK_INTERVAL_SECONDS: int = 60  # check trailing stops every 60s

# Session hours (UTC) — scanner runs 24/7 but these inform strategy
ACTIVE_SESSION_HOURS: list[tuple[int, int]] = [
    (7, 16),   # London
    (12, 21),  # New York
]

# ── V1 Scoring model (max 8, min 5) ──────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 5

SCORE_TREND_CONFIRMATION: int = 2
SCORE_RSI_PULLBACK:        int = 1
SCORE_MARKET_STRUCTURE:    int = 2
SCORE_ATR_VOLATILITY:      int = 1
SCORE_LIQUIDITY_SWEEP:     int = 2

# ── Indicators ────────────────────────────────────────────────────────────
EMA_FAST: int = 50
EMA_SLOW: int = 200

RSI_PERIOD:          int   = 14
RSI_BUY_THRESHOLD:   float = 40.0   # V1: strict pullback
RSI_SELL_THRESHOLD:  float = 60.0   # V1: strict pullback

ATR_PERIOD:     int = 14
ATR_AVG_PERIOD: int = 50

SWING_LOOKBACK:      int   = 20
SWING_PROXIMITY_PCT: float = 0.003
GOLD_PROXIMITY_PCT:  float = 0.008
LIQUIDITY_SWEEP_BARS: int  = 5

# ── Risk management (SL/TP) ───────────────────────────────────────────────
ATR_SL_MULTIPLIER: float = 1.5
ATR_TP_MULTIPLIER: float = 2.5
ATR_BUFFER:        float = 0.3

MIN_SL_PIPS_FOREX: float = 15.0
MIN_SL_PIPS_JPY:   float = 20.0
MIN_SL_PIPS_GOLD:  float = 150.0

MIN_RISK_REWARD: float = 1.5

# ── Position sizing (score-based) ─────────────────────────────────────────
# Risk % of account balance per trade based on signal score
RISK_PCT_BY_SCORE: dict = {
    5: 0.005,   # 0.5% — minimum confidence
    6: 0.010,   # 1.0% — standard
    7: 0.015,   # 1.5% — good setup
    8: 0.020,   # 2.0% — highest confidence
}

# ── Trade management ──────────────────────────────────────────────────────
MAX_OPEN_TRADES: int         = 3          # max simultaneous positions
TRAILING_STOP_MIN_SCORE: int = 7          # trailing only for 7/8+ scores
DAILY_LOSS_LIMIT_PCT: float  = 5.0        # stop if down 5% in one day
AUTO_TRADE: bool             = True       # set False to signal-only mode

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600
MAX_SIGNALS_PER_HOUR:   int = 6

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
