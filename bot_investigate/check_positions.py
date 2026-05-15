import sys, os, json, time
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

positions = c.get_positions()
tennis_positions = [p for p in positions if any(t in p.get("ticker", "").upper() for t in ["KXATP", "KXWTA", "TENNIS"])]

print(f"Total Tennis Positions: {len(tennis_positions)}")
print(f"{'PLAYER / TICKER':<45} | {'CURRENT PROB (BID-ASK)':<25} | POINT BOUGHT")
print("-" * 90)

underdogs = 0
favorites = 0
errors = 0

for p in tennis_positions:
    ticker = p.get("ticker", "")
    position_size = p.get("position", 0)
    
    if position_size <= 0:
        continue
        
    try:
        # Sleep to respect rate limits
        time.sleep(0.15)
        m_data = c.get_markets(ticker=ticker)
        if m_data and len(m_data) > 0:
            m = m_data[0]
            yes_ask = m.get("yes_ask", 0)
            yes_bid = m.get("yes_bid", 0)
            status = m.get("status")
            
            # Determine if currently underdog or favorite
            if yes_ask > 0 and yes_ask < 50:
                underdogs += 1
                flag = "[UNDERDOG NOW]" 
            elif yes_ask >= 50 or yes_ask == 0:
                favorites += 1
                flag = "[FAVORITE NOW / CLOSED]"
            else:
                flag = ""

            print(f"{ticker:<45} | {f'{yes_bid}c - {yes_ask}c ({status})':<25} | {position_size} shares {flag}")
    except Exception as e:
        errors += 1
        print(f"{ticker:<45} | ERROR: {str(e)[:20]:<25}")

print(f"\nSummary: {underdogs} current underdogs, {favorites} current favorites, {errors} errors.")
