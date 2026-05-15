import pandas as pd
import numpy as np

def optimize_btc_intersection():
    df = pd.read_csv('market_history.csv')
    btc = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    if btc.empty: return

    btc['t'] = pd.to_datetime(btc['timestamp'])
    btc['ct'] = pd.to_datetime(btc['close_time'])
    btc['rem'] = (btc['ct'] - btc['t']).dt.total_seconds() / 60.0
    btc['price'] = btc['last_price'].fillna((pd.to_numeric(btc['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(btc['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in btc.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    stats = []
    for price_target in [60, 65, 70, 75, 80, 85]:
        for minute in range(2, 12):
            trades = []
            for ticker, group in btc.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                match = group[(group['price'] >= price_target) & (group['rem'] <= minute)].head(1)
                if not match.empty:
                    trades.append(1 if outcome == 'YES' else 0)
            
            if len(trades) >= 10:
                stats.append({'Price': price_target, 'Minute': minute, 'Trades': len(trades), 'WR': np.mean(trades)})

    s_df = pd.DataFrame(stats).sort_values('WR', ascending=False)
    print("\n--- BTC INTERSECTION POINTS ---")
    print(s_df.head(20).to_string(index=False))

if __name__ == "__main__":
    optimize_btc_intersection()
