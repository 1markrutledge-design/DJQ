import pandas as pd
import numpy as np

def generate_table_data():
    df = pd.read_csv('market_history.csv')
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0
    
    sectors = {
        'Bitcoin (BTC)': 'KXBTC15M',
        'BNB': 'KXBNB15M',
        'Solana (SOL)': 'KXSOL15M',
        'XRP': 'KXXRP15M'
    }
    
    print(f"{'Asset':<15} | {'Accuracy':<10} | {'Trades':<8} | {'Profit/Share'}")
    print("-" * 55)

    for name, series in sectors.items():
        sdf = df[df['ticker'].str.contains(series, na=False)].copy()
        if sdf.empty: continue
        
        outcomes = {}
        for ticker, group in sdf.groupby('ticker'):
            res = group['result'].dropna()
            if not res.empty: outcomes[ticker] = res.iloc[0]
            else:
                try:
                    lp = (float(group['yes_bid'].iloc[-1]) + float(group['yes_ask'].iloc[-1]))/2
                except: lp = 50
                if lp > 70: outcomes[ticker] = 'YES'
                elif lp < 30: outcomes[ticker] = 'NO'
        
        stats = []
        for ticker, group in sdf.groupby('ticker'):
            if ticker not in outcomes: continue
            out = outcomes[ticker]
            subset = group[(group['rem'] <= 6.0) & (group['rem'] >= 0.5)].sort_values('t')
            
            for _, row in subset.iterrows():
                try:
                    price = float(row['last_price'] or row['yes_bid'] or row['yes_ask'] or 0)
                except: price = 0
                if price >= 50:
                    stats.append(1 if out == 'YES' else 0)
                    break
        
        if stats:
            wr = np.mean(stats)
            profit_per_share = (wr * 50) - ((1 - wr) * 50)
            print(f"{name:<15} | {wr:<10.1%} | {len(stats):<8} | ${profit_per_share/100.0:+.2f}")

if __name__ == "__main__":
    generate_table_data()
