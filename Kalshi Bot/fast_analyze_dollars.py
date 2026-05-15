import sys, os, json
from datetime import datetime, timezone, timedelta
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
with open(settings_path, "r") as f:
    vals = json.load(f).get("Values", {})
os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
os.environ["KALSHI_ENVIRONMENT"] = "prod"

c = KalshiClient()
c.login()

# Last 7 days
min_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
fills = []
cursor = None
while True:
    res = c._request("GET", "/portfolio/fills", params={"limit": 1000, "min_ts": min_ts, "cursor": cursor}).json()
    batch = res.get("fills", [])
    fills.extend(batch)
    cursor = res.get("cursor")
    if not cursor or not batch: break

trades = {}
for f in fills:
    t = f.get("ticker", "")
    if "KXATP" not in t and "KXWTA" not in t and "TENNIS" not in t: continue
    if t not in trades: trades[t] = {"buys": 0.0, "sells": 0.0, "sb": 0.0, "ss": 0.0}
    
    count = float(f.get("count_fp", 0))
    action = f.get("action")
    side = f.get("side", "yes")
    
    # Cost calculation (use yes_price if YES side, no_price if NO side)
    price_key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
    price = float(f.get(price_key, 0))
    
    cost = count * price
    
    if action == "buy":
        trades[t]["buys"] += cost
        trades[t]["sb"] += count
    elif action == "sell":
        trades[t]["sells"] += cost
        trades[t]["ss"] += count

wins = 0
losses = 0
gross_profit = 0
gross_loss = 0
open_positions = 0

for t, data in trades.items():
    sb = data["sb"]
    ss = data["ss"]
    if sb > 0 and abs(sb - ss) < 0.1: # Fully closed
        pnl = data["sells"] - data["buys"]
        if pnl > 0.01:
            wins += 1
            gross_profit += pnl
        elif pnl < -0.01:
            losses += 1
            gross_loss += abs(pnl)
    elif sb > 0 and ss == 0:
        # Simplistic assumption: mostly stop-out failures or active
        open_positions += 1

total = wins + losses
win_pct = wins / total * 100 if total > 0 else 0
net = gross_profit - gross_loss

print(f"Total Fills Checked: {len(fills)}")
print(f"Total Closed Tennis Trades (Last 7 Days): {total}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Win Rate: {win_pct:.1f}%")
print(f"Gross Profit: ${gross_profit:.2f}")
print(f"Gross Loss: ${gross_loss:.2f}")
print(f"Net P&L: ${net:.2f}")
print(f"Currently Open/Settling Positions: {open_positions}")
