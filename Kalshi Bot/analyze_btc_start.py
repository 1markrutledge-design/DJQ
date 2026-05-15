import pandas as pd
import numpy as np

def analyze_btc_start():
    df = pd.read_csv('market_history.csv')
    btc_df = df[df['ticker'].str.contains('KXBTC', na=False)].copy()
    
    btc_df['mid'] = (btc_df['yes_bid'].fillna(0) + btc_df['yes_ask'].fillna(100)) / 2.0
    btc_df['price'] = btc_df['last_price'].fillna(btc_df['mid'])
    btc_df['t'] = pd.to_datetime(btc_df['timestamp'])
    btc_df['ct'] = pd.to_datetime(btc_df['close_time'])
    btc_df['rem'] = (btc_df['ct'] - btc_df['t']).dt.total_seconds() / 60.0

    results = {}
    for ticker, group in btc_df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print("--- BTC Start Bias (First Snapshot) ---")
    preds = []
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        first = group.iloc[0]
        
        if first['price'] >= 55:
            preds.append({'outcome': results[ticker], 'pred': 'YES'})
        elif first['price'] <= 45:
            preds.append({'outcome': results[ticker], 'pred': 'NO'})
            
    if preds:
        p_df = pd.DataFrame(preds)
        acc = (p_df['pred'] == p_df['outcome']).mean()
        print(f"Initial Bias (>55 or <45): n={len(p_df)}, Accuracy={acc:.1%}")

if __name__ == "__main__":
    analyze_btc_start()
