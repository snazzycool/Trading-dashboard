"""
config.py — All tunable parameters for the trading signal engine.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY: str = os.getenv("TWELVEDATA_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────
_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.join(os.path.dirname(__file__), "data")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH: str = os.path.join(_DATA_DIR, "signals.db")

# ── Scanner ───────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS: int = 300        # every 5 minutes
RESULT_CHECK_INTERVAL_SECONDS: int = 1800  # every 30 minutes

WATCHLIST: list[str] = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
    "EUR/GBP", "GBP/JPY", "NZD/USD",
    "BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD",
]

ENTRY_INTERVAL: str = "15min"
HTF_INTERVAL:   str = "1h"
BARS_REQUIRED:  int = 250

# ── Strategy scoring ──────────────────────────────────────────────────────
MIN_SCORE_TO_TRADE: int = 5

SCORE_TREND_CONFIRMATION: int = 2
SCORE_RSI_PULLBACK:       int = 1
SCORE_MARKET_STRUCTURE:   int = 2
SCORE_ATR_VOLATILITY:     int = 1
SCORE_LIQUIDITY_SWEEP:    int = 2

# ── Indicators ────────────────────────────────────────────────────────────
EMA_FAST:            int   = 50
EMA_SLOW:            int   = 200
RSI_PERIOD:          int   = 14
RSI_BUY_THRESHOLD:   float = 40.0
RSI_SELL_THRESHOLD:  float = 60.0
ATR_PERIOD:          int   = 14
ATR_AVG_PERIOD:      int   = 50
SWING_LOOKBACK:      int   = 20
SWING_PROXIMITY_PCT: float = 0.003
LIQUIDITY_SWEEP_BARS: int  = 5

# ── Risk management ───────────────────────────────────────────────────────
ATR_SL_MULTIPLIER: float = 1.5
ATR_TP_MULTIPLIER: float = 2.5
MIN_RISK_REWARD:   float = 1.5

# ── Anti-spam ─────────────────────────────────────────────────────────────
MIN_SIGNAL_GAP_SECONDS: int = 3600
MAX_SIGNALS_PER_HOUR:   int = 5

# ── Session filter (UTC) — set to None to disable ─────────────────────────
ACTIVE_SESSION_HOURS: list[tuple[int, int]] | None = [
    (7, 16),   # London
    (12, 21),  # New York
]

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
