import pandas as pd
import numpy as np

def analyze_btc_late_no():
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

    print("--- BTC Late NO Momentum (Price > 60 drops to < 40 late) ---")
    trades = []
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Condition: Price was HIGH (> 60 at 10m)
        early = group[(group['rem'] > 10) & (group['price'] > 60)]
        if early.empty: continue
        
        # Then drops to < 40 late (1-5m)
        late = group[(group['rem'] < 5) & (group['rem'] > 1) & (group['price'] <= 40)]
        if not late.empty:
            trades.append({'outcome': outcome, 'action': 'NO', 'price': 100 - late.iloc[0]['price']})
        
    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'NO').mean()
        ev = (acc * (100 - t_df['price'].mean())) - ((1 - acc) * t_df['price'].mean())
        print(f"Late Drop (NO Play): n={len(t_df)}, Accuracy={acc:.1%}, EV={ev:.1f}¢")

if __name__ == "__main__":
    analyze_btc_late_no()
