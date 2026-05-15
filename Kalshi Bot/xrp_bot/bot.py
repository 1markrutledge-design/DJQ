#!/usr/bin/env python3
"""
Kalshi XRP 15-Minute "Late Sniper" Bot
=====================================
Strategy derived from data analysis (90% WR):
  1. Poll KXXRP15M markets every 1s.
  2. Only trade in the FINAL 5 minutes of the market.
  3. If YES or NO bid hits 80¢, immediately place a limit BUY at 81¢.
  4. Once filled, monitor position for stop-loss at 40¢.
"""

import os
import sys
import json
import time
import uuid
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

API_BASE         = "https://api.elections.kalshi.com"
POLL_INTERVAL_S  = 1.0       
TARGET_SERIES    = "KXXRP15M"

# High-Conviction Parameters from Analysis
ENTRY_TRIGGER   = 80       # Trigger at 80c
BUY_PRICE       = 81       # Aggressive limit bid
STOP_LOSS_PRICE = 40       # Safety floor
CONTRACT_COUNT  = 3        # Default sizing

WINDOW_MINUTES     = 5     # XRP Late Sniper window (Verified 90% WR)
FINAL_MINUTE_BAN   = 45    # Don't enter in the very last 45 seconds to avoid expiration gaps

# ─────────────────────────────────────────────────────────────────────────────
# Logging Ticker Logic (Status Bar)
# ─────────────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def status_ticker(ticker, current_window, time_left_sec, yes_bid, no_bid, state="WATCHING"):
    """Prints a self-overwriting status line to the terminal."""
    m, s = divmod(int(time_left_sec), 60)
    time_str = f"{m}m {s:02d}s"
    
    ticker_short = ticker[-20:]
    
    line = (
        f"[XRP] {ticker_short} | Time: {time_str} | "
        f"YES: {yes_bid or '??'}¢ | NO: {no_bid or '??'}¢ | State: {state}"
    )
    sys.stdout.write(f"\r{line}{' ' * 10}")
    sys.stdout.flush()

# ─────────────────────────────────────────────────────────────────────────────
# RSA-PSS Authentication
# ─────────────────────────────────────────────────────────────────────────────

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
            # Fallback to absolute or shared path if needed
            if not os.path.exists(path):
                alt_paths = [
                    os.path.join(os.path.dirname(os.path.dirname(__file__)), "kalshi_private.pem"),
                    os.path.join(os.path.dirname(os.path.dirname(__file__)), "eth_bot", "kalshi_private.pem")
                ]
                for ap in alt_paths:
                    if os.path.exists(ap):
                        path = ap
                        break
            
            if os.path.exists(path):
                with open(path, "rb") as f:
                    pem_data = f.read().decode()
            else:
                raise ValueError(f"Could not find Kalshi private key at {path}")

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

    def _sign(self, method: str, path: str) -> dict:
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

    def request(self, method: str, path: str, **kwargs) -> dict:
        url = API_BASE + path
        headers = self._sign(method, path)
        resp = self.session.request(method, url, headers=headers, timeout=12, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_active_markets(self) -> list[dict]:
        res = self.request("GET", f"/trade-api/v2/markets?status=open&series_ticker={TARGET_SERIES}")
        return res.get("markets", [])

# ─────────────────────────────────────────────────────────────────────────────
# Trading Engine
# ─────────────────────────────────────────────────────────────────────────────

def run_bot():
    client = KalshiClient()
    log("🚀 XRP LATE SNIPER STARTING...")
    log(f"Config: Window={WINDOW_MINUTES}m | Trigger={ENTRY_TRIGGER}¢ | Limit={BUY_PRICE}¢ | StopLoss={STOP_LOSS_PRICE}¢")
    
    current_market = None
    state          = "WATCHING"
    order_id       = None
    filled_side    = None

    while True:
        try:
            # 1. Market Discovery
            if not current_market:
                markets = client.get_active_markets()
                if not markets:
                    time.sleep(10); continue
                
                markets.sort(key=lambda x: x["close_time"])
                for m in markets:
                    close_dt = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
                    if close_dt > datetime.now(timezone.utc):
                        current_market = m
                        log(f"Targeting Market: {m['ticker']}")
                        state = "WATCHING"
                        break
                
                if not current_market:
                    time.sleep(10); continue

            # 2. Timing and Prices
            ticker   = current_market["ticker"]
            close_dt = datetime.fromisoformat(current_market["close_time"].replace("Z", "+00:00"))
            time_left = (close_dt - datetime.now(timezone.utc)).total_seconds()
            mins      = time_left / 60.0

            market_data = client.request("GET", f"/trade-api/v2/markets/{ticker}")["market"]
            
            yes_bid = market_data.get("yes_bid") or int(float(market_data.get("yes_bid_dollars", 0)) * 100)
            no_bid = market_data.get("no_bid") or int(float(market_data.get("no_bid_dollars", 0)) * 100)

            status_ticker(ticker, WINDOW_MINUTES, time_left, yes_bid, no_bid, state)

            if time_left <= 0:
                print(f"\nFinalized {ticker}. Moving to next...")
                current_market = None
                continue

            # 3. Strategy Logic
            
            # --- ENTERING (Sniper Logic) ---
            if state == "WATCHING":
                # ONLY ENTER IN FINAL WINDOW
                if mins > WINDOW_MINUTES:
                    time.sleep(POLL_INTERVAL_S); continue
                
                if time_left < FINAL_MINUTE_BAN:
                    time.sleep(POLL_INTERVAL_S); continue

                # Triggers
                side_to_buy = None
                if yes_bid and yes_bid >= ENTRY_TRIGGER:
                    side_to_buy = "yes"
                elif no_bid and no_bid >= ENTRY_TRIGGER:
                    side_to_buy = "no"

                if side_to_buy:
                    log(f"🔥 LATE SNIPER TRIGGER! {side_to_buy.upper()} at {yes_bid if side_to_buy=='yes' else no_bid}¢")
                    
                    body = {
                        "ticker": ticker,
                        "action": "buy",
                        "side": side_to_buy,
                        "type": "limit",
                        "count": CONTRACT_COUNT,
                        "yes_price" if side_to_buy == "yes" else "no_price": BUY_PRICE,
                        "client_order_id": f"XRP-{int(time.time())}-{uuid.uuid4().hex[:6]}"
                    }
                    
                    try:
                        res = client.request("POST", "/trade-api/v2/portfolio/orders", json=body)
                        order_id = res.get("order", {}).get("order_id")
                        filled_side = side_to_buy
                        state = "ENTERED"
                        log(f"SNIPER ORDER PLACED: {order_id} | {side_to_buy.upper()} @ {BUY_PRICE}¢")
                    except Exception as e:
                        log(f"Sniper order failed: {e}")

            # --- MONITORING / STOP LOSS ---
            elif state == "ENTERED":
                current_val = yes_bid if filled_side == "yes" else no_bid
                
                if current_val and current_val <= STOP_LOSS_PRICE:
                    log(f"🛑 STOP LOSS HIT! Value={current_val}¢")
                    
                    sell_body = {
                        "ticker": ticker,
                        "action": "sell",
                        "side": filled_side,
                        "type": "limit",
                        "count": CONTRACT_COUNT,
                        "yes_price" if filled_side == "yes" else "no_price": 1, # Sweep exit
                        "client_order_id": f"XRP-SL-{int(time.time())}"
                    }
                    try:
                        client.request("POST", "/trade-api/v2/portfolio/orders", json=sell_body)
                        log("Emergency Exit Order Posted.")
                        state = "EXITED"
                        current_market = None 
                    except Exception as e:
                        log(f"Exit failed: {e}")
            
            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            log(f"Error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\nBot stopped.")
