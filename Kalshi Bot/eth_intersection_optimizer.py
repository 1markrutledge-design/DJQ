import pandas as pd
import numpy as np

def optimize_eth_intersection():
    df = pd.read_csv('market_history.csv')
    eth = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth.empty: return

    eth['t'] = pd.to_datetime(eth['timestamp'])
    eth['ct'] = pd.to_datetime(eth['close_time'])
    eth['rem'] = (eth['ct'] - eth['t']).dt.total_seconds()
    eth['price'] = eth['last_price'].fillna((pd.to_numeric(eth['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(eth['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in eth.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    print(f"Optimizing Time-Price Intersections for {len(results)} ETH markets...")

    stats = []
    # Test every price (50-90) at every minute (1-12)
    for price_target in range(50, 95, 5):
        for minute in range(2, 13):
            sec_target = minute * 60
            
            trades = []
            for ticker, group in eth.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                
                # Check if price hits Target when Time Remaining is <= Target
                match = group[(group['price'] >= price_target) & (group['rem'] <= sec_target)].sort_values('rem', ascending=False).head(1)
                
                if not match.empty:
                    trades.append(1 if outcome == 'YES' else 0)
            
            if len(trades) >= 10:
                win_rate = np.mean(trades)
                stats.append({'Price': price_target, 'Minute': minute, 'Trades': len(trades), 'WR': win_rate})

    s_df = pd.DataFrame(stats).sort_values('WR', ascending=False)
    print("\nTop Intersection Points:")
    print(s_df.head(15).to_string(index=False))

if __name__ == "__main__":
    optimize_eth_intersection()
