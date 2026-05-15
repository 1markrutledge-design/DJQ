import csv
import os
from collections import defaultdict
from datetime import datetime
import json

CSV_FILE = 'market_history.csv'

def find_creative_eth_patterns():
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
            if res in ['YES', 'NO']: markets[ticker]['result'] = res
            try:
                bid = float(row['yes_bid']) if row['yes_bid'] else None
                ask = float(row['yes_ask']) if row['yes_ask'] else None
                last = float(row['last_price']) if row['last_price'] else None
                close_time_str = row.get('close_time')
                close_dt = datetime.fromisoformat(close_time_str.replace('Z', '+00:00')) if close_time_str else None
                if bid is not None or ask is not None or last is not None:
                    markets[ticker]['history'].append({'ts': ts, 'price': last or ask or bid, 'ask': ask, 'bid': bid, 'close_dt': close_dt})
            except Exception: pass

    active_markets = {t: d for t, d in markets.items() if d['result'] and len(d['history']) > 20}
    for t in active_markets: active_markets[t]['history'].sort(key=lambda x: x['ts'])

    print(f"Creative Analysis on {len(active_markets)} ETH Markets...")

    results = []

    # Strategy 1: The "Gush Reversal"
    # Logic: Price pokes above 75 (Overextended), then drops 3c (Confirmation).
    # Entry: Buy NO.
    for threshold in [70, 75, 80]:
        for confirmation_drop in [2, 3, 5]:
            name = f"Gush Reversal (Hit {threshold}, Drop {confirmation_drop})"
            trades, wins, pnl = 0, 0, 0
            for ticker, data in active_markets.items():
                peak = 0
                entry_p = None
                for h in data['history']:
                    p = h['price']
                    if p > peak: peak = p
                    if peak >= threshold and (peak - p) >= confirmation_drop:
                        entry_p = 100 - (h['bid'] or p)
                        break
                if entry_p:
                    trades += 1
                    if data['result'] == 'NO': wins += 1; pnl += (100 - entry_p)
                    else: pnl -= entry_p
            if trades > 3:
                results.append({'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%", 'Profit/Trade': round(pnl/trades, 1)})

    # Strategy 2: The "Late Window Sniper" (The 11-Minute Fade)
    # Logic: In the last 4 minutes, if price is still > 90 or < 10, fade it.
    for time_left in [120, 240, 360]:
        for extreme in [85, 90, 95]:
            name = f"Late Fade ({time_left}s left, Extreme {extreme})"
            trades, wins, pnl = 0, 0, 0
            for ticker, data in active_markets.items():
                entry_p = None
                for h in data['history']:
                    if not h['close_dt']: continue
                    seconds_left = (h['close_dt'] - h['ts']).total_seconds()
                    if seconds_left <= time_left:
                        if h['price'] >= extreme:
                            entry_p = 100 - (h['bid'] or h['price'])
                            side = 'NO'
                            break
                        if h['price'] <= (100-extreme):
                            entry_p = h['ask'] or h['price']
                            side = 'YES'
                            break
                if entry_p:
                    trades += 1
                    if data['result'] == side: wins += 1; pnl += (100 - entry_p)
                    else: pnl -= entry_p
            if trades > 3:
                results.append({'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%", 'Profit/Trade': round(pnl/trades, 1)})

    # Strategy 3: The "Volatile Pivot"
    # Logic: If price moves > 15c in 60s, it's exhausted. Buy REVERSAL.
    for volatility in [15, 20]:
        name = f"Exhaustion Fade (Move {volatility}c in 60s)"
        trades, wins, pnl = 0, 0, 0
        for ticker, data in active_markets.items():
            entry_p = None
            side = None
            for i in range(1, len(data['history'])):
                curr = data['history'][i]
                for j in range(i-1, -1, -1):
                    base = data['history'][j]
                    if (curr['ts'] - base['ts']).total_seconds() > 60:
                        if curr['price'] - base['price'] >= volatility:
                            entry_p = 100 - (curr['bid'] or curr['price']); side = 'NO'; break
                        if base['price'] - curr['price'] >= volatility:
                            entry_p = curr['ask'] or curr['price']; side = 'YES'; break
                        break
                if entry_p: break
            if entry_p:
                trades += 1
                if data['result'] == side: wins += 1; pnl += (100 - entry_p)
                else: pnl -= entry_p
        if trades > 3:
            results.append({'Strategy': name, 'Trades': trades, 'Win Rate': f"{(wins/trades)*100:.1f}%", 'Profit/Trade': round(pnl/trades, 1)})

    results.sort(key=lambda x: x['Profit/Trade'], reverse=True)
    print(json.dumps(results[:15], indent=2))

if __name__ == "__main__":
    find_creative_eth_patterns()
