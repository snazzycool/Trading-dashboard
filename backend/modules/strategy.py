"""
modules/strategy.py — Signal scoring engine with market-structure SL/TP.

SL/TP Logic (NEW):
  Instead of fixed ATR multiples, SL and TP are placed at real market
  structure levels:
    BUY:  SL = just below nearest swing LOW  (with small ATR buffer)
          TP = nearest swing HIGH above entry
    SELL: SL = just above nearest swing HIGH (with small ATR buffer)
          TP = nearest swing LOW below entry

  ATR is still used as a minimum distance filter:
    - If the structure-based SL is closer than 0.5×ATR, the setup
      is too tight and gets skipped (avoiding fake-outs).
    - If TP is closer than 1.0×ATR, not enough reward — skip.

  This produces more realistic, market-aware SL/TP levels.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import config

logger = logging.getLogger(__name__)


def _pip_value(pair: str) -> float:
    if "JPY" in pair:
        return 0.01
    if pair == "XAU/USD":
        return 0.1
    return 0.0001


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """
    Stable rolling ATR (avoids EWM runaway from early extreme candles).
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


@dataclass
class SignalResult:
    pair: str
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    score: int
    score_breakdown: dict
    atr: float
    risk_reward: float
    pip_risk: float
    pip_reward: float


@dataclass
class _Card:
    total: int = 0
    breakdown: dict = field(default_factory=dict)

    def add(self, name: str, pts: int):
        self.total += pts
        self.breakdown[name] = pts


# ── Market structure SL/TP ─────────────────────────────────────────────────

def _find_swing_levels(
    df: pd.DataFrame,
    direction: str,
    lookback: int = 30,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Find the nearest relevant swing low (for SL on BUY) or swing high
    (for SL on SELL), and the nearest opposing swing for TP.

    Returns (sl_level, tp_level) — either can be None if not found.
    """
    if len(df) < lookback + 5:
        return None, None

    recent = df.iloc[-(lookback + 1):-1]
    highs = recent["high"].values
    lows  = recent["low"].values
    n     = len(highs)

    swing_highs = []
    swing_lows  = []

    for i in range(2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    close = float(df["close"].iloc[-1])

    if direction == "BUY":
        # SL: highest swing low that is below current price
        below_lows = [l for l in swing_lows if l < close]
        sl_level = max(below_lows) if below_lows else None
        # TP: lowest swing high that is above current price
        above_highs = [h for h in swing_highs if h > close]
        tp_level = min(above_highs) if above_highs else None
    else:  # SELL
        # SL: lowest swing high that is above current price
        above_highs = [h for h in swing_highs if h > close]
        sl_level = min(above_highs) if above_highs else None
        # TP: highest swing low that is below current price
        below_lows = [l for l in swing_lows if l < close]
        tp_level = max(below_lows) if below_lows else None

    return sl_level, tp_level


def _structure_sl_tp(
    df: pd.DataFrame,
    direction: str,
    close: float,
    atr: float,
    is_gold: bool,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute SL and TP from market structure with ATR buffer and validation.

    Buffer: SL is placed slightly beyond the swing level so normal
    price noise doesn't trigger it prematurely.
    """
    buffer_multiplier = 0.3   # SL = swing_level ± 0.3×ATR buffer
    min_sl_distance   = 0.5   # SL must be at least 0.5×ATR from entry
    min_tp_distance   = 1.0   # TP must be at least 1.0×ATR from entry
    min_rr            = config.MIN_RISK_REWARD

    sl_raw, tp_raw = _find_swing_levels(df, direction, lookback=40)

    if sl_raw is None or tp_raw is None:
        # Fall back to ATR-based levels if no clear structure found
        logger.debug("No swing structure found — falling back to ATR levels")
        if direction == "BUY":
            sl_raw = close - atr * config.ATR_SL_MULTIPLIER
            tp_raw = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl_raw = close + atr * config.ATR_SL_MULTIPLIER
            tp_raw = close - atr * config.ATR_TP_MULTIPLIER

    # Apply ATR buffer to SL (push it slightly beyond the structure)
    if direction == "BUY":
        sl = sl_raw - atr * buffer_multiplier
        tp = tp_raw
    else:
        sl = sl_raw + atr * buffer_multiplier
        tp = tp_raw

    risk   = abs(close - sl)
    reward = abs(tp - close)

    # Validate minimum distances
    if risk < atr * min_sl_distance:
        logger.debug("SL too close to entry (%.5f < %.5f ATR) — skip", risk, min_sl_distance * atr)
        return None, None

    if reward < atr * min_tp_distance:
        logger.debug("TP too close to entry (%.5f < %.5f ATR) — skip", reward, min_tp_distance * atr)
        return None, None

    rr = reward / risk
    if rr < min_rr:
        logger.debug("RR %.2f below minimum %.2f — skip", rr, min_rr)
        return None, None

    return sl, tp


# ── Main evaluation ─────────────────────────────────────────────────────────

def evaluate_pair(pair, df_entry, df_htf):
    try:
        df_entry = _indicators(df_entry)
        df_htf   = _indicators(df_htf)

        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.EMA_SLOW + 10 or len(df_htf) < config.EMA_SLOW + 10:
            return None

        last_e = df_entry.iloc[-1]
        last_h = df_htf.iloc[-1]
        close  = float(last_e["close"])
        atr    = float(last_e["atr"])

        if np.isnan(atr) or atr <= 0:
            return None

        # Sanity check: ATR must be < 5% of price
        if atr > close * 0.05:
            logger.warning("%s: ATR %.5f > 5%% of price %.5f — data likely corrupted", pair, atr, close)
            return None

        htf_bias   = _bias(last_h)
        entry_bias = _bias(last_e)
        if htf_bias == "NEUTRAL" or entry_bias == "NEUTRAL" or htf_bias != entry_bias:
            return None

        direction     = htf_bias
        is_gold       = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT

        # ── Score ─────────────────────────────────────────────────────────
        card = _Card()
        card.add("trend_confirmation", config.SCORE_TREND_CONFIRMATION)

        rsi = float(last_e["rsi"])
        if direction == "BUY" and rsi < config.RSI_BUY_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        elif direction == "SELL" and rsi > config.RSI_SELL_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        else:
            card.add("rsi_pullback", 0)

        card.add("market_structure", _score_structure(df_entry, close, direction, proximity_pct))
        card.add("atr_volatility",   _score_atr(df_entry))
        card.add("liquidity_sweep",  _score_sweep(df_entry, direction))

        logger.info("%s %s | Score %d/8", pair, direction, card.total)

        if card.total < config.MIN_SCORE_TO_TRADE:
            return None

        # ── Market structure SL/TP ────────────────────────────────────────
        sl, tp = _structure_sl_tp(df_entry, direction, close, atr, is_gold)
        if sl is None or tp is None:
            logger.debug("%s: structure SL/TP invalid — signal rejected", pair)
            return None

        risk   = abs(close - sl)
        reward = abs(tp - close)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        if rr < config.MIN_RISK_REWARD:
            return None

        pip      = _pip_value(pair)
        pip_risk   = round(risk   / pip, 1)
        pip_reward = round(reward / pip, 1)

        decimals = 2 if is_gold else 5

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


def check_outcome(direction, entry, stop_loss, take_profit, current_price):
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


# ── Indicators ────────────────────────────────────────────────────────────

def _indicators(df):
    try:
        df = df.copy()
        c  = df["close"]
        h  = df["high"]
        l  = df["low"]

        df["ema_fast"] = c.ewm(span=config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=config.EMA_SLOW, adjust=False).mean()

        delta = c.diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        ag    = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        al    = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        rs    = ag / al.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        df["atr"]     = _compute_atr(h, l, c, config.ATR_PERIOD)
        df["atr_avg"] = df["atr"].rolling(config.ATR_AVG_PERIOD, min_periods=config.ATR_PERIOD).mean()

        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None


def _bias(row):
    ef = row.get("ema_fast")
    es = row.get("ema_slow")
    if pd.isna(ef) or pd.isna(es):
        return "NEUTRAL"
    if ef > es:
        return "BUY"
    if ef < es:
        return "SELL"
    return "NEUTRAL"


def _score_structure(df, close, direction, proximity_pct):
    lb     = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]
    if direction == "BUY":
        level = float(recent["low"].min())
    else:
        level = float(recent["high"].max())
    if abs(close - level) / close <= proximity_pct:
        return config.SCORE_MARKET_STRUCTURE
    return 0


def _score_atr(df):
    last = df.iloc[-1]
    atr  = last.get("atr",     np.nan)
    avg  = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    if atr > avg:
        return config.SCORE_ATR_VOLATILITY
    return 0


def _score_sweep(df, direction):
    lb = min(config.LIQUIDITY_SWEEP_BARS + config.SWING_LOOKBACK, len(df) - 2)
    if lb < 4:
        return 0
    ref    = df.iloc[-(lb + 1):-(config.LIQUIDITY_SWEEP_BARS + 1)]
    recent = df.iloc[-(config.LIQUIDITY_SWEEP_BARS + 1):]
    try:
        if direction == "BUY":
            prior = float(ref["low"].min())
            swept = recent[(recent["low"] < prior) & (recent["close"] > prior)]
        else:
            prior = float(ref["high"].max())
            swept = recent[(recent["high"] > prior) & (recent["close"] < prior)]
        if not swept.empty:
            return config.SCORE_LIQUIDITY_SWEEP
        return 0
    except Exception:
        return 0
