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

ticker = "KXATPCHALLENGERMATCH-26MAR27UCHMAT-UCH"
m = c._request("GET", f"/markets/{ticker}").json().get("market", {})

print(f"Ticker: {ticker}")
print(f"Open Time: {m.get('open_time')}")
print(f"Close Time: {m.get('close_time')}")
print(f"Expected Price Start: {m.get('expected_price_start_time')}")
print(f"Current UTC: {datetime.now(timezone.utc).isoformat()}")
