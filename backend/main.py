"""
main.py — FastAPI application with Capital.com automation.
"""
import logging
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import config
from modules import database as db_sqlite
from modules import database_supabase as db_supabase
from modules import scanner
from modules import market_data as md
from modules.capital_client import capital
from modules.trade_executor import sync_open_positions

# Use Supabase if configured, otherwise fall back to SQLite
db = db_supabase if config.USE_SUPABASE else db_sqlite

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    db.init_db()

    # Connect to Capital.com
    if config.CAPITAL_API_KEY and config.CAPITAL_IDENTIFIER:
        connected = capital.login()
        if connected:
            logger.info("Capital.com connected (%s)", config.CAPITAL_ENV.upper())
            await sync_open_positions()
        else:
            logger.warning(
                "Capital.com login failed — signals will work but no auto-trading"
            )
    else:
        logger.warning("Capital.com credentials not set — running in signal-only mode")

    scanner.start_scheduler()
    logger.info("Trading bot started")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    scanner.stop_scheduler()
    capital.logout()
    logger.info("Trading bot stopped")


app = FastAPI(title="Trading Signal Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket ─────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    async def send(msg: str):
        await ws.send_text(msg)

    scanner.register_client(send)
    logger.info("WebSocket client connected")

    try:
        # Send full state on connect
        account_info = scanner.get_account_cache() or {}
        positions    = capital.get_open_positions() if capital.is_connected() else []

        await ws.send_text(json.dumps({
            "event": "init",
            "data": {
                "scanner_active": db.get_state("scanner_active", "off") == "on",
                "signals":        [db.serialize(s) for s in db.get_all_signals(50)],
                "stats":          db.get_performance_stats(),
                "account":        account_info,
                "positions":      positions,
                "auto_trade":     config.AUTO_TRADE,
                "capital_env":    config.CAPITAL_ENV.upper(),
                "capital_connected": capital.is_connected(),
            },
        }))

        async for raw in ws.iter_text():
            try:
                await _handle_ws(json.loads(raw), ws)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        scanner.unregister_client(send)


async def _handle_ws(msg: dict, ws: WebSocket):
    action = msg.get("action")

    if action == "start_scanner":
        db.set_state("scanner_active", "on")
        await ws.send_text(json.dumps({
            "event": "scanner_toggled", "data": {"active": True}
        }))

    elif action == "stop_scanner":
        db.set_state("scanner_active", "off")
        await ws.send_text(json.dumps({
            "event": "scanner_toggled", "data": {"active": False}
        }))

    elif action == "get_stats":
        await ws.send_text(json.dumps({
            "event": "stats_update", "data": db.get_performance_stats()
        }))

    elif action == "get_account":
        info = capital.get_account_info() if capital.is_connected() else {}
        await ws.send_text(json.dumps({
            "event": "account_update", "data": info or {}
        }))

    elif action == "get_positions":
        positions = capital.get_open_positions() if capital.is_connected() else []
        await ws.send_text(json.dumps({
            "event": "positions_update", "data": positions
        }))


# ── REST endpoints ────────────────────────────────────────────────────────

@app.get("/api/signals")
def get_signals(limit: int = 100):
    return [db.serialize(s) for s in db.get_all_signals(limit)]

@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: int):
    sig = db.get_signal_by_id(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return db.serialize(sig)

@app.get("/api/stats")
def get_stats():
    return db.get_performance_stats()

@app.get("/api/account")
def get_account():
    if not capital.is_connected():
        return {"error": "Capital.com not connected", "connected": False}
    info = capital.get_account_info()
    if not info:
        return {"error": "Failed to fetch account", "connected": True}
    return {**info, "connected": True, "environment": config.CAPITAL_ENV.upper()}

@app.get("/api/positions")
def get_positions():
    if not capital.is_connected():
        return []
    return capital.get_open_positions()

@app.get("/api/scanner/status")
def scanner_status():
    return {
        "active":            db.get_state("scanner_active", "off") == "on",
        "capital_connected": capital.is_connected(),
        "auto_trade":        config.AUTO_TRADE,
        "environment":       config.CAPITAL_ENV.upper(),
    }

@app.post("/api/scanner/start")
def start_scanner():
    db.set_state("scanner_active", "on")
    return {"active": True}

@app.post("/api/scanner/stop")
def stop_scanner():
    db.set_state("scanner_active", "off")
    return {"active": False}


@app.get("/api/usage")
def get_api_usage():
    """Get TwelveData API usage statistics."""
    return md.get_api_usage()


# ── Serve React frontend ──────────────────────────────────────────────────

_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "dist")

if os.path.isdir(_FRONTEND_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))
