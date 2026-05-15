import pandas as pd
import numpy as np

def synthesize_eth_velocity():
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

    trades = []
    for ticker, group in eth.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        for i in range(5, len(group)):
            row = group.iloc[i]
            
            # Condition 1: Time Window (4-8m)
            if 240 <= row['rem'] <= 480:
                # Condition 2: Price Level (75c)
                if row['price'] >= 75:
                    # Condition 3: Velocity/Acceleration (10s move > 5c)
                    prev_10s = group[(group['t'] >= row['t'] - pd.Timedelta(seconds=10)) & (group['t'] < row['t'])]
                    if not prev_10s.empty:
                        move_10s = row['price'] - prev_10s['price'].iloc[0]
                        if move_10s >= 5:
                            trades.append(1 if outcome == 'YES' else 0)
                            break

    if trades:
        print(f"--- 75-4 VELOCITY SNIPER SYNTHESIS ---")
        print(f"Trades: {len(trades)}")
        print(f"Win Rate: {np.mean(trades):.1%}")
    else:
        print("No trades found for this specific combination.")

if __name__ == "__main__":
    synthesize_eth_velocity()
