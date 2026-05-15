import pandas as pd
import numpy as np

def analyze_sol_anytime():
    df = pd.read_csv('market_history.csv')
    sol_df = df[df['ticker'].str.contains('KXSOL15M', na=False)].copy()
    if sol_df.empty: return

    sol_df['t'] = pd.to_datetime(sol_df['timestamp'])
    sol_df['ct'] = pd.to_datetime(sol_df['close_time'])
    sol_df['rem'] = (sol_df['ct'] - sol_df['t']).dt.total_seconds() / 60.0
    
    sol_df['mid'] = (sol_df['yes_bid'].fillna(0) + sol_df['yes_ask'].fillna(100)) / 2.0
    sol_df['price'] = sol_df['last_price'].fillna(sol_df['mid'])
    
    results = {}
    for ticker, group in sol_df.groupby('ticker'):
        outcome = group['result'].dropna()
        if not outcome.empty:
            results[ticker] = outcome.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print(f"Outcome identified for {len(results)} total SOL tickers.")

    all_trades = []
    # Test Strategy: Bet on the TREND as soon as it clears a threshold
    # Look at any time between 15m and 2m remaining
    for ticker, group in sol_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Check every row in the market's lifetime
        # Only take the FIRST trigger for each ticker
        subset = group[(group['rem'] >= 2) & (group['rem'] <= 14)]
        
        for _, row in subset.iterrows():
            if row['price'] >= 60:
                all_trades.append({'ticker': ticker, 'outcome': outcome, 'action': 'YES', 'time_left': row['rem']})
                break
            elif row['price'] <= 40:
                all_trades.append({'ticker': ticker, 'outcome': outcome, 'action': 'NO', 'time_left': row['rem']})
                break
                
    trades_df = pd.DataFrame(all_trades)
    print(f"Total Triggers for SOL only: {len(trades_df)} / {len(results)}")
    
    if not trades_df.empty:
        accuracy = (trades_df['action'] == trades_df['outcome']).mean()
        print(f"Overall Accuracy: {accuracy:.1%}")
        
        # Breakdown by trigger time
        trades_df['early'] = trades_df['time_left'] > 10
        trades_df['middle'] = (trades_df['time_left'] <= 10) & (trades_df['time_left'] > 5)
        trades_df['late'] = trades_df['time_left'] <= 5
        
        for stage in ['early', 'middle', 'late']:
            s_df = trades_df[trades_df[stage]]
            if not s_df.empty:
                s_acc = (s_df['action'] == s_df['outcome']).mean()
                print(f"- {stage}: {len(s_df)} trades, {s_acc:.1%} WR")

if __name__ == "__main__":
    analyze_sol_anytime()
