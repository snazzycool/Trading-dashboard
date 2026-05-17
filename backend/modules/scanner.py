"""
modules/scanner.py — Background scanner with automated trade execution.

Jobs:
  scan_markets      Every 30 min — scans pairs, fires signals, executes trades
  check_results     Every 30 min — checks pending signals against live price
  manage_trailing   Every 60 sec — manages breakeven and trailing stops
  update_account    Every 60 sec — fetches account info for dashboard
"""
import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from modules import database as db
from modules import market_data as md
from modules import strategy as strat
from modules.capital_client import capital
from modules.trade_executor import (
    execute_signal,
    manage_trailing_stops,
    sync_open_positions,
)

logger = logging.getLogger(__name__)

_executor  = ThreadPoolExecutor(max_workers=4)
_scheduler = AsyncIOScheduler(timezone="UTC")
_ws_clients: set = set()
_MAX_SIGNAL_AGE_HOURS = 24

# Latest account info cached for dashboard
_account_cache: dict = {}


def register_client(send_fn):
    _ws_clients.add(send_fn)


def unregister_client(send_fn):
    _ws_clients.discard(send_fn)


async def _broadcast(event: str, payload: dict):
    msg  = json.dumps({"event": event, "data": payload})
    dead = set()
    for fn in list(_ws_clients):
        try:
            await fn(msg)
        except Exception:
            dead.add(fn)
    for fn in dead:
        _ws_clients.discard(fn)


# ── Account updater ───────────────────────────────────────────────────────

async def update_account():
    """Fetch live account info every 60 seconds and push to dashboard."""
    global _account_cache
    if not capital.is_connected():
        return

    loop    = asyncio.get_event_loop()
    account = await loop.run_in_executor(_executor, capital.get_account_info)
    if not account:
        return

    positions = await loop.run_in_executor(_executor, capital.get_open_positions)

    _account_cache = account

    # Save snapshot every hour (on the hour)
    if datetime.utcnow().minute == 0:
        db.save_account_snapshot(account)

    await _broadcast("account_update", {
        "balance":     account.get("balance",     0),
        "equity":      account.get("balance", 0) + account.get("profit_loss", 0),
        "profit_loss": account.get("profit_loss", 0),
        "available":   account.get("available",   0),
        "currency":    account.get("currency",    "USD"),
        "environment": config.CAPITAL_ENV.upper(),
        "positions":   positions,
    })


# ── Market scanner ────────────────────────────────────────────────────────

async def scan_markets():
    """Main scan job — evaluates all pairs and executes qualifying signals."""
    if db.get_state("scanner_active", "off") != "on":
        return

    if db.count_signals_last_hour() >= config.MAX_SIGNALS_PER_HOUR:
        await _broadcast("scanner_status", {
            "message": "Hourly signal cap reached — pausing",
            "scanning": False,
        })
        return

    logger.info("Scan started — %d pairs", len(config.WATCHLIST))
    await _broadcast("scanner_status", {
        "message": f"Scanning {len(config.WATCHLIST)} pairs…",
        "scanning": True,
    })

    loop         = asyncio.get_event_loop()
    signals_sent = 0

    for pair in config.WATCHLIST:
        if db.count_signals_last_hour() >= config.MAX_SIGNALS_PER_HOUR:
            break

        recent = db.get_recent_signal_for_pair(pair, config.MIN_SIGNAL_GAP_SECONDS)
        if recent:
            logger.debug("%s: cooldown active", pair)
            continue

        try:
            df_entry, df_htf = await loop.run_in_executor(
                _executor, _fetch_pair, pair
            )
            if df_entry is None or df_htf is None:
                continue

            signal = strat.evaluate_pair(pair, df_entry, df_htf)
            if signal is None:
                continue

            # Persist signal
            sig_id = db.insert_signal(
                pair=signal.pair,
                direction=signal.direction,
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                score=signal.score,
                score_breakdown=signal.score_breakdown,
                atr=signal.atr,
                risk_reward=signal.risk_reward,
                pip_risk=signal.pip_risk,
                pip_reward=signal.pip_reward,
            )

            if sig_id < 0:
                continue

            sig_dict = db.get_signal_by_id(sig_id)
            if not sig_dict:
                continue

            # Broadcast signal to dashboard
            await _broadcast("new_signal", db.serialize(sig_dict))
            signals_sent += 1

            logger.info(
                "Signal: %s %s score=%d/8 pips risk=%.0f reward=%.0f",
                pair, signal.direction, signal.score,
                signal.pip_risk, signal.pip_reward,
            )

            # ── Auto trade execution ──────────────────────────────────────
            if config.AUTO_TRADE and capital.is_connected():
                sig_dict["id"] = sig_id
                trade_placed = await execute_signal(sig_dict)
                if trade_placed:
                    await _broadcast("trade_opened", {
                        "signal_id": sig_id,
                        "pair":      signal.pair,
                        "direction": signal.direction,
                        "score":     signal.score,
                        "message":   f"Trade opened: {signal.pair} {signal.direction}",
                    })
                else:
                    logger.warning("%s: signal generated but trade not placed", pair)

        except Exception as e:
            logger.error("Error scanning %s: %s", pair, e, exc_info=True)

    await _broadcast("scanner_status", {
        "message":   f"Scan complete — {signals_sent} signal(s) found",
        "scanning":  False,
        "last_scan": datetime.utcnow().isoformat(),
    })
    logger.info("Scan complete. Signals: %d", signals_sent)


def _fetch_pair(pair: str):
    return (
        md.get_candles(pair, config.ENTRY_INTERVAL, config.BARS_REQUIRED),
        md.get_candles(pair, config.HTF_INTERVAL,   config.BARS_REQUIRED),
    )


# ── Result checker ────────────────────────────────────────────────────────

async def check_results():
    """Check pending signals against live price — mark WIN/LOSS/EXPIRED."""
    pending = db.get_pending_signals()
    if not pending:
        return

    logger.info("Checking %d pending signal(s)", len(pending))
    loop = asyncio.get_event_loop()

    for sig in pending:
        try:
            created = datetime.fromisoformat(sig["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - created).total_seconds() / 3600

            if age_h > _MAX_SIGNAL_AGE_HOURS:
                db.resolve_signal(sig["id"], "EXPIRED")
                await _broadcast("signal_update", {
                    "id":          sig["id"],
                    "status":      "EXPIRED",
                    "resolved_at": datetime.utcnow().isoformat(),
                })
                continue

            price = await loop.run_in_executor(
                _executor, md.get_current_price, sig["pair"]
            )
            if price is None:
                continue

            outcome = strat.check_outcome(
                direction=sig["direction"],
                entry=sig["entry"],
                stop_loss=sig["stop_loss"],
                take_profit=sig["take_profit"],
                current_price=price,
            )

            if outcome:
                db.resolve_signal(sig["id"], outcome)
                now = datetime.utcnow().isoformat()
                await _broadcast("signal_update", {
                    "id":            sig["id"],
                    "status":        outcome,
                    "resolved_at":   now,
                    "current_price": price,
                })
                logger.info("Signal #%d %s → %s", sig["id"], sig["pair"], outcome)

                # Notify dashboard
                icon = "✅" if outcome == "WIN" else "❌"
                await _broadcast("trade_closed", {
                    "signal_id": sig["id"],
                    "pair":      sig["pair"],
                    "direction": sig["direction"],
                    "outcome":   outcome,
                    "message":   f"{icon} {outcome}: {sig['pair']} {sig['direction']}",
                })

        except Exception as e:
            logger.error("Result check error signal #%d: %s", sig["id"], e)


# ── Trailing stop job ─────────────────────────────────────────────────────

async def run_trailing_stops():
    """Check and update trailing stops every 60 seconds."""
    if not capital.is_connected():
        return
    try:
        await manage_trailing_stops()
    except Exception as e:
        logger.error("Trailing stop error: %s", e)


# ── Scheduler ─────────────────────────────────────────────────────────────

def start_scheduler():
    now = datetime.now(timezone.utc)

    _scheduler.add_job(
        scan_markets, "interval",
        seconds=config.SCAN_INTERVAL_SECONDS,
        id="scan_markets", replace_existing=True,
        next_run_time=now + timedelta(seconds=10),
    )
    _scheduler.add_job(
        check_results, "interval",
        seconds=config.RESULT_CHECK_INTERVAL_SECONDS,
        id="check_results", replace_existing=True,
        next_run_time=now + timedelta(seconds=60),
    )
    _scheduler.add_job(
        run_trailing_stops, "interval",
        seconds=config.TRAILING_CHECK_INTERVAL_SECONDS,
        id="trailing_stops", replace_existing=True,
        next_run_time=now + timedelta(seconds=30),
    )
    _scheduler.add_job(
        update_account, "interval",
        seconds=60,
        id="update_account", replace_existing=True,
        next_run_time=now + timedelta(seconds=5),
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — scan=%ds results=%ds trailing=%ds account=60s",
        config.SCAN_INTERVAL_SECONDS,
        config.RESULT_CHECK_INTERVAL_SECONDS,
        config.TRAILING_CHECK_INTERVAL_SECONDS,
    )


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


def get_account_cache() -> dict:
    return _account_cache
