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
        if "KXBTC" not in ticker: continue
        
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
            "ask": ask,
            "ts": ts.timestamp()
        })

valid_tickers = [t for t in markets if t in outcomes]
print(f"Loaded {len(valid_tickers)} completed BTC markets from the last 24 hours.")

def test_strategy(name, window_min, window_max, side, condition_func):
    trades = 0
    wins = 0
    total_entry = 0
    total_profit = 0

    for t in valid_tickers:
        market_data = markets[t]
        # Sort chronologically (descending mins_left)
        market_data.sort(key=lambda x: x["mins_left"], reverse=True)
        
        for i, snap in enumerate(market_data):
            if window_min <= snap["mins_left"] <= window_max:
                bid = snap["bid"]
                ask = snap["ask"]
                
                # Check condition (can use history if needed by passing market_data and i)
                if condition_func(snap, market_data[:i+1]):
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
        return f"{name:30} | 0 trades"
        
    win_rate = wins / trades * 100
    avg_entry = total_entry / trades
    avg_profit = total_profit / trades
    return f"{name:30} | {trades:3} trades | {win_rate:4.1f}% WR | {avg_entry:4.1f}c entry | {avg_profit:+5.2f}c EV"

print("\n--- CURRENT BTC STRATEGIES ---")
# Strategy 1: Buy YES when ask is in the 60-72c zone, anytime 12min->1min left
def current_zone_sniper(snap, history):
    ask = snap["ask"]
    return ask > 0 and 60 <= ask <= 67
print(test_strategy("Zone Sniper (60-67c)", 1, 12, "YES", current_zone_sniper))

# Crash Recovery: Buy YES after an 8c+ price drop while ask <= 60c, in the 9-3 min window
def crash_recovery(snap, history):
    ask = snap["ask"]
    if ask > 60 or ask == 0: return False
    
    current_ts = snap["ts"]
    for old_snap in history:
        # Check window 30s
        if current_ts - old_snap["ts"] > 30:
            continue
        if old_snap["ask"] - ask >= 8:
            return True
    return False
print(test_strategy("Crash Recovery", 3, 9, "YES", crash_recovery))


print("\n--- ALTERNATIVE BTC STRATEGIES (LAST 24 HOURS) ---")
def late_dip(snap, history):
    ask = snap["ask"]
    return ask > 0 and ask <= 40
print(test_strategy("Late Dip Buyer (<=40c)", 1, 6, "YES", late_dip))

def momentum_fast(snap, history):
    ask = snap["ask"]
    return ask > 0 and ask >= 80
print(test_strategy("Fast Momentum (>=80c)", 1, 6, "YES", momentum_fast))

def momentum_early(snap, history):
    ask = snap["ask"]
    return ask > 0 and ask >= 70
print(test_strategy("Momentum Early (>=70c)", 7, 12, "YES", momentum_early))

def zone_sniper_wide(snap, history):
    ask = snap["ask"]
    return ask > 0 and 55 <= ask <= 75
print(test_strategy("Zone Sniper Wide (55-75c)", 1, 12, "YES", zone_sniper_wide))
