import os
import json
import base64
import time
from datetime import datetime, timezone
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# --- CONFIGURATION ---
KALSHI_BASE = "https://api.elections.kalshi.com"

print("Loading credentials...")

def get_credentials():
    # If running locally, check local.settings.json
    local_settings_path = '/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json'
    if os.path.exists(local_settings_path):
        with open(local_settings_path) as f:
            settings = json.load(f).get("Values", {})
            return settings.get("KALSHI_API_KEY_ID"), settings.get("KALSHI_PRIVATE_KEY_PEM")
    
    # Otherwise check environment variables directly
    return os.environ.get("KALSHI_API_KEY_ID"), os.environ.get("KALSHI_PRIVATE_KEY_PEM")

API_KEY, PRIVATE_KEY_PEM = get_credentials()

if not API_KEY or not PRIVATE_KEY_PEM:
    print("ERROR: Could not find Kalshi credentials in local.settings.json or environment variables.")
    exit(1)

def sign_request(method: str, path: str) -> dict:
    pem_bytes = PRIVATE_KEY_PEM.replace('\\n', '\n').encode("utf-8")
    private_key = serialization.load_pem_private_key(pem_bytes, password=None)
    
    timestamp_ms = str(int(time.time() * 1000))
    msg = timestamp_ms + method + path
    
    signature = private_key.sign(
        msg.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    
    return {
        "KALSHI-ACCESS-KEY": API_KEY,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path: str, params: dict = None) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()

def kalshi_delete(path: str) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("DELETE", path)
    resp = requests.delete(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    print("Fetching active Kalshi portfolio orders...")
    try:
        orders_data = kalshi_get("/trade-api/v2/portfolio/orders", {"status": "resting"})
        orders = orders_data.get("orders", [])
        
        buy_orders = [o for o in orders if ("KXATP" in o.get("ticker", "").upper() or "KXWTA" in o.get("ticker", "").upper()) and o.get("action") == "buy"]
        
        if not buy_orders:
            print("No active tennis BUY orders found. The slate is already clean!")
        else:
            print(f"Found {len(buy_orders)} active resting BUY orders. Cancelling them now...")
            for o in buy_orders:
                order_id = o.get("order_id")
                ticker = o.get("ticker")
                try:
                    kalshi_delete(f"/trade-api/v2/portfolio/orders/{order_id}")
                    print(f"✅ Cancelled BUY order {order_id} for {ticker}")
                except Exception as e:
                    print(f"❌ Failed to cancel BUY order {order_id} for {ticker}: {e}")
                    
            print(f"\nAll resting BUY orders wiped. Ready for the new 70-cent strategy.")
            
    except Exception as e:
        print(f"Error fetching orders: {e}")
