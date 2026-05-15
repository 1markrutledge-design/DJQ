import sys, os, json, time
from datetime import datetime, timezone, timedelta

# Try loading from strikeout_bot folder
settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
with open(settings_path, "r") as f:
    vals = json.load(f).get("Values", {})

os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
os.environ["KALSHI_ENVIRONMENT"] = "prod"

sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

c = KalshiClient()
c.login()

# Look at fills over the past 3 days to see losses
now = int(time.time())
three_days_ago = now - (3 * 24 * 3600)

res = c.get_fills(limit=1000)
tennis_fills = []
for f in res:
    if f.get('created_ts') and f['created_ts'] >= three_days_ago:
        if "KXATP" in f.get('ticker', '') or "KXWTA" in f.get('ticker', ''):
            tennis_fills.append(f)

print(f"Found {len(tennis_fills)} recent tennis fills.")

from collections import defaultdict
pnl_by_ticker = defaultdict(float)
shares_by_ticker = defaultdict(int)

for f in tennis_fills:
    ticker = f.get('ticker', '')
    action = f.get('action') # 'buy' or 'sell'
    count = f.get('count', 0)
    yes_price = f.get('yes_price', 0)
    
    if action == 'buy':
        pnl_by_ticker[ticker] -= (count * yes_price)
        shares_by_ticker[ticker] += count
    elif action == 'sell':
        pnl_by_ticker[ticker] += (count * yes_price)
        shares_by_ticker[ticker] -= count

total_pnl = 0
for t, pnl in pnl_by_ticker.items():
    shares = shares_by_ticker[t]
    print(f"Ticker: {t: <40} Net PNL: {pnl: <6}c Shares Opened/Closed delta: {shares}")
    
print(f"Done.")
