"""
Kalshi Tennis Trading Bot — Azure Function (Python v2)
Timer Trigger: every 30 minutes (0 */30 * * * *)

Strategy:
  1. Scan Tennis markets for matches starting within 30 min
  2. If yes_ask >= 65¢ and not already tracked → place 1-share Buy Limit at 45¢
  3. On each run check fills — if 45¢ buy filled → place 99¢ Sell Limit
  4. Auto-cleanup: cancel stale 45¢ orders if match_start + 60 min has passed
"""

import os
import json
import time
import uuid
import logging
import base64
import hashlib
from datetime import datetime, timezone, timedelta

import azure.functions as func
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from azure.storage.blob import BlobServiceClient, ContainerClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KALSHI_BASE = "https://api.elections.kalshi.com"
BLOB_CONTAINER = "tennis-bot-state"
BLOB_NAME = "validated_targets.json"
BUY_PRICE_CENTS = 45        # maker buy limit
TIERED_SELLS = [52, 57, 62] # tiered exit targets
BUY_COUNT = 3               # number of shares to buy
MIN_BID_CENTS = 55          # minimum yes_bid to prove liquidity/favorite status
MAX_ASK_CENTS = 98          # maximum yes_ask to ensure market isn't fully closed/locked
MIN_MEAN_CENTS = 72         # minimum (bid+ask)/2 to guarantee true favorite probability
# SCAN_WINDOW_MINUTES = 30  # Deprecated: Exact match times are unavailable from Kalshi
# STALE_MINUTES = 60        # Deprecated: Using date-based cleanup instead

app = func.FunctionApp()

# ---------------------------------------------------------------------------
# RSA-PSS Signing (Kalshi v2 auth)
# ---------------------------------------------------------------------------

def _load_private_key():
    """Load the RSA private key from the KALSHI_PRIVATE_KEY_PEM env var with super-robust cleaning."""
    pem_data = os.environ["KALSHI_PRIVATE_KEY_PEM"]
    
    # 1. Clean basic noise
    pem_data = pem_data.replace('\\n', '\n').replace('"', '').strip()

    # 2. Handle 'One-Line' corruption (missing newlines after headers)
    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"
    
    if header in pem_data and "\n" not in pem_data[len(header):len(header)+10]:
        # If there's no newline shortly after the header, it's likely collapsed
        content = pem_data.replace(header, "").replace(footer, "").strip()
        # Restore with proper newlines
        pem_data = f"{header}\n{content}\n{footer}"
    elif header not in pem_data and "MIIE" in pem_data:
        # If headers are missing entirely but it looks like base64
        pem_data = f"{header}\n{pem_data}\n{footer}"

    try:
        return serialization.load_pem_private_key(pem_data.encode(), password=None)
    except Exception as e:
        logging.error("Failed to load private key. PEM starting with: %s", pem_data[:50])
        raise e


def sign_request(method: str, path: str) -> dict:
    """
    Build Kalshi v2 auth headers.

    Message = timestamp_ms + method + path  (path WITHOUT query params)
    Signature = RSA-PSS(SHA-256) → base64
    """
    # Strip query string from path
    clean_path = path.split("?")[0]

    timestamp_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (timestamp_ms + method.upper() + clean_path).encode()

    private_key = _load_private_key()
    logging.info("Signing message: [%s]", message.decode())
    
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    # Key ID cleanup
    key_id = os.environ["KALSHI_API_KEY_ID"].replace('"', "").strip()
    logging.info("Using Key ID: %s...%s", key_id[:5], key_id[-5:])

    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }


def kalshi_get(path: str, params: dict | None = None) -> dict:
    """Authenticated GET to Kalshi v2 API with rate-limit sleep."""
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    time.sleep(0.5)
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def kalshi_post(path: str, body: dict) -> dict:
    """Authenticated POST to Kalshi v2 API with rate-limit sleep."""
    url = KALSHI_BASE + path
    headers = sign_request("POST", path)
    time.sleep(0.5)
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def kalshi_delete(path: str) -> dict | None:
    """Authenticated DELETE to Kalshi v2 API with rate-limit sleep."""
    url = KALSHI_BASE + path
    headers = sign_request("DELETE", path)
    time.sleep(0.5)
    resp = requests.delete(url, headers=headers, timeout=30)
    resp.raise_for_status()
    if resp.content:
        return resp.json()
    return None


# ---------------------------------------------------------------------------
# Azure Blob Storage — State Management
# ---------------------------------------------------------------------------

def _get_container_client() -> ContainerClient:
    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container = blob_service.get_container_client(BLOB_CONTAINER)
    if not container.exists():
        container.create_container()
        logging.info("Created blob container: %s", BLOB_CONTAINER)
    return container


def load_state() -> dict:
    """Load state from blob storage. Returns empty dict if blob doesn't exist."""
    try:
        container = _get_container_client()
        blob = container.get_blob_client(BLOB_NAME)
        data = blob.download_blob().readall()
        state = json.loads(data)
        logging.info("Loaded state with %d tracked tickers", len(state))
        return state
    except Exception as exc:
        if "BlobNotFound" in str(exc) or "ResourceNotFound" in str(exc):
            logging.info("No existing state file — starting fresh")
            return {}
        raise


def save_state(state: dict) -> None:
    """Persist state dict to blob storage."""
    container = _get_container_client()
    blob = container.get_blob_client(BLOB_NAME)
    blob.upload_blob(json.dumps(state, indent=2), overwrite=True)
    logging.info("Saved state with %d tracked tickers", len(state))


# ---------------------------------------------------------------------------
# Market Scanning
# ---------------------------------------------------------------------------

def fetch_tennis_markets() -> list[dict]:
    """
    Fetch Tennis markets from Kalshi by targeting known tennis series tickers directly.
    Falls back to a capped full scan if targeted fetch returns nothing.
    """
    now = datetime.now(timezone.utc)
    # window_end is no longer used since we rely on date filtering

    # Known Kalshi tennis series tickers (ATP/WTA use KXATPMATCH, KXWTAMATCH etc.)
    TENNIS_SERIES_PREFIXES = ("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "TENNIS")

    def is_tennis(m: dict) -> bool:
        series = m.get("series_ticker", "").upper()
        event = m.get("event_ticker", "").upper()
        return any(series.startswith(p) or p in series or p in event for p in TENNIS_SERIES_PREFIXES)

    def get_match_start_time(m: dict) -> datetime | None:
        """Helper to extract and parse match start time."""
        time_str = m.get("expected_expiration_time") or m.get("close_time")
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def filter_tennis(markets: list[dict]) -> list[dict]:
        """Filter markets to PRE_EVENT open tennis markets within the time window."""
        results = []
        for m in markets:
            if not is_tennis(m) or m.get("result"):
                continue
            
            match_start = get_match_start_time(m)
            if not match_start:
                continue
                
            # EXECUTION GUARD: Only consider PRE_EVENT markets
            if now >= match_start:
                continue
                
            # Date check is now the primary filter handled in filter_tennis_in_window
            results.append(m)
        return results

    def filter_tennis_in_window(markets: list[dict]) -> list[dict]:
        """Return PRE_EVENT tennis markets for today's (or yesterday's) matchday.
        Kalshi close_time = tournament end date (useless for filtering).
        Instead filter by the YYMMMDD date embedded in the ticker, e.g. 26FEB23.
        MUST ALSO ENSURE MATCH IS PRE_EVENT."""
        valid_dates = {
            (now - timedelta(days=d)).strftime("%y%b%d").upper()
            for d in range(2)  # today and yesterday UTC
        }
        
        results = []
        for m in markets:
            if not is_tennis(m) or m.get("result"):
                continue
                
            if not any(d in m.get("ticker", "").upper() for d in valid_dates):
                continue
                
            # EXECUTION GUARD: Only consider PRE-ROUND markets 
            # Kalshi expiration marks the round start, blocking anything after morning matches begin
            match_start = get_match_start_time(m)
            if not match_start or now >= match_start:
                continue
                
            results.append(m)
            
        return results


    all_tennis = []

    # Step 1: Try known tennis series tickers directly (fast path)
    known_tennis_series = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "KXMTENNIS", "TENNIS"]
    for series in known_tennis_series:
        try:
            cursor = None
            while True:
                params = {"limit": 200, "status": "open", "series_ticker": series}
                if cursor:
                    params["cursor"] = cursor
                data = kalshi_get("/trade-api/v2/markets", params=params)
                markets = data.get("markets", [])
                all_tennis.extend(filter_tennis_in_window(markets))
                cursor = data.get("cursor")
                if not cursor or not markets:
                    break
        except Exception as exc:
            logging.warning("series_ticker=%s fetch failed: %s", series, exc)

    if all_tennis:
        logging.info("Targeted tennis fetch: %d targets in window", len(all_tennis))
        return all_tennis

    # Step 2: Fallback — capped full scan (max 10 pages = 2000 markets)
    logging.warning("Targeted fetch returned 0 — falling back to capped full scan (max 10 pages)")
    all_markets = []
    cursor = None
    for page_num in range(10):
        params = {"limit": 200, "status": "open"}
        if cursor:
            params["cursor"] = cursor
        try:
            data = kalshi_get("/trade-api/v2/markets", params=params)
        except Exception as exc:
            logging.error("Full scan page %d failed: %s", page_num, exc)
            break
        markets = data.get("markets", [])
        all_markets.extend(markets)
        cursor = data.get("cursor")
        if not cursor or not markets:
            break

    tennis_targets = filter_tennis(all_markets)
    logging.info(
        "Fallback scan: %d total markets, %d tennis targets in window",
        len(all_markets), len(tennis_targets),
    )
    return tennis_targets




# ---------------------------------------------------------------------------
# Order Helpers
# ---------------------------------------------------------------------------

def get_resting_orders() -> list[dict]:
    """Return all currently resting (working) orders on Kalshi."""
    data = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting", "limit": 1000})
    return data.get("orders", [])


def get_portfolio_orders(ticker: str) -> list[dict]:
    """Get all open orders for a specific ticker."""
    data = kalshi_get(
        "/trade-api/v2/portfolio/orders",
        params={"ticker": ticker, "status": "resting"},
    )
    return data.get("orders", [])


def get_fills(ticker: str | None = None) -> list[dict]:
    """Get recent fills, optionally filtered by ticker."""
    params = {"limit": 100}
    if ticker:
        params["ticker"] = ticker
    data = kalshi_get("/trade-api/v2/portfolio/fills", params=params)
    return data.get("fills", [])


def place_buy_order(ticker: str, price_cents: int) -> str | None:
    """
    Place a 1-share Buy Limit Order (maker).
    Returns the order_id as a string, or None on failure.
    """
    body = {
        "ticker": ticker,
        "action": "buy",
        "side": "yes",
        "type": "limit",
        "count": BUY_COUNT,
        "yes_price": price_cents,
        # Enforce a 1-minute distributed lock across all concurrent Azure workers:
        # If 3 workers fire at the same second, they generate the exact same ID, 
        # and Kalshi natively blocks the duplicates with a 409 Conflict.
        "client_order_id": f"92-{ticker}-buy-{int(time.time() // 60)}"
    }
    try:
        resp = kalshi_post("/trade-api/v2/portfolio/orders", body)
        order = resp.get("order", {})
        order_id = str(order.get("order_id", ""))
        logging.info(
            "BUY ORDER PLACED — ticker: %s, price: %d¢, order_id: %s",
            ticker,
            price_cents,
            order_id,
        )
        return order_id
    except requests.HTTPError as exc:
        logging.error("Failed to place buy order for %s: %s", ticker, exc)
        return None


def place_sell_order(ticker: str, price_cents: int, count: int = 1) -> str | None:
    """
    Place a Sell Limit Order (taker).
    Returns the order_id as a string, or None on failure.
    """
    body = {
        "ticker": ticker,
        "action": "sell",
        "side": "yes",
        "type": "limit",
        "count": count,
        "yes_price": price_cents,
        # Enforce a 1-minute distributed lock across all concurrent Azure workers:
        # If 3 workers fire at the same second, they generate the exact same ID, 
        # and Kalshi natively blocks the duplicates with a 409 Conflict.
        "client_order_id": f"92-{ticker}-sell-{price_cents}-{int(time.time() // 60)}"
    }
    try:
        resp = kalshi_post("/trade-api/v2/portfolio/orders", body)
        order = resp.get("order", {})
        order_id = str(order.get("order_id", ""))
        logging.info(
            "SELL ORDER PLACED — ticker: %s, price: %d¢, order_id: %s",
            ticker,
            price_cents,
            order_id,
        )
        return order_id
    except requests.HTTPError as exc:
        logging.error("Failed to place sell order for %s: %s", ticker, exc)
        return None


def cancel_order(order_id: str) -> bool:
    """Cancel a resting order by its ID."""
    try:
        kalshi_delete(f"/trade-api/v2/portfolio/orders/{order_id}")
        logging.info("ORDER CANCELLED — order_id: %s", order_id)
        return True
    except requests.HTTPError as exc:
        logging.error("Failed to cancel order %s: %s", order_id, exc)
        return False


# ---------------------------------------------------------------------------
# Core Bot Logic
# ---------------------------------------------------------------------------

def scan_and_target(state: dict) -> dict:
    """Step 1: Scan markets and place buy orders on new targets."""
    markets = fetch_tennis_markets()
    
    # NEW STRATEGY: Group markets by event to find the true single favorite
    # This prevents betting on both players in the same match if odds swing.
    events = {}
    for m in markets:
        event_tk = m.get("event_ticker")
        if not event_tk:
            continue
        if event_tk not in events:
            events[event_tk] = []
        events[event_tk].append(m)

    for event_tk, event_markets in events.items():
        # A standard tennis match should have 2 markets (Player A vs Player B)
        # We find the one with the highest Mean probability
        best_market = None
        best_mean = 0.0
        
        for m in event_markets:
            # Handle Kalshi's V2 API nomenclature updates where legacy 'yes_bid' might be deprecated soon
            ask_val = m.get("yes_ask_dollars") or (m.get("yes_ask", 0) / 100.0)
            bid_val = m.get("yes_bid_dollars") or (m.get("yes_bid", 0) / 100.0)
            
            if not ask_val or not bid_val:
                continue
                
            yes_ask = int(float(ask_val) * 100)
            yes_bid = int(float(bid_val) * 100)

            # 1. Floor condition
            if yes_bid <= MIN_BID_CENTS:
                continue
                
            # 2. Ceiling condition
            if yes_ask > MAX_ASK_CENTS:
                continue
                
            mean_price = (yes_bid + yes_ask) / 2.0
            
            # Find the strongest player in this specific match
            if mean_price > best_mean:
                best_mean = mean_price
                best_market = m
                
        # 3. True Probability Condition (Mean > 63)
        if best_market and best_mean > MIN_MEAN_CENTS:
            ticker = best_market["ticker"]
            
            # Double check we haven't already bet on the *other* player in this match
            # by seeing if any market from this event is already in our state
            already_bet_event = False
            for state_ticker in state:
                if state_ticker.startswith(event_tk):
                    already_bet_event = True
                    # Optional: Could add logging here for debugging
                    break
                    
            if already_bet_event:
                continue

            if ticker in state:
                logging.info("Ticker %s already tracked — skipping. Pre-Match Favorite identity persists.", ticker)
                continue

            ask_val = best_market.get("yes_ask_dollars") or (best_market.get("yes_ask", 0) / 100.0)
            bid_val = best_market.get("yes_bid_dollars") or (best_market.get("yes_bid", 0) / 100.0)
            best_bid_cents = int(float(bid_val) * 100)
            best_ask_cents = int(float(ask_val) * 100)

            logging.info(
                "TRUE FAVORITE FOUND IN EVENT %s — ticker: %s, bid: %d¢, ask: %d¢, mean: %.1f¢",
                event_tk,
                ticker,
                best_bid_cents,
                best_ask_cents,
                best_mean
            )

            # Store today's date instead of the unreliable exact match time
            close_time_str = datetime.now(timezone.utc).isoformat()

            order_id = place_buy_order(ticker, BUY_PRICE_CENTS)
            if order_id:
                state[ticker] = {
                    "order_id": order_id,
                    "match_start": close_time_str, # now stores when we placed it
                    "status": "pending_buy",
                }
                save_state(state) # IMMEDIATE SAVE to prevent amnesia

    return state


def check_fills_and_sell(state: dict) -> dict:
    """Step 2: Check if any pending buy orders have been filled, then place tiered sells."""
    pending_buys = {
        ticker: info
        for ticker, info in state.items()
        if info.get("status") == "pending_buy"
    }

    if not pending_buys:
        logging.info("No pending buy orders to check for fills")
        return state

    for ticker, info in pending_buys.items():
        try:
            ticker_fills = get_fills(ticker)
        except Exception as exc:
            logging.error("Failed to fetch fills for %s: %s", ticker, exc)
            continue
            
        # Count how many shares have actually filled for this buy order
        filled_count = sum(
            int(float(f.get("count_fp", 0) or f.get("count", 0)))
            for f in ticker_fills
            if f.get("action") == "buy" and f.get("order_id") == info["order_id"]
        )
        
        if filled_count == 0:
            continue

        logging.info("FILL DETECTED — ticker: %s, shares filled: %d", ticker, filled_count)

        try:
            existing_orders = get_portfolio_orders(ticker)
        except Exception as exc:
            logging.error("Failed to fetch resting orders for %s: %s", ticker, exc)
            continue
            
        existing_sells = {}
        for o in existing_orders:
            if o.get("action") == "sell":
                price_val = o.get("yes_price_dollars") or (o.get("yes_price", 0) / 100.0)
                price_cents = int(float(price_val) * 100)
                existing_sells[price_cents] = o
        
        if "sell_order_ids" not in state[ticker]:
            state[ticker]["sell_order_ids"] = []
            
        if "sell_targets_placed" not in state[ticker]:
            state[ticker]["sell_targets_placed"] = []
            
        # We need to ensure we have exactly one 1-share sell order for each tier 
        # up to the number of shares we currently own (filled_count).
        targets_to_place = TIERED_SELLS[:filled_count]
        
        placed_new = False
        for target_price in targets_to_place:
            if target_price in existing_sells:
                logging.info("Valid %d¢ sell order already resting for %s", target_price, ticker)
                if target_price not in state[ticker]["sell_targets_placed"]:
                    state[ticker]["sell_targets_placed"].append(target_price)
                    placed_new = True
                if str(existing_sells[target_price].get("order_id")) not in state[ticker]["sell_order_ids"]:
                    state[ticker]["sell_order_ids"].append(str(existing_sells[target_price].get("order_id")))
                    placed_new = True
                continue
                
            # If not resting, check if we already placed it (meaning it executed!)
            if target_price in state[ticker].get("sell_targets_placed", []):
                logging.info("Sell order for %d¢ was already placed and executed for %s", target_price, ticker)
                continue
                
            sell_order_id = place_sell_order(ticker, target_price, count=1)
            if sell_order_id:
                state[ticker]["sell_order_ids"].append(sell_order_id)
                state[ticker]["sell_targets_placed"].append(target_price)
                placed_new = True
                
        # If we reached our max buy count (3), mark as pending_sell to stop checking buy fills
        if filled_count >= BUY_COUNT:
            state[ticker]["status"] = "pending_sell"
            placed_new = True
            
        if placed_new:
            save_state(state) # IMMEDIATE SAVE

    return state


def auto_cleanup(state: dict) -> dict:
    """Step 3: Sync state with Kalshi and cancel stale orders.
    1. If a pending_buy order is NO LONGER resting on Kalshi (e.g. user manually cancelled it), remove it from state so we can re-buy.
    2. Cancel any pending_buy orders older than 2 days.
    """
    now = datetime.now(timezone.utc)
    tickers_to_remove = []

    # Fetch real resting orders to prevent ghost-tracking
    try:
        resting = get_resting_orders()
        resting_ids = {str(o.get("order_id")) for o in resting}
    except Exception as exc:
        logging.error("Failed to fetch resting orders for sync: %s", exc)
        resting_ids = None

    for ticker, info in state.items():
        if info.get("status") != "pending_buy":
            # For settled or pending_sell orders, we just want to remove them if they are too old (memory cleanup)
            placement_time_str = info.get("match_start", "")
            if not placement_time_str:
                continue

            try:
                placement_time = datetime.fromisoformat(
                    placement_time_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue
                
            deadline = placement_time + timedelta(days=2)
            if now > deadline:
                logging.info("MEMORY CLEANUP: Removing old %s ticker %s", info.get("status"), ticker)
                tickers_to_remove.append(ticker)
            continue

        # Sync check: If we successfully fetched resting IDs, and this order isn't resting anymore...
        if resting_ids is not None and str(info["order_id"]) not in resting_ids:
            # IMPORTANT: Prevent false-ghosting if it actually filled but check_fills_and_sell missed it due to rate limits
            try:
                fills = get_fills(ticker)
                filled_ids = {f.get("order_id") for f in fills if f.get("action") == "buy"}
                if str(info["order_id"]) in filled_ids:
                    logging.info("GHOST ORDER SYNC BYPASS — ticker: %s actually filled! Leaving as pending_buy so Step 2 can retry placing sell next minute.", ticker)
                    continue
            except Exception as exc:
                logging.error("Failed to verify ghost status fills for %s: %s", ticker, exc)
                continue # Safety skip
                
            logging.info("GHOST ORDER SYNC — ticker: %s is no longer resting and has no fills. Flagging as ghost.", ticker)
            state[ticker]["status"] = "ghost"
            continue

        placement_time_str = info.get("match_start", "")
        if not placement_time_str:
            continue

        try:
            placement_time = datetime.fromisoformat(
                placement_time_str.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            continue

        # Cancel orders older than 2 days (48 hours)
        deadline = placement_time + timedelta(days=2)
        if now > deadline:
            logging.info(
                "STALE ORDER (2-DAY EXPIRY) — ticker: %s, cancelling order_id: %s",
                ticker,
                str(info["order_id"]),
            )
            cancelled = cancel_order(str(info["order_id"]))
            if cancelled:
                tickers_to_remove.append(ticker)

    for ticker in tickers_to_remove:
        del state[ticker]
        logging.info("Removed stale ticker from state: %s", ticker)

    return state


def check_settled_markets(state: dict) -> dict:
    """Step 4: Clean up any settled markets from state."""
    for ticker, info in state.items():
        if info.get("status") not in ("pending_sell",):
            continue

        # Check if market has settled by looking at fills for sell-side
        fills = get_fills(ticker=ticker)
        sell_filled = any(
            f.get("action") == "sell"
            for f in fills
        )

        if sell_filled:
            logging.info(
                "SELL FILLED / SETTLED — ticker: %s, marking as settled to prevent re-betting",
                ticker,
            )
            # DO NOT DELETE FROM STATE! If we delete it, the bot will forget we bet on this match
            # and may bet on the opposing player later. We keep it as 'settled' for 2 days.
            info["status"] = "settled"

    return state


# ---------------------------------------------------------------------------
# Timer Trigger (every 1 minute)
# ---------------------------------------------------------------------------

@app.timer_trigger(
    schedule="0 */1 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def tennis_bot(timer: func.TimerRequest) -> None:
    """Main entry point — runs every 1 minute."""
    logging.info("=" * 60)
    logging.info("TENNIS BOT RUN STARTED at %s", datetime.now(timezone.utc).isoformat())
    logging.info("=" * 60)

    if timer.past_due:
        logging.warning("Timer is past due — running anyway")

    try:
        # Load persisted state
        state = load_state()

        # Step 1: Scan markets and place new buy orders
        state = scan_and_target(state)

        # Step 2: Check fills and place sell orders
        state = check_fills_and_sell(state)

        # Step 3: Auto-cleanup stale orders
        state = auto_cleanup(state)

        # Step 4: Clean up settled markets
        state = check_settled_markets(state)

        # Persist updated state
        save_state(state)

        logging.info("TENNIS BOT RUN COMPLETED — %d tickers tracked", len(state))

    except Exception:
        logging.exception("TENNIS BOT RUN FAILED")
        raise
