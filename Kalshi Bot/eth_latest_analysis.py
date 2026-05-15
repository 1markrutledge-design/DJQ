import csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta

DATA_FILE = "market_history.csv"

def run_grid_search(hours_back):
    markets = defaultdict(list)
    outcomes = {}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip()
            if "KXETH" not in ticker: continue
            
            ts_str = row.get("timestamp") or ""
            if not ts_str: continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except: continue
                
            if ts < cutoff: continue

            result = (row.get("result") or "").strip().upper()
            if result in ["YES", "NO"]:
                outcomes[ticker] = result

            close_str = row.get("close_time") or ""
            if not close_str: continue
            try:
                close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            except: continue

            try:
                bid = int(row.get("yes_bid") or 0)
                ask = int(row.get("yes_ask") or 0)
            except: continue

            mins_left = (close_dt - ts).total_seconds() / 60.0
            markets[ticker].append({
                "mins_left": mins_left,
                "bid": bid,
                "ask": ask
            })

    valid_tickers = [t for t in markets if t in outcomes]
    
    results = []
    
    # Grid Search YES Strategies (Dip Buying)
    for thresh in range(10, 60, 5):
        trades, wins, total_entry, total_profit = 0, 0, 0, 0
        for t in valid_tickers:
            md = sorted(markets[t], key=lambda x: x["mins_left"], reverse=True)
            for snap in md:
                if 1 <= snap["mins_left"] <= 8 and snap["ask"] > 0 and snap["ask"] <= thresh:
                    trades += 1
                    maker = max(1, snap["ask"] - 1)
                    total_entry += maker
                    if outcomes[t] == "YES":
                        wins += 1; total_profit += (100 - maker)
                    else:
                        total_profit -= maker
                    break
        if trades > 3:
            results.append((f"YES Ask <= {thresh} (1-8m)", trades, wins/trades*100, total_entry/trades, total_profit/trades))

    # Grid Search YES Strategies (Momentum)
    for thresh in range(60, 90, 5):
        trades, wins, total_entry, total_profit = 0, 0, 0, 0
        for t in valid_tickers:
            md = sorted(markets[t], key=lambda x: x["mins_left"], reverse=True)
            for snap in md:
                if 1 <= snap["mins_left"] <= 8 and snap["ask"] > 0 and snap["ask"] >= thresh:
                    trades += 1
                    maker = max(1, snap["ask"] - 1)
                    total_entry += maker
                    if outcomes[t] == "YES":
                        wins += 1; total_profit += (100 - maker)
                    else:
                        total_profit -= maker
                    break
        if trades > 3:
            results.append((f"YES Ask >= {thresh} (1-8m)", trades, wins/trades*100, total_entry/trades, total_profit/trades))

    # Grid Search NO Strategies (Fade Wide)
    for thresh in range(20, 65, 5):
        trades, wins, total_entry, total_profit = 0, 0, 0, 0
        for t in valid_tickers:
            md = sorted(markets[t], key=lambda x: x["mins_left"], reverse=True)
            for snap in md:
                if 5 <= snap["mins_left"] <= 12 and snap["bid"] > 0 and snap["bid"] <= thresh:
                    trades += 1
                    maker = max(1, (100 - snap["bid"]) - 1)
                    total_entry += maker
                    if outcomes[t] == "NO":
                        wins += 1; total_profit += (100 - maker)
                    else:
                        total_profit -= maker
                    break
        if trades > 3:
            results.append((f"NO Bid <= {thresh} (5-12m)", trades, wins/trades*100, total_entry/trades, total_profit/trades))

    # Grid Search NO Strategies (Fade Spike)
    for thresh in range(65, 90, 5):
        trades, wins, total_entry, total_profit = 0, 0, 0, 0
        for t in valid_tickers:
            md = sorted(markets[t], key=lambda x: x["mins_left"], reverse=True)
            for snap in md:
                if 5 <= snap["mins_left"] <= 12 and snap["bid"] > 0 and snap["bid"] >= thresh:
                    trades += 1
                    maker = max(1, (100 - snap["bid"]) - 1)
                    total_entry += maker
                    if outcomes[t] == "NO":
                        wins += 1; total_profit += (100 - maker)
                    else:
                        total_profit -= maker
                    break
        if trades > 3:
            results.append((f"NO Bid >= {thresh} (5-12m)", trades, wins/trades*100, total_entry/trades, total_profit/trades))


    results.sort(key=lambda x: x[4], reverse=True)
    
    print(f"\n======================================")
    print(f" TOP ETH STRATEGIES (LAST {hours_back} HOURS)")
    print(f"======================================")
    print(f"{'Strategy':30} | {'Trades':>6} | {'WR%':>6} | {'Entry':>6} | {'EV/sh':>6}")
    print("-" * 65)
    for res in results[:10]:
        print(f"{res[0]:30} | {res[1]:6} | {res[2]:5.1f}% | {res[3]:5.1f}c | {res[4]:+5.2f}c")

run_grid_search(5)
run_grid_search(12)
run_grid_search(24)
