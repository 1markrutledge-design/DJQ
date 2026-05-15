import csv
import os
from collections import defaultdict
from datetime import datetime

CSV_FILE = 'market_history.csv'

def eth_scaling_fade():
    if not os.path.exists(CSV_FILE): return

    markets = defaultdict(lambda: {'history': [], 'result': None})
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker', '')
            if "KXETH15M" not in ticker: continue
            ts_str = row.get('timestamp')
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            res = row.get('result', '').upper()
            if res in ['YES', 'NO']: markets[ticker]['result'] = res
            try:
                bid = float(row['yes_bid']) if row['yes_bid'] else None
                ask = float(row['yes_ask']) if row['yes_ask'] else None
                last = float(row['last_price']) if row['last_price'] else None
                if bid is not None or ask is not None or last is not None:
                    markets[ticker]['history'].append({'ts': ts, 'price': last or ask or bid, 'ask': ask, 'bid': bid})
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 20}
    for t in active_markets: active_markets[t]['history'].sort(key=lambda x: x['ts'])

    total_pnl = 0
    total_markets = 0
    total_wins = 0

    for ticker, data in active_markets.items():
        hist = data['history']
        res = data['result']
        
        shares = 0
        spent = 0
        
        # Scale steps for NO
        steps = [80, 85, 90, 95]
        next_step_idx = 0
        
        for h in hist:
            p = h['price']
            if next_step_idx < len(steps) and p >= steps[next_step_idx]:
                # Buy NO
                qty = (next_step_idx + 1) # Buy 1, then 2, then 3...
                price = 100 - (h['bid'] or p)
                spent += qty * price
                shares += qty
                next_step_idx += 1
                
        if shares > 0:
            total_markets += 1
            if res == 'NO':
                total_pnl += (shares * 100) - spent
                total_wins += 1
            else:
                total_pnl -= spent

    if total_markets > 0:
        print(f"--- THE ETH SCALING FADE (1-2-3-4 Scale) ---")
        print(f"Markets Traded: {total_markets}")
        print(f"Win Rate: {total_wins/total_markets*100:.1f}%")
        print(f"Total PnL (Scaled shares): ${total_pnl/100:.2f}")
        print(f"Avg PnL per market: {total_pnl/total_markets:.1f}c")

if __name__ == "__main__":
    eth_scaling_fade()
