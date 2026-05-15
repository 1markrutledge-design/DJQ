import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def robust_analysis():
    if not os.path.exists(CSV_FILE): return

    markets = defaultdict(lambda: {'history': [], 'result': None})
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker', '')
            if "KXBTC15M" not in ticker: continue
            
            ts_str = row.get('timestamp')
            if not ts_str: continue
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            
            res = row.get('result', '').upper()
            if res in ['YES', 'NO']:
                markets[ticker]['result'] = res

            try:
                bid = float(row['yes_bid']) if row['yes_bid'] else None
                ask = float(row['yes_ask']) if row['yes_ask'] else None
                last = float(row['last_price']) if row['last_price'] else None
                if bid is not None or ask is not None or last is not None:
                    markets[ticker]['history'].append({
                        'ts': ts, 'bid': bid, 'ask': ask, 'last': last
                    })
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 10}
    for t in active_markets:
        active_markets[t]['history'].sort(key=lambda x: x['ts'])
        
    print(f"Total Markets for Robust Analysis: {len(active_markets)}")

    # We want to test strategies that are "Direction Agnostic"
    # i.e. They can buy YES or NO based on the SAME logic.

    combined_results = []

    # 1. Pure Momentum Trend Following
    for jump in [5, 8, 10]:
        for window in [30, 60]:
            name = f"Momentum ({jump}c in {window}s)"
            trades, wins, pnl = 0, 0, 0
            yes_trades, no_trades = 0, 0
            yes_wins, no_wins = 0, 0
            for ticker, data in active_markets.items():
                entry = detect_momentum(data['history'], jump, window)
                if entry:
                    trades += 1
                    is_win = (data['result'] == entry['side'])
                    if entry['side'] == 'YES':
                        yes_trades += 1
                        if is_win: yes_wins += 1
                    else:
                        no_trades += 1
                        if is_win: no_wins += 1

                    if is_win:
                        wins += 1
                        pnl += (100 - entry['price'])
                    else:
                        pnl -= entry['price']
            
            if trades > 0:
                combined_results.append({
                    'Strategy': name, 'Trades': trades, 
                    'Side Breakdown': f"YES: {yes_trades} (Win {yes_wins}), NO: {no_trades} (Win {no_wins})",
                    'Win Rate': f"{(wins/trades)*100:.1f}%",
                    'PnL': round(pnl, 2), 'Profit/Trade': round(pnl/trades, 2)
                })

    # 2. Reversion (The "Rubber Band")
    # Trigger: If price reaches extreme (e.g. 85), buy the OTHER side (e.g. NO).
    for extreme in [80, 85, 90]:
        name = f"Reversion at {extreme}"
        trades, wins, pnl = 0, 0, 0
        for ticker, data in active_markets.items():
            # If price hits 90, buy NO. If price hits 10, buy YES.
            # We track the first extreme hit.
            entry = None
            for h in data['history']:
                p = h['last'] or h['ask'] or h['bid']
                if p >= extreme:
                    entry = {'side': 'NO', 'price': 100 - (h['bid'] or p)}
                    break
                if p <= (100 - extreme):
                    entry = {'side': 'YES', 'price': h['ask'] or p}
                    break
            
            if entry:
                trades += 1
                if data['result'] == entry['side']:
                    wins += 1
                    pnl += (100 - entry['price'])
                else:
                    pnl -= entry['price']
        
        if trades > 0:
            combined_results.append({
                'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%",
                'PnL': round(pnl, 2), 'Profit/Trade': round(pnl/trades, 2)
            })

    combined_results.sort(key=lambda x: x['Profit/Trade'], reverse=True)
    print(json.dumps(combined_results, indent=2))

def detect_momentum(history, jump, window):
    for i in range(1, len(history)):
        curr = history[i]
        curr_p = curr['last'] or curr['ask'] or curr['bid']
        for j in range(i-1, -1, -1):
            base = history[j]
            if (curr['ts'] - base['ts']).total_seconds() > window:
                base_p = base['last'] or base['ask'] or base['bid']
                if curr_p - base_p >= jump:
                    return {'side': 'YES', 'price': curr['ask'] or curr_p}
                if base_p - curr_p >= jump:
                    return {'side': 'NO', 'price': 100 - (curr['bid'] or curr_p)}
                break
    return None

if __name__ == "__main__":
    robust_analysis()
