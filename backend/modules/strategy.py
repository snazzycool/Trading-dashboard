"""
modules/strategy.py
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
import config

logger = logging.getLogger(__name__)


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


@dataclass
class _Card:
    total: int = 0
    breakdown: dict = field(default_factory=dict)

    def add(self, name: str, pts: int):
        self.total += pts
        self.breakdown[name] = pts


def evaluate_pair(pair, df_entry, df_htf):
    try:
        df_entry = _indicators(df_entry)
        df_htf = _indicators(df_htf)
        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.EMA_SLOW + 10 or len(df_htf) < config.EMA_SLOW + 10:
            return None
        last_e = df_entry.iloc[-1]
        last_h = df_htf.iloc[-1]
        close = float(last_e["close"])
        atr = float(last_e["atr"])
        if atr <= 0 or np.isnan(atr):
            return None
        htf_bias = _bias(last_h)
        entry_bias = _bias(last_e)
        if htf_bias == "NEUTRAL" or entry_bias == "NEUTRAL" or htf_bias != entry_bias:
            return None
        direction = htf_bias
        is_gold = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT
        card = _Card()
        card.add("trend_confirmation", config.SCORE_TREND_CONFIRMATION)
        rsi = float(last_e["rsi"])
        if direction == "BUY" and rsi < config.RSI_BUY_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        elif direction == "SELL" and rsi > config.RSI_SELL_THRESHOLD:
            card.add("rsi_pullback", config.SCORE_RSI_PULLBACK)
        else:
            card.add("rsi_pullback", 0)
        struct_pts = _score_structure(df_entry, close, direction, proximity_pct)
        card.add("market_structure", struct_pts)
        card.add("atr_volatility", _score_atr(df_entry))
        card.add("liquidity_sweep", _score_sweep(df_entry, direction))
        logger.info("%s %s | Score %d/8", pair, direction, card.total)
        if card.total < config.MIN_SCORE_TO_TRADE:
            return None
        if direction == "BUY":
            sl = close - atr * config.ATR_SL_MULTIPLIER
            tp = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl = close + atr * config.ATR_SL_MULTIPLIER
            tp = close - atr * config.ATR_TP_MULTIPLIER
        risk = abs(close - sl)
        reward = abs(tp - close)
        rr = round(reward / risk, 2) if risk > 0 else 0.0
        if rr < config.MIN_RISK_REWARD:
            return None
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


def _indicators(df):
    try:
        df = df.copy()
        c = df["close"]
        h = df["high"]
        l = df["low"]
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
        df["atr"] = tr.ewm(alpha=1 / config.ATR_PERIOD, adjust=False).mean()
        df["atr_avg"] = df["atr"].rolling(config.ATR_AVG_PERIOD, min_periods=1).mean()
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
    lb = min(config.SWING_LOOKBACK, len(df) - 1)
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
    atr = last.get("atr", np.nan)
    avg = last.get("atr_avg", np.nan)
    if pd.isna(atr) or pd.isna(avg) or avg == 0:
        return 0
    if atr > avg:
        return config.SCORE_ATR_VOLATILITY
    return 0


def _score_sweep(df, direction):
    lb = min(config.LIQUIDITY_SWEEP_BARS + config.SWING_LOOKBACK, len(df) - 2)
    if lb < 4:
        return 0
    ref = df.iloc[-(lb + 1):-(config.LIQUIDITY_SWEEP_BARS + 1)]
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
