import requests
import os
import sys
from datetime import datetime, timezone
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE = "https://api.elections.kalshi.com"

# Load .env manually for this script
def load_env(env_path):
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env("/Users/markrutledge/Documents/DjQueue/Kalshi Bot/sol_bot/.env")

KEY_ID = os.environ.get("KALSHI_API_KEY_ID")
def get_private_key():
    path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/sol_bot/kalshi_private.pem"
    with open(path, "rb") as f:
        pem_data = f.read()
    return serialization.load_pem_private_key(pem_data, password=None)

private_key = get_private_key()

def rest_headers(method, path):
    clean_path = path.split("?")[0]
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (ts_ms + method.upper() + clean_path).encode()
    sig = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "Content-Type": "application/json",
    }

def get_market(ticker):
    path = f"/trade-api/v2/markets/{ticker}"
    headers = rest_headers("GET", path)
    r = requests.get(API_BASE + path, headers=headers)
    r.raise_for_status()
    return r.json()

def get_active_sol_market():
    path = "/trade-api/v2/markets?status=open&series_ticker=KXSOL15M"
    headers = rest_headers("GET", path)
    r = requests.get(API_BASE + path, headers=headers)
    r.raise_for_status()
    markets = r.json().get("markets", [])
    if markets:
        markets.sort(key=lambda x: x.get("close_time", ""))
        return markets[0].get("ticker")
    return None

if __name__ == "__main__":
    ticker = get_active_sol_market()
    if ticker:
        print(f"Ticker: {ticker}")
        m = get_market(ticker)
        import json
        print(json.dumps(m, indent=2))
    else:
        print("No active Solana markets found.")
