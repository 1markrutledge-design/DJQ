import pandas as pd
import numpy as np

def analyze_btc_drawdown():
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

    entry = 65
    drawdowns = []
    
    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Trigger at 65
        trigger = group[(group['rem'] > 0.5) & (group['price'] >= entry)]
        if not trigger.empty:
            entry_t = trigger.iloc[0]['t']
            post = group[group['t'] > entry_t]
            if not post.empty:
                min_p = post['price'].min()
                drawdowns.append({'ticker': ticker, 'outcome': outcome, 'min_p': min_p})

    dd_df = pd.DataFrame(drawdowns)
    if dd_df.empty:
        print("No trades triggered.")
        return

    winners = dd_df[dd_df['outcome'] == 'YES']
    losers = dd_df[dd_df['outcome'] == 'NO']
    
    print(f"BTC Entries (at 65¢): {len(dd_df)}")
    if not winners.empty:
        print(f"Winners Avg Min Price: {winners['min_p'].mean():.1f}¢ (Min of Min: {winners['min_p'].min():.1f}¢)")
        stopped_winners = (winners['min_p'] < 50).sum()
        print(f"Winners killed by 50¢ stop-loss: {stopped_winners} / {len(winners)}")
    
    if not losers.empty:
        print(f"Losers Avg Min Price: {losers['min_p'].mean():.1f}¢")

if __name__ == "__main__":
    analyze_btc_drawdown()
