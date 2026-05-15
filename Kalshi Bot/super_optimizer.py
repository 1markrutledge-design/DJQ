import pandas as pd
import numpy as np

def deep_optimize_all():
    df = pd.read_csv('market_history.csv')
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0
    
    # 7 Crypto Series
    series_list = ['KXBTC15M', 'KXBNB15M', 'KXETH15M', 'KXSOL15M', 'KXXRP15M', 'KXDOGE15M', 'KXHYPE15M']
    
    results = []
    
    for series in series_list:
        sdf = df[df['ticker'].str.contains(series, na=False)].copy()
        if sdf.empty: continue
        
        # Outcomes identification
        outcomes = {}
        for ticker, group in sdf.groupby('ticker'):
            res = group['result'].dropna()
            if not res.empty: outcomes[ticker] = res.iloc[0]
            else:
                lp = (group['yes_bid'].fillna(0).iloc[-1] + group['yes_ask'].fillna(100).iloc[-1])/2
                if lp > 70: outcomes[ticker] = 'YES'
                elif lp < 30: outcomes[ticker] = 'NO'
        
        if not outcomes: continue
        
        # Search for best (Thresh, Window)
        best_ev = -999
        best_cfg = None
        
        for thresh in [30, 40, 50, 60, 70]:
            for win_start in [10, 8, 6, 4]:
                stats = []
                for ticker, group in sdf.groupby('ticker'):
                    if ticker not in outcomes: continue
                    out = outcomes[ticker]
                    subset = group[(group['rem'] <= win_start) & (group['rem'] >= 0.5)].sort_values('t')
                    
                    found = False
                    for _, row in subset.iterrows():
                        # We use mid-price to approximate trigger fill
                        price = (row['yes_bid'] + row['yes_ask']) / 2 if (pd.notna(row['yes_bid']) and pd.notna(row['yes_ask'])) else row['last_price']
                        if pd.isna(price): continue
                        
                        if price >= thresh:
                            stats.append(1 if out == 'YES' else 0)
                            found = True; break
                
                if len(stats) >= 10:
                    wr = np.mean(stats)
                    # Expected Profit per trade = (WR * (100-thresh)) - ((1-WR) * thresh)
                    ev = (wr * (100 - thresh)) - ((1 - wr) * thresh)
                    if ev > best_ev:
                        best_ev = ev
                        best_cfg = {'thresh': thresh, 'win': win_start, 'n': len(stats), 'wr': wr, 'ev': ev}
        
        if best_cfg:
            results.append({
                'Asset': series.replace('KX', '').replace('15M', ''),
                'Threshold': best_cfg['thresh'],
                'Window': f"Final {best_cfg['win']}m",
                'Win Rate': f"{best_cfg['wr']:.1%}",
                'Trades': best_cfg['n'],
                'EV_Cents': round(best_cfg['ev'], 1)
            })

    # Sort by EV
    sorted_res = sorted(results, key=lambda x: x['EV_Cents'], reverse=True)
    
    print(f"{'Asset':<10} | {'Thresh':<6} | {'Win Rate':<8} | {'EV/Trade'}")
    print("-" * 45)
    for r in sorted_res:
        print(f"{r['Asset']:<10} | {r['Threshold']:<6} | {r['Win Rate']:<8} | {r['EV_Cents']:+.1f}c")

if __name__ == "__main__":
    deep_optimize_all()
