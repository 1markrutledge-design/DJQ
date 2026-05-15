#!/usr/bin/env python3
"""
Kalshi SOL 15-Minute Dual-Strategy Bot
====================================
Strategy A (Fast Momentum Lock): Buy YES Maker if YES Ask >= 75c (1-8m)
Strategy B (Mid-Market Fade): Buy NO Maker if NO Bid <= 35c (5-12m)
"""

import sys
import time
import os
import uuid
import base64
import requests
import argparse
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE = "https://api.elections.kalshi.com"
POLL_INTERVAL_S = 1.0

# ─── Core strategy parameters ───────────────────────────────────────────────
CONTRACT_COUNT = 1

# Strategy A
A_TRIGGER = 75   # YES Ask >= 75
A_MIN_LEFT = 1.0
A_MAX_LEFT = 8.0

# Strategy B
B_TRIGGER = 35   # NO Bid <= 35 (means YES is strong but failing)
B_MIN_LEFT = 5.0
B_MAX_LEFT = 12.0

# ─── Auth ───────────────────────────────────────────────────────────────────
class KalshiAuth:
    def __init__(self):
        self._load_local_env()
        self.key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip().strip('"')
        if not self.key_id:
            raise ValueError("Missing KALSHI_API_KEY_ID env var")
        self.private_key = self._load_key()

    def _load_local_env(self):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.startswith("export "):
                            k = k[7:]
                        k = k.strip()
                        if k not in os.environ:
                            os.environ[k] = v.strip().strip('"').strip("'")

    def _load_key(self):
        pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
        if not pem_data:
            path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")
            if not os.path.exists(path):
                path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "btc_bot", "kalshi_private.pem")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    pem_data = f.read().decode()
            else:
                raise ValueError(f"Could not find Kalshi private key at {path} or in env vars!")

        pem_data = pem_data.replace("\\n", "\n").replace('"', "").strip()
        for header, footer in [
            ("-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----"),
            ("-----BEGIN PRIVATE KEY-----",     "-----END PRIVATE KEY-----"),
        ]:
            if header in pem_data and "\n" not in pem_data[len(header):len(header) + 10]:
                content = pem_data.replace(header, "").replace(footer, "").strip()
                pem_data = f"{header}\n{content}\n{footer}"
                break

        return serialization.load_pem_private_key(pem_data.encode(), password=None)

    def rest_headers(self, method: str, path: str) -> dict:
        clean_path = path.split("?")[0]
        ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        message = (ts_ms + method.upper() + clean_path).encode()
        sig = self.private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "Content-Type": "application/json",
        }


# ─── API Client ─────────────────────────────────────────────────────────────
class KalshiClient:
    def __init__(self, auth):
        self.auth = auth
        self.session = requests.Session()

    def _request(self, method, path, quiet_404=False, **kwargs):
        url = API_BASE + path
        max_retries = 3
        resp = None
        for attempt in range(max_retries):
            hdrs = self.auth.rest_headers(method, path)
            try:
                resp = self.session.request(method, url, headers=hdrs, timeout=15, **kwargs)
                if resp.status_code == 429:
                    wait = 1.0 * (attempt + 1)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    if not (resp.status_code == 404 and quiet_404):
                        pass # avoid spam
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if resp is not None and resp.status_code == 404 and quiet_404:
                    raise e
                if attempt == max_retries - 1:
                    raise e
                time.sleep(1)
        return {}

    def get_market(self, ticker):
        return self._request("GET", f"/trade-api/v2/markets/{ticker}").get("market", {})

    def get_active_sol_market(self):
        res = self._request("GET", "/trade-api/v2/markets?status=open&series_ticker=KXSOL15M")
        markets = res.get("markets", [])
        if markets:
            markets.sort(key=lambda x: x.get("close_time", ""))
            return markets[0].get("ticker")
        return None

    def place_order(self, ticker, action, count, side, price_cents) -> str:
        client_oid = f"SOL-{action.upper()}-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        
        # Elections V2 always uses yes_price
        if side == "yes":
            yes_price = price_cents
        else:
            yes_price = 100 - price_cents
            
        body = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "type": "limit",
            "count": count,
            "yes_price": yes_price,
            "client_order_id": client_oid,
        }
        try:
            res = self._request("POST", "/trade-api/v2/portfolio/orders", json=body)
            return str(res.get("order", {}).get("order_id", ""))
        except Exception as e:
            log(f"[!] Order failed: {e}")
            return ""

    def get_order(self, order_id, quiet=False):
        return self._request("GET", f"/trade-api/v2/portfolio/orders/{order_id}", quiet_404=quiet).get("order", {})


# ─── Helpers ────────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def fmt_remaining(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}m{seconds % 60:02d}s"

def to_cents(val):
    try:
        if val is None or val == "": return 0
        f = float(val)
        if 0 < abs(f) < 1.0: return int(round(f * 100))
        return int(round(f))
    except: return 0


# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Kalshi SOL 15-Minute Dual Strategy Bot")
    parser.add_argument("--count", type=int, default=CONTRACT_COUNT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    log("==============================================================")
    log("  SOL DUAL-STRATEGY BOT  —  Starting")
    log("==============================================================")
    log(f"  STRATEGY A — Fast Momentum Lock")
    log(f"    Trigger : YES ask >= {A_TRIGGER}c")
    log(f"    Window  : {A_MIN_LEFT}-{A_MAX_LEFT} min left")
    log(f"  STRATEGY B — Mid-Market Fade")
    log(f"    Trigger : NO bid <= {B_TRIGGER}c")
    log(f"    Window  : {B_MIN_LEFT}-{B_MAX_LEFT} min left")
    log("==============================================================")

    auth   = KalshiAuth()
    client = KalshiClient(auth)

    if args.dry_run: log("⚠️ DRY RUN ENABLED")

    last_finished_ticker = None

    while True:
        ticker = client.get_active_sol_market()
        if not ticker:
            time.sleep(5); continue

        if ticker == last_finished_ticker:
            time.sleep(5); continue

        log(f"\n[🚀] New Market Cycle: {ticker}")

        filled_side = None
        cycle_count = 0

        while True:
            try:
                market = client.get_market(ticker)
                
                close_time_str = market.get("close_time", "")
                close_dt       = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                now_dt         = datetime.now(timezone.utc)
                time_remaining = (close_dt - now_dt).total_seconds()
                mins_left      = time_remaining / 60.0
                rem_str        = fmt_remaining(time_remaining)

                if market.get("status") not in ["open", "active"] or time_remaining <= 0:
                    log(f"Market {ticker} finished. Cycle complete.")
                    break

                # Get prices
                yes_ask = to_cents(market.get("yes_ask") or market.get("yes_ask_dollars"))
                no_bid  = to_cents(market.get("no_bid") or market.get("no_bid_dollars"))
                
                # Derive NO bid from YES ask if not provided
                if yes_ask > 0 and no_bid == 0:
                    no_bid = 100 - yes_ask

                # ── ENTRY LOGIC ──────────────────────────────────────────────
                if not filled_side:
                    triggered = False
                    
                    # Strategy A check
                    if A_MIN_LEFT <= mins_left <= A_MAX_LEFT and yes_ask >= A_TRIGGER:
                        maker_price = max(1, yes_ask - 1)
                        log(f"💥 STRATEGY A TRIGGERED! YES Ask={yes_ask}c | Mins={mins_left:.1f}")
                        log(f"🛒 Placing Maker YES Bid @ {maker_price}c")
                        if not args.dry_run:
                            client.place_order(ticker, "buy", args.count, "yes", maker_price)
                        filled_side = "A"
                        triggered = True

                    # Strategy B check
                    if not triggered and B_MIN_LEFT <= mins_left <= B_MAX_LEFT and no_bid > 0 and no_bid <= B_TRIGGER:
                        maker_price = max(1, no_bid - 1)
                        log(f"💥 STRATEGY B TRIGGERED! NO Bid={no_bid}c | Mins={mins_left:.1f}")
                        log(f"🛒 Placing Maker NO Bid @ {maker_price}c")
                        if not args.dry_run:
                            client.place_order(ticker, "buy", args.count, "no", maker_price)
                        filled_side = "B"
                        triggered = True

                # UI Feed (Heartbeat every 10 cycles = ~10s to avoid spam)
                if cycle_count % 10 == 0:
                    status_str = f"HOLDING ({filled_side})" if filled_side else "WATCHING"
                    print(f"\r[🔍] {ticker} | {status_str} | {rem_str} left | Y_Ask: {yes_ask} | N_Bid: {no_bid}      ", end="", flush=True)

                cycle_count += 1
                time.sleep(POLL_INTERVAL_S)

            except Exception as e:
                time.sleep(5)

        last_finished_ticker = ticker
        time.sleep(10)

if __name__ == "__main__":
    main()
