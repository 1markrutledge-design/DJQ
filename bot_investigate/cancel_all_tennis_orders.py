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

# Temp set for the auth functions
os.environ["KALSHI_API_KEY_ID"] = API_KEY
os.environ["KALSHI_PRIVATE_KEY_PEM"] = PRIVATE_KEY_PEM

# --- KALSHI AUTH FUNCTIONS ---
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

def kalshi_get(path: str, params=None) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    time.sleep(0.5)
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def kalshi_delete(path: str) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("DELETE", path)
    time.sleep(0.5)
    resp = requests.delete(url, headers=headers, timeout=30)
    resp.raise_for_status()
    if resp.content: return resp.json()
    return None

# --- MAIN LOGIC ---

TENNIS_PREFIXES = ("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "KXMTENNIS", "TENNIS")

def is_tennis_ticker(ticker: str) -> bool:
    ticker_upper = ticker.upper()
    return any(p in ticker_upper for p in TENNIS_PREFIXES)

print("\nFetching all resting orders...")

try:
    data = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting"})
    all_orders = data.get("orders", [])
    
    tennis_orders = [o for o in all_orders if is_tennis_ticker(o.get("ticker", ""))]
    
    print(f"Found {len(all_orders)} total resting orders.")
    print(f"Found {len(tennis_orders)} TENNIS resting orders to cancel.")
    
    if len(tennis_orders) == 0:
        print("No tennis orders to cancel.")
        exit(0)
        
    print("\nCancelling orders...")
    success_count = 0
    fail_count = 0
    
    for o in tennis_orders:
        ticker = o.get("ticker")
        order_id = o.get("order_id")
        action = o.get("action")
        price = o.get("yes_price")
        
        print(f"Cancelling {action.upper()} for {ticker} at {price}¢ (ID: {order_id})...")
        try:
            kalshi_delete(f"/trade-api/v2/portfolio/orders/{order_id}")
            success_count += 1
            print("  -> Success")
        except Exception as e:
            fail_count += 1
            print(f"  -> Failed: {e}")
            
    print(f"\nCompleted. Successfully cancelled {success_count} orders. Failed: {fail_count}.")

except Exception as e:
    print(f"An error occurred: {e}")
