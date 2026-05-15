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

res = c.get_markets(event_ticker="KXATPCHALLENGERMATCH-26MAR27UCHMAT")
if not res:
    print("Market not found.")
else:
    for m in res:
        print(f"Ticker: {m.get('ticker')}")
        print(f"  Title: {m.get('title')}")
        print(f"  Status: {m.get('status')}")
        print(f"  Close Time: {m.get('close_time')}")
        print(f"  Bid/Ask: {m.get('yes_bid')}/{m.get('yes_ask')}")
        print(f"  Original Ticker Date: {m.get('ticker')}")
