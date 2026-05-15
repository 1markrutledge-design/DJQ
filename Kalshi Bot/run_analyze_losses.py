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

print(f"Total Tennis Tickers traded in last 30 days: {len(tennis_trades)}")
print("-" * 80)

total_pnl = 0

for ticker, data in tennis_trades.items():
    buy_cost = sum(f.get("yes_price", 0) * f.get("count", 0) for f in data["buys"])
    sell_rev = sum(f.get("yes_price", 0) * f.get("count", 0) for f in data["sells"])
    
    # Check if settled
    market_data = c.get_markets(ticker=ticker)
    payout = 0
    if market_data:
        m = market_data[0]
        if m.get("status") == "finalized":
            res = m.get("result", "").lower()
            shares = sum(f.get("count", 0) for f in data["buys"]) - sum(f.get("count", 0) for f in data["sells"])
            if res == "yes":
                payout = shares * 100

    pnl_cents = sell_rev + payout - buy_cost
    pnl_dollars = pnl_cents / 100.0
    total_pnl += pnl_dollars

print(f"Total Combined P&L (last 30 days): ${total_pnl:.2f}")

unsuccessful_trades = [t for t, d in tennis_trades.items() if (sum(f.get("yes_price", 0) * f.get("count", 0) for f in d["sells"]) + (0 if not c.get_markets(ticker=t) or c.get_markets(ticker=t)[0].get("result")!="yes" else sum(f.get("count", 0) for f in d["buys"]) - sum(f.get("count",0) for f in d["sells"])*100) - sum(f.get("yes_price", 0) * f.get("count", 0) for f in d["buys"]))/100.0 < 0]

wins = len(tennis_trades) - len(unsuccessful_trades)
losses = len(unsuccessful_trades)
win_pct = wins / len(tennis_trades) * 100 if len(tennis_trades) > 0 else 0

print(f"Number of losing tickers: {losses}")
print(f"Number of winning tickers: {wins}")
print(f"Win Percentage: {win_pct:.1f}%")
