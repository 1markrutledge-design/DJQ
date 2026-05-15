import pandas as pd
import numpy as np

def optimize_25c_dip():
    df = pd.read_csv('market_history.csv')
    eth = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth.empty: return

    eth['t'] = pd.to_datetime(eth['timestamp'])
    eth['ct'] = pd.to_datetime(eth['close_time'])
    eth['rem'] = (eth['ct'] - eth['t']).dt.total_seconds()
    eth['price'] = eth['last_price'].fillna((pd.to_numeric(eth['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(eth['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in eth.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    stats = []
    # Test 25c entry at different time windows
    for start_m in range(0, 15):
        for end_m in range(start_m + 1, 16):
            start_s = start_m * 60
            end_s = end_m * 60
            
            trades = []
            for ticker, group in eth.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                # Price hits 25-30c within the window
                match = group[(group['price'] <= 30) & (group['price'] >= 20) & (group['rem'] >= start_s) & (group['rem'] <= end_s)].sort_values('rem', ascending=False).head(1)
                
                if not match.empty:
                    trades.append(1 if outcome == 'YES' else 0)
            
            if len(trades) >= 10:
                stats.append({'StartM': start_m, 'EndM': end_m, 'Trades': len(trades), 'Profit/Share': (np.mean(trades)*100) - 25, 'WR': np.mean(trades)})

    s_df = pd.DataFrame(stats).sort_values('Profit/Share', ascending=False)
    print("\n--- ETH 25c DIP OPTIMIZATION ---")
    print(s_df.head(15).to_string(index=False))

if __name__ == "__main__":
    optimize_25c_dip()
