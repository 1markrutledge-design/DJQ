import pandas as pd
import numpy as np

def deep_dive_33():
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

    data = []
    for ticker, group in sol_df.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        
        # Check for first liquid price in the window (14m to 1m)
        liquid = group[group['yes_bid'].notna()]
        if liquid.empty: continue
        
        first_obs = liquid.iloc[0]
        
        data.append({
            'ticker': ticker,
            'outcome': results[ticker],
            'first_price': first_obs['price'],
            'time_rem': first_obs['rem']
        })

    stats_df = pd.DataFrame(data)
    print(f"Total Liquid Markets: {len(stats_df)}")
    
    # Threshold Search
    print("\n--- Optimized Breakout Search (for the 33 Liquid Markets) ---")
    for upper in [55, 60, 65, 70]:
        for lower in [30, 35, 40, 45]:
            trades = []
            for ticker, group in sol_df.groupby('ticker'):
                if ticker not in results: continue
                group = group.sort_values('t')
                subset = group[(group['rem'] >= 2) & (group['rem'] <= 14)]
                for _, row in subset.iterrows():
                    if row['price'] >= upper:
                        trades.append({'outcome': results[ticker], 'action': 'YES'})
                        break
                    elif row['price'] <= lower:
                        trades.append({'outcome': results[ticker], 'action': 'NO'})
                        break
            
            if trades:
                t_df = pd.DataFrame(trades)
                acc = (t_df['action'] == t_df['outcome']).mean()
                print(f"If > {upper}¢ or < {lower}¢: {len(t_df)}/33 trades, {acc:.1%} WR")

    # Let's see the 33 tickers
    print("\n--- The 33 Liquid Tickers & Results ---")
    print(stats_df[['ticker', 'outcome', 'first_price', 'time_rem']].sort_values('time_rem', ascending=False))

if __name__ == "__main__":
    deep_dive_33()
