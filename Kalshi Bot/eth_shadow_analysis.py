import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def cross_asset_analysis():
    if not os.path.exists(CSV_FILE): return

    # We need to find markets that exist at the same time.
    # Group by timeframe (approximate to nearest 15-min window)
    time_windows = defaultdict(lambda: {'btc': None, 'eth': None})
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker', '')
            if "KXBTC15M" not in ticker and "KXETH15M" not in ticker: continue
            
            # The ticker format: KXBTC15M-26APR211415-15
            # Extract common part: 211415-15
            parts = ticker.split('-')
            if len(parts) < 2: continue
            window_id = parts[1] # e.g. 26APR211415
            
            asset = 'btc' if 'BTC' in ticker else 'eth'
            
            if not time_windows[window_id][asset]:
                time_windows[window_id][asset] = {'history': [], 'result': None}
            
            ts_str = row.get('timestamp')
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            res = row.get('result', '').upper()
            if res in ['YES', 'NO']: time_windows[window_id][asset]['result'] = res
            
            price = float(row['last_price'] or row['yes_ask'] or row['yes_bid'] or 0)
            if price:
                time_windows[window_id][asset]['history'].append({'ts': ts, 'price': price, 'ask': float(row['yes_ask'] or 0), 'bid': float(row['yes_bid'] or 0)})

    print(f"Analyzing {len(time_windows)} shared windows...")

    # Strategy: "The ETH Shadow"
    # If BTC jumps 5c in 30s, and ETH hasn't moved yet -> Buy ETH in that direction.
    
    trades, wins, pnl = 0, 0, 0
    for wid, assets in time_windows.items():
        if not assets['btc'] or not assets['eth'] or not assets['eth']['result']: continue
        
        btc_h = sorted(assets['btc']['history'], key=lambda x: x['ts'])
        eth_h = sorted(assets['eth']['history'], key=lambda x: x['ts'])
        eth_res = assets['eth']['result']
        
        triggered = False
        for i in range(1, len(btc_h)):
            # Find BTC move
            for j in range(i-1, -1, -1):
                if (btc_h[i]['ts'] - btc_h[j]['ts']).total_seconds() <= 30:
                    btc_move = btc_h[i]['price'] - btc_h[j]['price']
                    if abs(btc_move) >= 5:
                        # BTC moved! Check ETH at this timestamp
                        target_ts = btc_h[i]['ts']
                        # Find ETH price close to target_ts
                        eth_entry = None
                        for eh in eth_h:
                            if abs((eh['ts'] - target_ts).total_seconds()) < 10:
                                # Found ETH snapshot at same time
                                if btc_move >= 5: # BTC Up
                                    eth_entry = {'side': 'YES', 'price': eh['ask'] or eh['price']}
                                else: # BTC Down
                                    eth_entry = {'side': 'NO', 'price': 100 - (eh['bid'] or eh['price'])}
                                break
                        
                        if eth_entry and eth_entry['price'] > 0:
                            trades += 1
                            if eth_res == eth_entry['side']:
                                wins += 1
                                pnl += (100 - eth_entry['price'])
                            else:
                                pnl -= eth_entry['price']
                            triggered = True
                            break
                if triggered: break
            if triggered: break

    if trades > 0:
        print(f"--- THE ETH SHADOW (BTC-LED) ---")
        print(f"Trades: {trades}")
        print(f"Win Rate: {wins/trades*100:.1f}%")
        print(f"Profit/Trade: {pnl/trades:.1f}c")
        print(f"Total PnL (1 share): ${pnl/100:.2f}")

if __name__ == "__main__":
    cross_asset_analysis()
