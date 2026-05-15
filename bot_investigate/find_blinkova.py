import os
import json
import base64
import time
from datetime import datetime, timezone
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Load credentials
with open('/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json') as f:
    settings = json.load(f)["Values"]
    os.environ["KALSHI_API_KEY_ID"] = settings["KALSHI_API_KEY_ID"]
    os.environ["KALSHI_PRIVATE_KEY_PEM"] = settings["KALSHI_PRIVATE_KEY_PEM"]

KALSHI_BASE = "https://api.elections.kalshi.com"

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

def find_match():
    print("Searching for Blinkova vs Jovic...")
    known_tennis_series = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "KXMTENNIS", "TENNIS"]
    for series in known_tennis_series:
        cursor = None
        while True:
            params = {"limit": 200, "status": "open", "series_ticker": series}
            if cursor: params["cursor"] = cursor
            try:
                data = kalshi_get("/trade-api/v2/markets", params=params)
            except Exception as e:
                print(f"Error fetching {series}: {e}")
                break
                
            markets = data.get("markets", [])
            for m in markets:
                title = m.get("title", "")
                ticker = m.get("ticker", "")
                event_ticker = m.get("event_ticker", "")
                if "Blinkova" in title or "Jovic" in title or "Blinkova" in event_ticker or "Jovic" in event_ticker or "Blinkova" in ticker or "Jovic" in ticker:
                    print(f"\nFound Match! Series: {series}")
                    print(f"Title: {title}")
                    print(f"Ticker: {ticker}")
                    print(f"Close Time: {m.get('close_time')}")
                    print(f"Expected Expiration Time: {m.get('expected_expiration_time')}")
            
            cursor = data.get("cursor")
            if not cursor or not markets:
                break
    print("\nSearch complete.")

find_match()
