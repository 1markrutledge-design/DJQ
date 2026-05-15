#!/usr/bin/env python3
import os
import sys
import json
import requests
import base64
import time
import csv
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# --- CONFIGURATION ---
# We focus on the main ATP and WTA match series
TARGET_SERIES = ["KXATPMATCH", "KXWTAMATCH"]

API_BASE = "https://api.elections.kalshi.com"
POLL_INTERVAL = 10  # Seconds
DATA_FILE = "tennis_market_history.csv"
SETTINGS_PATH = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"

# --- AUTHENTICATION ---
class KalshiAuth:
    def __init__(self):
        try:
            with open(SETTINGS_PATH) as f:
                settings = json.load(f)
                values = settings.get('Values', settings)
                self.key_id = values.get("KALSHI_API_KEY_ID")
                pem_data = values.get("KALSHI_PRIVATE_KEY_PEM", "").replace('\\n', '\n')
                self.private_key = serialization.load_pem_private_key(pem_data.encode(), password=None)
        except Exception as e:
            print(f"Error loading auth: {e}")
            sys.exit(1)

    def sign(self, method: str, path: str) -> dict:
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

auth = KalshiAuth()

def kalshi_get(path, params=None):
    url = API_BASE + path
    headers = auth.sign("GET", path)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # Silently handle common 404s for extremely new/old markets
        return None

# --- DATA COLLECTION ---

def get_live_tennis_markets():
    """Finds open tennis markets starting within 24 hours (or already started)."""
    all_markets = []
    now = datetime.now(timezone.utc)
    lookahead = now + timedelta(hours=24)

    for series in TARGET_SERIES:
        cursor = None
        while True:
            params = {"status": "open", "series_ticker": series, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = kalshi_get("/trade-api/v2/markets", params)
            if not data:
                break
            batch = data.get("markets", [])
            
            # Filter for "live" or soon-to-be live matches
            for m in batch:
                occ_str = m.get("occurrence_datetime")
                if occ_str:
                    try:
                        occ_dt = datetime.fromisoformat(occ_str.replace("Z", "+00:00"))
                        # Match started in past OR starts within next 24 hours
                        if occ_dt <= lookahead:
                            all_markets.append(m)
                    except ValueError:
                        all_markets.append(m) # Default to include if date parsing fails
                else:
                    all_markets.append(m) # Include if no occurrence date (unlikely for matches)

            cursor = data.get("cursor")
            if not cursor or not batch:
                break
    return all_markets

def save_to_csv(data):
    file_exists = os.path.isfile(DATA_FILE)
    fieldnames = ["timestamp", "ticker", "player", "occurrence_time", "yes_bid", "yes_ask", "last_price", "delta", "result", "title"]
    with open(DATA_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        # Filter data to only include valid fieldnames
        row = {k: v for k, v in data.items() if k in fieldnames}
        writer.writerow(row)

def get_cents(m, key):
    """Robust price extraction — handles both integer cents and dollar floats."""
    val = m.get(key)
    if val is not None:
        try: return int(val)
        except: pass
    val_dollars = m.get(f"{key}_dollars")
    if val_dollars is not None:
        try: return int(round(float(val_dollars) * 100))
        except: pass
    return 0

def main():
    print(f"🎾 Starting Tennis Market Data Collector (Polling every {POLL_INTERVAL}s)")
    print(f"📁 Data File: {os.path.abspath(DATA_FILE)}")
    print(f"📡 Tracking series: {', '.join(TARGET_SERIES)}")
    print(f"⏰ Filter: Matches starting within 24h or already live")

    price_memory       = {}  # ticker -> last_price
    pending_settlements = {}  # ticker -> close_time_str

    while True:
        try:
            start_time = time.time()
            markets = get_live_tennis_markets()
            logged = 0

            # ── 1. Log prices for every open live market ──────────────────
            for m in markets:
                ticker    = m["ticker"]
                occ_str   = m.get("occurrence_datetime") or ""
                player    = m.get("yes_sub_title") or ""
                
                bid  = get_cents(m, "yes_bid")
                ask  = get_cents(m, "yes_ask")
                last = get_cents(m, "last_price")

                # Delta vs previous poll
                prev_last = price_memory.get(ticker)
                if prev_last is None:
                    print(f"✨ [NEW MARKET] {ticker} ({player})")
                
                delta = (last - prev_last) if (prev_last is not None and last) else 0
                price_memory[ticker] = last

                entry = {
                    "timestamp":       datetime.now(timezone.utc).isoformat(),
                    "ticker":          ticker,
                    "player":          player,
                    "occurrence_time": occ_str,
                    "yes_bid":         bid,
                    "yes_ask":         ask,
                    "last_price":      last,
                    "delta":           delta,
                    "result":          "",
                    "title":           m.get("title", ""),
                }
                save_to_csv(entry)
                logged += 1

                # Queue for settlement check
                close_str = m.get("close_time") or m.get("expected_expiration_time") or ""
                if close_str:
                    pending_settlements[ticker] = close_str

                # Terminal output (only show markets with live prices to reduce noise)
                if bid or ask or last:
                    delta_str = f"(+{delta})" if delta > 0 else (f"({delta})" if delta < 0 else "(--)")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {ticker[-15:]:>15} "
                          f"| {player[:12]:<12} | Bid:{bid:>3}c Ask:{ask:>3}c Last:{last:>3}c {delta_str}")

            print(f"  → {logged} live tennis markets logged | "
                  f"{len(pending_settlements)} pending settlement | "
                  f"elapsed {time.time()-start_time:.1f}s")

            # ── 2. Check settled markets ──────────────────────────────────
            now = datetime.now(timezone.utc)
            to_remove = []
            for ticker, close_time_str in list(pending_settlements.items()):
                if not close_time_str:
                    continue
                try:
                    close_dt = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                    # Check 1 minute after close time
                    if now > (close_dt + timedelta(seconds=60)):
                        m_data = kalshi_get(f"/trade-api/v2/markets/{ticker}")
                        if m_data and m_data.get("market"):
                            res = m_data["market"].get("result")
                            if res:
                                print(f"✅ [SETTLED] {ticker} | Result: {res.upper()}")
                                save_to_csv({
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "ticker":    ticker,
                                    "result":    res.upper(),
                                    "title":     f"FINAL_RESULT: {ticker}",
                                })
                                to_remove.append(ticker)
                except Exception:
                    pass

            for ticker in to_remove:
                pending_settlements.pop(ticker, None)

            # ── 3. Sleep for remainder of polling window ──────────────────
            elapsed = time.time() - start_time
            sleep_for = max(0, POLL_INTERVAL - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

        except KeyboardInterrupt:
            print("\n👋 Stopping collector...")
            break
        except Exception as e:
            print(f"⚠️  Loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
