import pandas as pd
import numpy as np

def optimize_xrp():
    df = pd.read_csv('market_history.csv')
    xrp_df = df[df['ticker'].str.contains('KXXRP15M', na=False)].copy()
    if xrp_df.empty:
        print("No XRP data found.")
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
            if isinstance(val, str):
                results[ticker] = val
            else:
                results[ticker] = 'YES' if val > 0 else 'NO'
        else:
            group = group.sort_values('t')
            lp = group['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'
            else: continue # Skip if outcome is ambiguous

    print(f"XRP Outcome identified for {len(results)} tickers.")

    best_wr = 0
    best_strategy = None
    
    # Grid search for thresholds
    thresholds = [55, 60, 65, 70, 75, 80]
    windows = [(12, 2), (10, 2), (8, 2), (5, 2), (12, 5), (10, 5)]
    
    print("\n--- Strategy Exploration (XRP) ---")
    print(f"{'Threshold':<10} | {'Window':<10} | {'Trades':<10} | {'Win Rate':<10}")
    print("-" * 75)
    
    for thresh in thresholds:
        for start_rem, end_rem in windows:
            trades = []
            for ticker, group in xrp_df.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                group = group.sort_values('t')
                
                subset = group[(group['rem'] >= end_rem) & (group['rem'] <= start_rem)]
                for _, row in subset.iterrows():
                    # Check YES case
                    if row['price'] >= thresh:
                        trades.append({'ticker': ticker, 'action': 'YES', 'outcome': outcome})
                        break
                    # Check NO case
                    elif row['price'] <= (100 - thresh):
                        trades.append({'ticker': ticker, 'action': 'NO', 'outcome': outcome})
                        break
            
            if trades:
                t_df = pd.DataFrame(trades)
                wr = (t_df['action'] == t_df['outcome']).mean()
                
                yes_trades = t_df[t_df['action'] == 'YES']
                no_trades = t_df[t_df['action'] == 'NO']
                
                yes_wr = (yes_trades['action'] == yes_trades['outcome']).mean() if not yes_trades.empty else 0
                no_wr = (no_trades['action'] == no_trades['outcome']).mean() if not no_trades.empty else 0
                
                print(f"{thresh:<10} | {f'{start_rem}-{end_rem}m':<10} | {len(t_df):<10} | {wr:.1%} (Y:{yes_wr:.0%}, N:{no_wr:.0%})")
                if wr >= best_wr and len(t_df) >= 10:
                    best_wr = wr
                    best_strategy = (thresh, start_rem, end_rem, len(t_df), wr, yes_wr, no_wr)

    print("\n--- Best Found Strategy ---")
    if best_strategy:
        thresh, start_rem, end_rem, n, wr, y_wr, n_wr = best_strategy
        print(f"Threshold: {thresh}, Window: {start_rem}-{end_rem}m, Trades: {n}, WR: {wr:.1%} (Y:{y_wr:.0%}, N:{n_wr:.0%})")
    else:
        print("No strategy met the minimum trade count.")

if __name__ == "__main__":
    optimize_xrp()
