import os
import sys
import json
import base64
import time
from datetime import datetime
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

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
    timestamp_ms = str(int(datetime.now().timestamp() * 1000))
    message = (timestamp_ms + method.upper() + clean_path).encode()
    signature = _load_private_key().sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_API_KEY_ID"].replace('"', "").strip(),
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path: str, params=None) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()
try:
    for t in ["KXATPCHALLENGERMATCH-26FEB24FATMOR-MOR", "KXATPCHALLENGERMATCH-26FEB24FATMOR-FAT"]:
        try:
            m = kalshi_get(f"/trade-api/v2/markets/{t}")
            m = m.get("market")
            if not m:
                continue
            title = m.get("title", "")
            print(f"Match: {title}")
            print(f"Ticker: {m.get('ticker')}")
            print(f"Yes Bid: {m.get('yes_bid')}¢ | Yes Ask: {m.get('yes_ask')}¢")
            mean = (m.get('yes_bid', 0) + m.get('yes_ask', 0)) / 2
            print(f"Mean: {mean}¢")
            print(f"Close Time: {m.get('close_time')}")
            print(f"Expiration Time: {m.get('expected_expiration_time')}")
            print(f"Result: {m.get('result')}")
            print("-" * 30)
        except Exception as e:
            print(f"Failed to fetch {t}: {e}")
except Exception as e:
    print(f"Overall Error: {e}")
