import pandas as pd
import numpy as np

def analyze_btc_velocity():
    df = pd.read_csv('market_history.csv')
    btc = df[df['ticker'].str.contains('KXBTC')].copy()
    btc['t'] = pd.to_datetime(btc['timestamp'])
    btc['ct'] = pd.to_datetime(btc['close_time'])
    btc['rem'] = (btc['ct'] - btc['t']).dt.total_seconds() / 60.0
    btc['price'] = btc['last_price'] # ONLY use last_price for velocity, mid is fake
    
    results = {}
    for ticker, group in btc.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('rem')['last_price'].iloc[0] # closest to end
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print("--- BTC Velocity Strategy (Price jump > 15¢ in 2 mins) ---")
    
    trades = []
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t').dropna(subset=['price'])
        if len(group) < 2: continue
        
        # Check every 2-minute window
        for i in range(len(group)):
            start_row = group.iloc[i]
            # Find row ~2 mins later
            later = group[(group['t'] > start_row['t']) & (group['t'] <= start_row['t'] + pd.Timedelta(minutes=2))]
            if later.empty: continue
            
            end_row = later.iloc[-1]
            jump = end_row['price'] - start_row['price']
            
            if jump >= 15:
                trades.append({'outcome': results[ticker], 'time': end_row['rem']})
                break # Only one trade per ticker

    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'YES').mean()
        print(f"Velocity Trades: {len(t_df)} trades, {acc:.1%} Accuracy")
        print(f"Avg Time Remaining at trigger: {t_df['time'].mean():.1f}m")

if __name__ == "__main__":
    analyze_btc_velocity()
