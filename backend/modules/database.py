"""
modules/database.py — SQLite persistence layer.
Updated for automation: stores deal_id and trade_size from Capital.com.
"""
import sqlite3
import logging
import json
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
    deal_id         TEXT,
    trade_size      REAL    DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'PENDING'
                    CHECK(status IN ('PENDING','WIN','LOSS','EXPIRED')),
    created_at      TEXT    NOT NULL,
    resolved_at     TEXT
);

CREATE TABLE IF NOT EXISTS scanner_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    balance     REAL    NOT NULL,
    equity      REAL    NOT NULL,
    profit_loss REAL    NOT NULL,
    available   REAL    NOT NULL,
    recorded_at TEXT    NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    # Safe migrations for existing databases
    migrations = [
        ("pip_risk",    "REAL NOT NULL DEFAULT 0"),
        ("pip_reward",  "REAL NOT NULL DEFAULT 0"),
        ("deal_id",     "TEXT"),
        ("trade_size",  "REAL DEFAULT 0"),
    ]
    for col, typedef in migrations:
        try:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {typedef}")
            conn.commit()
        except Exception:
            pass
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL NOT NULL,
                equity REAL NOT NULL,
                profit_loss REAL NOT NULL,
                available REAL NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """)
        conn.commit()
    except Exception:
        pass
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
    logger.info("Database ready: %s", config.DB_PATH)


# ── Signal CRUD ───────────────────────────────────────────────────────────

def insert_signal(
    pair: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    score: int,
    score_breakdown: dict,
    atr: float,
    risk_reward: float,
    pip_risk: float = 0.0,
    pip_reward: float = 0.0,
) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    sql = """
        INSERT INTO signals
            (pair, direction, entry, stop_loss, take_profit,
             score, score_breakdown, atr, risk_reward,
             pip_risk, pip_reward, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING',?)
    """
    with _connect() as conn:
        cur = conn.execute(sql, (
            pair, direction, entry, stop_loss, take_profit,
            score, json.dumps(score_breakdown), atr, risk_reward,
            pip_risk, pip_reward, now,
        ))
        return cur.lastrowid or -1


def update_signal_deal_id(signal_id: int, deal_id: str, trade_size: float) -> None:
    """Store Capital.com deal_id and trade size after order is confirmed."""
    with _connect() as conn:
        conn.execute(
            "UPDATE signals SET deal_id=?, trade_size=? WHERE id=?",
            (deal_id, trade_size, signal_id),
        )


def get_pending_signals() -> list[dict]:
    sql = "SELECT * FROM signals WHERE status='PENDING' ORDER BY created_at"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def resolve_signal(signal_id: int, outcome: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "UPDATE signals SET status=?, resolved_at=? WHERE id=?",
            (outcome, now, signal_id),
        )


def get_recent_signal_for_pair(pair: str, within_seconds: int) -> Optional[dict]:
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


def get_all_signals(limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]


def get_signal_by_id(signal_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE id=?", (signal_id,)
        ).fetchone()
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
    wins     = row.get("wins")   or 0
    losses   = row.get("losses") or 0
    resolved = wins + losses
    row["win_rate"] = round(wins / resolved * 100, 1) if resolved > 0 else 0.0
    pair_sql = """
        SELECT pair,
            SUM(CASE WHEN status='WIN'  THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN status='LOSS' THEN 1 ELSE 0 END) AS losses,
            COUNT(*) AS total
        FROM signals GROUP BY pair ORDER BY total DESC
    """
    with _connect() as conn:
        row["by_pair"] = [dict(r) for r in conn.execute(pair_sql).fetchall()]
    return row


# ── Account snapshots ─────────────────────────────────────────────────────

def save_account_snapshot(info: dict) -> None:
    """Save account balance snapshot for dashboard history."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """INSERT INTO account_snapshots
               (balance, equity, profit_loss, available, recorded_at)
               VALUES (?,?,?,?,?)""",
            (
                info.get("balance",     0),
                info.get("balance", 0) + info.get("profit_loss", 0),
                info.get("profit_loss", 0),
                info.get("available",   0),
                now,
            ),
        )


def get_today_pnl() -> float:
    """Get total realized + unrealized P&L for today."""
    sql = """
        SELECT profit_loss FROM account_snapshots
        WHERE recorded_at >= date('now')
        ORDER BY recorded_at DESC LIMIT 1
    """
    with _connect() as conn:
        row = conn.execute(sql).fetchone()
        return float(row[0]) if row else 0.0


# ── State KV store ────────────────────────────────────────────────────────

def set_state(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scanner_state (key,value) VALUES (?,?)",
            (key, value),
        )


def get_state(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM scanner_state WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default


def serialize(row: dict) -> dict:
    try:
        row["score_breakdown"] = json.loads(row.get("score_breakdown") or "{}")
    except Exception:
        row["score_breakdown"] = {}
    return row
