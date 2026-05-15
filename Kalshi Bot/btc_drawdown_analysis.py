import pandas as pd
import numpy as np

def analyze_btc_drawdown():
    df = pd.read_csv('market_history.csv')
    btc = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    if btc.empty: return

    btc['t'] = pd.to_datetime(btc['timestamp'])
    btc['ct'] = pd.to_datetime(btc['close_time'])
    btc['rem'] = (btc['ct'] - btc['t']).dt.total_seconds() / 60.0
    btc['price'] = btc['last_price'].fillna((pd.to_numeric(btc['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(btc['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in btc.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    print(f"Analyzing BTC Drawdowns for {len(results)} markets...")

    drawdowns = []
    # Trigger: Price hits 60c
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # YES Trigger
        match_yes = group[group['price'] >= 60].head(1)
        if not match_yes.empty:
            trigger_time = match_yes['t'].iloc[0]
            later = group[group['t'] > trigger_time]
            if not later.empty:
                min_p = later['price'].min()
                drawdowns.append({'ticker': ticker, 'side': 'YES', 'outcome': outcome, 'min_price': min_p})

    dd_df = pd.DataFrame(drawdowns)
    if dd_df.empty: return

    # Analyze YES trades that won
    wins = dd_df[dd_df['outcome'] == 'YES']
    if not wins.empty:
        print(f"\nBTC Wins: {len(wins)}")
        print(f"Average Min Price after 60c entry: {wins['min_price'].mean():.1f}c")
        print(f"Worst Drawdown among winners: {wins['min_price'].min()}c")
    
    # Analyze losses
    losses = dd_df[dd_df['outcome'] == 'NO']
    if not losses.empty:
        print(f"BTC Losses: {len(losses)}")
        print(f"Average Min Price on losses: {losses['min_price'].mean():.1f}c")

if __name__ == "__main__":
    analyze_btc_drawdown()
