import pandas as pd
import numpy as np

def analyze_high_freq():
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
            if lp > 50: outcomes[ticker] = 'YES'
            else: outcomes[ticker] = 'NO'
            
    print(f"Testing High-Frequency Strategies on {len(outcomes)} BTC Markets...")
    
    strategies = [
        # Strategy name, Trigger, Logic (YES=bet with move, NO=bet against)
        ('Trend Follow 60/40', 60, 'F'),
        ('Trend Fade 60/40', 60, 'C'),
        ('Quick Trend 55/45', 55, 'F'),
        ('Quick Fade 55/45', 55, 'C'),
        ('Value Scoop 30/70', 30, 'F'), # Buy YES at 30? (Means bet with recovery)
    ]
    
    for name, thresh, mode in strategies:
        trades = []
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in outcomes: continue
            out = outcomes[ticker]
            
            # Hunting Window: Minute 10 to 2 (15 to 13 m left? no)
            # 15m market. 15-5 = 10 mins remaining.
            subset = group[(group['rem'] <= 12) & (group['rem'] >= 2)].sort_values('t')
            
            found = False
            for _, row in subset.iterrows():
                p = (row['yes_bid'] or 50) 
                
                # YES Move
                if p >= thresh:
                    action = 'YES' if mode == 'F' else 'NO'
                    price = thresh # Approximate
                    trades.append(1 if action == out else 0)
                    found = True; break
                # NO Move
                elif p <= (100 - thresh):
                    action = 'NO' if mode == 'F' else 'YES'
                    price = thresh # Approximate
                    trades.append(1 if action == out else 0)
                    found = True; break
        
        if trades:
            wr = np.mean(trades)
            # Profit per share assuming entry at 'thresh'
            cost = thresh
            ev = (wr * (100 - cost)) - ((1 - wr) * cost)
            print(f"{name:<20}: n={len(trades):<4} | WR={wr:.1%} | EV={ev:+.1f}c/share")

if __name__ == "__main__":
    analyze_high_freq()
