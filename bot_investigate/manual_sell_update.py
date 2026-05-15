import os, time, base64, requests, json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import uuid

def get_keys():
    with open("/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json") as f:
        vals = json.load(f).get("Values", {})
        return vals["KALSHI_API_KEY_ID"], vals["KALSHI_PRIVATE_KEY_PEM"]

API_KEY, PRIVATE_KEY = get_keys()

def sign_request(method, path):
    ts = str(int(time.time() * 1000))
    msg = ts + method + path
    pem = PRIVATE_KEY.replace("\\n", "\n").encode("utf-8")
    k = serialization.load_pem_private_key(pem, password=None)
    sig = k.sign(msg.encode("utf-8"), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    return {
        "KALSHI-ACCESS-KEY": API_KEY,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json"
    }

def kalshi_get(path, params=None):
    headers = sign_request("GET", path)
    resp = requests.get("https://api.elections.kalshi.com" + path, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()

def kalshi_delete(path):
    headers = sign_request("DELETE", path)
    resp = requests.delete("https://api.elections.kalshi.com" + path, headers=headers)
    resp.raise_for_status()
    return resp.json()

def kalshi_post(path, body):
    headers = sign_request("POST", path)
    resp = requests.post("https://api.elections.kalshi.com" + path, headers=headers, json=body)
    resp.raise_for_status()
    return resp.json()

SELL_PRICE_CENTS = 52

# Get positions
pos_data = kalshi_get("/trade-api/v2/portfolio/positions")
positions = pos_data.get("market_positions", [])
tennis_pos = [p for p in positions if ("KXATP" in p.get("ticker", "").upper() or "KXWTA" in p.get("ticker", "").upper()) and p.get("position", 0) != 0]

print(f"Found {len(tennis_pos)} active tennis positions.")

for p in tennis_pos:
    ticker = p.get("ticker")
    # Get resting orders for this ticker
    orders_data = kalshi_get("/trade-api/v2/portfolio/orders", {"status": "resting", "ticker": ticker})
    resting_orders = orders_data.get("orders", [])
    
    needs_sell = True
    for o in resting_orders:
        if o.get("action") == "sell":
            if o.get("yes_price") == SELL_PRICE_CENTS:
                print(f"[{ticker}] Already has a {SELL_PRICE_CENTS}c sell order.")
                needs_sell = False
            else:
                print(f"[{ticker}] Cancelling incorrect sell order at {o.get('yes_price')}c...")
                kalshi_delete(f"/trade-api/v2/portfolio/orders/{o.get('order_id')}")
                
    if needs_sell:
        print(f"[{ticker}] Placing new {SELL_PRICE_CENTS}c sell order...")
        body = {
            "ticker": ticker,
            "action": "sell",
            "side": "yes",
            "type": "limit",
            "count": p.get("position", 1),
            "yes_price": SELL_PRICE_CENTS,
            "client_order_id": str(uuid.uuid4())
        }
        try:
            kalshi_post("/trade-api/v2/portfolio/orders", body)
            print(f"[{ticker}] Successfully locked in at {SELL_PRICE_CENTS}c!")
        except Exception as e:
            print(f"[{ticker}] Failed to place sell order: {e}")

print("Done updating active positions.")
