import pandas as pd
import numpy as np

def analyze_acceleration():
    df = pd.read_csv('market_history.csv')
    eth = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth.empty: return

    eth['t'] = pd.to_datetime(eth['timestamp'])
    eth['price'] = eth['last_price'].fillna((pd.to_numeric(eth['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(eth['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in eth.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    trades = []
    for ticker, group in eth.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        for i in range(2, len(group)):
            curr = group.iloc[i]
            prev = group.iloc[i-1]
            prev2 = group.iloc[i-2]
            
            # Change in price per second
            dt1 = (curr['t'] - prev['t']).total_seconds()
            dt2 = (prev['t'] - prev2['t']).total_seconds()
            
            if dt1 > 0 and dt2 > 0:
                v1 = (curr['price'] - prev['price']) / dt1
                v2 = (prev['price'] - prev2['price']) / dt2
                
                # Acceleration: Velocity is positive and increasing
                if v1 > 1.0 and v1 > v2 and curr['price'] > 60:
                    trades.append({'action': 'YES', 'outcome': outcome})
                    break

    if trades:
        t_df = pd.DataFrame(trades)
        wr = (t_df['action'] == t_df['outcome']).mean()
        print(f"Acceleration Strategy (>1c/s and increasing): {len(t_df)} trades, {wr:.1%} WR")

if __name__ == "__main__":
    analyze_acceleration()
