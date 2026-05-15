import os, json, requests, base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from collections import defaultdict

# 1. Load keys from local settings
settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
try:
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    key_id = vals["KALSHI_API_KEY_ID"]
    pem_data = vals["KALSHI_PRIVATE_KEY_PEM"]
except Exception as e:
    print(f"Error loading keys: {e}")
    exit(1)

# 2. Kalshi Auth Logic
def _load_private_key():
    clean_pem = pem_data.replace('\\n', '\n').replace('"', '').strip()
    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"
    if header in clean_pem and "\n" not in clean_pem[len(header):len(header)+10]:
        content = clean_pem.replace(header, "").replace(footer, "").strip()
        clean_pem = f"{header}\n{content}\n{footer}"
    elif header not in clean_pem and "MIIE" in clean_pem:
        clean_pem = f"{header}\n{clean_pem}\n{footer}"
    return serialization.load_pem_private_key(clean_pem.encode(), password=None)

def sign_request(method, path):
    clean_path = path.split("?")[0]
    timestamp_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (timestamp_ms + method.upper() + clean_path).encode()
    private_key = _load_private_key()
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": key_id.replace('"', "").strip(),
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path, params=None):
    url = "https://api.elections.kalshi.com" + path
    headers = sign_request("GET", path)
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

# 3. Fetch recent fills
print("Fetching past 500 fills from Kalshi...")
fills = []
cursor = None
for _ in range(5):
    params = {"limit": 100}
    if cursor: params["cursor"] = cursor
    data = kalshi_get("/trade-api/v2/portfolio/fills", params=params)
    fills.extend(data.get("fills", []))
    cursor = data.get("cursor")
    if not cursor: break


if fills:
    print("KEYS:", fills[0].keys())
    print("SAMPLE FILL:", fills[0])
