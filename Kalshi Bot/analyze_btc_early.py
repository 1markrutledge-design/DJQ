import pandas as pd
import numpy as np

def analyze_btc_early():
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

    print("--- BTC Early Trend (Trigger at 35¢ or 40¢) ---")
    for thr in [35, 40, 45]:
        trades = []
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            group = group.sort_values('t')
            # Look for trigger in first 7 minutes
            early = group[(group['rem'] > 8) & (group['price'] >= thr)]
            if not early.empty:
                trades.append({'outcome': outcome, 'action': 'YES', 'price': early.iloc[0]['price']})
        
        if trades:
            t_df = pd.DataFrame(trades)
            acc = (t_df['outcome'] == 'YES').mean()
            ev = (acc * (100 - t_df['price'].mean())) - ((1 - acc) * t_df['price'].mean())
            print(f"Price > {thr}¢ Early: n={len(t_df)}, Accuracy={acc:.1%}, EV={ev:.1f}¢")

if __name__ == "__main__":
    analyze_btc_early()
