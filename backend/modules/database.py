"""
modules/database.py
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional
import config

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pair            TEXT    NOT NULL,
    direction       TEXT    NOT NULL CHECK(direction IN ('BUY','SELL')),
    entry           REAL    NOT NULL,
    stop_loss       REAL    NOT NULL,
    take_profit     REAL    NOT NULL,
    score           INTEGER NOT NULL,
    score_breakdown TEXT    NOT NULL DEFAULT '{}',
    atr             REAL    NOT NULL,
    risk_reward     REAL    NOT NULL DEFAULT 0,
    pip_risk        REAL    NOT NULL DEFAULT 0,
    pip_reward      REAL    NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'PENDING'
                    CHECK(status IN ('PENDING','WIN','LOSS','EXPIRED')),
    created_at      TEXT    NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS scanner_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    # Add pip columns if upgrading from older schema
    try:
        conn.execute("ALTER TABLE signals ADD COLUMN pip_risk REAL NOT NULL DEFAULT 0")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE signals ADD COLUMN pip_reward REAL NOT NULL DEFAULT 0")
    except Exception:
        pass
    return conn

def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    logger.info("Database ready: %s", config.DB_PATH)

def insert_signal(pair, direction, entry, stop_loss, take_profit,
                  score, score_breakdown, atr, risk_reward,
                  pip_risk=0.0, pip_reward=0.0) -> int:
    import json
    now = datetime.utcnow().isoformat(timespec="seconds")
    sql = """
        INSERT INTO signals
            (pair, direction, entry, stop_loss, take_profit,
             score, score_breakdown, atr, risk_reward, pip_risk, pip_reward,
             status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING',?)
    """
    with _connect() as conn:
        cur = conn.execute(sql, (
            pair, direction, entry, stop_loss, take_profit,
            score, json.dumps(score_breakdown), atr, risk_reward,
            pip_risk, pip_reward, now
        ))
        return cur.lastrowid or -1

def get_pending_signals() -> list:
    sql = "SELECT * FROM signals WHERE status='PENDING' ORDER BY created_at"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]

def resolve_signal(signal_id: int, outcome: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "UPDATE signals SET status=?, resolved_at=? WHERE id=?",
            (outcome, now, signal_id)
        )

def get_recent_signal_for_pair(pair: str, within_seconds: int):
    sql = """
        SELECT * FROM signals
        WHERE pair=?
          AND created_at >= datetime('now', ? || ' seconds')
        ORDER BY created_at DESC LIMIT 1
    """
    with _connect() as conn:
        row = conn.execute(sql, (pair, f"-{within_seconds}")).fetchone()
        return dict(row) if row else None

def count_signals_last_hour() -> int:
    sql = "SELECT COUNT(*) FROM signals WHERE created_at >= datetime('now','-1 hour')"
    with _connect() as conn:
        return conn.execute(sql).fetchone()[0]

def get_all_signals(limit: int = 100) -> list:
    sql = "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]

def get_signal_by_id(signal_id: int):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        return dict(row) if row else None

def get_performance_stats() -> dict:
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='WIN'     THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN status='LOSS'    THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status='EXPIRED' THEN 1 ELSE 0 END) AS expired
        FROM signals
    """
    with _connect() as conn:
        row = dict(conn.execute(sql).fetchone())
    wins = row.get("wins") or 0
    losses = row.get("losses") or 0
    resolved = wins + losses
    row["win_rate"] = round(wins / resolved * 100, 1) if resolved > 0 else 0.0
    pair_sql = """
        SELECT pair,
            SUM(CASE WHEN status='WIN'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) as losses,
            COUNT(*) as total
        FROM signals GROUP BY pair ORDER BY total DESC
    """
    with _connect() as conn:
        row["by_pair"] = [dict(r) for r in conn.execute(pair_sql).fetchall()]
    return row

def set_state(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scanner_state (key,value) VALUES (?,?)",
            (key, value)
        )

def get_state(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM scanner_state WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default
