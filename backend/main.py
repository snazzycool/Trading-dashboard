"""
main.py — FastAPI application entry point.
Serves REST API + WebSocket endpoint for real-time signal streaming.
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
from modules import database as db
from modules import scanner

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App lifecycle ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scanner.start_scheduler()
    logger.info("Trading dashboard backend started")
    yield
    scanner.stop_scheduler()
    logger.info("Backend stopped")

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
        # Send current scanner state immediately on connect
        active = db.get_state("scanner_active", "off") == "on"
        await ws.send_text(json.dumps({
            "event": "init",
            "data": {
                "scanner_active": active,
                "signals": [_ser(s) for s in db.get_all_signals(50)],
                "stats": db.get_performance_stats(),
            }
        }))

        # Listen for control messages from browser
        async for raw in ws.iter_text():
            try:
                msg = json.loads(raw)
                await _handle_ws_message(msg, ws)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        scanner.unregister_client(send)

async def _handle_ws_message(msg: dict, ws: WebSocket):
    action = msg.get("action")
    if action == "start_scanner":
        db.set_state("scanner_active", "on")
        await ws.send_text(json.dumps({
            "event": "scanner_toggled", "data": {"active": True}
        }))
        logger.info("Scanner enabled via WebSocket")

    elif action == "stop_scanner":
        db.set_state("scanner_active", "off")
        await ws.send_text(json.dumps({
            "event": "scanner_toggled", "data": {"active": False}
        }))
        logger.info("Scanner disabled via WebSocket")

    elif action == "get_stats":
        await ws.send_text(json.dumps({
            "event": "stats_update",
            "data": db.get_performance_stats()
        }))

    elif action == "get_signals":
        limit = msg.get("limit", 100)
        await ws.send_text(json.dumps({
            "event": "signals_list",
            "data": [_ser(s) for s in db.get_all_signals(limit)]
        }))

# ── REST endpoints ────────────────────────────────────────────────────────

@app.get("/api/signals")
def get_signals(limit: int = 100):
    return [_ser(s) for s in db.get_all_signals(limit)]

@app.get("/api/signals/{signal_id}")
def get_signal(signal_id: int):
    sig = db.get_signal_by_id(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _ser(sig)

@app.get("/api/stats")
def get_stats():
    return db.get_performance_stats()

@app.get("/api/scanner/status")
def scanner_status():
    active = db.get_state("scanner_active", "off") == "on"
    return {"active": active}

@app.post("/api/scanner/start")
def start_scanner():
    db.set_state("scanner_active", "on")
    return {"active": True}

@app.post("/api/scanner/stop")
def stop_scanner():
    db.set_state("scanner_active", "off")
    return {"active": False}

# ── Serve React frontend (production) ─────────────────────────────────────

_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "dist")

if os.path.isdir(_FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        index = os.path.join(_FRONTEND_DIST, "index.html")
        return FileResponse(index)

# ── Helper ────────────────────────────────────────────────────────────────

def _ser(row: dict) -> dict:
    import json as _json
    try:
        row["score_breakdown"] = _json.loads(row.get("score_breakdown") or "{}")
    except Exception:
        row["score_breakdown"] = {}
    return row

# ── Dev entrypoint ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
