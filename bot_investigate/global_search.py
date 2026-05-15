import sys, os, json, time
from datetime import datetime, timezone, timedelta
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

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

# Global search for Uchiyama
print("Global search for 'Uchiyama'...")
res = c._request("GET", "/markets", params={"status": "open", "limit": 1000}).json().get("markets", [])
found = False
for m in res:
    title = m.get("title", "")
    ticker = m.get("ticker", "")
    if "Uchiyama" in title or "UCH" in ticker:
        print(f"FOUND: {ticker} | {title}")
        print(f"  Bid: {m.get('yes_bid')} | Ask: {m.get('yes_ask')}")
        found = True

if not found:
    print("No 'Uchiyama' markets found in the first 1000 open markets.")
