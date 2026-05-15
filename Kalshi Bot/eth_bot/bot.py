#!/usr/bin/env python3
"""
Kalshi ETH 15-Minute Dual-Strategy Bot
=======================================
Data-driven strategies from April 2026 backtest (Last 24h update).

STRATEGY A — "Late Dip Buyer"  [VALUE ENTRY]
  • Signal   : YES ask ≤ 30¢ when 1–5 minutes remain
  • Action   : BUY YES at maker price (1¢ below ask)
  • Hold     : To expiry, no stop-loss
  • Backtest : 48 trades, 25.0% win rate, +11.44¢ EV/share (Last 24h)

STRATEGY B — "Fast Momentum Lock"  [HIGH CONVICTION]
  • Signal   : YES ask ≥ 75¢ when 3–8 minutes remain
  • Action   : BUY YES at maker price (1¢ below ask)
  • Hold     : To expiry, no stop-loss
  • Backtest : 41 trades, 85.4% win rate, +3.68¢ EV/share (Last 24h)

KEY RULES:
  • One entry per market, per strategy
  • Strategies don't overlap (A fires on dips, B fires on breakouts)
  • Hold to expiry — no stop-loss, no early exit
  • 1 share per trade (scale via TRADE_SIZE)
  • Polls every 2 seconds to stay within API rate limits
  • Scans ALL open ETH markets simultaneously

COMBINED EXPECTATION: High volatility YES-only capture
"""

import os
import sys
import json
import time
import uuid
import base64
import logging
from datetime import datetime, timezone, timedelta

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  — tune these only
# ─────────────────────────────────────────────────────────────────────────────

TARGET_SERIES = "KXETH15M"
TRADE_SIZE    = 1           # shares per trade (scale up when confident)
POLL_INTERVAL = 2.0         # seconds between full scan cycles

# Strategy A — Late Dip Buyer
STRAT_A_WINDOW_MIN = 1      # minutes remaining (low end)
STRAT_A_WINDOW_MAX = 5      # minutes remaining (high end)
STRAT_A_THRESHOLD  = 30     # YES ask ≤ this → BUY YES
STRAT_A_SIDE       = "yes"

# Strategy B — Fast Momentum Lock
STRAT_B_WINDOW_MIN = 3
STRAT_B_WINDOW_MAX = 8
STRAT_B_THRESHOLD  = 75     # YES ask ≥ this → BUY YES
STRAT_B_SIDE       = "yes"

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("eth_dual_bot.log"),
    ],
)
log = logging.getLogger(__name__).info

# ─────────────────────────────────────────────────────────────────────────────
# KALSHI CLIENT
# ─────────────────────────────────────────────────────────────────────────────

API_BASE = "https://api.elections.kalshi.com"

class KalshiClient:
    def __init__(self):
        self._load_local_env()
        self.key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip().strip('"')
        if not self.key_id:
            raise ValueError("Missing KALSHI_API_KEY_ID env var")
        self.private_key = self._load_key()
        self.session = requests.Session()

    def _load_local_env(self):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.replace("export ", "").strip()
                        if k not in os.environ:
                            os.environ[k] = v.strip().strip('"').strip("'")

    def _load_key(self):
        pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
        if not pem:
            path = os.environ.get("KALSHI_PRIVATE_KEY_PATH",
                                  os.path.join(os.path.dirname(__file__), "kalshi_private.pem"))
            if not os.path.exists(path):
                # fallback to btc_bot key
                alt = os.path.join(os.path.dirname(os.path.dirname(__file__)), "btc_bot", "kalshi_private.pem")
                if os.path.exists(alt):
                    path = alt
            with open(path, "rb") as f:
                pem = f.read().decode()
        pem = pem.replace("\\n", "\n").replace('"', "").strip()
        return serialization.load_pem_private_key(pem.encode(), password=None)

    def _sign(self, method: str, path: str) -> dict:
        clean = path.split("?")[0]
        ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        sig = self.private_key.sign(
            (ts + method.upper() + clean).encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: dict = None) -> dict:
        url = API_BASE + path
        resp = self.session.get(url, headers=self._sign("GET", path),
                                params=params, timeout=12)
        if resp.status_code >= 400:
            log(f"GET {path} → {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: dict) -> dict:
        url = API_BASE + path
        resp = self.session.post(url, headers=self._sign("POST", path),
                                 json=body, timeout=12)
        if resp.status_code >= 400:
            log(f"POST {path} → {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def get_recent_settled_eth_results(self) -> list[str]:
        """Returns the results ('yes', 'no') of the 3 most recently settled ETH markets."""
        try:
            params = {"status": "settled", "series_ticker": TARGET_SERIES, "limit": 3}
            data = self.get("/trade-api/v2/markets", params)
            markets = data.get("markets", [])
            markets.sort(key=lambda m: m.get("close_time", ""), reverse=True)
            return [m.get("result") for m in markets[:3]]
        except Exception as e:
            log(f"Trend check failed: {e}")
            return []

    def get_open_eth_markets(self) -> list[dict]:
        """Returns all currently open ETH 15M markets."""
        markets = []
        cursor = None
        while True:
            params = {"status": "open", "series_ticker": TARGET_SERIES, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = self.get("/trade-api/v2/markets", params)
            batch = data.get("markets", [])
            markets.extend(batch)
            cursor = data.get("cursor")
            if not cursor or not batch:
                break
        return markets

    def get_cents(self, market: dict, key: str) -> int:
        """Extract a price field in cents regardless of API format."""
        val = market.get(key)
        if val is not None:
            try: return int(val)
            except: pass
        val_d = market.get(f"{key}_dollars")
        if val_d is not None:
            try: return int(round(float(val_d) * 100))
            except: pass
        return 0

    def place_order(self, ticker: str, side: str, price_cents: int,
                    count: int, order_type: str = "limit") -> "Optional[str]":
        """Place a limit order. Returns order_id or None on failure.
        
        IMPORTANT: Kalshi API always uses 'yes_price' regardless of side.
        For NO orders: yes_price = 100 - no_price.
        """
        # Kalshi always wants yes_price — convert if ordering NO
        if side == "yes":
            yes_price_field = price_cents
        else:
            yes_price_field = 100 - price_cents  # convert NO cents to YES equivalent
        body = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "type": order_type,
            "count": count,
            "yes_price": yes_price_field,
            "client_order_id": f"ETH-{side.upper()}-{int(time.time())}-{uuid.uuid4().hex[:6]}",
        }
        try:
            res = self.post("/trade-api/v2/portfolio/orders", body)
            return res.get("order", {}).get("order_id")
        except Exception as e:
            log(f"  ⚠️  Order failed ({side.upper()} {ticker}): {e}")
            return None

# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def minutes_remaining(close_dt: datetime) -> float:
    return (close_dt - datetime.now(timezone.utc)).total_seconds() / 60.0

def evaluate_market(client: KalshiClient, market: dict, entered: set) -> "Optional[str]":
    """
    Evaluate one market against both strategies.
    Returns: "A" if Strategy A fired, "B" if Strategy B fired, None otherwise.
    Adds ticker to `entered` set to prevent double-entry.
    """
    ticker = market["ticker"]
    if ticker in entered:
        return None

    close_str = market.get("close_time", "")
    try:
        close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
    except ValueError:
        return None

    mr = minutes_remaining(close_dt)

    # Skip markets outside the global strategy window (saves API calls)
    if mr < min(STRAT_A_WINDOW_MIN, STRAT_B_WINDOW_MIN) or mr > max(STRAT_A_WINDOW_MAX, STRAT_B_WINDOW_MAX):
        return None

    yes_ask = client.get_cents(market, "yes_ask")

    # ── STRATEGY A: Late Dip Buyer  [MAKER] ────────────────────────────────
    # YES ask ≤ THRESHOLD  →  buy the dip
    if STRAT_A_WINDOW_MIN <= mr <= STRAT_A_WINDOW_MAX and yes_ask > 0 and yes_ask <= STRAT_A_THRESHOLD:
        maker_yes_price = max(1, yes_ask - 1)  # 1¢ inside = maker, no fee
        order_id = client.place_order(ticker, STRAT_A_SIDE, maker_yes_price, TRADE_SIZE)
        if order_id:
            entered.add(ticker)
            log(f"  ✅ [A] DIP BUYER | {ticker} | YES_ask={yes_ask}¢ "
                f"→ MAKER BUY YES @ {maker_yes_price}¢ "
                f"| {mr:.1f}min left | order={order_id}")
            return "A"

    # ── STRATEGY B: Fast Momentum Lock  [MAKER] ────────────────────────────
    # YES ask ≥ 75¢  →  market is pricing a strong YES breakout
    if STRAT_B_WINDOW_MIN <= mr <= STRAT_B_WINDOW_MAX and yes_ask > 0 and yes_ask >= STRAT_B_THRESHOLD:
        maker_yes_price = max(1, yes_ask - 1)   # 1¢ inside YES ask = maker, no fee
        order_id = client.place_order(ticker, STRAT_B_SIDE, maker_yes_price, TRADE_SIZE)
        if order_id:
            entered.add(ticker)
            log(f"  ✅ [B] MOMENTUM | {ticker} | YES_ask={yes_ask}¢ "
                f"→ MAKER BUY YES @ {maker_yes_price}¢ "
                f"| {mr:.1f}min left | order={order_id}")
            return "B"

    return None

# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_bot():
    client = KalshiClient()

    log("=" * 62)
    log("  ETH DUAL-STRATEGY BOT  —  Starting")
    log("=" * 62)
    log(f"  Series        : {TARGET_SERIES}")
    log(f"  Trade size    : {TRADE_SIZE} share(s)")
    log(f"  Poll interval : {POLL_INTERVAL}s")
    log("")
    log("  STRATEGY A — Late Dip Buyer")
    log(f"    Trigger : YES ask ≤ {STRAT_A_THRESHOLD}¢")
    log(f"    Window  : {STRAT_A_WINDOW_MIN}–{STRAT_A_WINDOW_MAX} min remaining")
    log(f"    Action  : BUY YES at Maker Price (Ask - 1)")
    log(f"    Hold    : To expiry")
    log(f"    Expect  : ~48 trades/day, 25.0% win, +11.44¢ EV/share")
    log("")
    log("  STRATEGY B — Fast Momentum Lock")
    log(f"    Trigger : YES ask ≥ {STRAT_B_THRESHOLD}¢")
    log(f"    Window  : {STRAT_B_WINDOW_MIN}–{STRAT_B_WINDOW_MAX} min remaining")
    log(f"    Action  : BUY YES at Maker Price (Ask - 1)")
    log(f"    Hold    : To expiry")
    log(f"    Expect  : ~41 trades/day, 85.4% win, +3.68¢ EV/share")
    log("=" * 62)

    # entered: tracks tickers we've already placed an order on this calendar day
    entered: set[str] = set()
    last_reset = datetime.now(timezone.utc).date()

    cycle_count = 0
    trades_today = {"A": 0, "B": 0}
    
    trend_pause_until = 0
    last_trend_check = 0

    while True:
        try:
            t_start = time.time()

            # Reset entries at UTC midnight (new trading day)
            today = datetime.now(timezone.utc).date()
            if today != last_reset:
                log(f"  🗓️  New day — resetting entered set. "
                    f"Yesterday: A={trades_today['A']}, B={trades_today['B']}")
                entered.clear()
                trades_today = {"A": 0, "B": 0}
                last_reset = today

            # Fetch all open ETH markets
            try:
                markets = client.get_open_eth_markets()
            except Exception as e:
                log(f"  ⚠️  Market fetch failed: {e}")
                time.sleep(POLL_INTERVAL)
                continue

            # Filter to markets in strategy window before evaluating
            in_window = []
            for m in markets:
                close_str = m.get("close_time", "")
                try:
                    close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
                    mr = minutes_remaining(close_dt)
                    if min(STRAT_A_WINDOW_MIN, STRAT_B_WINDOW_MIN) <= mr <= max(STRAT_A_WINDOW_MAX, STRAT_B_WINDOW_MAX):
                        in_window.append(m)
                except ValueError:
                    pass

            cycle_count += 1

            if in_window:
                log(f"  Cycle {cycle_count:>4} | {len(markets)} open markets | "
                    f"{len(in_window)} in window | "
                    f"entered today: A={trades_today['A']} B={trades_today['B']}")

                for market in in_window:
                    fired = evaluate_market(client, market, entered)
                    if fired:
                        trades_today[fired] += 1
            else:
                # Quiet cycle — just print a heartbeat every 30 cycles
                if cycle_count % 30 == 0:
                    log(f"  Cycle {cycle_count:>4} | {len(markets)} open markets | "
                        f"none in {min(STRAT_A_WINDOW_MIN, STRAT_B_WINDOW_MIN)}–{max(STRAT_A_WINDOW_MAX, STRAT_B_WINDOW_MAX)}min window | "
                        f"today: A={trades_today['A']} B={trades_today['B']}")

            # Sleep for remainder of poll interval
            elapsed = time.time() - t_start
            sleep_for = max(0.0, POLL_INTERVAL - elapsed)
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            log("\n👋  Bot stopped by user.")
            log(f"   Final counts: A={trades_today['A']}, B={trades_today['B']}")
            break
        except Exception as e:
            log(f"  ⚠️  Unhandled loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
