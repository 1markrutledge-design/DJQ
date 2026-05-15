import csv
import os
import json
from collections import defaultdict

CSV_FILE = 'market_history.csv'

def find_absolute_optimal():
    if not os.path.exists(CSV_FILE):
        return {'error': 'No file.'}
    
    # Load data: ticker -> {series, result, history}
    data = defaultdict(lambda: {'history': [], 'result': None, 'series': ''})
    with open(CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker')
            if not ticker or ticker == 'ticker': continue
            series = ticker.split('-')[0]
            data[ticker]['series'] = series
            if row.get('result'):
                data[ticker]['result'] = row['result'].upper()
            if row.get('last_price') or row.get('yes_bid'):
                try:
                    p = float(row['last_price']) if row['last_price'] else float(row['yes_bid'] or 0)
                    if p > 0: data[ticker]['history'].append(p)
                except: pass

    # Get unique series list
    series_list = list(set(d['series'] for d in data.values() if d['result'] and d['history']))
    
    final_report = {}

    for series in series_list:
        tickers = [t for t, d in data.items() if d['series'] == series and d['result'] and d['history']]
        
        # We will track the Top 3 strategies for each coin
        top_strats = []
        
        # Test every entry from 1 to 99
        for entry in range(1, 100):
            for side in ['YES', 'NO']:
                total_pnl = 0
                trades = 0
                wins = 0
                for t in tickers:
                    res = data[t]['result']
                    hist = data[t]['history']
                    
                    # Entry logic: If price hits 'entry' level
                    entered = False
                    for p in hist:
                        # Normalize side
                        current_side_price = p if side == 'YES' else (100 - p)
                        if current_side_price >= entry:
                            entered = True
                            break
                    
                    if entered:
                        trades += 1
                        if res == side:
                            wins += 1
                            total_pnl += (100 - entry) # Profit from buy at 'entry'
                        else:
                            total_pnl -= entry # Loss of entire premium
                
                if trades >= 5:
                    win_rate = (wins / trades) * 100
                    profit_per_trade = total_pnl / trades
                    top_strats.append({
                        'entry': entry,
                        'side': side,
                        'win_rate': f"{round(win_rate, 1)}%",
                        'pnl_per_trade': f"${round(profit_per_trade, 2)}",
                        'total_pnl': round(total_pnl, 2),
                        'trades': trades
                    })
        
        # Sort by total PnL
        top_strats.sort(key=lambda x: float(x['total_pnl']), reverse=True)
        final_report[series] = top_strats[:3] # Keep top 3

    return final_report

if __name__ == "__main__":
    report = find_absolute_optimal()
    print(json.dumps(report, indent=2))
