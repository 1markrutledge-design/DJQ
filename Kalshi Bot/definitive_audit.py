import csv, os, json
from collections import defaultdict
from datetime import datetime

CSV_FILE = 'market_history.csv'

def definitive_profit_audit():
    if not os.path.exists(CSV_FILE): return {'error': 'No file.'}
    data = defaultdict(lambda: {'history': [], 'result': None, 'start': None})
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker')
            if not ticker or ticker == 'ticker': continue
            ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            if data[ticker]['start'] is None or ts < data[ticker]['start']: data[ticker]['start'] = ts
            if row.get('result'): data[ticker]['result'] = row['result'].upper()
            if row.get('last_price') or row.get('yes_bid'):
                p = float(row['last_price']) if row['last_price'] else float(row['yes_bid'] or 0)
                if p > 0: data[ticker]['history'].append((ts, p))

    series_list = list(set(ticker.split('-')[0] for ticker in data))
    final_ranking = []

    for series in series_list:
        tickers = [t for t, d in data.items() if series in t and d['result'] and d['history']]
        best_pnl_per_trade = -9999
        best_strat = None
        for entry_price in range(5, 96, 5):
            for min_mark in range(1, 15):
                for side in ['YES', 'NO']:
                    wins, trades, pnl = 0, 0, 0
                    for t in tickers:
                        start = data[t]['start']; res = data[t]['result']
                        triggered = False
                        for ts, p in data[t]['history']:
                            if (ts - start).total_seconds() >= (min_mark * 60):
                                cp = p if side == 'YES' else (100 - p)
                                if cp >= entry_price: triggered = True; break
                        if triggered:
                            trades += 1
                            if res == side: wins += 1; pnl += (100 - entry_price)
                            else: pnl -= entry_price
                    if trades >= 10:
                        avg_pnl = pnl / trades
                        if avg_pnl > best_pnl_per_trade:
                            best_pnl_per_trade = avg_pnl
                            best_strat = {'coin': series, 'entry': entry_price, 'time': f'{min_mark}m', 'side': side, 'avg_profit': round(avg_pnl, 2), 'win_rate': round(wins/trades*100, 1), 'trades': trades}
        if best_strat: final_ranking.append(best_strat)
    final_ranking.sort(key=lambda x: x['avg_profit'], reverse=True)
    return final_ranking

print(json.dumps(definitive_profit_audit(), indent=2))
