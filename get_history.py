import os
import time
import requests
import base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

KALSHI_BASE = "https://api.elections.kalshi.com"

def _load_private_key():
    pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM")
    if not pem_data:
        # try loading from Kalshi Bot/local.settings.json or similar?
        return None
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
    if not private_key: return {}
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    key_id = os.environ.get("KALSHI_API_KEY_ID", "").replace('"', "").strip()
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path: str, params=None) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    import json
    # Let's read local.settings.json from Kalshi Bot to get the keys
    try:
        with open("Kalshi Bot/local.settings.json") as f:
            settings = json.load(f)
            os.environ["KALSHI_PRIVATE_KEY_PEM"] = settings["Values"]["KALSHI_PRIVATE_KEY_PEM"]
            os.environ["KALSHI_API_KEY_ID"] = settings["Values"]["KALSHI_API_KEY_ID"]
    except Exception as e:
        print("Could not load local.settings.json:", e)
        exit(1)

    print("Fetching recent fills...")
    try:
        fills = kalshi_get("/trade-api/v2/portfolio/fills", {"limit": 20})
        for f in fills.get("fills", []):
            print(f["created_time"], f["action"], f["count"], f["yes_price"], f["ticker"])
    except Exception as e:
        print(e)
        
    print("\nFetching recent orders...")
    try:
        orders = kalshi_get("/trade-api/v2/portfolio/orders", {"limit": 20})
        for o in orders.get("orders", []):
            print(o["created_time"], o["action"], o["status"], o["yes_price"], o["ticker"])
    except Exception as e:
        print(e)
