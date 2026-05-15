import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def backtest_strategies():
    if not os.path.exists(CSV_FILE):
        print("No market_history.csv found.")
        return

    markets = defaultdict(lambda: {'history': [], 'result': None})
    
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker', '')
            if not ticker or "KXBTC15M" not in ticker: continue
            
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
                close_time_str = row.get('close_time')
                close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00')) if close_time_str else None
                
                if bid is not None or ask is not None or last is not None:
                    markets[ticker]['history'].append({
                        'ts': ts,
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'close_time': close_time
                    })
            except Exception:
                pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 5}
    for t in active_markets:
        active_markets[t]['history'].sort(key=lambda x: x['ts'])
        
    print(f"Analyzing {len(active_markets)} BTC markets...")

    strategies = []

    # 1. Fixed Price Entry (YES)
    for price in [30, 50, 70, 90]:
        strategies.append({
            'name': f'Fixed YES @ {price}',
            'func': lambda h, p=price: next((entry['ask'] for entry in h if entry['ask'] and entry['ask'] <= p), None),
            'side': 'YES'
        })

    # 2. Momentum Burst (YES)
    strategies.append({
        'name': 'Momentum Burst (+7 in 20s)',
        'func': lambda h: momentum_trigger(h, 'YES', 7, 20),
        'side': 'YES'
    })

    # 3. Slow Trend Rider (YES)
    strategies.append({
        'name': 'Trend Rider (+10 in 2m)',
        'func': lambda h: momentum_trigger(h, 'YES', 10, 120),
        'side': 'YES'
    })

    # 4. Deep Value NO Sniper
    strategies.append({
        'name': 'NO Value (YES > 95)',
        'func': lambda h: next((100 - entry['bid'] for entry in h if entry['bid'] and entry['bid'] >= 95), None),
        'side': 'NO'
    })

    # 5. Overbought Reversal (NO)
    strategies.append({
        'name': 'Reversal (YES drops 5 from peak > 80)',
        'func': lambda h: reversal_trigger(h, 'NO', 80, 5),
        'side': 'NO'
    })

    # 6. Dip Buyer (YES)
    strategies.append({
        'name': 'Dip Buyer (YES bounces 3 from dip < 40)',
        'func': lambda h: dip_buyer_trigger(h, 40, 3),
        'side': 'YES'
    })

    results = []

    for strat in strategies:
        trades = 0
        wins = 0
        total_pnl = 0
        
        for ticker, data in active_markets.items():
            entry_price = strat['func'](data['history'])
            
            if entry_price is not None:
                trades += 1
                if data['result'] == strat['side']:
                    wins += 1
                    total_pnl += (100 - entry_price)
                else:
                    total_pnl -= entry_price
        
        if trades > 0:
            win_rate = (wins / trades) * 100
            avg_profit = total_pnl / trades
            results.append({
                'Strategy': strat['name'],
                'Trades': trades,
                'Win Rate': f"{win_rate:.1f}%",
                'Net PnL (1 share)': f"${total_pnl/100:.2f}",
                'Avg Profit/Trade': f"{avg_profit:.1f}c",
                'raw_pnl': total_pnl
            })

    results.sort(key=lambda x: x['raw_pnl'], reverse=True)
    print(json.dumps(results, indent=2))

def momentum_trigger(history, side, threshold, window_seconds):
    for i in range(1, len(history)):
        current = history[i]
        curr_p = current['last'] or current['ask'] or current['bid']
        if not curr_p: continue
        for j in range(i-1, -1, -1):
            base = history[j]
            if (current['ts'] - base['ts']).total_seconds() > window_seconds:
                base_p = base['last'] or base['ask'] or base['bid']
                if not base_p: continue
                if side == 'YES':
                    if curr_p - base_p >= threshold:
                        return current['ask'] if current['ask'] else curr_p
                else:
                    if base_p - curr_p >= threshold:
                        return (100 - current['bid']) if current['bid'] else (100 - curr_p)
                break
    return None

def reversal_trigger(history, side, min_peak, drop_needed):
    peak = 0
    for entry in history:
        p = entry['last'] or entry['bid'] or entry['ask']
        if not p: continue
        if p > peak: peak = p
        if peak >= min_peak and (peak - p) >= drop_needed:
            # Reversal detected
            if side == 'NO':
                return (100 - entry['bid']) if entry['bid'] else (100 - p)
            else:
                return entry['ask'] if entry['ask'] else p
    return None

def dip_buyer_trigger(history, max_dip, bounce_needed):
    dip = 100
    for entry in history:
        p = entry['last'] or entry['bid'] or entry['ask']
        if not p: continue
        if p < dip: dip = p
        if dip <= max_dip and (p - dip) >= bounce_needed:
            return entry['ask'] if entry['ask'] else p
    return None

if __name__ == "__main__":
    backtest_strategies()
