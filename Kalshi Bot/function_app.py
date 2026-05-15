"""
BTC Hourly Trading Bot (V1.0)
Strategy: Maker-First Proactive Bidding
1. Scan all KXBTCD (Bitcoin Hourly) strike tiers.
2. Place resting 80c 'YES' limit orders on every tier (Maker entries).
3. Monitor positions for 60c stop-loss (Emergency Exit).
4. Perform continuous account-aware audits to sync state and prevent overselling.
"""

import os
import json
import time
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
# Configuration (BTC Hourly Bot)
# ---------------------------------------------------------------------------
KALSHI_BASE = "https://api.elections.kalshi.com"
BLOB_CONTAINER = "btc-bot-state"
BLOB_NAME = "btc_hourly_state.json"
BTC_BLOB_NAME = "btc_hourly_state.json"
TARGET_EXIT_PRICE = None

# BTC Hourly Bot Strategy
BTC_HOURLY_SERIES = "KXBTCD"
BTC_BUY_THRESHOLD = 80
BTC_SELL_THRESHOLD = 60
BTC_TRADE_COUNT = 1

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


def kalshi_get(path: str, params: dict = None) -> dict:
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


def kalshi_delete(path: str) -> dict:
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


def load_state(blob_name: str = BLOB_NAME) -> dict:
    """Load state from blob storage. Returns empty dict if blob doesn't exist."""
    try:
        container = _get_container_client()
        blob = container.get_blob_client(blob_name)
        data = blob.download_blob().readall()
        state = json.loads(data)
        logging.info("Loaded state '%s' with %d tracked tickers", blob_name, len(state))
        return state
    except Exception as exc:
        if "BlobNotFound" in str(exc) or "ResourceNotFound" in str(exc):
            logging.info("No existing state file '%s' — starting fresh", blob_name)
            return {}
        raise


def save_state(state: dict, blob_name: str = BLOB_NAME) -> None:
    """Persist state dict to blob storage."""
    container = _get_container_client()
    blob = container.get_blob_client(blob_name)
    blob.upload_blob(json.dumps(state, indent=2), overwrite=True)
    logging.info("Saved state '%s' with %d tracked tickers", blob_name, len(state))


# ---------------------------------------------------------------------------
# Market Discovery
# ---------------------------------------------------------------------------

def fetch_btc_hourly_markets() -> list[dict]:
    """Fetch all open KXBTCD markets from Kalshi."""
    try:
        data = kalshi_get("/trade-api/v2/markets", params={"series_ticker": BTC_HOURLY_SERIES, "status": "open"})
        markets = data.get("markets", [])
        logging.info("BTC DISCOVERY: Found %d open hourly markets.", len(markets))
        return markets
    except Exception as exc:
        logging.error("Failed to fetch BTC hourly markets: %s", exc)
        return []


def btc_hourly_bot_logic(state: dict) -> dict:
    """
    Core logic for BTC Hourly Bot (Maker-First):
    1. Scan all KXBTCD strikes.
    2. Place 80c resting orders on all available strikes.
    3. Monitor filled positions for 60c stop-loss.
    """
    markets = fetch_btc_hourly_markets()
    
    # 1. Fetch current resting orders from state (populated by sync_portfolio_to_state)
    # This ensures we don't double-place
    
    for m in markets:
        ticker = m["ticker"]
        
        # Determine YES price
        yes_bid = m.get("yes_bid")
        if yes_bid is None and m.get("yes_bid_dollars") is not None:
            yes_bid = int(float(m["yes_bid_dollars"]) * 100)
        
        # Check current status
        has_position = state.get(ticker, {}).get("shares", 0) > 0
        has_resting_buy = state.get(ticker, {}).get("status") == "pending_buy"

        # PROACTIVE MAKER Logic: Place resting 80c bid on all tiers
        if not has_position and not has_resting_buy:
            logging.info("🎯 BTC MAKER ORDER: Placing resting 80¢ bid on %s", ticker)
            order_id = place_buy_order(ticker, BTC_BUY_THRESHOLD, count=BTC_TRADE_COUNT)
            if order_id:
                state[ticker] = {
                    "order_id": order_id,
                    "status": "pending_buy",
                    "shares": 0
                }

        # STOP LOSS Logic: If filled, monitor for 60c floor
        elif has_position and yes_bid is not None:
            if yes_bid <= BTC_SELL_THRESHOLD:
                logging.info("🛑 BTC STOP LOSS: %s at %d¢ (threshold %d¢)", ticker, yes_bid, BTC_SELL_THRESHOLD)
                shares = state[ticker].get("shares", 1)
                # Market sweep exit
                order_id = place_sell_order(ticker, 1, count=shares, is_emergency=True)
                if order_id:
                    state[ticker]["status"] = "pending_sell"
                    state[ticker]["sell_order_id"] = order_id

    return state


def get_market_pulse(ticker: str) -> dict:
    """Fetch the absolute latest orderbook for a specific ticker (Deep Pulse)."""
    try:
        data = kalshi_get(f"/trade-api/v2/markets/{ticker}")
        return data.get("market", {})
    except Exception as exc:
        logging.error("Pulse Failed for %s: %s", ticker, exc)
        return {}




# ---------------------------------------------------------------------------
# Order Helpers
# ---------------------------------------------------------------------------

def get_portfolio_orders(ticker: str) -> list[dict]:
    """Get all open orders for a specific ticker."""
    data = kalshi_get(
        "/trade-api/v2/portfolio/orders",
        params={"ticker": ticker, "status": "resting"},
    )
    return data.get("orders", [])


def get_fills(ticker: str = None) -> list[dict]:
    """Get recent fills, optionally filtered by ticker."""
    params = {"limit": 100}
    if ticker:
        params["ticker"] = ticker
    data = kalshi_get("/trade-api/v2/portfolio/fills", params=params)
    return data.get("fills", [])


def place_buy_order(ticker: str, price_cents: int, count: int = 7) -> str:
    """
    Place a Buy Limit Order (maker).
    Returns the order_id as a string, or None on failure.
    """
    # Removed Maker Protection to allow forced 80c entry as requested

    import uuid
    body = {
        "ticker": ticker,
        "action": "buy",
        "side": "yes",
        "type": "limit",
        "count": count,
        "yes_price": price_cents,
        "client_order_id": str(uuid.uuid4())
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
        err_body = ""
        try:
            err_body = f" | Body: {exc.response.text}"
        except: pass
        logging.error("Failed to place buy order for %s: %s%s", ticker, exc, err_body)
        return None


def place_sell_order(ticker: str, price_cents: int, count: int = 7, is_emergency: bool = False) -> str:
    """
    Place a Sell Limit Order (taker).
    If is_emergency, allow prices below 5c to ensure exit.
    """
    # MAKER PROTECTION: check current bid
    pulse = get_market_pulse(ticker)
    actual_bid = pulse.get("yes_bid")
    
    if actual_bid is not None and not is_emergency:
        # sit 1 cent above the current bid to ensure maker status
        # but ONLY if we aren't panicking (emergency exit)
        if price_cents <= actual_bid:
            price_cents = actual_bid + 1
            logging.info("Forcing MAKER sell at %d¢ for %s", price_cents, ticker)

        if price_cents < 5: # safety floor for standard sells
            logging.warning("Price too low for %s: %d", ticker, price_cents)
            return None
    
    if is_emergency:
        # Override floor and price for immediate exit
        price_cents = max(1, price_cents) # floor at 1 cent for API
        logging.warning("EMERGENCY EXIT for %s at %d¢ (%d shares)", ticker, price_cents, count)

    body = {
        "ticker": ticker,
        "action": "sell",
        "side": "yes",
        "type": "limit",
        "count": count,
        "yes_price": price_cents,
        "client_order_id": f"T-SELL-{int(time.time()*1000)}-{ticker[-32:]}"
    }
    try:
        resp = kalshi_post("/trade-api/v2/portfolio/orders", body)
        order = resp.get("order", {})
        order_id = str(order.get("order_id", ""))
        logging.info(
            "SELL ORDER PLACED — ticker: %s, price: %d¢, count: %d, order_id: %s",
            ticker,
            price_cents,
            count,
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

    return state


def sync_portfolio_to_state(state: dict, allowed_prefixes: tuple = ("KXBTCD",), target_exit_price: int = None) -> dict:
    """
    Account-Aware Audit:
    1. Fetches ALL positions and ALL resting orders from Kalshi.
    2. Updates state with actual shares owned for BTC strikes.
    3. Identifies and tracks resting buy orders to prevent double-bidding.
    """
    try:
        # Load reality from Kalshi
        logging.info("Step 0: Performing full Account-Aware Audit...")
        
        # 1. Fetch Positions
        resp_pos = kalshi_get("/trade-api/v2/portfolio/positions")
        pos_list = resp_pos if isinstance(resp_pos, list) else resp_pos.get("market_positions", [])
        
        # 2. Fetch ALL Resting Orders
        resp_ord = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting"})
        ord_list = resp_ord if isinstance(resp_ord, list) else resp_ord.get("orders", [])

        # Process Positions
        real_shares = {}
        for p in pos_list:
            ticker = p.get("ticker", "")
            if not ticker.startswith(allowed_prefixes): continue
            real_shares[ticker] = int(float(p.get("position_fp", 0)))

        # 2. Fetch ALL Resting Orders
        resp_ord = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting"})
        ord_list = resp_ord if isinstance(resp_ord, list) else resp_ord.get("orders", [])

        # Process Orders (Categorized by Ticker)
        resting_sells = {}
        resting_buys = {}
        for o in ord_list:
            ticker = o.get("ticker", "")
            if not ticker.startswith(allowed_prefixes): continue
            
            if o.get("action") == "sell":
                if ticker not in resting_sells: resting_sells[ticker] = []
                resting_sells[ticker].append(o)
            elif o.get("action") == "buy":
                if ticker not in resting_buys: resting_buys[ticker] = []
                resting_buys[ticker].append(o)

        # AUDIT Logic: Correct the bot's state and Kalshi's orders
        all_tracked_tickers = set(state.keys()) | set(real_shares.keys()) | set(resting_buys.keys())
        
        for ticker in all_tracked_tickers:
            if not ticker.startswith(allowed_prefixes): continue

            owned = real_shares.get(ticker, 0)
            sells = resting_sells.get(ticker, [])
            buys = resting_buys.get(ticker, [])
            total_committed = sum(int(s.get("count", 0)) for s in sells)
            
            # Update state memory
            if owned > 0:
                if ticker not in state:
                    state[ticker] = {"status": "pending_sell", "shares": owned, "match_start": datetime.now(timezone.utc).isoformat(), "is_real_start": False}
                else:
                    state[ticker]["shares"] = owned
                    if state[ticker].get("status") == "pending_buy":
                        state[ticker]["status"] = "pending_sell" # Flip to sell monitoring
            elif len(buys) > 0:
                # If we have a resting buy, ensure state knows it
                if ticker not in state:
                    state[ticker] = {"status": "pending_buy", "shares": 0, "order_id": str(buys[0]["order_id"])}
                else:
                    state[ticker]["status"] = "pending_buy"
                    state[ticker]["order_id"] = str(buys[0]["order_id"])

            # CORRECTIVE ACTION: Prevent Overselling or Price Drift
            if owned > 0 and target_exit_price is not None:
                # If we own shares but have the WRONG sell count or WRONG price
                wrong_price = any(int(s.get("yes_price", 0)) != target_exit_price for s in sells)
                
                if total_committed != owned or wrong_price:
                    logging.info("⚖️ AUDIT CORRECTION: Ticker %s owns %d, but has %d committed at various prices. Resetting to %d¢...", ticker, owned, total_committed, target_exit_price)
                    # Kill them all and start over for this ticker
                    for s in sells:
                        cancel_order(str(s["order_id"]))
                    # Place fresh precision order
                    new_id = place_sell_order(ticker, target_exit_price, count=owned)
                    if new_id: state[ticker]["sell_order_id"] = new_id
            
            elif owned == 0 and total_committed > 0:
                # GHOST ORDER/OVERSELL PROTECTION: If we own NOTHING but have a resting sell
                logging.warning("⚠️ SAFETY ALERT: Owning 0 shares of %s but found %d shares for sale. Cancelling orders to prevent NO position.", ticker, total_committed)
                for s in sells:
                    cancel_order(str(s["order_id"]))

        return state

    except Exception as e:
        logging.error("Failed full audit: %s", e)
        return state


    return state


def check_settled_markets(state: dict) -> dict:
    """Remove tickers from state that are no longer active in the portfolio."""
    # Logic to prune state can be added here if the sync isn't aggressive enough.
    return state


# ---------------------------------------------------------------------------
# BTC Hourly Timer Trigger (every 2 minutes)
# ---------------------------------------------------------------------------

@app.timer_trigger(
    schedule="0 * * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def btc_hourly_bot(timer: func.TimerRequest) -> None:
    """Bitcoin Hourly Bot — runs every 2 minutes."""
    try:
        # Load BTC Specific State
        state = load_state(BTC_BLOB_NAME)

        # Sync BTC Positions
        state = sync_portfolio_to_state(state, allowed_prefixes=(BTC_HOURLY_SERIES,), target_exit_price=None)

        # Principal Strategy: Scan KXBTCD and apply 80c rule
        state = btc_hourly_bot_logic(state)

        # Persist BTC State
        save_state(state, BTC_BLOB_NAME)

    except Exception as e:
        # EMERGENCY DIAGNOSTIC
        try:
            container = _get_container_client()
            err_blob = container.get_blob_client("final_crash.log")
            import traceback
            err_msg = f"TIME: {datetime.now(timezone.utc).isoformat()}\nERROR: {str(e)}\nTRACE: {traceback.format_exc()}"
            err_blob.upload_blob(err_msg, overwrite=True)
        except:
            pass
        logging.exception("BTC HOURLY BOT RUN FAILED")
        raise
