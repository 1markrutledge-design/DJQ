#!/usr/bin/env python3
"""
Kalshi BTC 15-Minute Front-Runner Bot
======================================
Strategy : On window entry (final 12 min), post MAKER bids at 89¢ on BOTH
           YES (BTC up) and NO (BTC down) simultaneously. Whichever side moves
           strongly fills; the other is cancelled at close. Stop-loss at 40¢.

Auth     : RSA-PSS (Elections API v2)
Transport: WebSocket orderbook_delta channel
Fees     : Maker-only (both entry and stop-loss are limit orders).

Usage:
    python bot.py              # live trading
    python bot.py --dry-run    # simulate signals, no real orders
    python bot.py --debug      # verbose logging
"""

import asyncio
import base64
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# ── Helpers ───────────────────────────────────────────────────────────────────
def to_int(val) -> int:
    """Safely convert None, string decimals ('1.00'), or floats to int."""
    try:
        if val is None: return 0
        return int(float(str(val)))
    except: return 0

def to_cents(val) -> Optional[int]:
    """Safely convert dollar strings/floats or integer cents to int cents. Returns None for None/empty."""
    try:
        if val is None or val == "": return None
        f = float(val)
        # If value is small (e.g. 0.70), it's likely dollars. Convert to cents.
        if 0 < abs(f) < 1.0: return int(round(f * 100))
        return int(round(f))
    except: return None

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

API_BASE      = "https://api.elections.kalshi.com"
WS_URL        = "wss://api.elections.kalshi.com/trade-api/ws/v2"
TARGET_SERIES = ["KXBTC15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M"]
GLOBAL_MAX_SPREAD = 50

STRATEGIES = {
    "KXBTC15M":  {
        "logic_type": "BTC_BREAKOUT",
        "trade_count": 1,
        "stop_loss": 10,
        "trigger": 35,
        "max_entry": 58,
        "profit_target": 75,
        "min_mins": 1.0,
        "max_mins": 10.0
    },
    
    "KXSOL15M":  {
        "logic_type": "BTC_BREAKOUT",
        "trade_count": 1,
        "stop_loss": 25,
        "trigger": 35,
        "max_entry": 58,
        "profit_target": 75,
        "min_mins": 1.0,
        "max_mins": 10.0
    },
    
    "KXXRP15M":  {
        "logic_type": "XRP_BREAKOUT",
        "trade_count": 1, 
        "stop_loss": 30,
        "trigger": 40,
        "max_entry": 58,
        "profit_target": 80,
        "min_mins": 1.0,
        "max_mins": 10.0
    },
    
    "KXDOGE15M":  {
        "logic_type": "DOGE_BREAKOUT",
        "trade_count": 1, 
        "stop_loss": 25,
        "trigger": 35,
        "max_entry": 58,
        "profit_target": 65,
        "min_mins": 1.0,
        "max_mins": 10.0
    },
    
    "DEFAULT":   {"logic_type": "SNIPER", "trigger": 90, "bid": 90, "stop_loss": 70, "profit_target": 99, "trade_count": 1, "post_only": True},
}

def get_strategy(ticker: str) -> dict:
    for series, strat in STRATEGIES.items():
        if ticker.startswith(series):
            return strat
    return STRATEGIES["DEFAULT"]

WINDOW_MINUTES     = 7    # Only trade in the final 7 minutes (Skip volatile early/mid market)

# Runtime flags
DRY_RUN     = "--dry-run" in sys.argv or os.environ.get("DRY_RUN", "").lower() == "true"
DEBUG       = "--debug"   in sys.argv or os.environ.get("DEBUG",   "").lower() == "true"

# Bot loop config
DISCOVERY_INTERVAL_S = 30    # Re-discover new markets every 30 seconds
POLL_INTERVAL_S      = 30    # Slowed down from 10s to prevent 429s (WS fills handle the speed)
STABILITY_TICKS_REQUIRED = 1     # Instant fire for sniper moves (prevent missed bets)
STATUS_SAVE_INTERVAL = 15    # Write bot_status.json every N WebSocket messages

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Silence noisy websockets internals (heartbeat pings, frame-level chatter)
logging.getLogger("websockets").setLevel(logging.WARNING)
log = logging.getLogger("btcbot")

# ─────────────────────────────────────────────────────────────────────────────
# RSA-PSS Authentication
# ─────────────────────────────────────────────────────────────────────────────

class KalshiAuth:
    """
    RSA-PSS signing for the Kalshi Elections API v2.
    Loads the private key from env var KALSHI_PRIVATE_KEY_PEM (preferred in
    cloud) or from a local file at KALSHI_PRIVATE_KEY_PATH (default: kalshi_private.pem).
    """

    def __init__(self):
        self._load_env_file()
        self.key_id = os.environ["KALSHI_API_KEY_ID"].strip().strip('"')
        self.private_key = self._load_key()
        log.info("Auth ready. Key ID: %s…%s", self.key_id[:8], self.key_id[-6:])

    def _load_env_file(self):
        """Auto-load .env from the bot's directory (mirrors ETH bot behaviour)."""
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if not os.path.exists(env_path):
            return
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.replace("export ", "").strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v


    def _load_key(self):
        pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
        if not pem_data:
            path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
            with open(path, "rb") as f:
                pem_data = f.read().decode()

        # Robust cleanup of common corruption (env var escaping, etc.)
        pem_data = pem_data.replace("\\n", "\n").replace('"', "").strip()

        # Re-wrap one-liner keys so cryptography can parse them
        for header, footer in [
            ("-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----"),
            ("-----BEGIN PRIVATE KEY-----",     "-----END PRIVATE KEY-----"),
        ]:
            if header in pem_data and "\n" not in pem_data[len(header):len(header) + 10]:
                content = pem_data.replace(header, "").replace(footer, "").strip()
                pem_data = f"{header}\n{content}\n{footer}"
                break

        try:
            return serialization.load_pem_private_key(pem_data.encode(), password=None)
        except Exception as e:
            log.error("Failed to load private key. PEM starts: %s", pem_data[:80])
            raise

    def _sign(self, method: str, path: str) -> dict:
        """Build auth headers for a given method + path."""
        clean_path = path.split("?")[0]
        ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        message = (ts_ms + method.upper() + clean_path).encode()
        sig = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY":       self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "Content-Type":            "application/json",
        }

    def rest_headers(self, method: str, path: str) -> dict:
        return self._sign(method, path)

    def ws_headers(self) -> dict:
        """Signed headers for the WebSocket upgrade handshake."""
        return self._sign("GET", "/trade-api/ws/v2")


# ─────────────────────────────────────────────────────────────────────────────
# REST Client
# ─────────────────────────────────────────────────────────────────────────────

class KalshiRest:
    """Thin authenticated REST wrapper around the Kalshi Elections API."""

    def __init__(self, auth: KalshiAuth):
        self.auth    = auth
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "btcbot/1.0"})
        # 🧪 HARDENING: Increase pool size to prevent connection queuing (fixes "Pool is full" warnings)
        adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # ── Low-level verbs ───────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url  = API_BASE + path
        hdrs = self.auth.rest_headers("GET", path)
        log.debug("📡 REST GET: %s", path)
        resp = self.session.get(url, headers=hdrs, params=params, timeout=15)
        if resp.status_code != 200:
            log.error("❌ API ERROR %d on %s: %s", resp.status_code, path, resp.text)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        url  = API_BASE + path
        hdrs = self.auth.rest_headers("POST", path)
        resp = self.session.post(url, headers=hdrs, json=body, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> Optional[dict]:
        url  = API_BASE + path
        hdrs = self.auth.rest_headers("DELETE", path)
        resp = self.session.delete(url, headers=hdrs, timeout=15)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    # ── Market discovery ──────────────────────────────────────────────────────

    def get_active_target_markets(self) -> list[dict]:
        """Return all open markets for target series (handles pagination)."""
        all_markets = []
        for series in TARGET_SERIES:
            cursor = None
            series_markets = []
            while True:
                params: dict = {"limit": 100, "status": "open", "series_ticker": series}
                if cursor:
                    params["cursor"] = cursor
                try:
                    data   = self._get("/trade-api/v2/markets", params=params)
                    batch  = data.get("markets", [])
                    series_markets.extend(batch)
                    cursor = data.get("cursor")
                    if not cursor or not batch:
                        break
                except Exception as e:
                    log.error("Market discovery error for %s: %s", series, e)
                    break
            if series_markets:
                log.info("Discovered %d open %s markets", len(series_markets), series)
            all_markets.extend(series_markets)
        return all_markets

    def get_market(self, ticker: str) -> dict:
        """Fetch current market snapshot for a single ticker."""
        try:
            data = self._get(f"/trade-api/v2/markets/{ticker}")
            return data.get("market", {})
        except Exception as e:
            log.error("get_market failed for %s: %s", ticker, e)
            return {}

    def get_balance_cents(self) -> int:
        try:
            data = self._get("/trade-api/v2/portfolio/balance")
            return data.get("balance", 0)
        except Exception:
            return 0

    def get_positions(self) -> list[dict]:
        """Fetch ALL positions for the account in one batch."""
        try:
            data = self._get("/trade-api/v2/portfolio/positions")
            return data.get("positions", [])
        except Exception as e:
            log.error("Batch positions fetch failed: %s", e)
            return []

    def get_position(self, ticker: str) -> dict:
        """Fetch position for a single ticker."""
        try:
            params = {"ticker": ticker}
            data = self._get("/trade-api/v2/portfolio/positions", params=params)
            pos_list = data.get("positions", [])
            return pos_list[0] if pos_list else {}
        except Exception:
            return {}

    # ── Order management ──────────────────────────────────────────────────────

    def place_order(
        self,
        ticker: str,
        action: str,       # "buy" | "sell"
        price_cents: int,
        count: int,
        side: str = "yes",      # "yes" | "no"
        post_only: bool = False,
    ) -> Optional[str]:
        """
        Place a YES or NO limit order. Returns order_id or None on failure.
        Maker by default (limit order rests on book).
        """
        if DRY_RUN:
            fake_id = f"DRY-{action.upper()}-{side.upper()}-{ticker[-12:]}-{int(time.time())}"
            log.info(
                "[DRY-RUN] Would place %s %s @ %d¢ x%d for %s → %s",
                action.upper(), side.upper(), price_cents, count, ticker, fake_id,
            )
            return fake_id

        # Kalshi V2 typically wants 'yes_price' or 'no_price' depending on the side.
        body = {
            "ticker":          ticker,
            "action":          action,
            "side":            side,
            "type":            "limit",
            "count":           count,
            "client_order_id": f"35-{int(time.time())}-{uuid.uuid4().hex[:4]}",
        }
        # 🧪 HARDENING: Elections API v2 requires 'yes_price' regardless of side.
        if side == "yes":
            body["yes_price"] = price_cents
        else:
            body["yes_price"] = 100 - price_cents
        
        # 🧪 DEBUG: Save body for error reporting
        body_json = json.dumps(body)
        
        try:
            resp     = self._post("/trade-api/v2/portfolio/orders", body)
            order_id = str(resp.get("order", {}).get("order_id", ""))
            log.info(
                "ORDER PLACED — %s %s %s @ %d¢ x%d → order_id=%s",
                action.upper(), side.upper(), ticker, price_cents, count, order_id,
            )
            return order_id
        except requests.HTTPError as e:
            if "insufficient_funds" in str(e).lower():
                log.warning("💰 INSUFFICIENT FUNDS to place %s %s on %s", action.upper(), side.upper(), ticker)
            else:
                details = e.response.text if e.response else "No body"
                log.error("Order failed! \nURL: %s \nBody: %s \nError: %s \nDetails: %s", 
                          e.request.url, body_json, e, details)
            return None

    def cancel_order(self, order_id: str):
        try:
            return self._delete(f"/trade-api/v2/portfolio/orders/{order_id}")
        except Exception as e:
            if "409" in str(e):
                # 409 Conflict = order already filled or cancelled
                return "CONFLICT"
            log.warning("Order %s cancel failed (%s)", order_id, e)
            return None
        except requests.HTTPError as e:
            if "404" in str(e):
                log.warning("Order %s already gone (404)", order_id)
                return True
            log.error("Cancel failed for %s: %s", order_id, e)
            return False

    def get_order_status(self, order_id: str) -> Optional[str]:
        """Return order status string: 'resting', 'filled', 'canceled', etc. None on error."""
        if DRY_RUN:
            return "filled"
        try:
            data = self._get(f"/trade-api/v2/portfolio/orders/{order_id}")
            return data.get("order", {}).get("status")
        except Exception as e:
            log.debug("get_order_status failed for %s: %s", order_id, e)
            return None

    def get_position(self, ticker: str) -> Optional[dict]:
        """Fetch position for a SINGLE ticker using the API filter."""
        try:
            # The Kalshi V2 API supports filtering by ticker directly
            path = f"/trade-api/v2/portfolio/positions?ticker={ticker}"
            data = self._get(path)
            
            # The response is usually a list under 'market_positions'
            pos_list = data.get("market_positions", []) or data.get("positions", [])
            for p in pos_list:
                if p.get("ticker") == ticker:
                    return p
            return None
        except Exception as e:
            log.debug("get_position failed for %s: %s", ticker, e)
            return None

    def get_positions(self) -> list[dict]:
        """Fetch all positions from the account portfolio."""
        try:
            data = self._get("/trade-api/v2/portfolio/positions")
            return data.get("market_positions", []) or data.get("positions", [])
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Orderbook Tracker
# ─────────────────────────────────────────────────────────────────────────────

class OrderbookTracker:
    """
    Maintains a local copy of each market's orderbook from WebSocket deltas.

    Kalshi convention:
      - "yes" levels = YES bids   (buyers of YES contracts)
      - "no"  levels = NO bids    (buyers of NO = implied YES sellers)

    Derived prices:
      best_yes_bid = max{price | qty > 0 in yes levels}
      best_yes_ask = 100 - max{price | qty > 0 in no levels}
    """

    def __init__(self):
        # ticker → {"yes": {price_cents: qty}, "no": {price_cents: qty}}
        self._books: dict[str, dict] = {}

    def snapshot(self, ticker: str, yes_levels: list, no_levels: list, src_type="dollars"):
        """Full orderbook snapshot."""
        out_yes = {}
        out_no  = {}
        
        if src_type == "dollars":
            for p, q in yes_levels:
                qty = float(q)
                if qty > 0: out_yes[round(float(p) * 100)] = qty
            for p, q in no_levels:
                qty = float(q)
                if qty > 0: out_no[round(float(p) * 100)] = qty
        else:
            # Trade V2 format: integers. yes_levels=bids, no_levels=asks
            for p, q in yes_levels:
                qty = float(q)
                if qty > 0: out_yes[int(p)] = qty
            for p, q in no_levels:
                qty = float(q)
                # no_levels are `asks` for YES. NO bid = 100 - YES ask
                if qty > 0: out_no[100 - int(p)] = qty
                
        self._books[ticker] = {"yes": out_yes, "no": out_no}

    def delta(self, ticker: str, side: str, price: int, qty_delta: int):
        """Incremental update to a single price level."""
        book = self._books.setdefault(ticker, {"yes": {}, "no": {}})
        current = book[side].get(price, 0)
        new_qty  = current + qty_delta
        if new_qty <= 0:
            book[side].pop(price, None)
        else:
            book[side][price] = new_qty

    def best_bid(self, ticker: str) -> Optional[int]:
        """Highest price someone will pay for YES (¢)."""
        book = self._books.get(ticker)
        if not book:
            return None
        active = {p: q for p, q in book["yes"].items() if q > 0}
        return max(active) if active else None

    def best_ask(self, ticker: str) -> Optional[int]:
        """
        Lowest price someone will sell YES at (¢).
        Derived from: 100 - max(no_bids).
        """
        book = self._books.get(ticker)
        if not book:
            return None
        active = {p: q for p, q in book["no"].items() if q > 0}
        return (100 - max(active)) if active else None

    def best_bid_no(self, ticker: str) -> Optional[int]:
        """Highest price someone will pay for NO (¢)."""
        book = self._books.get(ticker)
        if not book:
            return None
        active = {p: q for p, q in book["no"].items() if q > 0}
        return max(active) if active else None

    def has_book(self, ticker: str) -> bool:
        return ticker in self._books


# ─────────────────────────────────────────────────────────────────────────────
# Per-Ticker State Machine
# ─────────────────────────────────────────────────────────────────────────────

class TickerState:
    """
    State machine for one 15-minute market.

    Strategy: Watch silently until YES or NO hits ENTRY_TRIGGER (84¢).
    Then post a single resting MAKER_BID_PRICE (85¢) bid on that side.
    Whichever side fills, hold and monitor trailing stop (drop TRAILING_STOP_DROP¢ from peak / floor STOP_LOSS_FLOOR).

    Transitions:
      WATCHING → ENTERED    (trigger fired, one-sided bid posted)
      ENTERED  → FILLED_YES  (YES bid filled)
      ENTERED  → FILLED_NO   (NO  bid filled)
      FILLED_* → EXITED      (stop-loss or settlement)
      WATCHING → LOCKED      (market expired before trigger)
      ENTERED  → LOCKED      (market expired before fill)
    """

    WATCHING   = "WATCHING"
    HIT_TRIGGER = "HIT_TRIGGER" # Trigger hit (65c), waiting for pullback
    STABILIZING = "STABILIZING" # In pullback range (50-60c), waiting 30s
    ENTERED    = "ENTERED"     # one bid resting on book
    FILLED_YES = "FILLED_YES"  # YES bid filled — holding YES contracts
    FILLED_NO  = "FILLED_NO"   # NO  bid filled — holding NO  contracts
    EXITING    = "EXITING"
    EXITED     = "EXITED"      # position closed
    LOCKED     = "LOCKED"      # terminal: expired or order failed

    def __init__(self, ticker: str, close_time: datetime):
        self.ticker           = ticker
        self.ticker_short     = ticker[-12:]
        self.close_time       = close_time
        self.status           = self.WATCHING

        # One order ID per side
        self.yes_order_id:   Optional[str]      = None
        self.no_order_id:    Optional[str]      = None

        self.entry_price:    Optional[int]      = None   # always 89
        self.filled_side:    Optional[str]      = None   # "yes" or "no"
        self.shares:         int                = 0
        self.sell_order_id:   Optional[str]      = None
        self.profit_order_id: Optional[str]      = None
        self.entry_time:      Optional[datetime] = None
        self.exit_price:      Optional[int]      = None
        self.exit_time:       Optional[datetime] = None
        self.realized_pl_c:   Optional[int]      = None
        self.max_favorable_price: int           = 0     # for trailing stop-loss
        self.stability_count: int               = 0     # for stabilized entry
        self._prev_bid: Optional[int]           = None  # for directional momentum detection (50c strat)
        self._last_logged_bid: Optional[int]    = None  # for change-driven logging
        self.fallback_attempted: bool           = False  # prevent fallback from firing repeatedly
        self._last_watch_time: float            = 0      # rate-limit WATCHING logs
        
        # 🛡️ PRICE MEMORY (for hardened stop-loss)
        self.last_bid: Optional[int]    = None
        self.last_ask: Optional[int]    = None
        self.last_no_bid: Optional[int] = None
        self.last_no_ask: Optional[int] = None

        # 🎯 PULLBACK & MOMENTUM STRATEGY FIELDS
        self.pullback_side: Optional[str]          = None
        self.hit_trigger_time: Optional[float]     = None
        self.stability_start_time: Optional[float] = None
        self.price_history: list[tuple[float, int]] = [] # list of (timestamp, bid)
        
        # 🌊 BTC LATE SURGE TRACKER
        self.seconds_below_barrier: float = 0.0
        self.last_barrier_update: float   = time.time()

    def is_filled(self) -> bool:
        return self.status in (self.FILLED_YES, self.FILLED_NO)

    def minutes_to_close(self) -> float:
        return (self.close_time - datetime.now(timezone.utc)).total_seconds() / 60.0

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.close_time

    def to_dict(self) -> dict:
        return {
            "ticker":         self.ticker,
            "status":         self.status,
            "close_time":     self.close_time.isoformat(),
            "mins_to_close":  round(self.minutes_to_close(), 1),
            "yes_order_id":   self.yes_order_id,
            "no_order_id":    self.no_order_id,
            "entry_price":    self.entry_price,
            "filled_side":    self.filled_side,
            "shares":         self.shares,
            "sell_order_id":  self.sell_order_id,
            "entry_time":     self.entry_time.isoformat()  if self.entry_time  else None,
            "exit_price":     self.exit_price,
            "exit_time":      self.exit_time.isoformat()   if self.exit_time   else None,
            "realized_pl_c":  self.realized_pl_c,
            "last_bid":       self.last_bid,
            "last_ask":       self.last_ask,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Bot
# ─────────────────────────────────────────────────────────────────────────────

class KalshiBtcBot:

    def __init__(self):
        self.auth      = KalshiAuth()
        self.rest      = KalshiRest(self.auth)
        self.orderbook = OrderbookTracker()

        # ticker → TickerState
        self.tickers:  dict[str, TickerState] = {}

        self._running         = True
        self._ws_id_counter   = 0
        self._last_discovery  = 0.0
        self._msg_count       = 0
        self._total_pl_cents  = 0
        self._trade_log: list[dict] = []
        
        self._last_balance_cents = 0
        self._last_balance_ts    = 0.0
        
        # ⚡ SHADOW SNIPER: Track BTC bursts to signal ETH trades
        self.btc_bursts: dict[str, dict] = {} # suffix -> {"side": "yes", "time": timestamp}

        if DRY_RUN:
            log.warning("=" * 60)
            log.warning("  DRY-RUN MODE — zero real orders will be placed")
            log.warning("=" * 60)

    # ── Market discovery ──────────────────────────────────────────────────────

    def _discover_markets(self) -> list[str]:
        """
        Fetch live target markets and register any new ones in self.tickers.
        Returns list of newly registered ticker strings.
        """
        markets    = self.rest.get_active_target_markets()
        new_tickers: list[str] = []

        # Fetch existing positions once to 'adopt' orphans from previous runs
        try:
            positions_data = self.rest.get_positions()
            active_pos = {}
            for p in positions_data:
                ticker = p.get("ticker")
                # 🧪 HARDENING: Handle decimal strings like "1.00"
                shares = to_int(p.get("position") or p.get("count") or p.get("position_fp"))
                if abs(shares) > 0:
                    active_pos[ticker] = p
        except Exception:
            active_pos = {}

        for m in markets:
            ticker = m["ticker"]
            if ticker in self.tickers or ticker.endswith("-NO"):
                continue

            close_str = m.get("close_time") or m.get("expected_expiration_time")
            if not close_str:
                continue
            try:
                close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            if close_dt <= datetime.now(timezone.utc):
                continue  # already expired, skip

            # Create state and check for adoption
            state = TickerState(ticker, close_dt)
            if ticker in active_pos:
                p = active_pos[ticker]
                # In V2, side is derived from the sign of the position
                shares_val = to_int(p.get("position_fp") or p.get("position") or p.get("count"))
                side = "yes" if shares_val > 0 else "no"
                
                state.status      = TickerState.FILLED_YES if side == "yes" else TickerState.FILLED_NO
                state.filled_side = side
                state.shares      = abs(shares_val)
                log.info("🧠 ADOPTED POSITION — %s | Side: %s | Shares: %d", ticker[-12:], side.upper(), state.shares)

            self.tickers[ticker] = state
            new_tickers.append(ticker)
            log.debug("Registered: %s (closes %s)", ticker, close_str)
            
            # 🧪 SEED ORDERBOOK: Fetch immediate price via REST ONCE at discovery.
            # This ensures the bot isn't "blind" during the final 12 minutes.
            try:
                m = self.rest.get_market(ticker)
                bid = to_cents(m.get("yes_bid") or m.get("yes_bid_dollars"))
                ask = to_cents(m.get("yes_ask") or m.get("yes_ask_dollars"))
                if bid is not None and ask is not None:
                    state.last_bid, state.last_ask = bid, ask
                    # Snapshot the tracker so best_bid() returns a value
                    self.orderbook.snapshot(ticker, [[bid, 1]], [[100 - ask, 1]], src_type="cents")
            except Exception:
                pass

        if new_tickers:
            log.info("Registered %d new 15-minute markets", len(new_tickers))
        return new_tickers

    # ── Strategy logic ────────────────────────────────────────────────────────

    def _check_exit_triggers(self, ticker: str):
        """ Hardened exit guardian: Checks STOP-LOSS logic. (Take-Profit removed by request). """
        state = self.tickers[ticker]
        
        # 🛡️ SAFETY: Do not attempt to exit if market is already expired
        if state.is_expired():
            return

        strat = get_strategy(ticker)
        
        # 🧪 FAIL-SAFE: Return early if already exiting
        if state.status == TickerState.EXITING:
            return
            
        if not state.is_filled():
            return

        # 🛑 GRACE PERIOD: Don't fire stop-loss for the first 10 seconds of a trade.
        # This prevents "Orderbook Amnesia" panic sells immediately after a fill.
        if state.entry_time:
            elapsed = (datetime.now(timezone.utc) - state.entry_time).total_seconds()
            if elapsed < 10:
                return

        # Exit Strategy Config
        if strat.get("stop_loss") is None:
            return
            
        STOP_LOSS_TRIGGER = strat["stop_loss"] + 1
        
        # Determine current value BASED ON SIDE
        # 🧪 HARDENING: Force derive NO value from YES Ask to ensure we don't look at stale data
        if state.status == TickerState.FILLED_YES or state.filled_side == 'yes':
            val = state.last_bid
        elif state.status == TickerState.FILLED_NO or state.filled_side == 'no':
            # Priority: last_no_bid, Fallback: 100 - last_ask (mirroring market logic)
            val = state.last_no_bid
            if val is None and state.last_ask is not None:
                val = 100 - state.last_ask
        else:
            val = None

        if val is None:
            return

        # Diagnostic logging for user visibility
        if DEBUG or (val < (STOP_LOSS_TRIGGER + 10)):
            log.debug("🛡️ [%s] %s Value: %d¢ | Stop-Loss: %d¢", 
                      ticker[-12:], state.filled_side.upper(), val, strat["stop_loss"])

        # 1. Minute 1 Panic (The "Drop Out" Strategy)
        # If < 60s left and price is below our entry, exit immediately.
        mins_left = state.minutes_to_close()
        if mins_left <= 1.05 and state.entry_price is not None:
            if val < state.entry_price - 2: # price slipping
                log.warning("🧨 MINUTE 1 PANIC — %s | Price %d¢ < Entry %d¢ | SAVING CAPITAL", 
                            ticker[-12:], val, state.entry_price)
                self._execute_exit(ticker, state, val, exit_type="MINUTE_1_PANIC")
                return

        # 2. Stop-Loss Logic (Standard)
        if val <= STOP_LOSS_TRIGGER:
            log.warning("🛑 STOP LOSS TRIGGERED — %s | current_val=%d¢ ≤ %d¢", ticker[-12:], val, STOP_LOSS_TRIGGER)
            self._execute_exit(ticker, state, val, exit_type="STOP_LOSS")
        
        # 3. Global Hard Floor (Emergency Backup)
        elif val < 5:
            log.warning("🚨 GLOBAL SAFETY FLOOR HIT — %s | current_val=%d¢ < 5¢", ticker[-12:], val)
            self._execute_exit(ticker, state, val, exit_type="GLOBAL_FLOOR")

    async def _handle_message(self, raw_msg: str):
        """Routes WebSocket messages to the correct handler based on type."""
        try:
            msg = json.loads(raw_msg)
            m_type = msg.get("type")
            
            if m_type == "ticker":
                await self._on_orderbook_update(msg)
                self._check_exit_triggers(msg.get("market_ticker"))
            elif m_type == "fill":
                await self._on_fill_v2(msg)
            elif m_type == "error":
                log.error("❌ WS ERROR: %s", msg.get("msg"))
        except Exception as e:
            log.error("❌ Error parsing WS message: %s", e)

    async def _on_fill_v2(self, msg: dict):
        """Instant fill detection for the current orders."""
        ticker   = msg.get("market_ticker")
        side     = msg.get("side")
        order_id = msg.get("order_id")
        
        if ticker in self.tickers and side:
            state = self.tickers[ticker]
            log.info("⚡️ WS FILL RECEIVED — %s filled %s contracts", ticker[-12:], side.upper())
            
            # --- PROFIT/EXIT FILL DETECTION ---
            # If the filled order is our 'Take Profit' or 'Panic Exit', we are fully OUT.
            if order_id and (order_id == state.profit_order_id or order_id == state.sell_order_id):
                log.info("🎯 EXIT CONFIRMED — %s filled at target. Transitioning to EXITED.", ticker[-12:])
                state.status = TickerState.EXITED
                state.shares = 0
                self._save_status()
                return

            # --- ENTRY FILL DETECTION ---
            new_status = TickerState.FILLED_YES if side.lower() == "yes" else TickerState.FILLED_NO
            if state.status != new_status:
                state.status      = new_status
                state.filled_side = side
                state.shares      = to_int(msg.get("count") or msg.get("position"))
                state.entry_price = to_int(msg.get("price"))
                state.entry_time  = datetime.now(timezone.utc)
                
                self._ensure_profit_order_is_posted(ticker, state)
                self._save_status()
                # TRIGGER STOP-LOSS GUARDIAN IMMEDIATELY
                self._check_exit_triggers(ticker)

    def _ensure_profit_order_is_posted(self, ticker: str, state: TickerState):
        """
        Centrally handles placing the resting profit sell order.
        Checks if one already exists to avoid duplicates.
        """
        if not state.is_filled():
            return
        
        if state.profit_order_id:
            return # Already has a resting order
        
        strat = get_strategy(ticker)
        profit_target = strat.get("profit_target")
        if not profit_target:
            return

        log.info("🎯 TARGETING PROFIT — Posting resting %d¢ sell for %s", profit_target, ticker[-12:])
        
        async def _place_profit_order():
            try:
                # Post a LIMIT SELL at the target price
                # 🧪 HARDENING: Post only for the exact amount of shares we own
                pid = await asyncio.to_thread(self.rest.place_order, 
                    ticker, "sell", profit_target, state.shares, side=state.filled_side, post_only=True
                )
                if pid:
                    state.profit_order_id = pid
                    log.info("✅ Profit order posted: %s", pid)
                    self._save_status()
            except Exception as e:
                log.error("❌ Failed to post profit order for %s: %s", ticker, e)

        asyncio.create_task(_place_profit_order())

    async def _execute_entry(self, ticker: str, action: str, price: int, count: int, side: str, post_only: bool):
        """Helper to fire entry orders in the background."""
        state = self.tickers[ticker]
        oid = await asyncio.to_thread(self.rest.place_order, ticker, action, price, count, side, post_only=post_only)
        if oid:
            state.entry_price  = price
            state.entry_time   = datetime.now(timezone.utc)
            state.status       = TickerState.ENTERED
            state.filled_side  = side
            if side == "yes": state.yes_order_id = oid
            else: state.no_order_id = oid
            self._log_trade(f"{side.upper()}_{action.upper()}_POSTED", ticker=ticker, price=price)
            self._save_status()
        else:
            # If order failed, reset to WATCHING to allow retry
            log.error("💥 Entry order failed for %s. Resetting to WATCHING.", ticker[-12:])
            state.status = TickerState.WATCHING
            self._save_status()

    async def _on_orderbook_update(self, msg: dict):
        """Handle incoming 'ticker' messages from WebSocket."""
        ticker = msg.get("market_ticker")
        if not ticker or ticker not in self.tickers:
            return

        state = self.tickers[ticker]
        strat = get_strategy(ticker)
        
        # BBO (Best Bid/Offer) from the ticker channel
        # 🧪 HARDENING: Capture both sides directly to eliminate blind spots
        msg_yes_bid = to_cents(msg.get("yes_bid") or msg.get("yes_bid_cents") or msg.get("yes_bid_dollars"))
        msg_yes_ask = to_cents(msg.get("yes_ask") or msg.get("yes_ask_cents") or msg.get("yes_ask_dollars"))
        msg_no_bid  = to_cents(msg.get("no_bid")  or msg.get("no_bid_cents")  or msg.get("no_bid_dollars"))
        msg_no_ask  = to_cents(msg.get("no_ask")  or msg.get("no_ask_cents")  or msg.get("no_ask_dollars"))

        if msg_yes_bid is not None: state.last_bid = msg_yes_bid
        if msg_yes_ask is not None: state.last_ask = msg_yes_ask
        
        # 🧪 HARDENING: Derive NO prices if missing (Kalshi feed often only sends YES)
        if msg_no_bid is not None:
            state.last_no_bid = msg_no_bid
        elif state.last_ask is not None:
            state.last_no_bid = 100 - state.last_ask
            
        if msg_no_ask is not None:
            state.last_no_ask = msg_no_ask
        elif state.last_bid is not None:
            state.last_no_ask = 100 - state.last_bid
        
        bid = state.last_bid
        ask = state.last_ask
        
        # 🔗 MOMENTUM MEMORY: Record 'YES' bid into rolling window (default 30s)
        if msg_yes_bid is not None:
            now = time.time()
            state.price_history.append((now, msg_yes_bid))
            
            # Continuous pruning of old data
            cutoff = now - strat.get("window_s", 30)
            state.price_history = [(t, p) for t, p in state.price_history if t >= cutoff]

            # ⚡ BTC BURST DETECTION (For Shadow Sniper)
            if ticker.startswith("KXBTC15M"):
                min_in_window = min([p for t, p in state.price_history])
                max_in_window = max([p for t, p in state.price_history])
                
                burst_side = None
                if msg_yes_bid - min_in_window >= 8: burst_side = "yes"
                elif max_in_window - msg_yes_bid >= 8: burst_side = "no"
                
                if burst_side:
                    suffix = ticker.split("-")[-2] # e.g. 26APR232230
                    self.btc_bursts[suffix] = {"side": burst_side, "time": now}
                    log.info("⚡ BTC BURST DETECTED (%s): %s signaled for expiry %s", burst_side.upper(), ticker[-12:], suffix)

        # ── WATCHING / STRATEGY SEQUENCE ───────────────────────────────────────
        if state.status in (TickerState.WATCHING, TickerState.HIT_TRIGGER, TickerState.STABILIZING):
            logic_type = strat.get("logic_type", "SNIPER")
            
            # 🌊 BTC LATE SURGE TRACKER: Accumulate time YES bid is below barrier (e.g. 40c)
            if logic_type == "LATE_SURGE" and state.last_bid is not None:
                now = time.time()
                delta = now - state.last_barrier_update
                state.last_barrier_update = now
                if state.last_bid < strat.get("barrier", 40):
                    state.seconds_below_barrier += delta

            # 1. PULLBACK STRATEGY (e.g. ETH)
            if logic_type == "PULLBACK":
                # Get the relevant bids for both sides
                y_bid = state.last_bid
                n_bid = state.last_no_bid
                
                # BREAKOUT DETECTION (Phase 1)
                if state.status == TickerState.WATCHING:
                    if y_bid is not None and y_bid >= strat["trigger"]:
                        state.status = TickerState.HIT_TRIGGER
                        state.pullback_side = "yes"
                        state.hit_trigger_time = time.time()
                        log.info("🚀 ETH TRIGGER (YES): %s hit %d¢ breakout! Waiting for pullback to %d-%d¢ range...", 
                                 ticker[-12:], y_bid, strat["pullback_min"], strat["pullback_max"])
                        self._save_status()
                    elif n_bid is not None and n_bid >= strat["trigger"]:
                        state.status = TickerState.HIT_TRIGGER
                        state.pullback_side = "no"
                        state.hit_trigger_time = time.time()
                        log.info("🚀 ETH TRIGGER (NO): %s hit %d¢ breakout! Waiting for pullback to %d-%d¢ range...", 
                                 ticker[-12:], n_bid, strat["pullback_min"], strat["pullback_max"])
                        self._save_status()
                
                # PULLBACK DETECTION (Phase 2)
                elif state.status == TickerState.HIT_TRIGGER:
                    side_bid = state.last_bid if state.pullback_side == "yes" else state.last_no_bid
                    
                    if side_bid is not None:
                        # RESET condition: Drop below 50c means it must hit 65c again
                        if side_bid < strat["pullback_min"]:
                            log.info("⚠️ ETH RESET: %s dropped to %d¢ (below %d¢). Must hit %d¢ again.", 
                                     ticker[-12:], side_bid, strat["pullback_min"], strat["trigger"])
                            state.status = TickerState.WATCHING
                            state.pullback_side = None
                            self._save_status()
                        # ENTRY condition: Pulled back into range
                        elif strat["pullback_min"] <= side_bid <= strat["pullback_max"]:
                            state.status = TickerState.STABILIZING
                            state.stability_start_time = time.time()
                            log.info("📉 ETH PULLBACK (%s): %s entered %d-%d¢ range. Stabilizing for %ds...", 
                                     state.pullback_side.upper(), ticker[-12:], strat["pullback_min"], strat["pullback_max"], strat["stability_duration"])
                            self._save_status()
                
                # STABILITY CHECK (Phase 3)
                elif state.status == TickerState.STABILIZING:
                    side_bid = state.last_bid if state.pullback_side == "yes" else state.last_no_bid
                    
                    if side_bid is not None:
                        # RESET condition: Drop below 50c
                        if side_bid < strat["pullback_min"]:
                            log.info("⚠️ ETH RESET: %s dropped to %d¢ (below %d¢) during stabilization. Must hit %d¢ again.", 
                                     ticker[-12:], side_bid, strat["pullback_min"], strat["trigger"])
                            state.status = TickerState.WATCHING
                            state.pullback_side = None
                            self._save_status()
                        # STABILITY condition: Stay in range
                        elif strat["pullback_min"] <= side_bid <= strat["pullback_max"]:
                            elapsed = time.time() - state.stability_start_time
                            if elapsed >= strat["stability_duration"]:
                                log.info("⚖️ ETH STABLE: %s held range for %ds! Placing highest maker bid...", 
                                         ticker[-12:], int(elapsed))
                                asyncio.create_task(self._execute_entry(
                                    ticker, "buy", side_bid, strat["trade_count"], state.pullback_side, strat.get("post_only", False)
                                ))
                                state.status = TickerState.ENTERED
                                self._save_status()
                        else:
                            log.info("⚠️ ETH STABILITY INTERRUPTED: %s at %d¢ (left range). Waiting for drop back into %d-%d¢.", 
                                     ticker[-12:], side_bid, strat["pullback_min"], strat["pullback_max"])
                            state.status = TickerState.HIT_TRIGGER
                            state.stability_start_time = None
                            self._save_status()
                return

            # 2. ZONE SNIPER STRATEGY (BTC — data-driven Apr 21-27)
            elif logic_type == "ZONE_SNIPER":
                mins_left = state.minutes_to_close()

                # ── Primary: 60-72c Zone Sniper (12min → 1min) ──────────────
                if strat["window_end_mins"] <= mins_left <= strat["window_start_mins"]:
                    if state.status == TickerState.WATCHING:
                        bid = state.last_bid
                        ask = state.last_ask
                        # Detect zone by BID (consistent with backtest mid-price ~= bid)
                        if bid is not None and strat["zone_min"] <= bid <= strat["zone_max"]:
                            # Spread safety
                            spread = (ask - bid) if (ask and bid) else 99
                            if spread > GLOBAL_MAX_SPREAD:
                                log.warning("⚠️ [%s] BTC ZONE: Spread %d¢ too wide, skipping.", ticker[-12:], spread)
                                return
                            # MAKER order at bid+1 — rests on the book, guaranteed fill when someone sells
                            entry_price = bid + 1
                            if entry_price > strat["max_price"]:
                                return
                            log.info("🎯 BTC ZONE SNIPER: %s BID=%d¢ in 60-72c zone @ %.1fm left. MAKER buy @ %d¢.",
                                     ticker[-12:], bid, mins_left, entry_price)
                            asyncio.create_task(self._execute_entry(
                                ticker, "buy", entry_price, strat["trade_count"], "yes", True  # post_only=True (maker)
                            ))
                            state.status = TickerState.ENTERED
                            self._save_status()

                # ── Secondary: Crash Recovery (9min → 3min) ─────────────────
                elif strat["crash_window_end_mins"] <= mins_left <= strat["crash_window_start_mins"]:
                    if state.status == TickerState.WATCHING:
                        bid = state.last_bid
                        ask = state.last_ask
                        if bid is not None and ask is not None:
                            # Calculate single-tick price drop using price_history
                            history = state.price_history
                            if len(history) >= 2:
                                prev_bid = history[-2][1]
                                curr_bid = bid
                                drop = prev_bid - curr_bid
                                if drop >= strat["crash_drop_thresh"] and bid <= strat["crash_max_price"]:
                                    spread = ask - bid if ask > bid else 99
                                    if spread > GLOBAL_MAX_SPREAD:
                                        return
                                    # TAKER on crash recovery — need immediate fill on the dip
                                    entry_price = ask
                                    log.info("⚡ BTC CRASH RECOVERY: %s dropped %d¢ → BID=%d¢ @ %.1fm left. TAKER buy @ %d¢.",
                                             ticker[-12:], drop, bid, mins_left, entry_price)
                                    asyncio.create_task(self._execute_entry(
                                        ticker, "buy", entry_price, strat["trade_count"], "yes", False
                                    ))
                                    state.status = TickerState.ENTERED
                                    self._save_status()
                return

            # 3. CRYPTO BREAKOUT (BTC, SOL, XRP, DOGE)
            elif logic_type in ["BTC_BREAKOUT", "XRP_BREAKOUT", "DOGE_BREAKOUT"]:
                mins_left = state.minutes_to_close()
                if state.status == TickerState.WATCHING:
                    ask = state.last_ask
                    bid = state.last_bid
                    
                    if (strat["min_mins"] <= mins_left <= strat["max_mins"]):
                        trigger_price = None
                        max_entry = strat.get("max_entry", 100)
                        
                        # 🧪 STRICT CEILING: Only trigger if price is between Trigger and Max Entry
                        if ask and (strat["trigger"] <= ask <= max_entry):
                            trigger_price = ask
                        elif bid and (strat["trigger"] <= bid <= max_entry):
                            trigger_price = bid
                        
                        if trigger_price:
                            # 🛡️ SMART PRICING: Ensure fill without overpaying
                            maker_price = max(1, (ask - 1) if ask else (bid + 1))
                            maker_price = min(99, maker_price)
                            log.info("💥 %s TRIGGERED! (Price=%d¢) | Ceiling=%d¢ | Mins=%.1f", logic_type, trigger_price, max_entry, mins_left)
                            asyncio.create_task(self._execute_entry(ticker, "buy", maker_price, strat["trade_count"], "yes", False))
                            state.status = TickerState.ENTERED
                            self._save_status()
                return
                
            elif logic_type == "LATE_SURGE":
                mins_left = state.minutes_to_close()
                # Phase 2: Only strikes after Minute 10 (<= 5.0 mins remaining)
                # wait_mins is 10.0 (the period we monitor). 15 - 10 = 5 mins left.
                if mins_left > (15.0 - strat.get("wait_mins", 10.0)):
                    return
                
                if state.status == TickerState.WATCHING:
                    current_bid = state.last_bid
                    if current_bid is None: return
                    
                    # Condition 1: Was below 40c for at least 6 minutes (360s)
                    enough_time_depressed = (state.seconds_below_barrier >= strat.get("barrier_total_s", 360))
                    
                    # Condition 2: Price is now >= 60c
                    surge_hit = (current_bid >= strat.get("surge_trigger", 60))
                    
                    if enough_time_depressed and surge_hit:
                        # Taker price (Bid + 2c)
                        price = max(state.last_ask or 0, current_bid + 2)
                        
                        if price > strat.get("max_price", 94):
                            log.info("⚠️ BTC SURGE IGNORED: Price %d¢ above ceiling 94¢", price)
                            return
                            
                        # Spread safety
                        spread = (price - current_bid)
                        if spread > GLOBAL_MAX_SPREAD:
                             log.warning(f"⚠️ [{state.ticker_short}] SPREAD TOO WIDE ({spread}¢): skipping entry until market tightens.")
                             return

                        log.info("🌊 BTC LATE SURGE STRIKE: %s at %d¢! (Spent %.1fm below %d¢)", 
                                 ticker[-12:], price, (state.seconds_below_barrier/60.0), strat.get("barrier", 40))
                                 
                        asyncio.create_task(self._execute_entry(ticker, "buy", price, strat["trade_count"], "yes", False))
                        state.status = TickerState.ENTERED
                        self._save_status()
                return

            # 5. DUO_SNIPER (ETH Volume + Sniper)
            elif logic_type == "DUO_SNIPER":
                mins_left = state.minutes_to_close()
                if not (strat["mins_min"] <= mins_left <= strat["mins_max"]):
                    return
                
                if state.status == TickerState.WATCHING:
                    y_bid = state.last_bid
                    y_ask = state.last_ask
                    
                    target_side = None
                    if y_bid is not None and y_bid <= strat["no_threshold"]:
                        target_side = "no"
                    elif y_ask is not None and y_ask >= strat["yes_threshold"]:
                        target_side = "yes"
                        
                    if target_side:
                        # Execution Price (Taker)
                        if target_side == "yes":
                            price = y_ask or (y_bid + 2)
                        else:
                            # 100 - YES_bid is the taker price for NO
                            current_no_bid = state.last_no_bid or 80
                            price = state.last_no_ask or (current_no_bid + 2)

                        log.info("🎯 DUO STRIKE: %s | Final %.1fm | Side: %s | Price: %d¢", 
                                 ticker[-12:], mins_left, target_side.upper(), price)
                                 
                        asyncio.create_task(self._execute_entry(ticker, "buy", price, strat["trade_count"], target_side, False))
                        state.status = TickerState.ENTERED
                        self._save_status()
                return

            # CRASH RECOVERY (Legacy — ETH uses this)
            elif logic_type == "CRASH_RECOVERY":
                pass  # ETH crash recovery handled by KXETH15M config

            # 4. MOMENTUM BREAKOUT (SOL-Style Jump Detection)
            elif logic_type == "MOMENTUM_BREAKOUT":
                # Skip volatile early market (User setting: WINDOW_MINUTES)
                if state.minutes_to_close() > WINDOW_MINUTES:
                    return

                if state.status == TickerState.WATCHING:
                    # Need at least 2 points to detect a jump
                    if len(state.price_history) < 2: 
                        return

                    current_bid = state.last_bid
                    if current_bid is None: return

                    # Find minimum price in the memory window
                    min_in_window = min([p for t, p in state.price_history])
                    jump = current_bid - min_in_window
                    
                    THRESHOLD = strat.get("jump_threshold", 3)
                    MIN_PRICE = strat.get("min_price", 0)
                    
                    if jump >= THRESHOLD:
                        # 🛡️ PRICE FLOOR: Only buy if price >= user min_price (e.g. 50c)
                        if current_bid < MIN_PRICE:
                            return
                        # 🛡️ SPREAD SAFETY: Don't buy into illiquid momentum
                        spread = (state.last_ask - state.last_bid) if (state.last_ask and state.last_bid) else 99
                        if spread > GLOBAL_MAX_SPREAD:
                            log.warning(f"⚠️ [{state.ticker_short}] SPREAD TOO WIDE ({spread}¢): skipping Momentum breakout.")
                            return

                        log.info("🔥 BREAKOUT DETECTED: %s jumped %d¢ (min=%d¢, current=%d¢) in %ds!", 
                                 ticker[-12:], jump, min_in_window, current_bid, strat.get("window_s", 30))
                        
                        # EXECUTE: Target the ASK for immediate 'Taker' adoption (YES only)
                        price = state.last_ask or (current_bid + 2)
                        
                        log.info("🚀 MOMENTUM ENTRY: Buying YES on %s @ TAKER price %d¢", ticker[-12:], price)
                        asyncio.create_task(self._execute_entry(ticker, "buy", price, strat["trade_count"], "yes", False))
                        state.status = TickerState.ENTERED
                        self._save_status()
                return

            # 5. SHADOW SNIPER (ETH follows BTC)
            elif logic_type == "SHADOW_SNIPER":
                mins_left = state.minutes_to_close()
                # Skip first and last minute
                if mins_left > 14.0 or mins_left < 1.0:
                    return

                if state.status == TickerState.WATCHING:
                    y_bid = state.last_bid
                    if y_bid is None: return

                    # Check for matching BTC burst
                    suffix = ticker.split("-")[-2]
                    burst = self.btc_bursts.get(suffix)
                    
                    if burst and (time.time() - burst["time"]) < 15.0:
                        # BTC Burst is fresh! Check ETH quiet range
                        if strat["entry_range_min"] <= y_bid <= strat["entry_range_max"]:
                            target_side = burst["side"]
                            current_bid = state.last_bid if target_side == "yes" else state.last_no_bid
                            price = max(state.last_ask or 0, current_bid + 2) if target_side == "yes" else max(state.last_no_ask or 0, current_bid + 2)
                            
                            log.info("🕵️ SHADOW STRIKE: BTC burst signaled %s. ETH following at %d¢.", 
                                     target_side.upper(), price)
                                     
                            asyncio.create_task(self._execute_entry(ticker, "buy", price, strat["trade_count"], target_side, False))
                            state.status = TickerState.ENTERED
                            
                            # Set stop loss dynamically based on entry
                            strat["stop_loss"] = max(0, price - strat.get("stop_loss_drop", 40))
                            self._save_status()
                return

            # 4. SNATCHER STRATEGY (Lotto / Deep Value)
            elif logic_type == "SNATCHER":
                mins_left = state.minutes_to_close()
                if mins_left > strat["mins_mark"]:
                    return
                
                if state.status == TickerState.WATCHING:
                    y_bid = state.last_bid
                    n_bid = state.last_no_bid
                    
                    target_side = None
                    if y_bid is not None and y_bid <= strat["threshold"]:
                        target_side = "yes"
                    elif n_bid is not None and n_bid <= strat["threshold"]:
                        target_side = "no"
                        
                    if target_side:
                        price = state.last_bid if target_side == "yes" else state.last_no_bid
                        log.info("🎯 %s SNATCHER: Final %.1fm. Price has crashed to %d¢! Snatching %s.", 
                                 ticker[-12:], mins_left, price, target_side.upper())
                        asyncio.create_task(self._execute_entry(ticker, "buy", price, strat["trade_count"], target_side, False))
                        state.status = TickerState.ENTERED
                        self._save_status()
                return

            # 4. STANDARD SNIPER (DEFAULT)
            elif logic_type == "SNIPER":
                ENTRY_TRIGGER   = strat["trigger"]
                TRADE_COUNT     = strat["trade_count"]
                POST_ONLY       = strat.get("post_only", True)
                
                if bid is not None and bid >= ENTRY_TRIGGER:
                    log.info("📈 TREND-UP: Crossing %d¢ — Posting %d¢ YES bid", ENTRY_TRIGGER, ENTRY_TRIGGER)
                    asyncio.create_task(self._execute_entry(ticker, "buy", ENTRY_TRIGGER, TRADE_COUNT, "yes", POST_ONLY))
                    state.status = TickerState.ENTERED
                elif ask is not None and ask <= (100 - ENTRY_TRIGGER):
                    log.info("📉 TREND-DOWN: Crossing %d¢ — Posting %d¢ NO bid", 100 - ENTRY_TRIGGER, ENTRY_TRIGGER)
                    asyncio.create_task(self._execute_entry(ticker, "buy", ENTRY_TRIGGER, TRADE_COUNT, "no", POST_ONLY))
                    state.status = TickerState.ENTERED
                return

        # ── FILLED: Monitor for stop-loss (WebSocket side) ────────────────────
        self._check_exit_triggers(ticker)

    def _check_expirations(self):
        """Handle market expiry — cancel any resting order, lock tickers that never triggered."""
        for ticker, state in list(self.tickers.items()):
            strat = get_strategy(ticker)
            # 🛡️ FIX: Use .get() to prevent crash if 'bid' is missing in new strategies
            MAKER_BID_PRICE = strat.get("bid", state.entry_price or 0)
            
            if not state.is_expired():
                continue

            if state.status == TickerState.WATCHING:
                # Never triggered — market expired with no action taken
                log.info("⌛ %s expired without trigger — no orders placed", ticker)
                state.status = TickerState.LOCKED
                self._save_status()

            elif state.status == TickerState.ENTERED:
                log.warning(
                    "⌛ MARKET CLOSED with unfilled order — %s | YES: %s  NO: %s",
                    ticker, state.yes_order_id, state.no_order_id,
                )
                res_yes = self.rest.cancel_order(state.yes_order_id) if state.yes_order_id else None
                res_no  = self.rest.cancel_order(state.no_order_id) if state.no_order_id else None

                # 🧪 HARDENING: If cancel fails with Conflict, it filled!
                if res_yes == "CONFLICT" or res_no == "CONFLICT":
                    log.info("🎯 CONFLICT DETECTED on expiry — %s filled! Adoption in progress...", ticker[-12:])
                    # Set to LOCKED to break the loop; Portfolio Monitor will flip it to FILLED in 10s
                    state.status = TickerState.LOCKED
                    return

                state.status = TickerState.LOCKED
                self._log_trade("CANCELLED_UNFILLED", ticker=ticker, price=MAKER_BID_PRICE)
                self._save_status()
                
            elif state.status in (TickerState.FILLED_YES, TickerState.FILLED_NO):
                # SETTLEMENT LOGIC: Calculate win/loss based on price at moment of close
                # (Note: For 15m, price usually ends at 100 or 0)
                bid = self.orderbook.best_bid(ticker)
                
                final_val = bid if bid is not None else 0
                if state.status == TickerState.FILLED_NO:
                    final_val = 100 - (self.orderbook.best_ask(ticker) or 100)
                
                # If it didn't stop-loss, it settled.
                # Settlement is 100¢ if it finished high, 0¢ if it finished low.
                settlement_val = 100 if final_val > 50 else 0
                # 🧪 HARDENING: Never mark a trade as LOCKED or EXITED if we still own it.
                # The Portfolio Monitor will handle the final state change once positions are zero.
                if state.is_filled():
                    log.info("⌛ %s closed, but bot is holding position. Keep monitoring.", ticker[-12:])
                    continue

                pl_cents = (settlement_val - MAKER_BID_PRICE) * state.shares if MAKER_BID_PRICE else 0
                
                log.info("⌛ %s settled! Outcome: %d¢ | P&L: %+d¢", ticker, settlement_val, pl_cents)
                state.realized_pl_c = pl_cents
                state.exit_price    = settlement_val
                state.exit_time     = datetime.now(timezone.utc)
                state.status        = TickerState.EXITED
                
                self._total_pl_cents += pl_cents
                self._log_trade("SETTLEMENT", ticker=ticker, price=settlement_val, pl_cents=pl_cents)
                self._save_status()

    def _log_trade(self, event: str, **kwargs):
        entry = {
            "event":     event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self._trade_log.append(entry)
        self._trade_log = self._trade_log[-50:]  # keep last 50 events

    def _execute_exit(self, ticker: str, state: TickerState, val: int, exit_type: str = "EXIT"):
        """
        Executes a 'Panic Exit' at 1 cent to guarantee an immediate fill.
        This handles both Stop-Loss and Take-Profit logic.
        """
        side = "yes" if ("FILLED_YES" in str(state.status) or state.filled_side == "yes") else "no"
        shares = state.shares or 1
        
        # 🛡️ SAFETY: Do not attempt to exit if market is already expired
        if state.is_expired():
            log.info("⌛ %s expired — waiting for settlement instead of panic exit.", ticker[-12:])
            return

        # 🛡️ SAFETY: Do not attempt to exit if market is already expired
        if state.is_expired():
            log.info("⌛ %s expired — waiting for settlement instead of panic exit.", ticker[-12:])
            return

        state.status = TickerState.EXITING
        log.warning("🎯 [%s] Triggered for %s at %d¢", exit_type, ticker, val)

        async def _do_panic_exit():
            try:
                # 🧪 HARDENING: Instead of selling at 1¢ (which causes catastrophic slippage), 
                # we sell at (TriggerPrice - 2¢). This ensures a 'Taker' fill but prevents sliding to zero.
                protected_exit_price = max(1, val - 2)
                
                log.info("🎯 Price-Protected Exit (%s): Selling %d %s contracts for %s at %d¢", 
                    exit_type, shares, side.upper(), ticker, protected_exit_price)
                
                # 🧹 Order Cleanup: Clear the deck before trying a new exit
                if state.profit_order_id:
                    log.info("🧹 Cancelling resting profit order: %s", state.profit_order_id)
                    await asyncio.to_thread(self.rest.cancel_order, state.profit_order_id)
                    state.profit_order_id = None

                if state.sell_order_id:
                    log.info("🧹 Cancelling stale exit order (Chasing): %s", state.sell_order_id)
                    try:
                        await asyncio.to_thread(self.rest.cancel_order, state.sell_order_id)
                    except Exception as e:
                        log.debug("Found nothing to cancel for sell_order_id (already filled or gone)")
                    state.sell_order_id = None

                # Fire the price-protected 'Taker' order immediately
                res_oid = await asyncio.to_thread(self.rest.place_order, 
                    ticker, 
                    "sell", 
                    protected_exit_price, 
                    shares, 
                    side, 
                    False # post_only=False to ensure it takes liquidity
                )
                
                if res_oid:
                    log.info("✅ Exit order successful: %s at %d¢", res_oid, protected_exit_price)
                    state.sell_order_id = res_oid
                    state.exit_price    = protected_exit_price
                    state.exit_time     = datetime.now(timezone.utc)
                    state.status        = TickerState.EXITED
                    
                    # Record P&L
                    entry = state.entry_price or 0
                    if entry > 0:
                        pl = (protected_exit_price - entry) * shares
                        state.realized_pl_c = pl
                        self._total_pl_cents += pl
                        self._log_trade("STOP_LOSS_EXIT", ticker=ticker, price=protected_exit_price, pl_cents=pl)
                    
                    self._save_status()
                else:
                    log.error("💥 Exit order returned no ID for %s", ticker)
                    # Reset status to allow retry in next loop
                    state.status = TickerState.FILLED_YES if side == "yes" else TickerState.FILLED_NO
                    self._save_status()

            except Exception as e:
                log.error("💥 Panic exit execution failed for %s: %s", ticker, e)
                state.status = TickerState.FILLED_YES if side == "yes" else TickerState.FILLED_NO

        asyncio.create_task(_do_panic_exit())

    def _get_cached_balance(self) -> int:
        """Fetch balance only once per minute to avoid 429 rate limits."""
        now = time.monotonic()
        if now - self._last_balance_ts > 60:
            self._last_balance_cents = self.rest.get_balance_cents()
            self._last_balance_ts    = now
        return self._last_balance_cents

    def _save_status(self):
        """Write bot_status.json — read by dashboard.py."""
        now = datetime.now(timezone.utc)
        
        # CLEANUP: Remove markets older than 2 hours to keep file small
        self.tickers = {
            t: s for t, s in self.tickers.items()
            if (now - s.close_time).total_seconds() < 7200  # 2 hours
        }

        relevant = {
            t: s.to_dict()
            for t, s in self.tickers.items()
            if s.status != TickerState.WATCHING or s.minutes_to_close() <= WINDOW_MINUTES + 2
        }
        data = {
            "last_updated":      datetime.now(timezone.utc).isoformat(),
            "dry_run":           DRY_RUN,
            "total_pl_cents":    self._total_pl_cents,
            "total_pl_dollars":  round(self._total_pl_cents / 100, 2),
            "balance_cents":     self._get_cached_balance(),
            "markets":           relevant,
            "trade_log":         self._trade_log,
            "strategy":          STRATEGIES,
        }
        try:
            with open("bot_status.json", "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error("Failed to save status: %s", e)

    # ── REST position monitor (Safety poll) ────────────────────────────────

    async def _monitor_positions(self):
        """
        Independent REST-based polling loop.
        Guardian of stop-losses in case WebSocket fails.
        TARGETED SCAN: Only asks for your crypto positions (ignores weather trades).
        """
        log.info("⏱  Position monitor started (Targeted Crypto-Only Sync every 10s)")
        while self._running:
            try:
                active_tickers = list(self.tickers.keys())
                if not active_tickers:
                    await asyncio.sleep(10)
                    continue

                # 🧪 BATCH SYNC: Single account-wide call instead of 7 individual ones
                results = await asyncio.to_thread(self.rest.get_positions)
                
                # Map ticker -> position result
                active_pos = {}
                for pos in results:
                    ticker = pos.get("ticker")
                    if ticker and ticker in active_tickers:
                        shares = to_int(pos.get("position_fp") or pos.get("position") or pos.get("count"))
                        if abs(shares) > 0:
                            log.info("📊 Portfolio Match: %s | shares: %d", ticker[-12:], shares)
                            pos["_shares"] = abs(shares)
                            active_pos[ticker] = pos

                # Update internal state
                for ticker, state in list(self.tickers.items()):
                    # 1. Sync state from Portfolio (Source of Truth)
                    if ticker in active_pos:
                        pos  = active_pos[ticker]
                        shares_val = to_int(pos.get("position_fp") or pos.get("position") or pos.get("count"))
                        side = "yes" if shares_val > 0 else "no"
                        shares = abs(shares_val)
                        new_status = TickerState.FILLED_YES if side == "yes" else TickerState.FILLED_NO
                        
                        if state.status != new_status or state.shares != shares:
                            if state.status == TickerState.ENTERED:
                                log.info("🎯 ADOPTED POSITION — %s confirmed as %s contracts", ticker, side.upper())
                            elif state.status == TickerState.EXITED:
                                log.info("🎯 RE-ADOPTED POSITION — %s back in portfolio", ticker)
                            else:
                                log.info("🎯 SYNC UPDATE — %s state %s -> %s (Shares: %d)", ticker, state.status, new_status, shares)
                            
                            state.status      = new_status
                            state.filled_side = side
                            state.shares      = shares
                            
                            if state.entry_price is None:
                                exposure_cents = to_cents(pos.get("market_exposure") or pos.get("market_exposure_dollars"))
                                state.entry_price = abs(exposure_cents / shares) if shares > 0 else 0
                                
                            # 🎯 NEW: Ensure profit-taker is placed even if Adopted via REST
                            self._ensure_profit_order_is_posted(ticker, state)
                            
                            self._save_status()
                            self._check_exit_triggers(ticker)
                    
                    elif state.is_filled():
                        # If we have a record of a fill, but the targeted scan says it's gone
                        log.info("🏁 POSITION CLOSED — %s no longer in portfolio. Transitioning to EXITED.", ticker)
                        state.status = TickerState.EXITED
                        state.shares = 0
                        self._save_status()

                # 2. WATCHLIST: Entry logic safety check
                for ticker, state in self.tickers.items():
                    if state.status == TickerState.WATCHING:
                        mins = state.minutes_to_close()
                        if 0 < mins <= WINDOW_MINUTES:
                            m = await asyncio.to_thread(self.rest.get_market, ticker)
                            y_bid = to_cents(m.get("yes_bid") or m.get("yes_bid_dollars"))
                            y_ask = to_cents(m.get("yes_ask") or m.get("yes_ask_dollars"))
                            n_bid = to_cents(m.get("no_bid")  or m.get("no_bid_dollars"))
                            n_ask = to_cents(m.get("no_ask")  or m.get("no_ask_dollars"))
                            
                            if y_bid is not None or y_ask is not None:
                                log.info("📡 [TICK] %s | YES: %d¢ / %d¢ | Mins: %.1f", 
                                         ticker[-12:], y_bid or 0, y_ask or 0, mins)
                                payload = {"market_ticker": ticker}
                                if y_bid is not None: payload["yes_bid_cents"] = y_bid
                                if y_ask is not None: payload["yes_ask_cents"] = y_ask
                                if n_bid is not None: payload["no_bid_cents"] = n_bid
                                if n_ask is not None: payload["no_ask_cents"] = n_ask
                                await self._on_orderbook_update(payload)

                    if state.is_filled():
                        # 🧪 REST SAFETY-NET: Fetch fresh market snapshot to bypass any WebSocket failures
                        try:
                            m = await asyncio.to_thread(self.rest.get_market, ticker)
                            bid = to_cents(m.get("yes_bid") or m.get("yes_bid_dollars"))
                            ask = to_cents(m.get("yes_ask") or m.get("yes_ask_dollars"))
                            n_bid = to_cents(m.get("no_bid") or m.get("no_bid_dollars"))
                            
                            if bid is not None: state.last_bid = bid
                            if ask is not None: state.last_ask = ask
                            
                            # Update NO prices directly or via derivation
                            if n_bid is not None: 
                                state.last_no_bid = n_bid
                            elif ask is not None: 
                                state.last_no_bid = 100 - ask
                                
                            if bid is not None: 
                                state.last_no_ask = 100 - bid
                            
                            log.debug("📡 REST Safety Sync — %s | Price: %s¢", ticker[-12:], 
                                      state.last_bid if state.filled_side == 'yes' else state.last_no_bid)
                        except Exception as e:
                            log.warning("📡 REST Safety Sync failed for %s: %s", ticker, e)

                        self._check_exit_triggers(ticker)

            except Exception as e:
                log.error("Targeted monitor cycle failed: %s", e)
            
            # 🏎️ High-Frequency Windowing: If we are close to expiration, poll faster!
            sleep_time = 10
            for s in self.tickers.values():
                if s.status == TickerState.WATCHING and 0 < s.minutes_to_close() <= WINDOW_MINUTES:
                    sleep_time = 2 # Boost to 2s polls during the trading window
                    break
            
            await asyncio.sleep(sleep_time)
    # ── WebSocket layer ───────────────────────────────────────────────────────

    def _next_ws_id(self) -> int:
        self._ws_id_counter += 1
        return self._ws_id_counter

    async def _subscribe(self, ws, tickers: list[str]):
        if not tickers:
            return
        # Switch to 'ticker' channel for real-time BBO (Best Bid/Offer)
        # Add 'fills' and 'orders' for instant fill detection (bypass REST lag)
        msg = {
            "id":  self._next_ws_id(),
            "cmd": "subscribe",
            "params": {
                "channels":       ["ticker", "fill", "fills"],
                "market_tickers": tickers,
            },
        }
        await ws.send(json.dumps(msg))
        log.info(
            "Subscribed to ticker channel for %d ticker(s): %s…",
            len(tickers), tickers[0] if tickers else "",
        )

    async def _handle_message(self, raw: str):
        """Route a raw WebSocket message to the appropriate handler."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type")
        
        # New Ticker Channel Handler (High Speed)
        if msg_type == "ticker":
            await self._on_orderbook_update(msg)

        elif msg_type == "fill":
            ticker = msg.get("market_ticker")
            if ticker in self.tickers:
                state = self.tickers[ticker]
                side  = msg.get("side", "yes")
                new_status = TickerState.FILLED_YES if side.lower() == "yes" else TickerState.FILLED_NO
                
                if state.status != new_status:
                    log.info("🎯 WS FILL ALERT — %s filled as %s", ticker[-12:], side.upper())
                    state.status      = new_status
                    state.filled_side = side
                    # Update entry price if provided
                    fill_price = msg.get("yes_price") or msg.get("no_price") or msg.get("price")
                    if fill_price: state.entry_price = to_cents(fill_price)
                    
                    self._save_status()
                    # Trigger immediate exit check
                    self._check_exit_triggers(ticker)

        elif msg_type in ("order_update", "order"):
            # Handle order status changes (e.g. fully filled)
            order = msg.get("order", {})
            ticker = order.get("ticker")
            if ticker in self.tickers and order.get("status") == "filled":
                state = self.tickers[ticker]
                side  = order.get("side", "yes")
                new_status = TickerState.FILLED_YES if side.lower() == "yes" else TickerState.FILLED_NO
                if state.status != new_status:
                    log.info("🎯 WS ORDER FILL — %s confirmed filled", ticker[-12:])
                    state.status = new_status
                    state.filled_side = side
                    self._save_status()
                    self._check_exit_triggers(ticker)

        elif msg_type == "subscribed":
            log.debug("Subscription ACK")

        # Periodic status save
        self._msg_count += 1
        if self._msg_count % STATUS_SAVE_INTERVAL == 0:
            self._save_status()

    async def _ws_loop(self):
        """
        Main WebSocket event loop.
        Also spawns the REST position monitor as a concurrent asyncio task.
        Handles auto-reconnect with exponential back-off.
        """
        subscribed:       set[str] = set()
        reconnect_delay: int       = 5

        # Start the REST polling safety net as a background task
        monitor_task = asyncio.ensure_future(self._monitor_positions())
        log.info("Position monitor task started")

        # Keep a shared queue so the discovery task can hand new tickers to the ws loop
        new_ticker_queue: asyncio.Queue = asyncio.Queue()

        async def _discovery_task():
            """Independent 30-second discovery loop. Puts new tickers into the queue."""
            await asyncio.sleep(2)  # let the ws connect first
            while self._running:
                new_tickers = self._discover_markets()
                for t in new_tickers:
                    await new_ticker_queue.put(t)
                await asyncio.sleep(DISCOVERY_INTERVAL_S)

        discovery_task = asyncio.ensure_future(_discovery_task())

        while self._running:
            try:
                ws_headers = self.auth.ws_headers()

                async with websockets.connect(
                    WS_URL,
                    additional_headers=ws_headers,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10,
                ) as ws:
                    log.info("✅ WebSocket connected to %s", WS_URL)
                    reconnect_delay = 5  # reset on successful connection

                    # Subscribe to all currently-known tickers
                    all_known = list(self.tickers.keys())
                    await self._subscribe(ws, all_known)
                    subscribed = set(all_known)

                    # Message loop with timeout so we drain queue even during silence
                    last_orderbook_ts = time.monotonic()
                    STALE_SECONDS     = 20  # reconnect if no orderbook data for this long

                    while self._running:
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        except asyncio.TimeoutError:
                            raw_msg = None  # no message in 5s — still check queue below

                        if raw_msg is not None:
                            await self._handle_message(raw_msg)
                            # Track freshness: reset watchdog on ticker, orderbook, or fill
                            msg_json = json.loads(raw_msg)
                            msg_type = msg_json.get("type")
                            if msg_type in ["ticker", "orderbook", "fill"]:
                                last_orderbook_ts = time.monotonic()

                        self._check_expirations()

                        # Drain any new tickers the discovery task found
                        while not new_ticker_queue.empty():
                            t = new_ticker_queue.get_nowait()
                            if t not in subscribed:
                                log.info("🔔 Subscribing to new market: %s", t)
                                await self._subscribe(ws, [t])
                                subscribed.add(t)
                                last_orderbook_ts = time.monotonic()  # reset on new sub

                        # Staleness check: reconnect if orderbook went silent
                        active_watching = any(
                            s.status == TickerState.WATCHING
                            for s in self.tickers.values()
                        )
                        if active_watching and (time.monotonic() - last_orderbook_ts) > STALE_SECONDS:
                            log.warning("⚠️  No orderbook data for %ds — reconnecting…", STALE_SECONDS)
                            break  # exit inner loop → triggers reconnect

            except websockets.exceptions.ConnectionClosedError as e:
                log.warning("WebSocket closed: %s — reconnecting in %ds…", e, reconnect_delay)
            except websockets.exceptions.InvalidStatusCode as e:
                log.error(
                    "WebSocket rejected (HTTP %s). Check KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY_PEM.",
                    e.status_code,
                )
                reconnect_delay = min(reconnect_delay * 2, 120)
            except Exception as e:
                log.error("Unexpected WebSocket error: %s — reconnecting in %ds…", e, reconnect_delay)

            if self._running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def _shutdown(self, *_):
        log.info("Shutdown signal — stopping gracefully…")
        self._running = False

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        loop = asyncio.get_event_loop()
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT,  self._shutdown)

        log.info("━" * 60)
        log.info("  Kalshi 15-Minute Multi-Market Bot")
        log.info("  Target : %s", ", ".join(TARGET_SERIES))
        log.info("  Strategies : Loaded unique config per coin")
        log.info("  Mode   : %s", "DRY-RUN" if DRY_RUN else "LIVE 🔴")
        log.info("━" * 60)

        # Run initial discovery SYNCHRONOUSLY before any async code
        log.info("Running initial market discovery…")
        self._discover_markets()
        log.info("Initial discovery done. %d ticker(s) registered.", len(self.tickers))

        try:
            loop.run_until_complete(self._ws_loop())
        finally:
            self._save_status()
            log.info(
                "Bot stopped. Session P&L: %+d¢ ($%+.2f)",
                self._total_pl_cents, self._total_pl_cents / 100,
            )


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    KalshiBtcBot().run()
