import urllib.request
import json
import base64
import os
import sys
import time
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:
    print("cryptography module not found")
    sys.exit(1)

KALSHI_BASE = "https://api.elections.kalshi.com"

def _load_private_key():
    try:
        with open(".env.local") as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
    except Exception as e:
        print("Could not load .env.local:", e)
        return None

    pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    pem_data = pem_data.replace('\\n', '\n').replace('"', '').strip()
    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"
    if header in pem_data and "\n" not in pem_data[len(header):len(header)+10]:
        content = pem_data.replace(header, "").replace(footer, "").strip()
        pem_data = f"{header}\n{content}\n{footer}"
    elif header not in pem_data and "MIIE" in pem_data:
        pem_data = f"{header}\n{pem_data}\n{footer}"
    if not pem_data: return None
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

def kalshi_get(path: str) -> dict:
    url = KALSHI_BASE + path
    headers = sign_request("GET", path)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.read().decode()}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        print("Fetching portfolio fills...")
        fills = kalshi_get("/trade-api/v2/portfolio/fills?limit=20")
        for f in fills.get("fills", []):
            print("FILL:", f.get("created_time"), f.get("action"), f.get("count"), f.get("yes_price"), f.get("ticker"))
            
        print("---")
        print("Fetching portfolio settlements...")
        settle = kalshi_get("/trade-api/v2/portfolio/settlements?limit=20")
        for s in settle.get("settlements", []):
            print("SETTLEMENT:", s.get("created_time"), s.get("market_result"), s.get("revenue"), s.get("ticker"))
    except Exception as e:
        print(e)
