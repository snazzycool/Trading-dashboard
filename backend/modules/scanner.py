"""
modules/scanner.py — Background scanner v2.
Scans every 15 minutes during London/New York sessions only.
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

logger = logging.getLogger(__name__)

_executor  = ThreadPoolExecutor(max_workers=4)
_scheduler = AsyncIOScheduler(timezone="UTC")
_ws_clients: set = set()
_MAX_SIGNAL_AGE_HOURS = 24


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


# ── Session check ─────────────────────────────────────────────────────────

def _in_active_session() -> bool:
    hour = datetime.now(timezone.utc).hour
    return any(s <= hour < e for s, e in config.ACTIVE_SESSION_HOURS)


# ── Market scanner ────────────────────────────────────────────────────────

async def scan_markets():
    if db.get_state("scanner_active", "off") != "on":
        return

    if not _in_active_session():
        logger.debug("Outside active session — scanner sleeping")
        await _broadcast("scanner_status", {
            "message": "Outside London/New York session — waiting",
            "scanning": False,
        })
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
            logger.debug("%s: cooldown active — skipping", pair)
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
            if sig_dict:
                await _broadcast("new_signal", db.serialize(sig_dict))
                signals_sent += 1
                logger.info(
                    "Signal: %s %s score=%d/10 pips risk=%.0f reward=%.0f",
                    pair, signal.direction, signal.score,
                    signal.pip_risk, signal.pip_reward,
                )

        except Exception as e:
            logger.error("Error scanning %s: %s", pair, e, exc_info=True)

    await _broadcast("scanner_status", {
        "message": f"Scan complete — {signals_sent} signal(s) found",
        "scanning": False,
        "last_scan": datetime.utcnow().isoformat(),
    })
    logger.info("Scan complete. Signals sent: %d", signals_sent)


def _fetch_pair(pair: str):
    df_entry = md.get_candles(pair, config.ENTRY_INTERVAL, config.BARS_REQUIRED)
    df_htf   = md.get_candles(pair, config.HTF_INTERVAL,   config.BARS_REQUIRED)
    return df_entry, df_htf


# ── Result checker ────────────────────────────────────────────────────────

async def check_results():
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
                await _broadcast("signal_update", {
                    "id":            sig["id"],
                    "status":        outcome,
                    "resolved_at":   datetime.utcnow().isoformat(),
                    "current_price": price,
                })
                logger.info("Signal #%d %s → %s", sig["id"], sig["pair"], outcome)

        except Exception as e:
            logger.error("Result check error signal #%d: %s", sig["id"], e)


# ── Scheduler ─────────────────────────────────────────────────────────────

def start_scheduler():
    _scheduler.add_job(
        scan_markets, "interval",
        seconds=config.SCAN_INTERVAL_SECONDS,
        id="scan_markets",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    _scheduler.add_job(
        check_results, "interval",
        seconds=config.RESULT_CHECK_INTERVAL_SECONDS,
        id="check_results",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — scan every %ds, results every %ds",
        config.SCAN_INTERVAL_SECONDS,
        config.RESULT_CHECK_INTERVAL_SECONDS,
    )


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
