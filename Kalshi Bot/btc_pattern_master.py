import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def find_patterns():
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
                        'ts': ts, 'bid': bid, 'ask': ask, 'last': last,
                        'price': last or ask or bid
                    })
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 20}
    for t in active_markets:
        active_markets[t]['history'].sort(key=lambda x: x['ts'])
        
    print(f"Deep Analyzing {len(active_markets)} Markets...")

    patterns = []

    # Let's analyze "Sequence Momentum"
    # Logic: Look at a 15-second window (3 snapshots). 
    # Calculate the sum of deltas.
    
    momentum_stats = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})

    for ticker, data in active_markets.items():
        hist = data['history']
        outcome = data['result']
        
        # Track if we already "traded" on a specific pattern for this market 
        # to avoid double counting the same move
        seen_patterns = set()

        for i in range(3, len(hist)):
            # Lookback 3 segments (approx 15 seconds)
            p_now = hist[i]['price']
            p_prev1 = hist[i-1]['price']
            p_prev2 = hist[i-2]['price']
            p_prev3 = hist[i-3]['price']
            
            # Pattern: 3 consecutive price changes
            d1 = p_now - p_prev1
            d2 = p_prev1 - p_prev2
            d3 = p_prev2 - p_prev3
            
            total_delta = d1 + d2 + d3 # Total change over 15s
            
            # Round deltas to 1c buckets to find patterns
            # Or just use the 'Total Jump' as the key
            
            if total_delta >= 5: # A significant 15s jump
                key = f"Jump +{int(total_delta)} in 15s"
                if key not in seen_patterns:
                    momentum_stats[key]['total'] += 1
                    if outcome == 'YES':
                        momentum_stats[key]['wins'] += 1
                        momentum_stats[key]['pnl'] += (100 - hist[i]['ask'])
                    else:
                        momentum_stats[key]['pnl'] -= hist[i]['ask']
                    seen_patterns.add(key)

            if total_delta <= -5: # A significant 15s drop
                key = f"Drop {int(total_delta)} in 15s"
                if key not in seen_patterns:
                    momentum_stats[key]['total'] += 1
                    if outcome == 'NO':
                        momentum_stats[key]['wins'] += 1
                        # Buying NO price = 100 - YES Bid
                        no_price = 100 - hist[i]['bid']
                        momentum_stats[key]['pnl'] += (100 - no_price)
                    else:
                        no_price = 100 - hist[i]['bid']
                        momentum_stats[key]['pnl'] -= no_price
                    seen_patterns.add(key)

    # Convert stats to sorted list
    results = []
    for p, s in momentum_stats.items():
        if s['total'] > 5:
            wr = s['wins'] / s['total']
            results.append({
                'Pattern': p,
                'Frequency': s['total'],
                'Win Rate': f"{wr*100:.1f}%",
                'Avg Profit': round(s['pnl'] / s['total'], 1),
                'Total PnL': round(s['pnl'], 1)
            })

    results.sort(key=lambda x: x['Total PnL'], reverse=True)
    print(json.dumps(results, indent=2))

    # Pattern 2: "The Acceleration"
    # Price moves +2, then +3, then +4 (Speeds up)
    # vs "The Deceleration"
    # Price moves +4, then +3, then +2 (Slows down)
    
if __name__ == "__main__":
    find_patterns()
