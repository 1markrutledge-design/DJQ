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

# Inspecting Uchiyama vs Matsuoka
ticker = "KXATPCHALLENGERMATCH-26MAR27UCHMAT-UCH"
res = c.get_markets(ticker=ticker)
if not res:
    print("Ticker not found.")
else:
    m = res[0]
    now = datetime.now(timezone.utc)
    # The 'close_time' is often the tournament end for tennis, but 'match_start' is usually in the title or custom field.
    # In V2, we often check 'open_time' or look for the first trade.
    
    print(f"Ticker: {ticker}")
    print(f"  Bid: {m.get('yes_bid')} | Ask: {m.get('yes_ask')}")
    print(f"  Close Time: {m.get('close_time')}")
    print(f"  Status: {m.get('status')}")
    print(f"  Current Time (UTC): {now.isoformat()}")

    # Check the 30-minute window
    # Note: If the match has already started, close_time might STILL be in the future (for the whole tourney).
    # But for a specific match, Kalshi usually closes it when it starts.
    # Let's see if there's a 'match_start_time' in the full payload.
    full_m = c._request("GET", f"/markets/{ticker}").json().get("market", {})
    print(f"  Expected Price Start Time: {full_m.get('expected_price_start_time')}")
    print(f"  Expiration Time: {full_m.get('expiration_time')}")
