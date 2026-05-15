import pandas as pd
import numpy as np

def analyze_btc_no_edge():
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

    print("--- BTC NO Strategy Search ---")
    
    # Strat 1: The "Dead Cat Bounce" (NO Play)
    # Price was very high (> 70) early, but drops below 40 late
    trades = []
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        early = group[(group['rem'] > 10) & (group['price'] > 70)]
        if early.empty: continue
        
        late = group[(group['rem'] < 5) & (group['price'] < 40)]
        if not late.empty:
            trades.append({'outcome': outcome})

    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'NO').mean()
        print(f"Dead Cat Bounce NO: n={len(t_df)}, Accuracy={acc:.1%}")

    # Strat 2: The "Overbought Fade" (NO Play)
    # Price hits > 90 but then drops below 75 late
    trades = []
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        peak = group['price'].max()
        if peak >= 90:
            late_drop = group[(group['rem'] < 4) & (group['price'] < 75)]
            if not late_drop.empty:
                 trades.append({'outcome': outcome})
                 
    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'NO').mean()
        print(f"Overbought Fade NO: n={len(t_df)}, Accuracy={acc:.1%}")

if __name__ == "__main__":
    analyze_btc_no_edge()
