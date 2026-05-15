import pandas as pd
import numpy as np

def analyze_history():
    df = pd.read_csv('market_history.csv')
    sol_df = df[df['ticker'].str.contains('KXSOL15M', na=False)].copy()
    if sol_df.empty: return

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

    all_trades = []
    # Test Strategy: Bet toward the end of the market (most data here)
    for ticker, group in sol_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Check for observation near 3 minutes remaining
        window = group[(group['rem'] >= 2.5) & (group['rem'] <= 4.0)]
        if window.empty: continue
        
        obs = window.iloc[0]
        price = obs['price']
        
        all_trades.append({
            'ticker': ticker,
            'outcome': outcome,
            'price': price
        })

    trades_df = pd.DataFrame(all_trades)
    print(f"Total Tickers with observations at 3m remaining: {len(trades_df)}")

    for thr in [40, 50, 60, 70, 80]:
        yes_trades = trades_df[trades_df['price'] > thr]
        if not yes_trades.empty:
            win_rate = (yes_trades['outcome'] == 'YES').mean()
            print(f"If Price > {thr}¢ at 3m: {len(yes_trades)} trades, {win_rate:.1%} Win Rate")

    # The "Every Opportunity" Strategy
    # If price > 55, Bet YES. If price < 45, Bet NO.
    # Check trigger at ANY time between 5m and 1m remaining.
    anytime_trades = []
    for ticker, group in sol_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        
        # First observation between 5m and 1m
        window = group[(group['rem'] >= 1.0) & (group['rem'] <= 5.0)]
        if window.empty: continue
        
        obs = window.sort_values('t').iloc[0]
        price = obs['price']
        
        action = None
        if price >= 55: action = 'YES'
        elif price <= 45: action = 'NO'
        
        if action:
            anytime_trades.append({'outcome': outcome, 'action': action})

    any_df = pd.DataFrame(anytime_trades)
    accuracy = (any_df['action'] == any_df['outcome']).mean()
    print(f"\nAnytime Trend Strategy (5m-1m remaining):")
    print(f"Total Trades: {len(any_df)} / 213")
    print(f"Accuracy: {accuracy:.1%}")
    
    # Let's see YES vs NO accuracy
    y_acc = (any_df[any_df['action'] == 'YES']['outcome'] == 'YES').mean()
    n_acc = (any_df[any_df['action'] == 'NO']['outcome'] == 'NO').mean()
    print(f"YES Accuracy: {y_acc:.1%} (n={len(any_df[any_df['action']=='YES'])})")
    print(f"NO Accuracy: {n_acc:.1%} (n={len(any_df[any_df['action']=='NO'])})")

if __name__ == "__main__":
    analyze_history()
