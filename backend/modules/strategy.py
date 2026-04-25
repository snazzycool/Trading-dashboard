"""
modules/strategy.py — Signal scoring engine.

Scoring model (max 8 points — minimum 5 required to fire a signal):
  +2  Trend confirmation  EMA50/200 aligned on BOTH timeframes
  +1  RSI pullback        RSI < 40 (BUY) or > 60 (SELL)
  +2  Market structure    Price near recent swing low (BUY) / high (SELL)
  +1  ATR volatility      Current ATR above its rolling average
  +2  Liquidity sweep     Price swept recent H/L then reversed

XAU/USD (Gold) uses a wider swing proximity (0.8%) because gold
moves in much larger nominal ranges than forex pairs (0.3%).
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
import config

logger = logging.getLogger(__name__)


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


@dataclass
class _Card:
    total:     int  = 0
    breakdown: dict = field(default_factory=dict)

    def add(self, name: str, pts: int):
        self.total += pts
        self.breakdown[name] = pts


# ── Public entry point ────────────────────────────────────────────────────

def evaluate_pair(
    pair:     str,
    df_entry: pd.DataFrame,
    df_htf:   pd.DataFrame,
) -> Optional[SignalResult]:
    try:
        df_entry = _indicators(df_entry)
        df_htf   = _indicators(df_htf)

        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.EMA_SLOW + 10 or len(df_htf) < config.EMA_SLOW + 10:
            logger.debug("%s: not enough bars", pair)
            return None

        last_e = df_entry.iloc[-1]
        last_h = df_htf.iloc[-1]
        close  = float(last_e["close"])
        atr    = float(last_e["atr"])

        if atr <= 0 or np.isnan(atr):
            logger.debug("%s: invalid ATR", pair)
            return None

        # Both timeframes must agree on direction
        htf_bias   = _bias(last_h)
        entry_bias = _bias(last_e)
        if htf_bias == "NEUTRAL" or entry_bias == "NEUTRAL" or htf_bias != entry_bias:
            logger.debug("%s: no TF agreement (HTF=%s entry=%s)", pair, htf_bias, entry_bias)
            return None

        direction = htf_bias

        # Gold needs a wider proximity due to larger price ranges
        is_gold       = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT

        # ── Score ─────────────────────────────────────────────────────────
        card = _Card()

        # Component 1: Trend confirmation (already verified above)
        card.add("trend_confirmation", config.SCORE_TREND_CONFIRMATION)

        # Component 2: RSI pullback
        rsi = float(last_e["rsi"])
        if direction == "BUY" and rsi < config.RSI_BUY_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        elif direction == "SELL" and rsi > config.RSI_SELL_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        else:
            card.add("rsi_pullback", 0)

        # Component 3: Market structure (proximity_pct passed correctly)
        card.add("market_structure",
                 _score_structure(df_entry, close, direction, proximity_pct))

        # Component 4: ATR volatility
        card.add("atr_volatility", _score_atr(df_entry))

        # Component 5: Liquidity sweep
        card.add("liquidity_sweep", _score_sweep(df_entry, direction))

        logger.info("%s %s | Score %d/8 | %s",
                    pair, direction, card.total,
                    {k: v for k, v in card.breakdown.items() if v > 0})

        if card.total < config.MIN_SCORE_TO_TRADE:
            logger.debug("%s: score %d below threshold %d",
                         pair, card.total, config.MIN_SCORE_TO_TRADE)
            return None

        # ── Risk management ───────────────────────────────────────────────
        if direction == "BUY":
            sl = close - atr * config.ATR_SL_MULTIPLIER
            tp = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl = close + atr * config.ATR_SL_MULTIPLIER
            tp = close - atr * config.ATR_TP_MULTIPLIER

        risk   = abs(close - sl)
        reward = abs(tp - close)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        if rr < config.MIN_RISK_REWARD:
            logger.debug("%s: RR %.2f below minimum %.2f", pair, rr, config.MIN_RISK_REWARD)
            return None

        # Gold prices are large numbers — use 2 decimal places
        decimals = 2 if is_gold else 6

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
    """Return 'WIN', 'LOSS', or None if still open."""
    if direction == "BUY":
        if current_price >= take_profit: return "WIN"
        if current_price <= stop_loss:   return "LOSS"
    else:
        if current_price <= take_profit: return "WIN"
        if current_price >= stop_loss:   return "LOSS"
    return None


# ── Indicators ────────────────────────────────────────────────────────────

def _indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Compute EMA50, EMA200, RSI14, ATR14, ATR rolling avg."""
    try:
        df   = df.copy()
        c, h, l = df["close"], df["high"], df["low"]

        df["ema_fast"] = c.ewm(span=config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=config.EMA_SLOW, adjust=False).mean()

        delta    = c.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        prev = c.shift(1)
        tr   = pd.concat(
            [h - l, (h - prev).abs(), (l - prev).abs()], axis=1
        ).max(axis=1)
        df["atr"]     = tr.ewm(alpha=1 / config.ATR_PERIOD, adjust=False).mean()
        df["atr_avg"] = df["atr"].rolling(config.ATR_AVG_PERIOD, min_periods=1).mean()

        return df
    except Exception as e:
        logger.error("Indicator computation error: %s", e)
        return None


# ── Scoring helpers ───────────────────────────────────────────────────────

def _bias(row: pd.Series) -> str:
    """Return BUY, SELL, or NEUTRAL based on EMA cross."""
    ef = row.get("ema_fast")
    es = row.get("ema_slow")
    if pd.isna(ef) or pd.isna(es): return "NEUTRAL"
    if ef > es: return "BUY"
    if ef < es: return "SELL"
    return "NEUTRAL"


def _score_structure(
    df:            pd.DataFrame,
    close:         float,
    direction:     str,
    proximity_pct: float,      # 4th argument — 0.003 for forex, 0.008 for Gold
) -> int:
    """
    +2 if price is within proximity_pct of a recent swing low (BUY)
    or swing high (SELL).
    """
    lb     = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]

    if direction == "BUY":
        level = float(recent["low"].min())
    else:
        level = float(recent["high"].max())

    if abs(close - level) / close <= proximity_pct:
        return config.SCORE_MARKET_STRUCTURE
    return 0


def _score_atr(df: pd.DataFrame) -> int:
    """
    +1 if current ATR is above its rolling average —
    confirms the market is liquid and actively moving.
    """
    last = df.iloc[-1]
    atr  = last.get("atr",     np.nan)
    avg  = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    return config.SCORE_ATR_VOLATILITY if atr > avg else 0


def _score_sweep(df: pd.DataFrame, direction: str) -> int:
    """
    +2 if there is evidence of a liquidity sweep:
    a recent bar's low/high broke beyond a prior swing level
    and then closed back inside it (stop-hunt reversal pattern).
    """
    lb = min(config.LIQUIDITY_SWEEP_BARS + config.SWING_LOOKBACK, len(df) - 2)
    if lb < 4:
        return 0

    ref    = df.iloc[-(lb + 1):-(config.LIQUIDITY_SWEEP_BARS + 1)]
    recent = df.iloc[-(config.LIQUIDITY_SWEEP_BARS + 1):]

    try:
        if direction == "BUY":
            prior = float(ref["low"].min())
            swept = recent[
                (recent["low"] < prior) & (recent["close"] > prior)
            ]
        else:
            prior = float(ref["high"].max())
            swept = recent[
                (recent["high"] > prior) & (recent["close"] < prior)
            ]
        return config.SCORE_LIQUIDITY_SWEEP if not swept.empty else 0
    except Exception:
        return 0            sl = close - atr * config.ATR_SL_MULTIPLIER
            tp = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl = close + atr * config.ATR_SL_MULTIPLIER
            tp = close - atr * config.ATR_TP_MULTIPLIER

        risk   = abs(close - sl)
        reward = abs(tp - close)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        if rr < config.MIN_RISK_REWARD:
            return None

        # Gold prices are large numbers — round to 2 decimal places
        decimals = 2 if is_gold else 6

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
        )
    except Exception as e:
        logger.error("Strategy error %s: %s", pair, e, exc_info=True)
        return None


def check_outcome(
    direction: str, entry: float,
    stop_loss: float, take_profit: float,
    current_price: float
) -> Optional[str]:
    if direction == "BUY":
        if current_price >= take_profit: return "WIN"
        if current_price <= stop_loss:   return "LOSS"
    else:
        if current_price <= take_profit: return "WIN"
        if current_price >= stop_loss:   return "LOSS"
    return None


# ── Indicators ────────────────────────────────────────────────────────────

def _indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    try:
        df = df.copy()
        c, h, l = df["close"], df["high"], df["low"]
        df["ema_fast"] = c.ewm(span=config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=config.EMA_SLOW, adjust=False).mean()
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        ag = gain.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        al = loss.ewm(alpha=1 / config.RSI_PERIOD, adjust=False).mean()
        rs = ag / al.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        prev = c.shift(1)
        tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
        df["atr"]     = tr.ewm(alpha=1 / config.ATR_PERIOD, adjust=False).mean()
        df["atr_avg"] = df["atr"].rolling(config.ATR_AVG_PERIOD, min_periods=1).mean()
        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None


def _bias(row: pd.Series) -> str:
    ef = row.get("ema_fast")
    es = row.get("ema_slow")
    if pd.isna(ef) or pd.isna(es): return "NEUTRAL"
    if ef > es: return "BUY"
    if ef < es: return "SELL"
    return "NEUTRAL"


def _score_structure(
    df: pd.DataFrame, close: float, direction: str, proximity_pct: float
) -> int:
    lb = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]
    if direction == "BUY":
        level = float(recent["low"].min())
    else:
        level = float(recent["high"].max())
    if abs(close - level) / close <= proximity_pct:
        return config.SCORE_MARKET_STRUCTURE
    return 0


def _score_atr(df: pd.DataFrame) -> int:
    last = df.iloc[-1]
    atr  = last.get("atr",     np.nan)
    avg  = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    return config.SCORE_ATR_VOLATILITY if atr > avg else 0


def _score_sweep(df: pd.DataFrame, direction: str) -> int:
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
        return config.SCORE_LIQUIDITY_SWEEP if not swept.empty else 0
    except Exception:
        return 0
        return SignalResult(
            pair=pair,
            direction=direction,
            entry=round(close, 6),
            stop_loss=round(sl, 6),
            take_profit=round(tp, 6),
            score=card.total,
            score_breakdown=card.breakdown,
            atr=round(atr, 6),
            risk_reward=rr,
        )
    except Exception as e:
        logger.error("Strategy error %s: %s", pair, e, exc_info=True)
        return None

def check_outcome(
    direction: str, entry: float,
    stop_loss: float, take_profit: float,
    current_price: float
) -> Optional[str]:
    if direction == "BUY":
        if current_price >= take_profit: return "WIN"
        if current_price <= stop_loss:   return "LOSS"
    else:
        if current_price <= take_profit: return "WIN"
        if current_price >= stop_loss:   return "LOSS"
    return None

# ── Indicators ────────────────────────────────────────────────────────────

def _indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    try:
        df = df.copy()
        c, h, l = df["close"], df["high"], df["low"]
        df["ema_fast"] = c.ewm(span=config.EMA_FAST, adjust=False).mean()
        df["ema_slow"] = c.ewm(span=config.EMA_SLOW, adjust=False).mean()
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        ag = gain.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
        al = loss.ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
        rs = ag / al.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))
        prev = c.shift(1)
        tr = pd.concat([h - l, (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
        df["atr"]     = tr.ewm(alpha=1/config.ATR_PERIOD, adjust=False).mean()
        df["atr_avg"] = df["atr"].rolling(config.ATR_AVG_PERIOD, min_periods=1).mean()
        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None

def _bias(row: pd.Series) -> str:
    ef, es = row.get("ema_fast"), row.get("ema_slow")
    if pd.isna(ef) or pd.isna(es): return "NEUTRAL"
    if ef > es: return "BUY"
    if ef < es: return "SELL"
    return "NEUTRAL"

def _score_structure(df: pd.DataFrame, close: float, direction: str) -> int:
    lb = min(config.SWING_LOOKBACK, len(df) - 1)
    recent = df.iloc[-(lb + 1):-1]
    if direction == "BUY":
        level = float(recent["low"].min())
    else:
        level = float(recent["high"].max())
    if abs(close - level) / close <= config.SWING_PROXIMITY_PCT:
        return config.SCORE_MARKET_STRUCTURE
    return 0

def _score_atr(df: pd.DataFrame) -> int:
    last = df.iloc[-1]
    atr, avg = last.get("atr", np.nan), last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    return config.SCORE_ATR_VOLATILITY if atr > avg else 0

def _score_sweep(df: pd.DataFrame, direction: str) -> int:
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
        return config.SCORE_LIQUIDITY_SWEEP if not swept.empty else 0
    except Exception:
        return 0
