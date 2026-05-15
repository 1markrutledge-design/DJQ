import sys, os, json, time
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient
from datetime import datetime

def load_azure_env():
    settings_path = "/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json"
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
    os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
    os.environ["KALSHI_ENVIRONMENT"] = "prod"

load_azure_env()
c = KalshiClient()
c.login()

# Fills for DUTCOL match
fills = []
cursor = None
while True:
    params = {"limit": 200, "ticker": "KXATPCHALLENGERMATCH-26FEB24DUTCOL"}
    if cursor: params["cursor"] = cursor
    try:
        res = c._request("GET", "/portfolio/fills", params=params).json()
        batch = res.get("fills", [])
        fills.extend(batch)
        cursor = res.get("cursor")
        if not cursor or not batch: break
    except Exception as e:
        print("Failed to get fills for series ticker:", e)
        break

# If the above fails because ticker needs to be specific side, fetch both:
if not fills:
    for t in ["KXATPCHALLENGERMATCH-26FEB24DUTCOL-COL", "KXATPCHALLENGERMATCH-26FEB24DUTCOL-DUT"]:
        cursor = None
        while True:
            params = {"limit": 200, "ticker": t}
            if cursor: params["cursor"] = cursor
            res = c._request("GET", "/portfolio/fills", params=params).json()
            batch = res.get("fills", [])
            fills.extend(batch)
            cursor = res.get("cursor")
            if not cursor or not batch: break

fills.sort(key=lambda x: x.get("created_time", ""))

print("=== FILLS FOR DUT vs COL ===")
for f in fills:
    dt = f.get("created_time")
    action = f.get("action")
    side = f.get("side")
    count = f.get("count")
    price = f.get("yes_price")
    client_id = f.get("client_order_id")
    ticker = f.get("ticker")
    print(f"{dt} | {ticker} | {action} {count} @ {price}c | ID: {client_id}")

EOF
