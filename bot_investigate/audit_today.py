import sys, os, json, time
from datetime import datetime, timezone
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

# Midnight UTC today (Feb 24, 2026) => approx 7 PM EST yesterday, but we'll use midnight local time (EST / -05:00)
# The current time is Feb 24 08:55 EST. Midnight EST was 8 hours and 55 minutes ago.
# Let's map EST midnight to a UTC unix timestamp:
midnight_est_dt = datetime(2026, 2, 24, 0, 0, 0) # EST midnight
ext_midnight_utc = datetime(2026, 2, 24, 5, 0, 0, tzinfo=timezone.utc) # 5AM UTC = Midnight EST
midnight_ts = int(ext_midnight_utc.timestamp())

# Fetch all fills
fills = []
cursor = None
while True:
    params = {"limit": 200}
    if cursor: params["cursor"] = cursor
    
    # Passing minimum timestamp to filter efficiently
    params["min_ts"] = midnight_ts
    
    res = c._request("GET", "/portfolio/fills", params=params).json()
    batch = res.get("fills", [])
    fills.extend(batch)
    cursor = res.get("cursor")
    if not cursor or not batch: break

# Filter for TENNIS bought by this bot specifically (not manual/weather/ufc)
tennis_buy_fills = []
for f in fills:
    ticker = f.get("ticker", "")
    client_id = f.get("client_order_id", "")
    action = f.get("action", "")
    
    # We only care about ENTRY buys (45c) on Tennis markets
    is_tennis = any(p in ticker for p in ['KXATP', 'KXWTA', 'TENNIS'])
    if is_tennis and action == "buy" and (f.get("yes_price", 0) == 45 or "TENNIS" in client_id.upper()):
        tennis_buy_fills.append(f)

print(f"Total Tennis Buys since Midnight (EST): {len(tennis_buy_fills)}\n")

if not tennis_buy_fills:
    print("No tennis bets placed today since 12:00 AM EST.")
    sys.exit(0)

print(f"{'PLAYER / TICKER':<45} | {'BOUGHT AT':<10} | {'CURRENT WIN %':<15}")
print("-" * 75)

# Group by ticker in case there were multiple 1-share fills for the same bot order
unique_tickers = {f["ticker"] for f in tennis_buy_fills}

for ticker in unique_tickers:
    # Fetch current market price to get probability
    try:
        m_data = c.get_markets(ticker=ticker)
        if m_data and len(m_data) > 0:
            market = m_data[0]
            yes_ask = market.get("yes_ask", 0)
            yes_bid = market.get("yes_bid", 0)
            status = market.get("status", "unknown")
            
            # Use mid-price for probability, or just state the ask
            if yes_ask == 0 and yes_bid == 0:
                current_prob = f"Settled/Closed ({status})"
            else:
                current_prob = f"{yes_bid}¢ - {yes_ask}¢"
                
            print(f"{ticker:<45} | {'45¢':<10} | {current_prob:<15}")
        else:
             print(f"{ticker:<45} | {'45¢':<10} | {'Not Found':<15}")
    except Exception as e:
        print(f"{ticker:<45} | {'45¢':<10} | {'API Error':<15}")

print("\n(Note: Win % is represented by the current Kalshi Bid-Ask spread in cents)")
