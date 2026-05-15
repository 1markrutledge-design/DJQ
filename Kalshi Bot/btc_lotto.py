import pandas as pd
import numpy as np

def analyze_btc_lotto():
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

    print("--- BTC Lotto Strategy (Buy YES < 20¢ early) ---")
    
    trades = []
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Condition: Price starts low (< 20) in first 5 minutes (15m-10m remaining)
        # BUT shows signs of life (jumps > 5c)
        early = group[(group['rem'] >= 10) & (group['rem'] <= 14)]
        if early.empty: continue
        
        min_p = early['price'].min()
        max_p = early['price'].max()
        
        if min_p < 20 and (max_p - min_p) > 5:
            trades.append({'outcome': outcome, 'entry_price': max_p})

    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'YES').mean()
        print(f"Lotto Trades: {len(t_df)} trades, {acc:.1%} WR")
        print(f"Avg Entry: {t_df['entry_price'].mean():.1f}¢")

if __name__ == "__main__":
    analyze_btc_lotto()
