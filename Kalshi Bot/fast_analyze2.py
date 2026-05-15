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

# Take only 50 tickers
sample_tickers = list(tennis_trades.items())[:50]

total_pnl = 0
unsuccessful = 0

for ticker, data in sample_tickers:
    # the client might use "price" or "yes_price", let's handle both safely
    def get_p(f): return f.get("yes_price") or f.get("price") or 0
    buy_cost = sum(get_p(f) * f.get("count", 0) for f in data["buys"])
    sell_rev = sum(get_p(f) * f.get("count", 0) for f in data["sells"])
    
    # Check if settled
    market_data = c.get_markets(ticker=ticker)
    payout = 0
    if market_data:
        m = market_data[0]
        if m.get("status") in ["finalized", "settled"]:
            res = m.get("result", "").lower()
            shares = sum(f.get("count", 0) for f in data["buys"]) - sum(f.get("count", 0) for f in data["sells"])
            if res == "yes":
                payout = shares * 100

    pnl_cents = sell_rev + payout - buy_cost
    total_pnl += pnl_cents / 100.0
    
    if pnl_cents < 0:
        unsuccessful += 1

wins = len(sample_tickers) - unsuccessful
losses = unsuccessful
win_pct = wins / len(sample_tickers) * 100

print(f"Sampled 50 Tickers out of {len(tennis_trades)}")
print(f"Total Losses (Sample): {losses}")
print(f"Total Wins (Sample): {wins}")
print(f"Win Percentage: {win_pct:.1f}%")
print(f"Total Net P&L for Sample: ${total_pnl:.2f}")

