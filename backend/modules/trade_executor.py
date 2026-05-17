"""
modules/trade_executor.py — Automated trade execution engine.

Handles:
  - Score-based position sizing
  - Max 3 open trades circuit breaker
  - Duplicate pair prevention
  - Trade placement and confirmation
  - Trailing stop management
  - Daily loss circuit breaker
  - Breakeven stop logic
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import config
from modules.capital_client import capital, EPIC_MAP
from modules import database as db

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

# In-memory trailing stop state: deal_id → { entry, sl, tp, direction, score, pair }
_trailing_state: dict[str, dict] = {}


# ── Position sizing ───────────────────────────────────────────────────────

def calculate_position_size(
    pair:      str,
    score:     int,
    entry:     float,
    stop_loss: float,
    balance:   float,
) -> float:
    """
    Score-based position sizing.
    Risk % of account based on signal quality:
      score 5/8 → 0.5%
      score 6/8 → 1.0%
      score 7/8 → 1.5%
      score 8/8 → 2.0%

    Size = (balance × risk%) / (entry - stop_loss)
    """
    risk_pct_map = {
        5: 0.005,   # 0.5%
        6: 0.010,   # 1.0%
        7: 0.015,   # 1.5%
        8: 0.020,   # 2.0%
    }
    risk_pct  = risk_pct_map.get(score, 0.005)
    risk_amt  = balance * risk_pct
    risk_per_unit = abs(entry - stop_loss)

    if risk_per_unit <= 0:
        logger.warning("%s: zero risk per unit — using minimum size", pair)
        return _min_size(pair)

    size = risk_amt / risk_per_unit

    # Round to appropriate precision
    if pair == "XAU/USD":
        size = max(round(size, 2), _min_size(pair))
    else:
        size = max(round(size / 1000) * 1000, _min_size(pair))

    logger.info(
        "%s: balance=%.2f risk_pct=%.1f%% risk_amt=%.2f size=%.2f",
        pair, balance, risk_pct * 100, risk_amt, size,
    )
    return size


def _min_size(pair: str) -> float:
    from modules.capital_client import MIN_SIZE, EPIC_MAP
    epic = EPIC_MAP.get(pair, "")
    return MIN_SIZE.get(epic, 1000)


# ── Circuit breakers ──────────────────────────────────────────────────────

def check_max_trades() -> bool:
    """Return True if we can open more trades (< MAX_OPEN_TRADES)."""
    positions = capital.get_open_positions()
    if len(positions) >= config.MAX_OPEN_TRADES:
        logger.info("Max open trades reached (%d) — blocking new entry", config.MAX_OPEN_TRADES)
        return False
    return True


def check_duplicate_pair(pair: str) -> bool:
    """Return True if pair is NOT already open (safe to trade)."""
    epic = EPIC_MAP.get(pair)
    positions = capital.get_open_positions()
    for p in positions:
        if p.get("epic") == epic:
            logger.info("%s already has an open position — skipping", pair)
            return False
    return True


def check_daily_loss_limit(account_info: dict) -> bool:
    """
    Return True if we haven't hit the daily loss limit.
    Compares today's P&L against DAILY_LOSS_LIMIT_PCT of balance.
    """
    balance   = account_info.get("balance",     0)
    profit    = account_info.get("profit_loss",  0)
    limit_pct = config.DAILY_LOSS_LIMIT_PCT / 100

    if balance <= 0:
        return True

    if profit < 0 and abs(profit) / balance >= limit_pct:
        logger.warning(
            "Daily loss limit hit: P&L=%.2f Balance=%.2f (%.1f%% loss)",
            profit, balance, abs(profit) / balance * 100,
        )
        return False
    return True


# ── Trade execution ───────────────────────────────────────────────────────

async def execute_signal(signal: dict) -> bool:
    """
    Full trade execution pipeline for a given signal dict.
    Returns True if trade was placed successfully.
    """
    pair      = signal["pair"]
    direction = signal["direction"]
    entry     = signal["entry"]
    sl        = signal["stop_loss"]
    tp        = signal["take_profit"]
    score     = signal["score"]

    # ── Circuit breakers ──────────────────────────────────────────────────
    if not capital.is_connected():
        logger.error("Capital.com not connected — cannot execute trade")
        return False

    loop = asyncio.get_event_loop()

    account = await loop.run_in_executor(_executor, capital.get_account_info)
    if not account:
        logger.error("Cannot fetch account info — aborting trade")
        return False

    if not check_daily_loss_limit(account):
        logger.warning("Daily loss limit reached — no new trades today")
        return False

    if not check_max_trades():
        return False

    if not check_duplicate_pair(pair):
        return False

    # ── Position sizing ───────────────────────────────────────────────────
    balance = account.get("balance", 0)
    size    = calculate_position_size(pair, score, entry, sl, balance)

    # ── Place order ───────────────────────────────────────────────────────
    deal_ref = await loop.run_in_executor(
        _executor,
        lambda: capital.place_order(pair, direction, size, sl, tp),
    )

    if not deal_ref:
        logger.error("%s: order placement failed", pair)
        return False

    # ── Confirm order ─────────────────────────────────────────────────────
    await asyncio.sleep(2)   # brief wait for confirmation to be available

    confirmation = await loop.run_in_executor(
        _executor,
        lambda: capital.get_deal_confirmation(deal_ref),
    )

    if not confirmation or confirmation.get("status") != "ACCEPTED":
        logger.error("%s: order not accepted — %s", pair, confirmation)
        return False

    deal_id = confirmation.get("deal_id")
    logger.info(
        "Trade confirmed: %s %s deal_id=%s size=%.2f",
        pair, direction, deal_id, size,
    )

    # ── Store trade in database with deal_id ──────────────────────────────
    db.update_signal_deal_id(signal["id"], deal_id, size)

    # ── Register for trailing stop if score qualifies ─────────────────────
    if score >= config.TRAILING_STOP_MIN_SCORE:
        _trailing_state[deal_id] = {
            "pair":       pair,
            "direction":  direction,
            "entry":      entry,
            "sl":         sl,
            "tp":         tp,
            "score":      score,
            "size":       size,
            "breakeven":  False,   # has SL been moved to breakeven?
            "trailing":   False,   # has trailing started?
        }
        logger.info("%s: registered for trailing stop (score=%d)", pair, score)

    return True


# ── Trailing stop management ──────────────────────────────────────────────

async def manage_trailing_stops():
    """
    Called every 60 seconds by the scheduler.
    Manages breakeven and trailing stop logic for qualifying trades.

    Logic:
      Stage 1 — Breakeven:
        When profit >= risk (1:1 RR), move SL to entry price.
        Trade can no longer result in a loss.

      Stage 2 — Trailing:
        When profit >= 1.5 × risk, trail SL at 50% of the move.
        As price advances, SL follows at half the distance.
        Locks in profit while letting winners run.
    """
    if not _trailing_state:
        return

    loop      = asyncio.get_event_loop()
    positions = await loop.run_in_executor(_executor, capital.get_open_positions)
    pos_map   = {p["deal_id"]: p for p in positions}

    for deal_id, state in list(_trailing_state.items()):
        if deal_id not in pos_map:
            # Position closed — remove from trailing state
            _trailing_state.pop(deal_id, None)
            continue

        pos       = pos_map[deal_id]
        current   = pos.get("open_level", state["entry"])
        direction = state["direction"]
        entry     = state["entry"]
        sl        = state["sl"]
        tp        = state["tp"]

        risk   = abs(entry - sl)
        profit = (current - entry) if direction == "BUY" else (entry - current)

        # ── Stage 1: Breakeven ─────────────────────────────────────────────
        if not state["breakeven"] and profit >= risk:
            new_sl = entry   # move SL to entry (zero loss)
            success = await loop.run_in_executor(
                _executor,
                lambda: capital.modify_stop_loss(deal_id, new_sl),
            )
            if success:
                state["sl"]        = new_sl
                state["breakeven"] = True
                logger.info(
                    "%s: SL moved to breakeven (entry=%.5f profit=%.5f)",
                    state["pair"], entry, profit,
                )

        # ── Stage 2: Trailing ──────────────────────────────────────────────
        elif state["breakeven"] and profit >= risk * 1.5:
            # Trail at 50% of the move above/below entry
            if direction == "BUY":
                trail_sl = current - risk * 0.5
                if trail_sl > state["sl"]:   # only move SL forward
                    success = await loop.run_in_executor(
                        _executor,
                        lambda: capital.modify_stop_loss(deal_id, trail_sl),
                    )
                    if success:
                        state["sl"]      = trail_sl
                        state["trailing"] = True
                        logger.info(
                            "%s: trailing SL updated to %.5f (profit=%.5f)",
                            state["pair"], trail_sl, profit,
                        )
            else:  # SELL
                trail_sl = current + risk * 0.5
                if trail_sl < state["sl"]:   # only move SL forward
                    success = await loop.run_in_executor(
                        _executor,
                        lambda: capital.modify_stop_loss(deal_id, trail_sl),
                    )
                    if success:
                        state["sl"]      = trail_sl
                        state["trailing"] = True
                        logger.info(
                            "%s: trailing SL updated to %.5f (profit=%.5f)",
                            state["pair"], trail_sl, profit,
                        )


# ── Startup position sync ─────────────────────────────────────────────────

async def sync_open_positions():
    """
    On bot startup, sync Capital.com open positions with our database.
    Re-registers qualifying positions for trailing stop management.
    """
    loop      = asyncio.get_event_loop()
    positions = await loop.run_in_executor(_executor, capital.get_open_positions)

    if not positions:
        logger.info("No open positions to sync on startup")
        return

    logger.info("Syncing %d open position(s) from Capital.com", len(positions))

    pending_signals = db.get_pending_signals()
    sig_map = {s.get("deal_id"): s for s in pending_signals if s.get("deal_id")}

    for pos in positions:
        deal_id = pos.get("deal_id")
        if deal_id and deal_id in sig_map:
            sig = sig_map[deal_id]
            if sig.get("score", 0) >= config.TRAILING_STOP_MIN_SCORE:
                _trailing_state[deal_id] = {
                    "pair":       sig["pair"],
                    "direction":  sig["direction"],
                    "entry":      sig["entry"],
                    "sl":         sig["stop_loss"],
                    "tp":         sig["take_profit"],
                    "score":      sig["score"],
                    "size":       sig.get("trade_size", 0),
                    "breakeven":  False,
                    "trailing":   False,
                }
                logger.info(
                    "%s: re-registered for trailing stop after sync",
                    sig["pair"],
                )
