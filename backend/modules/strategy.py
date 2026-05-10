"""
modules/strategy.py — Signal scoring engine v3 (simplified).

What changed from v2:
  - Removed candle confirmation (was silently killing all signals)
  - Session filter is now a score BONUS (+1) not a hard gate
  - Scanner runs all day, London/NY signals score higher
  - Min score lowered to 5/10 for practical signal generation
  - MACD histogram requirement relaxed (line cross is enough)
  - All other quality filters kept intact

Scoring model (max 10, min 5 to trade):
  +2  Trend (structure HH/HL or EMA fallback)
  +1  RSI on correct side of midline
  +2  Price near swing level
  +1  ATR above average (volatile market)
  +2  Liquidity sweep / ORB reversal
  +2  MACD momentum
  +1  BONUS: signal fired during London or NY session
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import config

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────

def _pip_value(pair: str) -> float:
    if "JPY" in pair:
        return 0.01
    if pair == "XAU/USD":
        return 0.1
    return 0.0001


def _min_sl_pips(pair: str) -> float:
    if "JPY" in pair:
        return config.MIN_SL_PIPS_JPY
    if pair == "XAU/USD":
        return config.MIN_SL_PIPS_GOLD
    return config.MIN_SL_PIPS_FOREX


def _compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
) -> pd.Series:
    """Stable rolling ATR."""
    prev = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _in_session() -> bool:
    """True if current UTC hour is inside London or New York session."""
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in config.ACTIVE_SESSION_HOURS)


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class SignalResult:
    pair:            str
    direction:       str
    entry:           float
    stop_loss:       float
    take_profit:     float
    score:           int
    score_breakdown: dict
    atr:             float
    risk_reward:     float
    pip_risk:        float
    pip_reward:      float


@dataclass
class _Card:
    total:     int  = 0
    breakdown: dict = field(default_factory=dict)

    def add(self, name: str, pts: int) -> None:
        self.total += pts
        self.breakdown[name] = pts


# ── Indicators ────────────────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    try:
        df = df.copy()
        c  = df["close"]
        h  = df["high"]
        l  = df["low"]

        # EMA (fallback trend + MACD)
        df["ema_fast"] = c.ewm(span=config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=config.EMA_SLOW, adjust=False).mean()

        # RSI
        delta = c.diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        ag    = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        al    = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        rs    = ag / al.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ATR (stable rolling)
        df["atr"]     = _compute_atr(h, l, c, config.ATR_PERIOD)
        df["atr_avg"] = df["atr"].rolling(
            config.ATR_AVG_PERIOD, min_periods=config.ATR_PERIOD
        ).mean()

        # MACD
        ema_f       = c.ewm(span=config.MACD_FAST,   adjust=False).mean()
        ema_s       = c.ewm(span=config.MACD_SLOW,   adjust=False).mean()
        macd        = ema_f - ema_s
        signal      = macd.ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df["macd"]        = macd
        df["macd_signal"] = signal
        df["macd_hist"]   = macd - signal

        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None


# ── Hybrid trend detection ────────────────────────────────────────────────

def _structure_trend(df: pd.DataFrame) -> str:
    """
    Detect trend from market structure (HH/HL or LH/LL).
    Requires 3 confirmed swing points — high quality signal.
    """
    if len(df) < 50:
        return "NEUTRAL"

    n     = len(df)
    lb    = min(config.SWING_LOOKBACK * 2, n - 4)
    highs = df["high"].values
    lows  = df["low"].values
    sh, sl = [], []

    for i in range(n - lb + 2, n - 2):
        if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
            sh.append(highs[i])
        if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
            sl.append(lows[i])

    sh = sh[-config.TREND_LOOKBACK:]
    sl = sl[-config.TREND_LOOKBACK:]

    if len(sh) >= 3 and len(sl) >= 3:
        if (all(sh[i] < sh[i+1] for i in range(len(sh)-1)) and
                all(sl[i] < sl[i+1] for i in range(len(sl)-1))):
            return "BUY"
        if (all(sl[i] > sl[i+1] for i in range(len(sl)-1)) and
                all(sh[i] > sh[i+1] for i in range(len(sh)-1))):
            return "SELL"

    return "NEUTRAL"


def _ema_trend(df: pd.DataFrame) -> str:
    """EMA 50/200 fallback — used when structure is unclear."""
    last = df.iloc[-1]
    ef   = last.get("ema_fast")
    es   = last.get("ema_slow")
    if pd.isna(ef) or pd.isna(es):
        return "NEUTRAL"
    if ef > es:
        return "BUY"
    if ef < es:
        return "SELL"
    return "NEUTRAL"


def _detect_trend(df: pd.DataFrame) -> Tuple[str, bool]:
    """
    Try structure first, fall back to EMA.
    Returns (direction, is_structure_based).
    """
    s = _structure_trend(df)
    if s != "NEUTRAL":
        return s, True
    e = _ema_trend(df)
    return e, False


# ── Scoring components ────────────────────────────────────────────────────

def _score_rsi(df: pd.DataFrame, direction: str) -> int:
    rsi = float(df["rsi"].iloc[-1])
    if np.isnan(rsi):
        return 0
    if direction == "BUY"  and rsi < config.RSI_BUY_THRESHOLD:
        return config.SCORE_RSI
    if direction == "SELL" and rsi > config.RSI_SELL_THRESHOLD:
        return config.SCORE_RSI
    return 0


def _score_swing_proximity(
    df: pd.DataFrame,
    close: float,
    direction: str,
    proximity_pct: float,
) -> int:
    lb     = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]
    level  = (float(recent["low"].min()) if direction == "BUY"
              else float(recent["high"].max()))
    if abs(close - level) / close <= proximity_pct:
        return config.SCORE_SWING_PROXIMITY
    return 0


def _score_atr(df: pd.DataFrame) -> int:
    last = df.iloc[-1]
    atr  = last.get("atr",     np.nan)
    avg  = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    return config.SCORE_ATR_VOLATILITY if atr > avg else 0


def _score_liquidity_sweep(df: pd.DataFrame, direction: str) -> int:
    """
    Checks for liquidity sweep: price broke a swing level then reversed.
    During London/NY open (first 15 min) this scores full bonus — ORB effect.
    """
    lb = min(config.LIQUIDITY_SWEEP_BARS + config.SWING_LOOKBACK, len(df) - 2)
    if lb < 4:
        return 0

    ref    = df.iloc[-(lb + 1):-(config.LIQUIDITY_SWEEP_BARS + 1)]
    recent = df.iloc[-(config.LIQUIDITY_SWEEP_BARS + 1):]

    try:
        if direction == "BUY":
            prior = float(ref["low"].min())
            swept = not recent[
                (recent["low"] < prior) & (recent["close"] > prior)
            ].empty
        else:
            prior = float(ref["high"].max())
            swept = not recent[
                (recent["high"] > prior) & (recent["close"] < prior)
            ].empty
        return config.SCORE_LIQUIDITY_SWEEP if swept else 0
    except Exception:
        return 0


def _score_macd(df: pd.DataFrame, direction: str) -> int:
    """
    +2 if MACD line is on the correct side of signal line.
    Histogram growing is preferred but not required (relaxed from v2).
    """
    if len(df) < 3:
        return 0

    last = df.iloc[-1]
    macd = last.get("macd",        np.nan)
    sig  = last.get("macd_signal", np.nan)

    if pd.isna(macd) or pd.isna(sig):
        return 0

    if direction == "BUY"  and macd > sig:
        return config.SCORE_MACD
    if direction == "SELL" and macd < sig:
        return config.SCORE_MACD
    return 0


# ── Market structure SL/TP ────────────────────────────────────────────────

def _find_structure_levels(
    df: pd.DataFrame,
    direction: str,
) -> Tuple[Optional[float], Optional[float]]:
    if len(df) < 40:
        return None, None

    recent = df.iloc[-41:-1]
    highs  = recent["high"].values
    lows   = recent["low"].values
    n      = len(highs)
    sh, sl = [], []

    for i in range(2, n - 2):
        if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
            sh.append(highs[i])
        if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
            sl.append(lows[i])

    close = float(df["close"].iloc[-1])

    if direction == "BUY":
        below    = [l for l in sl if l < close]
        above    = [h for h in sh if h > close]
        sl_level = max(below) if below else None
        tp_level = min(above) if above else None
    else:
        above    = [h for h in sh if h > close]
        below    = [l for l in sl if l < close]
        sl_level = min(above) if above else None
        tp_level = max(below) if below else None

    return sl_level, tp_level


def _compute_sl_tp(
    df: pd.DataFrame,
    direction: str,
    close: float,
    atr: float,
    pair: str,
) -> Tuple[Optional[float], Optional[float]]:
    pip      = _pip_value(pair)
    min_pips = _min_sl_pips(pair)

    sl_raw, tp_raw = _find_structure_levels(df, direction)

    if sl_raw is None or tp_raw is None:
        logger.debug("%s: no structure levels — ATR fallback", pair)
        if direction == "BUY":
            sl_raw = close - atr * config.ATR_SL_MULTIPLIER
            tp_raw = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl_raw = close + atr * config.ATR_SL_MULTIPLIER
            tp_raw = close - atr * config.ATR_TP_MULTIPLIER

    sl = (sl_raw - atr * config.ATR_BUFFER if direction == "BUY"
          else sl_raw + atr * config.ATR_BUFFER)
    tp = tp_raw

    # Enforce minimum pip distance on SL
    sl_pips = abs(close - sl) / pip
    if sl_pips < min_pips:
        sl = (close - min_pips * pip if direction == "BUY"
              else close + min_pips * pip)

    risk   = abs(close - sl)
    reward = abs(tp - close)

    if reward <= 0 or risk <= 0:
        return None, None
    if reward / risk < config.MIN_RISK_REWARD:
        logger.debug("%s: RR %.2f below minimum", pair, reward / risk)
        return None, None

    return sl, tp


# ── Main evaluation ───────────────────────────────────────────────────────

def evaluate_pair(
    pair:     str,
    df_entry: pd.DataFrame,
    df_htf:   pd.DataFrame,
) -> Optional[SignalResult]:
    """
    Full signal evaluation pipeline v3.
    Removed: candle confirmation, session hard gate.
    Added:   session as score bonus (+1).
    """
    try:
        df_entry = _add_indicators(df_entry)
        df_htf   = _add_indicators(df_htf)

        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.MACD_SLOW + 10 or len(df_htf) < config.MACD_SLOW + 10:
            logger.debug("%s: not enough bars", pair)
            return None

        close = float(df_entry["close"].iloc[-1])
        atr   = float(df_entry["atr"].iloc[-1])

        if np.isnan(atr) or atr <= 0:
            return None
        if atr > close * 0.05:
            logger.warning("%s: ATR sanity check failed — skipping", pair)
            return None

        # ── Trend detection (HTF + entry must agree) ──────────────────────
        htf_dir,   htf_struct   = _detect_trend(df_htf)
        entry_dir, entry_struct = _detect_trend(df_entry)

        if htf_dir == "NEUTRAL" or entry_dir == "NEUTRAL":
            logger.debug("%s: no clear trend", pair)
            return None
        if htf_dir != entry_dir:
            logger.debug("%s: TF conflict HTF=%s entry=%s", pair, htf_dir, entry_dir)
            return None

        direction     = htf_dir
        is_gold       = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT

        # ── Scoring ───────────────────────────────────────────────────────
        card = _Card()

        # Trend: +2 if structure confirmed on both TFs, +1 if EMA fallback
        trend_pts = config.SCORE_TREND_STRUCTURE if (htf_struct and entry_struct) else 1
        card.add("trend_structure",  trend_pts)
        card.add("rsi",              _score_rsi(df_entry, direction))
        card.add("swing_proximity",  _score_swing_proximity(df_entry, close, direction, proximity_pct))
        card.add("atr_volatility",   _score_atr(df_entry))
        card.add("liquidity_sweep",  _score_liquidity_sweep(df_entry, direction))
        card.add("macd",             _score_macd(df_entry, direction))

        # Session bonus: +1 if firing during London or New York
        if _in_session():
            card.add("session_bonus", 1)

        logger.info(
            "%s %s | Score %d/10 | trend=%s/%s | session=%s | %s",
            pair, direction, card.total,
            "S" if htf_struct   else "E",
            "S" if entry_struct else "E",
            "YES" if _in_session() else "NO",
            {k: v for k, v in card.breakdown.items() if v > 0},
        )

        if card.total < config.MIN_SCORE_TO_TRADE:
            logger.debug("%s: score %d below threshold %d",
                         pair, card.total, config.MIN_SCORE_TO_TRADE)
            return None

        # ── SL / TP ───────────────────────────────────────────────────────
        sl, tp = _compute_sl_tp(df_entry, direction, close, atr, pair)
        if sl is None or tp is None:
            return None

        risk   = abs(close - sl)
        reward = abs(tp - close)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        pip        = _pip_value(pair)
        pip_risk   = round(risk   / pip, 1)
        pip_reward = round(reward / pip, 1)
        decimals   = 2 if is_gold else (3 if "JPY" in pair else 5)

        return SignalResult(
            pair=pair,
            direction=direction,
            entry=round(close, decimals),
            stop_loss=round(sl, decimals),
            take_profit=round(tp, decimals),
            score=card.total,
            score_breakdown=card.breakdown,
            atr=round(atr, decimals),
            risk_reward=rr,
            pip_risk=pip_risk,
            pip_reward=pip_reward,
        )

    except Exception as e:
        logger.error("Strategy error %s: %s", pair, e, exc_info=True)
        return None


def check_outcome(
    direction:     str,
    entry:         float,
    stop_loss:     float,
    take_profit:   float,
    current_price: float,
) -> Optional[str]:
    if direction == "BUY":
        if current_price >= take_profit:
            return "WIN"
        if current_price <= stop_loss:
            return "LOSS"
    else:
        if current_price <= take_profit:
            return "WIN"
        if current_price >= stop_loss:
            return "LOSS"
    return None
