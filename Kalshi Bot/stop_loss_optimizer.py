import pandas as pd
import numpy as np

def analyze_stop_loss():
    df = pd.read_csv('market_history.csv')
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0
    
    btc_df = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    
    outcomes = {}
    for ticker, group in btc_df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: outcomes[ticker] = res.iloc[0]
        else:
            lp = (group['yes_bid'].fillna(50).iloc[-1] + group['yes_ask'].fillna(50).iloc[-1])/2
            outcomes[ticker] = 'YES' if lp > 50 else 'NO'

    print(f"{'Stop Loss Type':<20} | {'Win Rate':<10} | {'EV/Share'}")
    print("-" * 50)

    for sl_drop in [None, 10, 20, 30]:
        stats = []
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in outcomes: continue
            out = outcomes[ticker]
            # Window 10 to 2 mins
            subset = group[(group['rem'] <= 10) & (group['rem'] >= 2)].sort_values('t')
            
            entry_price = 55
            filled = False
            hit_sl = False
            
            for i, row in subset.iterrows():
                p = row.get('yes_bid', 50)
                if not filled and p >= entry_price:
                    filled = True
                    continue
                
                if filled and sl_drop:
                    # If we dropped sl_drop cents below entry
                    if p <= (entry_price - sl_drop):
                        hit_sl = True
                        break
            
            if filled:
                if hit_sl:
                    stats.append(-sl_drop)
                else:
                    profit = (100 - entry_price) if out == 'YES' else -entry_price
                    stats.append(profit)
        
        if stats:
            wr = np.mean([1 for s in stats if s > 0])
            ev = np.mean(stats)
            sl_name = f"{sl_drop}c Drop" if sl_drop else "None (Full Hold)"
            print(f"{sl_name:<20} | {wr:<10.1%} | {ev:+.1f}c")

if __name__ == "__main__":
    analyze_stop_loss()
