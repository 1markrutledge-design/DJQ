import pandas as pd
import numpy as np

def analyze_drawdown():
    df = pd.read_csv('market_history.csv')
    sol_df = df[df['ticker'].str.contains('KXSOL15M', na=False)].copy()
    sol_df['t'] = pd.to_datetime(sol_df['timestamp'])
    sol_df['ct'] = pd.to_datetime(sol_df['close_time'])
    sol_df['rem'] = (sol_df['ct'] - sol_df['t']).dt.total_seconds() / 60.0
    sol_df['mid'] = (sol_df['yes_bid'].fillna(0) + sol_df['yes_ask'].fillna(100)) / 2.0
    sol_df['price'] = sol_df['last_price'].fillna(sol_df['mid'])
    
    # Identify outcomes
    results = {}
    for ticker, group in sol_df.groupby('ticker'):
        outcome = group['result'].dropna()
        if not outcome.empty:
            results[ticker] = outcome.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    entry_price = 70
    stop_loss_candidates = [60, 50, 40, 30]
    
    trade_summary = []
    
    for ticker, group in sol_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Look for YES trigger (price hits 70)
        # We'll just analyze YES trades for simplicity, logic applies to NO too
        trigger_times = group[group['price'] >= entry_price]
        if trigger_times.empty: continue
        
        entry_time = trigger_times.iloc[0]['t']
        post_entry = group[group['t'] > entry_time]
        if post_entry.empty: continue
        
        min_price = post_entry['price'].min()
        max_price = post_entry['price'].max()
        
        trade_summary.append({
            'ticker': ticker,
            'outcome': outcome,
            'min_post': min_price,
            'max_post': max_price
        })

    trades_df = pd.DataFrame(trade_summary)
    
    print(f"Total YES Trades (at 70¢): {len(trades_df)}")
    
    # Analysis of "Winners"
    winners = trades_df[trades_df['outcome'] == 'YES']
    print(f"\nWinning Trades (n={len(winners)}):")
    print(f"Avg Minimum Price after entry: {winners['min_post'].mean():.1f}¢")
    print(f"Minimum of Minimums: {winners['min_post'].min():.1f}¢")
    
    # Analysis of "Losers"
    losers = trades_df[trades_df['outcome'] == 'NO']
    print(f"\nLosing Trades (n={len(losers)}):")
    print(f"Avg Minimum Price after entry: {losers['min_post'].mean():.1f}¢")
    print(f"Max Price after entry (Did they almost win?): {losers['max_post'].max():.1f}¢")

if __name__ == "__main__":
    analyze_drawdown()
