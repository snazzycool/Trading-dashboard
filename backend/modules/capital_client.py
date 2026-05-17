"""
modules/capital_client.py — Capital.com REST API client.

Handles:
  - Session management (login, keepalive, logout)
  - Account info (balance, equity, positions)
  - Order placement with SL/TP
  - Position monitoring and modification (trailing stop)
  - Session auto-renewal every 9 minutes
"""
import logging
import time
import threading
from typing import Optional
import requests
import config

logger = logging.getLogger(__name__)

# ── Capital.com API base URLs ─────────────────────────────────────────────
_DEMO_URL = "https://demo-api-capital.backend-capital.com/api/v1"
_LIVE_URL = "https://api-capital.backend-capital.com/api/v1"

# ── Epic mapping — Capital.com instrument names ───────────────────────────
EPIC_MAP: dict[str, str] = {
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "GBP/JPY": "GBPJPY",
    "AUD/USD": "AUDUSD",
    "XAU/USD": "GOLD",
    "NZD/USD": "NZDUSD",
}

# Minimum trade sizes per instrument (in units)
MIN_SIZE: dict[str, float] = {
    "EURUSD": 1000,
    "GBPUSD": 1000,
    "GBPJPY": 1000,
    "AUDUSD": 1000,
    "NZDUSD": 1000,
    "GOLD":   1,
}


class CapitalClient:
    """
    Thread-safe Capital.com API client with automatic session renewal.
    """

    def __init__(self):
        self._base_url  = _DEMO_URL if config.CAPITAL_ENV == "demo" else _LIVE_URL
        self._cst       = None   # authorization token
        self._sec_token = None   # security token (account selector)
        self._lock      = threading.Lock()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._running   = False

    # ── Session management ────────────────────────────────────────────────

    def login(self) -> bool:
        """
        Establish a Capital.com API session.
        Returns True on success.
        """
        try:
            resp = requests.post(
                f"{self._base_url}/session",
                headers={"X-CAP-API-KEY": config.CAPITAL_API_KEY},
                json={
                    "identifier":        config.CAPITAL_IDENTIFIER,
                    "password":          config.CAPITAL_PASSWORD,
                    "encryptedPassword": False,
                },
                timeout=15,
            )
            resp.raise_for_status()

            self._cst       = resp.headers.get("CST")
            self._sec_token = resp.headers.get("X-SECURITY-TOKEN")

            if not self._cst or not self._sec_token:
                logger.error("Capital.com login: missing tokens in response")
                return False

            logger.info(
                "Capital.com session started (%s)",
                "DEMO" if config.CAPITAL_ENV == "demo" else "LIVE",
            )
            self._start_keepalive()
            return True

        except requests.exceptions.HTTPError as e:
            logger.error("Capital.com login HTTP error: %s — %s", e, e.response.text if e.response else "")
            return False
        except Exception as e:
            logger.error("Capital.com login error: %s", e)
            return False

    def logout(self):
        """Close the API session cleanly."""
        self._running = False
        try:
            self._request("DELETE", "/session")
            logger.info("Capital.com session closed")
        except Exception:
            pass
        self._cst = self._sec_token = None

    def is_connected(self) -> bool:
        return bool(self._cst and self._sec_token)

    def _start_keepalive(self):
        """Ping every 9 minutes to prevent session expiry (10 min limit)."""
        self._running = True
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True
        )
        self._keepalive_thread.start()

    def _keepalive_loop(self):
        while self._running:
            time.sleep(540)   # 9 minutes
            if not self._running:
                break
            try:
                resp = self._request("GET", "/ping")
                if resp and resp.status_code == 200:
                    logger.debug("Capital.com session keepalive OK")
                else:
                    logger.warning("Keepalive failed — attempting re-login")
                    self.login()
            except Exception as e:
                logger.warning("Keepalive error: %s — re-logging in", e)
                self.login()

    # ── Account info ──────────────────────────────────────────────────────

    def get_account_info(self) -> Optional[dict]:
        """
        Return account balance, equity, margin, P&L.
        """
        try:
            resp = self._request("GET", "/accounts")
            if not resp or resp.status_code != 200:
                return None
            accounts = resp.json().get("accounts", [])
            if not accounts:
                return None

            acc  = accounts[0]
            bal  = acc.get("balance", {})
            return {
                "account_id":    acc.get("accountId"),
                "account_name":  acc.get("accountName"),
                "currency":      acc.get("currency", "USD"),
                "balance":       bal.get("balance",   0.0),
                "deposit":       bal.get("deposit",   0.0),
                "profit_loss":   bal.get("profitLoss", 0.0),
                "available":     bal.get("available", 0.0),
            }
        except Exception as e:
            logger.error("get_account_info error: %s", e)
            return None

    def get_open_positions(self) -> list[dict]:
        """Return all currently open positions."""
        try:
            resp = self._request("GET", "/positions")
            if not resp or resp.status_code != 200:
                return []
            positions = resp.json().get("positions", [])
            result = []
            for p in positions:
                pos   = p.get("position", {})
                mkt   = p.get("market", {})
                result.append({
                    "deal_id":    pos.get("dealId"),
                    "epic":       mkt.get("epic"),
                    "direction":  pos.get("direction"),   # BUY or SELL
                    "size":       pos.get("size"),
                    "open_level": pos.get("openLevel"),
                    "stop_loss":  pos.get("stopLevel"),
                    "take_profit": pos.get("limitLevel"),
                    "profit":     pos.get("upl"),          # unrealized P&L
                    "created_at": pos.get("createdDateUTC"),
                })
            return result
        except Exception as e:
            logger.error("get_open_positions error: %s", e)
            return []

    # ── Order placement ───────────────────────────────────────────────────

    def place_order(
        self,
        pair:      str,
        direction: str,
        size:      float,
        stop_loss: float,
        take_profit: float,
    ) -> Optional[str]:
        """
        Place a market order with SL and TP.
        Returns deal_reference on success, None on failure.
        """
        epic = EPIC_MAP.get(pair)
        if not epic:
            logger.error("No epic mapping for pair: %s", pair)
            return None

        # Enforce minimum size
        min_sz = MIN_SIZE.get(epic, 1000)
        if size < min_sz:
            logger.warning("%s: size %.2f below minimum %.2f — using minimum", pair, size, min_sz)
            size = min_sz

        payload = {
            "epic":           epic,
            "direction":      direction,   # "BUY" or "SELL"
            "size":           round(size, 2),
            "guaranteedStop": False,
            "stopLevel":      round(stop_loss,   5),
            "limitLevel":     round(take_profit, 5),
        }

        try:
            resp = self._request("POST", "/positions", json=payload)
            if not resp:
                return None

            if resp.status_code == 200:
                ref = resp.json().get("dealReference")
                logger.info(
                    "Order placed: %s %s size=%.2f SL=%.5f TP=%.5f ref=%s",
                    pair, direction, size, stop_loss, take_profit, ref,
                )
                return ref
            else:
                logger.error(
                    "Order failed %s: %s — %s",
                    pair, resp.status_code, resp.text
                )
                return None
        except Exception as e:
            logger.error("place_order error %s: %s", pair, e)
            return None

    def modify_stop_loss(self, deal_id: str, new_sl: float) -> bool:
        """
        Modify the stop loss of an open position.
        Used by the trailing stop system.
        """
        try:
            resp = self._request(
                "PUT",
                f"/positions/{deal_id}",
                json={"stopLevel": round(new_sl, 5)},
            )
            if resp and resp.status_code == 200:
                logger.info("SL modified deal=%s new_sl=%.5f", deal_id, new_sl)
                return True
            logger.warning("SL modify failed deal=%s: %s", deal_id, resp.text if resp else "no response")
            return False
        except Exception as e:
            logger.error("modify_stop_loss error: %s", e)
            return False

    def close_position(self, deal_id: str, size: float) -> bool:
        """Close an open position by deal ID."""
        try:
            resp = self._request(
                "DELETE",
                f"/positions/{deal_id}",
            )
            if resp and resp.status_code == 200:
                logger.info("Position closed: deal=%s", deal_id)
                return True
            logger.warning("Close failed deal=%s: %s", deal_id, resp.text if resp else "")
            return False
        except Exception as e:
            logger.error("close_position error: %s", e)
            return False

    def get_deal_confirmation(self, deal_reference: str) -> Optional[dict]:
        """Confirm a placed order and get the deal ID."""
        try:
            resp = self._request("GET", f"/confirms/{deal_reference}")
            if resp and resp.status_code == 200:
                data = resp.json()
                return {
                    "deal_id":    data.get("dealId"),
                    "status":     data.get("dealStatus"),
                    "direction":  data.get("direction"),
                    "size":       data.get("size"),
                    "open_level": data.get("level"),
                    "stop_loss":  data.get("stopLevel"),
                    "take_profit": data.get("limitLevel"),
                }
            return None
        except Exception as e:
            logger.error("get_deal_confirmation error: %s", e)
            return None

    # ── Internal request helper ───────────────────────────────────────────

    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[dict] = None,
    ) -> Optional[requests.Response]:
        """Make an authenticated API request."""
        if not self._cst or not self._sec_token:
            logger.warning("API request attempted without active session")
            return None

        with self._lock:
            try:
                resp = requests.request(
                    method,
                    f"{self._base_url}{endpoint}",
                    headers={
                        "X-CAP-API-KEY":    config.CAPITAL_API_KEY,
                        "CST":              self._cst,
                        "X-SECURITY-TOKEN": self._sec_token,
                        "Content-Type":     "application/json",
                    },
                    json=json,
                    timeout=15,
                )
                # Refresh tokens from response headers if present
                if "CST" in resp.headers:
                    self._cst = resp.headers["CST"]
                if "X-SECURITY-TOKEN" in resp.headers:
                    self._sec_token = resp.headers["X-SECURITY-TOKEN"]
                return resp
            except requests.exceptions.Timeout:
                logger.warning("API request timeout: %s %s", method, endpoint)
                return None
            except Exception as e:
                logger.error("API request error: %s %s — %s", method, endpoint, e)
                return None


# ── Singleton instance ────────────────────────────────────────────────────
capital = CapitalClient()
