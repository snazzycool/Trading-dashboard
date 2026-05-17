"""
modules/strategy.py — Signal scoring engine v1 RESTORED.

Back to what worked: simple, consistent, profitable.

Scoring model (max 8, min 5 to trade):
  +2  Trend confirmation   EMA50 > EMA200 (BUY) or < EMA200 (SELL)
                           confirmed on BOTH timeframes
  +1  RSI pullback         RSI < 40 (BUY) or > 60 (SELL)
  +2  Market structure     Price near recent swing low (BUY) / high (SELL)
  +1  ATR volatility       ATR above rolling average
  +2  Liquidity sweep      Price swept recent H/L then reversed

ATR fix retained (stable rolling instead of EWM — prevents runaway values).
Market structure SL/TP retained with ATR fallback.
Pip tracking retained.
"""
import logging
from dataclasses import dataclass, field
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


def _compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
) -> pd.Series:
    """Stable rolling ATR — prevents EWM runaway from extreme candles."""
    prev = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


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

        # EMA
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

        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None


# ── Trend detection (simple EMA cross) ───────────────────────────────────

def _ema_trend(df: pd.DataFrame) -> str:
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


# ── Scoring components ────────────────────────────────────────────────────

def _score_rsi(df: pd.DataFrame, direction: str) -> int:
    """RSI < 40 for BUY (pullback in uptrend), > 60 for SELL."""
    rsi = float(df["rsi"].iloc[-1])
    if np.isnan(rsi):
        return 0
    if direction == "BUY"  and rsi < config.RSI_BUY_THRESHOLD:
        return config.SCORE_RSI_PULLBACK
    if direction == "SELL" and rsi > config.RSI_SELL_THRESHOLD:
        return config.SCORE_RSI_PULLBACK
    return 0


def _score_market_structure(
    df: pd.DataFrame,
    close: float,
    direction: str,
    proximity_pct: float,
) -> int:
    """Price within proximity_pct of recent swing low (BUY) or high (SELL)."""
    lb     = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]
    level  = (float(recent["low"].min())  if direction == "BUY"
              else float(recent["high"].max()))
    if abs(close - level) / close <= proximity_pct:
        return config.SCORE_MARKET_STRUCTURE
    return 0


def _score_atr_volatility(df: pd.DataFrame) -> int:
    """ATR must be above its rolling average — confirms active market."""
    last = df.iloc[-1]
    atr  = last.get("atr",     np.nan)
    avg  = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    return config.SCORE_ATR_VOLATILITY if atr > avg else 0


def _score_liquidity_sweep(df: pd.DataFrame, direction: str) -> int:
    """
    Price swept recent H/L then reversed — smart money stop hunt signal.
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
    """Structure-based SL/TP with ATR fallback and minimum pip distance."""
    pip      = _pip_value(pair)
    min_pips = (config.MIN_SL_PIPS_JPY  if "JPY" in pair else
                config.MIN_SL_PIPS_GOLD if pair == "XAU/USD" else
                config.MIN_SL_PIPS_FOREX)

    sl_raw, tp_raw = _find_structure_levels(df, direction)

    if sl_raw is None or tp_raw is None:
        logger.debug("%s: using ATR fallback for SL/TP", pair)
        if direction == "BUY":
            sl_raw = close - atr * config.ATR_SL_MULTIPLIER
            tp_raw = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl_raw = close + atr * config.ATR_SL_MULTIPLIER
            tp_raw = close - atr * config.ATR_TP_MULTIPLIER

    # ATR buffer beyond structure
    sl = (sl_raw - atr * config.ATR_BUFFER if direction == "BUY"
          else sl_raw + atr * config.ATR_BUFFER)
    tp = tp_raw

    # Enforce minimum SL distance
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
    V1 evaluation pipeline — simple and consistent.
    EMA cross on both TFs must agree → RSI pullback → structure → ATR → sweep.
    """
    try:
        df_entry = _add_indicators(df_entry)
        df_htf   = _add_indicators(df_htf)

        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.EMA_SLOW + 10 or len(df_htf) < config.EMA_SLOW + 10:
            logger.debug("%s: not enough bars", pair)
            return None

        close = float(df_entry["close"].iloc[-1])
        atr   = float(df_entry["atr"].iloc[-1])

        if np.isnan(atr) or atr <= 0:
            return None
        if atr > close * 0.05:
            logger.warning("%s: ATR sanity check failed — skipping", pair)
            return None

        # Both timeframes must agree on direction
        htf_dir   = _ema_trend(df_htf)
        entry_dir = _ema_trend(df_entry)

        if htf_dir == "NEUTRAL" or entry_dir == "NEUTRAL":
            logger.debug("%s: no clear EMA trend", pair)
            return None
        if htf_dir != entry_dir:
            logger.debug("%s: TF conflict HTF=%s entry=%s", pair, htf_dir, entry_dir)
            return None

        direction     = htf_dir
        is_gold       = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT

        # ── Score ─────────────────────────────────────────────────────────
        card = _Card()
        card.add("trend_confirmation", config.SCORE_TREND_CONFIRMATION)
        card.add("rsi_pullback",       _score_rsi(df_entry, direction))
        card.add("market_structure",   _score_market_structure(df_entry, close, direction, proximity_pct))
        card.add("atr_volatility",     _score_atr_volatility(df_entry))
        card.add("liquidity_sweep",    _score_liquidity_sweep(df_entry, direction))

        logger.info("%s %s | Score %d/8 | %s",
                    pair, direction, card.total,
                    {k: v for k, v in card.breakdown.items() if v > 0})

        if card.total < config.MIN_SCORE_TO_TRADE:
            logger.debug("%s: score %d below threshold", pair, card.total)
            return None

        # ── SL/TP ─────────────────────────────────────────────────────────
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
