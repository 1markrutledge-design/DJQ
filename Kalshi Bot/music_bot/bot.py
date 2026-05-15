#!/usr/bin/env python3
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
CULTURE_LIMIT = 1
EVENT_DIVERSITY_LIMIT = 15
POLL_INTERVAL_S = 900.0  # Run every 15 minutes

# Core parameters based on standard strategy
ENTRY_TRIGGER = 81       # Has to be > 80 cents to enter a trade
BUY_PRICE = 81           # Placed buy price EXACTLY at trigger to remain a generic Maker (prevent Taker fees)
STOP_LOSS_PRICE = 60     # Relaxed stop loss for 80c entries
CONTRACT_COUNT = 1       # Ensure only 1 contract per market
STABILITY_REQUIRED = 1   # Lowered to 1 so it doesn't have to wait 30 minutes (2 polls) to trigger

CULTURE_SERIES_PREFIXES = [
    # Daily / Weekly Streaming Markets
    "KXSPOTSTREAMSUSA", "KXSPOTSTREAMGLOBAL", "KXSPOTIFYD", 
    "KXSPOTIFYGLOBALD", "KXSPOTIFYARTISTD", "KXARTISTSTREAMS",
    # Billboard / Top Charts Markets
    "KXTOPSONG", "KXTOPALBUM", "KXRANKLISTSONGTOP10", 
    "KXBBCHARTPOSITIONSONG", "KXBBCHARTPOSITIONALBUM", "KXBBCHART",
    # Spotify Weekly Markets
    "KXSPOTIFYW", "KXSPOTIFYARTISTW", "KXSPOTIFYALBUMW",
    # Entertainment, Movies & Gaming
    "KXBOXOFFICE", "KXROTTEN", "KXGT", "KXMEDIA", "KXSHOW", 
    "KXACTOR", "KXPERFORM", "KXBOND", "KXGTAPRICE", "KXMEDIARELEASE",
    "KXMETACRITIC", "KXCOACHELLA", "KXGLASTONBURY", "KXGAMING",
    # Awards & Ceremonies
    "KXOSCARS", "KXGRAMMYS", "KXEMMYS", "KXTONYS", "KXSTRMRS",
    # Social Media & Trends
    "KXYOUTUBE", "KXTWITCH", "KXSTREAMER", "KXMRBEAST", "KXSPEED", 
    "KXKAICENAT", "KXX", "KXTAYLOR", "KXKELCE", "KXYTUBESUBS", 
    "KXTRAVISKELCE", "KXTAYLORSWIFT", "KXSWIFTKELCE", "KXTWITTER", "KXSTREAMS",
    "KXBILLBOARD", "KXSPOTSEASON", "KXSTREAMERS", "KXYTUBES", "KXYTUBE", "KXBB",
    "KXALBUMW", "KXSONGW"
]


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
                        if k.startswith("export "): k = k[7:]
                        k = k.strip()
                        if k not in os.environ:
                            os.environ[k] = v.strip().strip('"').strip("'")

    def _load_key(self):
        pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
        if not pem_data:
            path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")
            # See if the system parent directory has the general key (for DJQueue)
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

    def _sign(self, method: str, path: str) -> dict:
        """Build auth headers for a given method + path."""
        # UPDATED: Use clean path for signatures to match working btc_bot/v2 auth
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

class KalshiClient:
    def __init__(self, auth):
        self.auth = auth
        self.session = requests.Session()

    def _request(self, method, path, quiet_404=False, **kwargs):
        url = API_BASE + path
        max_retries = 3
        for attempt in range(max_retries):
            hdrs = self.auth._sign(method, path)
            try:
                resp = self.session.request(method, url, headers=hdrs, timeout=15, **kwargs)
                if resp.status_code == 429:
                    wait = 1.0 * (attempt + 1)
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    if not (resp.status_code == 404 and quiet_404):
                        log(f"[!] API Error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if resp.status_code == 404 and quiet_404: raise e
                if attempt == max_retries - 1: raise e
                time.sleep(1)
        return {}

    def get_music_markets(self):
        # Fetch targeted series to ensure 100% coverage even with 50,000+ open markets
        all_music = []
        for series in CULTURE_SERIES_PREFIXES:
            try:
                res = self._request("GET", f"/trade-api/v2/markets?status=open&series_ticker={series}")
                all_music.extend(res.get("markets", []))
            except: pass
        return all_music

    def place_order(self, ticker, action, count, side, price_cents) -> str:
        # Time-blocked ID to prevent double-betting within a 15-minute window
        window_idx = int(time.time() // 900)
        client_oid = f"MUS-{action[0].upper()}-{ticker}-{side[0].upper()}-{window_idx}"
        price_field = "yes_price" if side == "yes" else "no_price"
        body = {
            "ticker": ticker, "action": action, "side": side,
            "type": "limit", "count": count, price_field: price_cents,
            "client_order_id": client_oid,
        }
        res = self._request("POST", "/trade-api/v2/portfolio/orders", json=body)
        return str(res.get("order", {}).get("order_id", ""))

    def cancel_order(self, order_id):
        try:
            self._request("DELETE", f"/trade-api/v2/portfolio/orders/{order_id}", quiet_404=True)
            return True
        except: return False

    def get_order(self, order_id):
        return self._request("GET", f"/trade-api/v2/portfolio/orders/{order_id}", quiet_404=True).get("order", {})

    def get_market_position(self, ticker):
        try:
            res = self._request("GET", "/trade-api/v2/portfolio/positions", quiet_404=True)
            for p in res.get("market_positions", []):
                if p.get("ticker") == ticker:
                    pos_val = int(float(p.get("position_fp", "0")))
                    if pos_val == 0: return 0, None
                    return abs(pos_val), "yes" if pos_val > 0 else "no"
        except: pass
        return 0, None

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def main():
    parser = argparse.ArgumentParser(description="Kalshi Culture Scanner Trading Bot")
    parser.add_argument("--count", type=int, default=CONTRACT_COUNT, help="Number of contracts to trade")
    parser.add_argument("--dry-run", action="store_true", help="Don't place actual orders")
    args = parser.parse_args()

    count = args.count
    dry_run = args.dry_run

    log("Initializing Auth...")
    auth = KalshiAuth()
    client = KalshiClient(auth)

    if dry_run: log("DRY RUN ENABLED - No actual money will be risked.")
    log(f"Config: Trigger={ENTRY_TRIGGER}¢ | Buy={BUY_PRICE}¢ | StopLoss={STOP_LOSS_PRICE}¢ | Contracts={count}")

    # Track stability per ticker: { ticker: { 'yes': 0, 'no': 0, 'stop': 0 } }
    stability = {}
    
    while True:
        try:
            markets = client.get_music_markets()
            log(f"Scanning {len(markets)} active culture markets...")
            
            # 1. Fetch current resting orders for cap checks
            res_orders = client._request("GET", "/trade-api/v2/portfolio/orders?status=resting")
            resting_orders = res_orders.get("orders", []) if isinstance(res_orders, dict) else []

            # Group by Event Ticker
            events = {}
            for m in markets:
                ticker = m.get("ticker", "")
                evt = m.get("event_ticker")
                if not evt: evt = ticker
                if evt not in events: events[evt] = []
                events[evt].append(m)

            for evt_ticker, tier_markets in events.items():
                event_owned_tickers = []
                # Check what we own in this event
                for m in tier_markets:
                    ticker = m.get("ticker")
                    pos, pos_side = client.get_market_position(ticker)
                    if pos > 0:
                        event_owned_tickers.append({'m': m, 'pos': pos, 'side': pos_side})

                # -- STATE: HOLDING (Manage Stop-Loss) --
                for owned in event_owned_tickers:
                    m = owned['m']
                    ticker = m.get("ticker")
                    yes_bid = int(float(m["yes_bid_dollars"])*100) if m.get("yes_bid_dollars") else None
                    no_bid = int(float(m["no_bid_dollars"])*100) if m.get("no_bid_dollars") else None
                    monitor_price = yes_bid if owned['side'] == 'yes' else no_bid
                    
                    if ticker not in stability:
                        stability[ticker] = {'yes': 0, 'no': 0, 'stop': 0}
                    st = stability[ticker]

                    if monitor_price and monitor_price <= STOP_LOSS_PRICE:
                        st['stop'] += 1
                        if st['stop'] >= STABILITY_REQUIRED:
                            log(f"🛑 [{ticker}] STOP LOSS TRIGGERED at {monitor_price}¢.")
                            if not dry_run:
                                client.place_order(ticker, "sell", owned['pos'], owned['side'], 1)
                            st['stop'] = 0
                    else: st['stop'] = 0

                # -- STATE: WATCHING (Find candidates) --
                candidates = []
                # Tracking active tiers in this event
                event_resting_tickers = {o.get("ticker") for o in resting_orders if any(m.get("ticker") == o.get("ticker") for m in tier_markets)}
                current_active_tiers = {o['m']['ticker'] for o in event_owned_tickers} | event_resting_tickers

                for m in tier_markets:
                    ticker = m.get("ticker")
                    
                    # Ticker-Level Cap (Strictly 3 contracts total)
                    ticker_owned_count = next((o['pos'] for o in event_owned_tickers if o['m']['ticker'] == ticker), 0)
                    ticker_resting_count = len([o for o in resting_orders if o.get("ticker") == ticker and o.get("action") == "buy"])
                    if (ticker_owned_count + ticker_resting_count) >= CULTURE_LIMIT:
                        continue
                        
                    yes_bid = int(float(m["yes_bid_dollars"])*100) if m.get("yes_bid_dollars") else None
                    no_bid = int(float(m["no_bid_dollars"])*100) if m.get("no_bid_dollars") else None
                    
                    if ticker not in stability:
                        stability[ticker] = {'yes': 0, 'no': 0, 'stop': 0}
                    st = stability[ticker]

                    is_known = ticker in current_active_tiers
                    if yes_bid and yes_bid >= ENTRY_TRIGGER:
                        st['yes'] += 1
                        if st['yes'] >= STABILITY_REQUIRED:
                            diff = yes_bid - ENTRY_TRIGGER
                            candidates.append({"ticker": ticker, "side": "yes", "bid": yes_bid, "diff": diff, "is_known": is_known})
                    else: st['yes'] = 0
                    
                    if no_bid and no_bid >= ENTRY_TRIGGER:
                        st['no'] += 1
                        if st['no'] >= STABILITY_REQUIRED:
                            diff = no_bid - ENTRY_TRIGGER
                            candidates.append({"ticker": ticker, "side": "no", "bid": no_bid, "diff": diff, "is_known": is_known})
                    else: st['no'] = 0

                # Sort and Take (Diversity First)
                candidates.sort(key=lambda x: (not x['is_known'], x['diff']))
                
                to_trade = []
                loop_active_tiers = current_active_tiers.copy()
                for can in candidates:
                    if can["ticker"] not in loop_active_tiers:
                        if len(loop_active_tiers) < EVENT_DIVERSITY_LIMIT:
                            to_trade.append(can)
                            loop_active_tiers.add(can["ticker"])
                    else:
                        to_trade.append(can)

                for can in to_trade:
                    ticker = can["ticker"]
                    log(f"🚀 [{ticker}] MULTI-TIER CHOICE on {can['side'].upper()} at {can['bid']}¢.")
                    if not dry_run:
                        client.place_order(ticker, "buy", count, can["side"], BUY_PRICE)
                    stability[ticker]['yes'] = 0
                    stability[ticker]['no'] = 0

            time.sleep(POLL_INTERVAL_S)

        except Exception as e:
            log(f"Scan Loop Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
