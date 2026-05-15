import csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta

DATA_FILE = "market_history.csv"

# ── Load data ──────────────────────────────────────────────────────────────
markets = defaultdict(list)
outcomes = {}

today_str = datetime.now(timezone.utc).date().isoformat()
# To get more data, let's use the last 24 hours
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ticker = (row.get("ticker") or "").strip()
        if "KXETH" not in ticker: continue
        
        ts_str = row.get("timestamp") or ""
        if not ts_str: continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except:
            continue
            
        if ts < cutoff:
            continue

        result = (row.get("result") or "").strip().upper()
        if result in ["YES", "NO"]:
            outcomes[ticker] = result

        # Only process if we have a close_time
        close_str = row.get("close_time") or ""
        if not close_str: continue
        try:
            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
        except:
            continue

        try:
            bid = int(row.get("yes_bid") or 0)
            ask = int(row.get("yes_ask") or 0)
        except:
            continue

        mins_left = (close_dt - ts).total_seconds() / 60.0
        markets[ticker].append({
            "mins_left": mins_left,
            "bid": bid,
            "ask": ask
        })

valid_tickers = [t for t in markets if t in outcomes]
print(f"Loaded {len(valid_tickers)} completed ETH markets from the last 24 hours.")

def test_strategy(name, window_min, window_max, side, condition_func):
    trades = 0
    wins = 0
    total_entry = 0
    total_profit = 0

    for t in valid_tickers:
        market_data = markets[t]
        # Sort chronologically (descending mins_left)
        market_data.sort(key=lambda x: x["mins_left"], reverse=True)
        
        for snap in market_data:
            if window_min <= snap["mins_left"] <= window_max:
                bid = snap["bid"]
                ask = snap["ask"]
                if condition_func(bid, ask):
                    # Triggered!
                    trades += 1
                    
                    if side == "YES":
                        entry_price = ask
                        maker_price = max(1, entry_price - 1)
                        total_entry += maker_price
                        
                        if outcomes[t] == "YES":
                            wins += 1
                            total_profit += (100 - maker_price)
                        else:
                            total_profit -= maker_price
                    else:
                        entry_price = 100 - bid
                        maker_price = max(1, entry_price - 1)
                        total_entry += maker_price
                        
                        if outcomes[t] == "NO":
                            wins += 1
                            total_profit += (100 - maker_price)
                        else:
                            total_profit -= maker_price
                    break # only one trade per market

    if trades == 0:
        return f"{name:20} | 0 trades"
        
    win_rate = wins / trades * 100
    avg_entry = total_entry / trades
    avg_profit = total_profit / trades
    return f"{name:25} | {trades:3} trades | {win_rate:4.1f}% WR | {avg_entry:4.1f}c entry | {avg_profit:+5.2f}c EV"

print("\n--- CURRENT STRATEGIES ---")
print(test_strategy("Strategy A (NO <= 45)", 8, 13, "NO", lambda bid, ask: bid > 0 and bid <= 45))
print(test_strategy("Strategy B (YES >= 71)", 8, 13, "YES", lambda bid, ask: ask > 0 and ask >= 71))

print("\n--- ALTERNATIVE STRATEGIES (LAST 24 HOURS) ---")
print(test_strategy("Dip Buyer (YES if Ask<=40)", 2, 8, "YES", lambda bid, ask: ask > 0 and ask <= 40))
print(test_strategy("Late Dip (YES if Ask<=30)", 1, 5, "YES", lambda bid, ask: ask > 0 and ask <= 30))
print(test_strategy("Momentum Fast (YES >= 75)", 3, 8, "YES", lambda bid, ask: ask > 0 and ask >= 75))
print(test_strategy("NO Fade Wide (NO <= 55)", 8, 13, "NO", lambda bid, ask: bid > 0 and bid <= 55))
print(test_strategy("NO Fade Narrow (NO <= 35)", 8, 13, "NO", lambda bid, ask: bid > 0 and bid <= 35))
