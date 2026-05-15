import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def eth_analysis():
    if not os.path.exists(CSV_FILE): return

    markets = defaultdict(lambda: {'history': [], 'result': None})
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker', '')
            if "KXETH15M" not in ticker: continue
            
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
                        'ts': ts, 'bid': bid, 'ask': ask, 'last': last,
                        'price': last or ask or bid
                    })
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 15}
    for t in active_markets:
        active_markets[t]['history'].sort(key=lambda x: x['ts'])
        
    print(f"Analyzing {len(active_markets)} ETH Markets...")

    combined_results = []

    # 1. Momentum Triggers
    for jump in [5, 8, 10, 15]:
        for window in [15, 30, 60]:
            name = f"Momentum ({jump}c in {window}s)"
            trades, wins, pnl = 0, 0, 0
            for ticker, data in active_markets.items():
                entry = detect_momentum(data['history'], jump, window)
                if entry:
                    trades += 1
                    if data['result'] == entry['side']:
                        wins += 1
                        pnl += (100 - entry['price'])
                    else:
                        pnl -= entry['price']
            
            if trades > 5:
                combined_results.append({
                    'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%",
                    'PnL (1 share)': round(pnl/100, 2), 'Profit/Trade': round(pnl/trades, 2)
                })

    # 2. Reversion Triggers
    for extreme in [80, 85, 90]:
        name = f"Reversion at {extreme}"
        trades, wins, pnl = 0, 0, 0
        for ticker, data in active_markets.items():
            entry = None
            for h in data['history']:
                p = h['price']
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
        
        if trades > 5:
            combined_results.append({
                'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%",
                'PnL (1 share)': round(pnl/100, 2), 'Profit/Trade': round(pnl/trades, 2)
            })

    # 3. Fixed Price Floors (YES and NO)
    for target in [20, 30, 40]:
        name = f"Fixed Buy @ {target}c"
        trades, wins, pnl = 0, 0, 0
        for ticker, data in active_markets.items():
            # Test YES side
            entry_yes = next((entry['ask'] for entry in data['history'] if entry['ask'] and entry['ask'] <= target), None)
            if entry_yes:
                trades += 1
                if data['result'] == 'YES': pnl += (100 - entry_yes); wins += 1
                else: pnl -= entry_yes
            
            # Test NO side
            entry_no = next((100 - entry['bid'] for entry in data['history'] if entry['bid'] and (100-entry['bid']) <= target), None)
            if entry_no:
                trades += 1
                if data['result'] == 'NO': pnl += (100 - entry_no); wins += 1
                else: pnl -= entry_no

        if trades > 5:
            combined_results.append({
                'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%",
                'PnL (1 share)': round(pnl/100, 2), 'Profit/Trade': round(pnl/trades, 2)
            })

    combined_results.sort(key=lambda x: x['Profit/Trade'], reverse=True)
    print(json.dumps(combined_results, indent=2))

def detect_momentum(history, jump, window):
    for i in range(1, len(history)):
        curr = history[i]
        curr_p = curr['price']
        for j in range(i-1, -1, -1):
            base = history[j]
            if (curr['ts'] - base['ts']).total_seconds() > window:
                base_p = base['price']
                if curr_p - base_p >= jump: return {'side': 'YES', 'price': curr['ask'] or curr_p}
                if base_p - curr_p >= jump: return {'side': 'NO', 'price': 100 - (curr['bid'] or curr_p)}
                break
    return None

if __name__ == "__main__":
    eth_analysis()
