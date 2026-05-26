"""
modules/database_supabase.py — Supabase persistence layer.

Replaces SQLite with Supabase for better analytics, real-time updates, and scalability.
"""
import logging
import json
from datetime import datetime, timezone
from typing import Optional, List
import os
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Initialize Supabase client
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")  # Use service role for backend

_client: Optional[Client] = None


def get_client() -> Client:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized")
    return _client


def init_db() -> None:
    """Verify database connection (tables created via migrations)."""
    try:
        client = get_client()
        # Test connection by querying scanner_state
        client.table("scanner_state").select("key").limit(1).execute()
        logger.info("Supabase database ready")
    except Exception as e:
        logger.error("Database initialization failed: %s", e, exc_info=True)
        raise


# ── Signal CRUD ─────────────────────────────────────────────────────────────

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
    user_id: Optional[str] = None,
) -> str:
    """Insert a new signal and return its ID."""
    try:
        client = get_client()
        data = {
            "pair": pair,
            "direction": direction,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "score": score,
            "score_breakdown": score_breakdown,
            "atr": atr,
            "risk_reward": risk_reward,
            "pip_risk": pip_risk,
            "pip_reward": pip_reward,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if user_id:
            data["user_id"] = user_id

        result = client.table("signals").insert(data).execute()
        signal_id = result.data[0]["id"] if result.data else None

        if signal_id:
            logger.info("Signal inserted: %s %s (ID: %s)", pair, direction, signal_id)
            return signal_id
        else:
            logger.error("Failed to insert signal: no ID returned")
            return ""

    except Exception as e:
        logger.error("Insert signal error: %s", e, exc_info=True)
        return ""


def update_signal_deal_id(signal_id: str, deal_id: str, trade_size: float) -> None:
    """Update signal with Capital.com deal ID after order confirmation."""
    try:
        client = get_client()
        client.table("signals").update({
            "deal_id": deal_id,
            "trade_size": trade_size
        }).eq("id", signal_id).execute()
        logger.debug("Updated signal %s with deal_id %s", signal_id, deal_id)
    except Exception as e:
        logger.error("Update signal deal_id error: %s", e)


def get_pending_signals() -> List[dict]:
    """Get all pending signals ordered by creation time."""
    try:
        client = get_client()
        result = client.table("signals").select("*").eq("status", "PENDING").order("created_at").execute()
        return [serialize(row) for row in result.data]
    except Exception as e:
        logger.error("Get pending signals error: %s", e)
        return []


def resolve_signal(signal_id: str, outcome: str) -> None:
    """Mark a signal as WIN, LOSS, or EXPIRED."""
    try:
        client = get_client()
        client.table("signals").update({
            "status": outcome,
            "resolved_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", signal_id).execute()
        logger.info("Signal %s resolved as %s", signal_id, outcome)
    except Exception as e:
        logger.error("Resolve signal error: %s", e)


def get_recent_signal_for_pair(pair: str, within_seconds: int) -> Optional[dict]:
    """Get most recent signal for a pair within the specified time window."""
    try:
        client = get_client()
        cutoff = datetime.now(timezone.utc).isoformat()
        result = client.table("signals").select("*").eq("pair", pair).gte(
            "created_at", cutoff
        ).order("created_at", desc=True).limit(1).execute()

        return serialize(result.data[0]) if result.data else None
    except Exception as e:
        logger.error("Get recent signal error: %s", e)
        return None


def count_signals_last_hour() -> int:
    """Count signals created in the last hour."""
    try:
        client = get_client()
        one_hour_ago = datetime.now(timezone.utc).isoformat()
        result = client.table("signals").select("id", count="exact").gte(
            "created_at", one_hour_ago
        ).execute()
        return result.count or 0
    except Exception as e:
        logger.error("Count signals error: %s", e)
        return 0


def get_all_signals(limit: int = 100) -> List[dict]:
    """Get all signals ordered by creation time (most recent first)."""
    try:
        client = get_client()
        result = client.table("signals").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return [serialize(row) for row in result.data]
    except Exception as e:
        logger.error("Get all signals error: %s", e)
        return []


def get_signal_by_id(signal_id: str) -> Optional[dict]:
    """Get a signal by its ID."""
    try:
        client = get_client()
        result = client.table("signals").select("*").eq("id", signal_id).maybe_single().execute()
        return serialize(result.data) if result.data else None
    except Exception as e:
        logger.error("Get signal by ID error: %s", e)
        return None


def get_performance_stats() -> dict:
    """Calculate performance statistics from all signals."""
    try:
        client = get_client()

        # Get all resolved signals
        result = client.table("signals").select("status, pair").execute()
        signals = result.data or []

        total = len(signals)
        wins = sum(1 for s in signals if s.get("status") == "WIN")
        losses = sum(1 for s in signals if s.get("status") == "LOSS")
        pending = sum(1 for s in signals if s.get("status") == "PENDING")
        expired = sum(1 for s in signals if s.get("status") == "EXPIRED")

        resolved = wins + losses
        win_rate = round(wins / resolved * 100, 1) if resolved > 0 else 0.0

        # Group by pair
        by_pair = {}
        for s in signals:
            pair = s.get("pair")
            if pair not in by_pair:
                by_pair[pair] = {"pair": pair, "wins": 0, "losses": 0, "total": 0}
            by_pair[pair]["total"] += 1
            if s.get("status") == "WIN":
                by_pair[pair]["wins"] += 1
            elif s.get("status") == "LOSS":
                by_pair[pair]["losses"] += 1

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "expired": expired,
            "win_rate": win_rate,
            "by_pair": list(by_pair.values())
        }

    except Exception as e:
        logger.error("Get performance stats error: %s", e)
        return {
            "total": 0, "wins": 0, "losses": 0, "pending": 0,
            "expired": 0, "win_rate": 0.0, "by_pair": []
        }


# ── Account snapshots ─────────────────────────────────────────────────────────

def save_account_snapshot(info: dict, user_id: Optional[str] = None) -> None:
    """Save account balance snapshot for historical tracking."""
    try:
        client = get_client()
        data = {
            "balance": info.get("balance", 0),
            "equity": info.get("balance", 0) + info.get("profit_loss", 0),
            "profit_loss": info.get("profit_loss", 0),
            "available": info.get("available", 0),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if user_id:
            data["user_id"] = user_id

        client.table("account_snapshots").insert(data).execute()
        logger.debug("Account snapshot saved")

    except Exception as e:
        logger.error("Save account snapshot error: %s", e)


def get_today_pnl() -> float:
    """Get total P&L for today."""
    try:
        client = get_client()
        today = datetime.now(timezone.utc).date().isoformat()
        result = client.table("account_snapshots").select("profit_loss").gte(
            "recorded_at", today
        ).order("recorded_at", desc=True).limit(1).maybe_single().execute()

        return float(result.data.get("profit_loss", 0)) if result.data else 0.0
    except Exception as e:
        logger.error("Get today P&L error: %s", e)
        return 0.0


# ── State KV store ────────────────────────────────────────────────────────────

def set_state(key: str, value: str) -> None:
    """Set a key-value pair in scanner_state table."""
    try:
        client = get_client()
        client.table("scanner_state").upsert({
            "key": key,
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logger.error("Set state error: %s", e)


def get_state(key: str, default: str = "") -> str:
    """Get a value from scanner_state table."""
    try:
        client = get_client()
        result = client.table("scanner_state").select("value").eq("key", key).maybe_single().execute()
        return result.data.get("value", default) if result.data else default
    except Exception as e:
        logger.error("Get state error: %s", e)
        return default


# ── Helpers ─────────────────────────────────────────────────────────────────

def serialize(row: dict) -> dict:
    """Parse JSON fields in a row dict."""
    if not row:
        return row

    # Parse score_breakdown if it's a string
    if "score_breakdown" in row and isinstance(row["score_breakdown"], str):
        try:
            row["score_breakdown"] = json.loads(row["score_breakdown"])
        except:
            row["score_breakdown"] = {}
    elif "score_breakdown" not in row:
        row["score_breakdown"] = {}

    return row
