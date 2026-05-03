"""
modules/strategy.py — Signal scoring engine v2.

New in v2:
  - Market structure trend detection (HH/HL / LH/LL) replaces EMA cross
  - MACD momentum confirmation (new +2 score component)
  - ORB (Opening Range Breakout) integrated into liquidity sweep scoring
  - Widened RSI (BUY<55, SELL>45 instead of <40/>60)
  - Candle direction confirmation before firing
  - Minimum pip distance on SL (prevents spread stopouts)
  - Stable rolling ATR with 5% sanity check
  - Market structure SL/TP with ATR fallback
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
    """Stable rolling ATR — immune to EWM runaway from extreme early bars."""
    prev = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _is_kill_zone() -> bool:
    """Return True if current UTC time is inside London or New York session."""
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in config.ACTIVE_SESSION_HOURS)


def _is_orb_window() -> bool:
    """
    Return True if we are within ORB_MINUTES of a session open.
    London opens 07:00 UTC, New York opens 12:00 UTC.
    """
    now  = datetime.now(timezone.utc)
    hour = now.hour
    mins = now.minute
    opens = [7, 12]
    for o in opens:
        if hour == o and mins < config.ORB_MINUTES:
            return True
    return False


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


# ── Indicator computation ─────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Add RSI, ATR, MACD to the DataFrame."""
    try:
        df = df.copy()
        c  = df["close"]
        h  = df["high"]
        l  = df["low"]

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
        ema_fast   = c.ewm(span=config.MACD_FAST,   adjust=False).mean()
        ema_slow   = c.ewm(span=config.MACD_SLOW,   adjust=False).mean()
        macd_line  = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df["macd"]       = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"]   = macd_line - signal_line

        return df
    except Exception as e:
        logger.error("Indicator error: %s", e)
        return None


# ── Trend structure detection (replaces EMA cross) ────────────────────────

def _detect_trend(df: pd.DataFrame) -> str:
    """
    Detect trend direction from market structure:
      Uptrend   = series of Higher Highs AND Higher Lows
      Downtrend = series of Lower  Lows  AND Lower  Highs
      Ranging   = neither pattern confirmed
    """
    if len(df) < 50:
        return "NEUTRAL"

    highs  = df["high"].values
    lows   = df["low"].values
    n      = len(highs)
    lb     = min(config.SWING_LOOKBACK * 2, n - 4)
    recent = slice(n - lb, n)

    sh, sl = [], []
    for i in range(n - lb + 2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            sh.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            sl.append(lows[i])

    # Need at least 3 swing points to confirm a pattern
    sh = sh[-config.TREND_LOOKBACK:]
    sl = sl[-config.TREND_LOOKBACK:]

    if len(sh) >= 3 and len(sl) >= 3:
        hh = all(sh[i] < sh[i+1] for i in range(len(sh)-1))
        hl = all(sl[i] < sl[i+1] for i in range(len(sl)-1))
        if hh and hl:
            return "BUY"

        ll = all(sl[i] > sl[i+1] for i in range(len(sl)-1))
        lh = all(sh[i] > sh[i+1] for i in range(len(sh)-1))
        if ll and lh:
            return "SELL"

    return "NEUTRAL"


# ── Candle confirmation ───────────────────────────────────────────────────

def _confirm_candle_direction(df: pd.DataFrame, direction: str) -> bool:
    """
    Last CANDLE_CONFIRM_COUNT closed candles must close in signal direction.
    Prevents entering mid-reversal before price commits.
    """
    n = config.CANDLE_CONFIRM_COUNT
    if len(df) < n + 1:
        return False
    recent = df.iloc[-(n+1):-1]  # exclude current forming candle
    if direction == "BUY":
        return all(recent["close"].iloc[i] > recent["open"].iloc[i]
                   for i in range(len(recent)))
    else:
        return all(recent["close"].iloc[i] < recent["open"].iloc[i]
                   for i in range(len(recent)))


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
    level  = float(recent["low"].min()) if direction == "BUY" \
             else float(recent["high"].max())
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


def _score_sweep_and_orb(df: pd.DataFrame, direction: str) -> int:
    """
    Score up to +2:
    - Liquidity sweep: price broke beyond a swing level then reversed
    - ORB bonus: if we are in the opening range window, a sweep scores max
    """
    lb = min(config.LIQUIDITY_SWEEP_BARS + config.SWING_LOOKBACK, len(df) - 2)
    if lb < 4:
        return 0

    ref    = df.iloc[-(lb + 1):-(config.LIQUIDITY_SWEEP_BARS + 1)]
    recent = df.iloc[-(config.LIQUIDITY_SWEEP_BARS + 1):]

    swept = False
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
    except Exception:
        pass

    if not swept:
        return 0

    # During kill zone opening range — sweep gets full bonus
    if _is_orb_window():
        logger.debug("ORB sweep detected — full bonus awarded")
        return config.SCORE_LIQUIDITY_SWEEP

    return config.SCORE_LIQUIDITY_SWEEP


def _score_macd(df: pd.DataFrame, direction: str) -> int:
    """
    +2 if MACD confirms direction:
    - MACD line must be on correct side of signal line
    - Histogram must be growing (momentum increasing, not fading)
    Both conditions must be true.
    """
    if len(df) < 3:
        return 0

    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd       = last.get("macd",       np.nan)
    sig        = last.get("macd_signal", np.nan)
    hist       = last.get("macd_hist",   np.nan)
    prev_hist  = prev.get("macd_hist",   np.nan)

    if any(pd.isna(v) for v in [macd, sig, hist, prev_hist]):
        return 0

    if direction == "BUY":
        # MACD above signal AND histogram growing upward
        cross_ok = macd > sig
        momentum_growing = hist > prev_hist and hist > 0
    else:
        # MACD below signal AND histogram growing downward
        cross_ok = macd < sig
        momentum_growing = hist < prev_hist and hist < 0

    if cross_ok and momentum_growing:
        return config.SCORE_MACD
    return 0


# ── Market structure SL/TP ────────────────────────────────────────────────

def _find_structure_levels(
    df: pd.DataFrame,
    direction: str,
) -> Tuple[Optional[float], Optional[float]]:
    """Find swing-based SL and TP levels."""
    if len(df) < 40:
        return None, None

    recent = df.iloc[-41:-1]
    highs  = recent["high"].values
    lows   = recent["low"].values
    n      = len(highs)

    sh, sl = [], []
    for i in range(2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            sh.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            sl.append(lows[i])

    close = float(df["close"].iloc[-1])

    if direction == "BUY":
        below = [l for l in sl if l < close]
        above = [h for h in sh if h > close]
        sl_level = max(below) if below else None
        tp_level = min(above) if above else None
    else:
        above = [h for h in sh if h > close]
        below = [l for l in sl if l < close]
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
    """
    Compute SL and TP with validation:
    1. Try market structure levels first
    2. Fall back to ATR multiples if structure not found
    3. Apply ATR buffer to SL
    4. Enforce minimum pip distance on SL
    5. Validate minimum RR
    """
    pip      = _pip_value(pair)
    min_pips = _min_sl_pips(pair)

    sl_raw, tp_raw = _find_structure_levels(df, direction)

    if sl_raw is None or tp_raw is None:
        logger.debug("%s: no clear structure — using ATR levels", pair)
        if direction == "BUY":
            sl_raw = close - atr * config.ATR_SL_MULTIPLIER
            tp_raw = close + atr * config.ATR_TP_MULTIPLIER
        else:
            sl_raw = close + atr * config.ATR_SL_MULTIPLIER
            tp_raw = close - atr * config.ATR_TP_MULTIPLIER

    # Apply ATR buffer beyond the structure level
    if direction == "BUY":
        sl = sl_raw - atr * config.ATR_BUFFER
        tp = tp_raw
    else:
        sl = sl_raw + atr * config.ATR_BUFFER
        tp = tp_raw

    # Enforce minimum SL distance in pips
    sl_pips = abs(close - sl) / pip
    if sl_pips < min_pips:
        logger.debug("%s: SL too tight (%.1f pips < %.1f min) — widening", pair, sl_pips, min_pips)
        if direction == "BUY":
            sl = close - (min_pips * pip)
        else:
            sl = close + (min_pips * pip)

    risk   = abs(close - sl)
    reward = abs(tp - close)

    if reward <= 0 or risk <= 0:
        return None, None

    rr = reward / risk
    if rr < config.MIN_RISK_REWARD:
        logger.debug("%s: RR %.2f below minimum %.2f", pair, rr, config.MIN_RISK_REWARD)
        return None, None

    return sl, tp


# ── Main evaluation ───────────────────────────────────────────────────────

def evaluate_pair(
    pair:     str,
    df_entry: pd.DataFrame,
    df_htf:   pd.DataFrame,
) -> Optional[SignalResult]:
    """
    Full v2 signal evaluation pipeline:
    1. Add indicators to both timeframes
    2. Detect trend from market structure (HTF + entry TF must agree)
    3. Candle direction confirmation
    4. Score all 5 components
    5. Compute market-structure SL/TP
    6. Validate RR and minimum score
    """
    try:
        df_entry = _add_indicators(df_entry)
        df_htf   = _add_indicators(df_htf)

        if df_entry is None or df_htf is None:
            return None
        if len(df_entry) < config.MACD_SLOW + 30 or len(df_htf) < config.MACD_SLOW + 30:
            logger.debug("%s: not enough bars", pair)
            return None

        close = float(df_entry["close"].iloc[-1])
        atr   = float(df_entry["atr"].iloc[-1])

        if np.isnan(atr) or atr <= 0:
            return None

        # Sanity check: ATR must be < 5% of price
        if atr > close * 0.05:
            logger.warning("%s: ATR %.5f > 5%% of price — data corrupted, skipping", pair, atr)
            return None

        # ── Trend detection (both TFs must agree) ─────────────────────────
        htf_trend   = _detect_trend(df_htf)
        entry_trend = _detect_trend(df_entry)

        if htf_trend == "NEUTRAL" or entry_trend == "NEUTRAL":
            logger.debug("%s: no clear trend on one or both TFs", pair)
            return None
        if htf_trend != entry_trend:
            logger.debug("%s: TF conflict HTF=%s entry=%s", pair, htf_trend, entry_trend)
            return None

        direction = htf_trend

        # ── Candle confirmation ────────────────────────────────────────────
        if not _confirm_candle_direction(df_entry, direction):
            logger.debug("%s: candle direction not confirmed", pair)
            return None

        # ── Scoring ───────────────────────────────────────────────────────
        is_gold       = (pair == "XAU/USD")
        proximity_pct = config.GOLD_PROXIMITY_PCT if is_gold else config.SWING_PROXIMITY_PCT

        card = _Card()
        card.add("trend_structure",  config.SCORE_TREND_STRUCTURE)  # already confirmed
        card.add("rsi",              _score_rsi(df_entry, direction))
        card.add("swing_proximity",  _score_swing_proximity(df_entry, close, direction, proximity_pct))
        card.add("atr_volatility",   _score_atr(df_entry))
        card.add("liquidity_sweep",  _score_sweep_and_orb(df_entry, direction))
        card.add("macd",             _score_macd(df_entry, direction))

        logger.info("%s %s | Score %d/10 | %s",
                    pair, direction, card.total,
                    {k: v for k, v in card.breakdown.items() if v > 0})

        if card.total < config.MIN_SCORE_TO_TRADE:
            logger.debug("%s: score %d below threshold %d",
                         pair, card.total, config.MIN_SCORE_TO_TRADE)
            return None

        # ── SL/TP ─────────────────────────────────────────────────────────
        sl, tp = _compute_sl_tp(df_entry, direction, close, atr, pair)
        if sl is None or tp is None:
            logger.debug("%s: invalid SL/TP — signal rejected", pair)
            return None

        risk   = abs(close - sl)
        reward = abs(tp - close)
        rr     = round(reward / risk, 2) if risk > 0 else 0.0

        pip        = _pip_value(pair)
        pip_risk   = round(risk   / pip, 1)
        pip_reward = round(reward / pip, 1)

        decimals = 2 if is_gold else (3 if "JPY" in pair else 5)

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
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
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
