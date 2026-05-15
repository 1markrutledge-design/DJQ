import os
import time
import logging
import base64
import uuid
import azure.functions as func
import requests
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

app = func.FunctionApp()

KALSHI_BASE = "https://api.elections.kalshi.com"

# --- CULTURE BOT CONFIGURATION ---
ENTRY_TRIGGER = 81       # Reverted: Entry trigger at 81¢
BUY_PRICE = 81           # Reverted: Place generic maker orders at 81¢
STOP_LOSS_PRICE = 60     # Stop-loss logic is currently DISABLED below
CONTRACT_COUNT = 1       # Ensure only 1 contract per market
CULTURE_LIMIT = 1        # REFINED: Strictly 1 contract per ticker
EVENT_DIVERSITY_LIMIT = 15 # 15 unique strike prices per event series

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
    "KXBBCHART", "KXSPOTSTREAMS", "KXBILLBOARD", "KXSPOTSEASON", "KXSTREAMERS",
    "KXMETACRITIC", "KXROTTEN", "KXGTAPRICE", "KXYTUBES", "KXYTUBE", "KXBB",
    "KXSPOTIFYW", "KXSPOTIFYARTISTW", "KXSPOTIFYALBUMW", "KXALBUMW", "KXSONGW"
]

def _load_private_key():
    pem_data = os.environ["KALSHI_PRIVATE_KEY_PEM"]
    pem_data = pem_data.replace('\\n', '\n').replace('"', '').strip()
    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"
    
    if header in pem_data and "\n" not in pem_data[len(header):len(header)+10]:
        content = pem_data.replace(header, "").replace(footer, "").strip()
        pem_data = f"{header}\n{content}\n{footer}"
    elif header not in pem_data and "MIIE" in pem_data:
        pem_data = f"{header}\n{pem_data}\n{footer}"

    return serialization.load_pem_private_key(pem_data.encode(), password=None)

def sign_request(method: str, path: str) -> dict:
    # UPDATED: Use clean path for signatures to match working btc_bot/v2 auth
    clean_path = path.split("?")[0]
    timestamp_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (timestamp_ms + method.upper() + clean_path).encode()
    private_key = _load_private_key()
    
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )

    key_id = os.environ["KALSHI_API_KEY_ID"].replace('"', "").strip()
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path: str, params: dict = None) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    time.sleep(0.5)
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def kalshi_post(path: str, body: dict) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("POST", path)
    time.sleep(0.5)
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()

def get_portfolio_state():
    try:
        pos_resp = kalshi_get("/trade-api/v2/portfolio/positions")
        positions = pos_resp.get("market_positions", [])
        
        ord_resp = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting"})
        orders = ord_resp.get("orders", []) if isinstance(ord_resp, dict) else []
        
        return positions, orders
    except Exception as e:
        logging.error(f"Failed to fetch portfolio state: {e}")
        return None, None

def get_active_culture_markets():
    all_markets = []
    
    for series in CULTURE_SERIES_PREFIXES:
        try:
            # Targeted API fetching cuts latency by 90% and ensures 100% accurate scans
            resp = kalshi_get("/trade-api/v2/markets", params={"series_ticker": series, "status": "open"})
            markets = resp.get("markets", [])
            all_markets.extend(markets)
        except Exception as e:
            logging.error(f"Error fetching specific series {series}: {e}")

    return all_markets

def execute_culture_trade_logic():
    positions, resting_orders = get_portfolio_state()
    if positions is None or resting_orders is None:
        logging.error("⛔ ABORTING: Could not fetch portfolio state. Preventing potentially unsafe trades.")
        return

    owned_positions = {}
    resting_tickers = set()
    
    # 1. Track owned positions (filled)
    for p in positions:
        pos_val = int(float(p.get("position_fp", 0)))
        if pos_val != 0:
            side = "yes" if pos_val > 0 else "no"
            owned_positions[p.get("ticker")] = {"count": abs(pos_val), "side": side}

    # 2. Track RESTING orders to prevent duplicate buying
    for o in resting_orders:
        if o.get("action") == "buy":
            resting_tickers.add(o.get("ticker"))

    markets = get_active_culture_markets()
    logging.info(f"Scanned {len(markets)} active culture markets.")

    events = {}
    for m in markets:
        ticker = m.get("ticker", "")
        evt = m.get("event_ticker")
        if not evt: evt = ticker
        if evt not in events: events[evt] = []
        events[evt].append(m)

    for evt_ticker, tier_markets in events.items():
        # 1. Identified markets already owned in this event
        event_owned_tickers = [m for m in tier_markets if m.get("ticker") in owned_positions]
        
        # 2. Count UNIQUE tiers that have a resting buy already
        event_resting_unique_tickers = {m.get("ticker") for m in tier_markets if m.get("ticker") in resting_tickers}
        
        # 3. Combined Unique "Active" Tiers (Goal: Max 3)
        active_tiers_count = len(set([m.get("ticker") for m in event_owned_tickers]) | event_resting_unique_tickers)

        # --- STOP LOSS LOGIC DISABLED per user request ---
        # monitor_price = yes_bid if pos_info["side"] == "yes" else no_bid
        # if monitor_price is not None and monitor_price <= STOP_LOSS_PRICE:
        #     ... logic to sell ...
        pass

        # -- STATE: WATCHING (Find potential tiers up to Event Diversity limit of 3) --
        candidates = []
        for m in tier_markets:
            ticker = m.get("ticker")
            
            # Check Ticker-Level Cap (Strictly 3 contracts total per ticker)
            ticker_owned_count = owned_positions.get(ticker, {}).get("count", 0)
            ticker_resting_count = len([o for o in resting_orders if o.get("ticker") == ticker and o.get("action") == "buy"])
            if (ticker_owned_count + ticker_resting_count) >= CULTURE_LIMIT:
                continue # At 3-order cap for this specific ticker
                
            yes_bid = m.get("yes_bid")
            no_bid = m.get("no_bid")
            if yes_bid is None and m.get("yes_bid_dollars") is not None:
                yes_bid = int(float(m["yes_bid_dollars"]) * 100)
            if no_bid is None and m.get("no_bid_dollars") is not None:
                no_bid = int(float(m["no_bid_dollars"]) * 100)

            if yes_bid is not None and yes_bid >= ENTRY_TRIGGER:
                diff = yes_bid - ENTRY_TRIGGER
                candidates.append({"ticker": ticker, "side": "yes", "bid": yes_bid, "diff": diff, "price_key": "yes_price", "is_known": (ticker in event_owned_tickers or ticker in event_resting_unique_tickers)})

            if no_bid is not None and no_bid >= ENTRY_TRIGGER:
                diff = no_bid - ENTRY_TRIGGER
                candidates.append({"ticker": ticker, "side": "no", "bid": no_bid, "diff": diff, "price_key": "no_price", "is_known": (ticker in event_owned_tickers or ticker in event_resting_unique_tickers)})

        # Sort: Favor tiers we AREN'T in yet to maximize diversity, then by price efficiency
        candidates.sort(key=lambda x: (not x['is_known'], x['diff']))
        
        # Take candidates that don't violate the Event Diversity (Max 3 Unique Tiers)
        to_trade = []
        current_active_tiers = set([m.get("ticker") for m in event_owned_tickers]) | event_resting_unique_tickers
        
        for can in candidates:
            # If we aren't in this tier yet, check if we have room for a new tier
            if can["ticker"] not in current_active_tiers:
                if len(current_active_tiers) < EVENT_DIVERSITY_LIMIT:
                    to_trade.append(can)
                    current_active_tiers.add(can["ticker"])
            else:
                # We are already in this tier, and we already passed the Ticker-Level cap check above
                to_trade.append(can)

        for can in to_trade:
            ticker = can["ticker"]
            side = can["side"]
            bid = can["bid"]
            key = can["price_key"]
            
            # 1. Determine how many more contracts we need to hit the limit of 3
            owned_cnt = owned_positions.get(ticker, {}).get("count", 0)
            rest_cnt = len([o for o in resting_orders if o.get("ticker") == ticker and o.get("action") == "buy"])
            needed = CULTURE_LIMIT - (owned_cnt + rest_cnt)
            
            if needed <= 0:
                continue

            logging.info(f"🚀 MULTI-TIER CHOICE: {ticker} on {side.upper()} at {bid}¢. (Need {needed} more to hit {CULTURE_LIMIT})")
            
            # 2. Place each contract with a unique sequence index to avoid 409 Conflicts
            for i in range(needed):
                # Start sequence index from the current total + 1
                seq_idx = owned_cnt + rest_cnt + i + 1
                unique_sid = f"MUS-B-{ticker}-{side}-{int(time.time() // 900)}-{seq_idx}"
                
                try:
                    kalshi_post("/trade-api/v2/portfolio/orders", {
                        "ticker": ticker, "action": "buy", "side": side, "type": "limit",
                        "count": CONTRACT_COUNT, key: BUY_PRICE,
                        "client_order_id": unique_sid
                    })
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 409:
                        logging.info(f"🛡️ SAFETY: Sequence ID {unique_sid} already exists. Skipping.")
                    else:
                        logging.error(f"Buy failed for {ticker} (idx {seq_idx}): {e}")
                except Exception as e:
                    logging.error(f"Buy failed for {ticker} (idx {seq_idx}): {e}")

@app.timer_trigger(schedule="0 */15 * * * *", arg_name="myTimer", run_name="culture_bot_timer")
def culture_bot_timer(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")
    
    logging.info("Culture Bot Timer Trigger Fired!")
    try:
        execute_culture_trade_logic()
    except Exception as e:
        logging.error(f"Culture Bot execution failed completely: {e}")
        raise
