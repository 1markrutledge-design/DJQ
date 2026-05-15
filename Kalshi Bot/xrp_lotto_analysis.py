import pandas as pd
import numpy as np

def analyze_xrp_lotto():
    df = pd.read_csv('market_history.csv')
    xrp_df = df[df['ticker'].str.contains('KXXRP15M', na=False)].copy()
    if xrp_df.empty:
        return

    xrp_df['t'] = pd.to_datetime(xrp_df['timestamp'])
    xrp_df['ct'] = pd.to_datetime(xrp_df['close_time'])
    xrp_df['rem'] = (xrp_df['ct'] - xrp_df['t']).dt.total_seconds() / 60.0
    
    xrp_df['mid'] = (xrp_df['yes_bid'].fillna(0) + xrp_df['yes_ask'].fillna(100)) / 2.0
    xrp_df['price'] = xrp_df['last_price'].fillna(xrp_df['mid'])
    
    results = {}
    for ticker, group in xrp_df.groupby('ticker'):
        outcome = group['result'].dropna()
        if not outcome.empty:
            val = outcome.iloc[0]
            if isinstance(val, str): results[ticker] = val
            else: results[ticker] = 'YES' if val > 0 else 'NO'
        else:
            group = group.sort_values('t')
            lp = group['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print(f"Analyzing {len(results)} XRP markets for lotto wins...")

    # Lotto: Price < 20 but settles YES, or Price > 80 but settles NO
    lotto_wins = []
    for ticker, group in xrp_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Check for YES lotto (buy < 20 early, win YES)
        early_cheap = group[(group['rem'] >= 7) & (group['price'] <= 15)]
        if not early_cheap.empty and outcome == 'YES':
            lotto_wins.append({'ticker': ticker, 'type': 'YES_LOTTO', 'min_price': early_cheap['price'].min()})
            
        # Check for NO lotto (buy > 80 early, win NO)
        early_expensive = group[(group['rem'] >= 7) & (group['price'] >= 85)]
        if not early_expensive.empty and outcome == 'NO':
            lotto_wins.append({'ticker': ticker, 'type': 'NO_LOTTO', 'max_price': early_expensive['price'].max()})

    print(f"Total Lotto Wins Found: {len(lotto_wins)}")
    for win in lotto_wins:
        print(f"- {win['type']} on {win['ticker']} at price {win.get('min_price', win.get('max_price'))}")

if __name__ == "__main__":
    analyze_xrp_lotto()
