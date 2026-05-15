import csv
import os
from collections import defaultdict
from datetime import datetime

CSV_FILE = 'market_history.csv'

def final_backtest():
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
            if res in ['YES', 'NO']: markets[ticker]['result'] = res
            try:
                bid = float(row['yes_bid']) if row['yes_bid'] else None
                ask = float(row['yes_ask']) if row['yes_ask'] else None
                last = float(row['last_price']) if row['last_price'] else None
                if bid is not None or ask is not None or last is not None:
                    markets[ticker]['history'].append({'ts': ts, 'bid': bid, 'ask': ask, 'last': last, 'price': last or ask or bid})
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 15}
    for t in active_markets: active_markets[t]['history'].sort(key=lambda x: x['ts'])

    total_profit = 0
    total_trades = 0
    total_wins = 0

    for ticker, data in active_markets.items():
        hist = data['history']
        outcome = data['result']
        bought_breakout = False
        bought_floor = False
        shares = 0
        spent = 0

        # Trigger check
        for i in range(3, len(hist)):
            p_now = hist[i]['price']
            p_15s_ago = hist[i-3]['price']
            
            # Breakout Entry
            if not bought_breakout and (p_now - p_15s_ago >= 8) and p_now <= 85:
                # Buy 1 share at Ask
                entry_p = hist[i]['ask'] or p_now
                shares += 1
                spent += entry_p
                bought_breakout = True
            
            # Floor Entry (can happen anytime if not already bought)
            if not bought_floor and p_now <= 30:
                # Buy 1 share
                entry_p = hist[i]['ask'] or p_now
                shares += 1
                spent += entry_p
                bought_floor = True
        
        if shares > 0:
            total_trades += 1
            if outcome == 'YES':
                total_profit += (shares * 100) - spent
                total_wins += 1
            else:
                total_profit -= spent

    print(f"--- COMBINED STRATEGY PERFORMANCE ---")
    print(f"Markets Traded: {total_trades}")
    print(f"Win Rate: {total_wins/total_trades*100:.1f}%")
    print(f"Total Profit (1 unit per trigger): ${total_profit/100:.2f}")
    print(f"Avg Profit per Market: {total_profit/total_trades:.1f}c")

if __name__ == "__main__":
    final_backtest()
