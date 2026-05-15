import os, json, base64, requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from datetime import datetime, timezone, timedelta

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
    if header not in pem_data:
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
        "KALSHI-ACCESS-KEY": os.environ["KALSHI_API_KEY_ID"].strip(),
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }

def kalshi_get(path: str, params=None) -> dict:
    url = KALSHI_BASE + path
    r = requests.get(url, headers=sign_request("GET", path), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

TENNIS_SERIES_PREFIXES = ("KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "TENNIS")

def is_tennis(m: dict) -> bool:
    series = m.get("series_ticker", "").upper()
    event = m.get("event_ticker", "").upper()
    return any(series.startswith(p) or p in series or p in event for p in TENNIS_SERIES_PREFIXES)

now = datetime.now(timezone.utc)
valid_dates = {(now - timedelta(days=d)).strftime("%y%b%d").upper() for d in range(2)}
print(f"Valid Dates: {valid_dates}")

def filter_tennis_in_window(markets: list[dict]) -> list[dict]:
    results = []
    for m in markets:
        if not is_tennis(m) or m.get("result"):
            continue
        if not any(d in m.get("ticker", "").upper() for d in valid_dates):
            continue
        results.append(m)
    return results

all_tennis = []
known_tennis_series = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "KXMTENNIS", "TENNIS"]

try:
    for series in known_tennis_series:
        cursor = None
        while True:
            params = {"limit": 200, "status": "open", "series_ticker": series}
            if cursor: params["cursor"] = cursor
            data = kalshi_get("/trade-api/v2/markets", params=params)
            markets = data.get("markets", [])
            all_tennis.extend(filter_tennis_in_window(markets))
            cursor = data.get("cursor")
            if not cursor or not markets:
                break
except Exception as e:
    print(f"Error fetching: {e}")

print(f"Total tennis targets in window: {len(all_tennis)}")

found_fatmor = False
for m in all_tennis:
    ticker = m.get("ticker", "")
    yes_bid = m.get('yes_bid', 0)
    yes_ask = m.get('yes_ask', 0)
    if "FATMOR" in ticker:
        found_fatmor = True
        print(f"EVALUATING: {ticker} (Bid: {yes_bid} | Ask: {yes_ask})")
        
        if yes_bid is None or yes_ask is None:
            print(f"Skipped {ticker}: yes_bid or yes_ask is None")
            continue
        if yes_bid <= 55:
            print(f"Skipped {ticker}: yes_bid ({yes_bid}) <= 55")
            continue
        if yes_ask > 98:
            print(f"Skipped {ticker}: yes_ask ({yes_ask}) > 98")
            continue
        
        mean_price = (yes_bid + yes_ask) / 2.0
        if mean_price <= 63:
            print(f"Skipped {ticker}: mean_price ({mean_price}) <= 63")
            continue
            
        print(f"TARGET FOUND! {ticker} Passes all filters!")

if not found_fatmor:
    print("FATMOR not found in final filtered scan!")
