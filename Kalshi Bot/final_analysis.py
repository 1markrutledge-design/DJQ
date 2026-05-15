import pandas as pd
import numpy as np

def analyze_v2():
    df = pd.read_csv('market_history.csv')
    print(f"Total rows in CSV: {len(df)}")
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0
    
    sectors = {'BTC': 'KXBTC15M', 'BNB': 'KXBNB15M', 'SOL': 'KXSOL15M', 'XRP': 'KXXRP15M'}
    
    for name, series in sectors.items():
        sdf = df[df['ticker'].str.contains(series, na=False)].copy()
        print(f"Analyzing {name}... {len(sdf)} rows.")
        if sdf.empty: continue
        
        outcomes = {}
        for ticker, group in sdf.groupby('ticker'):
            res = group['result'].dropna()
            if not res.empty: outcomes[ticker] = res.iloc[0]
            else:
                last_row = group.sort_values('t').iloc[-1]
                b = last_row.get('yes_bid', 0)
                a = last_row.get('yes_ask', 100)
                # handle potential object/string types
                try:
                    bv = float(b) if not pd.isna(b) else 0
                    av = float(a) if not pd.isna(a) else 100
                except:
                    bv, av = 0, 100
                lp = (bv + av)/2
                if lp > 70: outcomes[ticker] = 'YES'
                elif lp < 30: outcomes[ticker] = 'NO'

        print(f"Identified outcomes for {len(outcomes)} {name} markets.")

        for thresh in [40, 50, 60, 70, 80]:
            stats = []
            for ticker, group in sdf.groupby('ticker'):
                if ticker not in outcomes: continue
                out = outcomes[ticker]
                subset = group[(group['rem'] <= 10) & (group['rem'] >= 1)].sort_values('t')
                
                for _, row in subset.iterrows():
                    try:
                        ask = float(row.get('yes_ask')) if not pd.isna(row.get('yes_ask')) else None
                        bid = float(row.get('yes_bid')) if not pd.isna(row.get('yes_bid')) else None
                    except:
                        ask, bid = None, None
                        
                    # YES Fill
                    if ask is not None and ask <= thresh:
                        stats.append(1 if out == 'YES' else 0)
                        break
                    # NO Fill
                    if bid is not None and bid >= (100 - thresh):
                        stats.append(1 if out == 'NO' else 0)
                        break
            
            if stats:
                wr = np.mean(stats)
                ev = (wr * (100 - thresh)) - ((1 - wr) * thresh)
                print(f"  Thresh {thresh}c: n={len(stats)}, WR={wr:.1%}, EV={ev:+.1f}c")

if __name__ == "__main__":
    analyze_v2()
