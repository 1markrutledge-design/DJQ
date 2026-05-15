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

# Targeted series
series_list = ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH", "KXATP", "KXWTA", "TENNIS"]

print(f"{'Ticker':<40} | {'Bid':<4} | {'Ask':<4} | {'Mean':<5} | {'Note'}")
print("-" * 80)

for s in series_list:
    try:
        res = c.get_markets(series_ticker=s)
        if not res: continue
        
        for m in res:
            ticker = m.get("ticker", "")
            # Skip settled
            if m.get("status") == "finalized": continue
            
            yes_bid = m.get("yes_bid", 0)
            yes_ask = m.get("yes_ask", 0)
            mean = (yes_bid + yes_ask) / 2.0
            
            note = ""
            if yes_bid >= 55 and mean >= 63:
                note = "QUALIFIES"
            elif mean > 0:
                note = "Priced"
            else:
                note = "No Market"
                
            print(f"{ticker:<40} | {yes_bid:<4} | {yes_ask:<4} | {mean:<5.1f} | {note}")
    except Exception as e:
        print(f"Error fetching {s}: {e}")
