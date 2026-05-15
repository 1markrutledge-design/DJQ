import sys, os, json, time
from datetime import datetime, timezone, timedelta

sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

def load_azure_env():
    settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
    os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
    os.environ["KALSHI_ENVIRONMENT"] = "prod"

load_azure_env()
c = KalshiClient()
c.login()

# Look at last 30 days of fills
min_ts = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())

fills = []
cursor = None
while True:
    params = {"limit": 200, "min_ts": min_ts}
    if cursor: params["cursor"] = cursor
    res = c._request("GET", "/portfolio/fills", params=params).json()
    batch = res.get("fills", [])
    fills.extend(batch)
    cursor = res.get("cursor")
    if not cursor or not batch: break

tennis_trades = {}
for f in fills:
    ticker = f.get("ticker", "")
    if not any(p in ticker for p in ['KXATP', 'KXWTA', 'TENNIS']):
        continue
    
    if ticker not in tennis_trades:
        tennis_trades[ticker] = {"buys": [], "sells": []}
    
    if f.get("action") == "buy":
        tennis_trades[ticker]["buys"].append(f)
    else:
        tennis_trades[ticker]["sells"].append(f)

wins = 0
losses = 0
gross_profit = 0
gross_loss = 0

# Fast evaluation logic
for ticker, data in tennis_trades.items():
    shares_b = sum(f.get("count", 0) for f in data["buys"])
    shares_s = sum(f.get("count", 0) for f in data["sells"])
    
    buy_cost = sum(f.get("yes_price", 0) * f.get("count", 0) for f in data["buys"])
    sell_rev = sum(f.get("yes_price", 0) * f.get("count", 0) for f in data["sells"])
    
    # We only look at fully closed out trades to avoid API requests
    if shares_b > 0 and shares_b == shares_s:
        pnl = sell_rev - buy_cost
        if pnl > 0:
            wins += 1
            gross_profit += pnl
        elif pnl < 0:
            losses += 1
            gross_loss += abs(pnl)

total_pnl = gross_profit - gross_loss
win_pct = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

print(f"--- Fast Audit: Last 30 Days (Closed Trades Only) ---")
print(f"Total Completed Trades Analyzed: {wins + losses}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Win Percentage: {win_pct:.1f}%")
print(f"Gross Profit: ${gross_profit/100:.2f}")
print(f"Gross Loss: ${gross_loss/100:.2f}")
print(f"Net P&L: ${total_pnl/100:.2f}")
