import pandas as pd
import numpy as np

def analyze_btc_failure():
    df = pd.read_csv('market_history.csv')
    btc_df = df[df['ticker'].str.contains('KXBTC', na=False)].copy()
    
    # Identify outcomes
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

    print("--- BTC Breakdown by Entry Time (70¢ Threshold) ---")
    for time_bucket in [(12, 8), (8, 4), (4, 1)]:
        trades = []
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            # Look for trigger in THIS specific time window
            window = group[(group['rem'] <= time_bucket[0]) & (group['rem'] >= time_bucket[1])]
            if window.empty: continue
            
            trigger = window[window['price'] >= 70]
            if not trigger.empty:
                trades.append({'outcome': outcome, 'action': 'YES'})

        if trades:
            t_df = pd.DataFrame(trades)
            acc = (t_df['action'] == t_df['outcome']).mean()
            print(f"Entry {time_bucket[0]}m-{time_bucket[1]}m remaining: {len(t_df)} trades, {acc:.1%} WR")

    # Check for "Reversals"
    # How many times did price reach > 80 but finished NO?
    fakeouts = 0
    total_highs = 0
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        if group['price'].max() >= 80:
            total_highs += 1
            if results[ticker] == 'NO':
                fakeouts += 1
    
    print(f"\nBTC > 80¢ Fakeouts: {fakeouts} / {total_highs} ({fakeouts/total_highs:.1%})")

if __name__ == "__main__":
    analyze_btc_failure()
