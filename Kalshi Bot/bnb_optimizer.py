import pandas as pd
import numpy as np

def optimize_bnb():
    df = pd.read_csv('market_history.csv')
    bnb = df[df['ticker'].str.contains('KXBNB15M', na=False)].copy()
    if bnb.empty: return

    bnb['t'] = pd.to_datetime(bnb['timestamp'])
    bnb['ct'] = pd.to_datetime(bnb['close_time'])
    bnb['rem'] = (bnb['ct'] - bnb['t']).dt.total_seconds() / 60.0
    bnb['price'] = bnb['last_price'].fillna((pd.to_numeric(bnb['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(bnb['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in bnb.groupby('ticker'):
        res = group['result'].dropna().unique()
        if len(res) > 0: results[ticker] = res[0].upper()

    print(f"Optimizing BNB for {len(results)} markets...")

    stats = []
    # Test different thresholds and time windows
    for threshold in [60, 65, 70, 75, 80, 85]:
        for window in [2, 5, 8, 10, 12]:
            trades = []
            for ticker, group in bnb.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                group = group.sort_values('t')
                
                # Check for YES trigger (Price >= threshold) within window (rem <= window)
                match_yes = group[(group['price'] >= threshold) & (group['rem'] <= window)].head(1)
                if not match_yes.empty:
                    trades.append(1 if outcome == 'YES' else 0)
                    continue # One trade per market
                
                # Check for NO trigger (Price <= 100-threshold) within window
                match_no = group[(group['price'] <= (100 - threshold)) & (group['rem'] <= window)].head(1)
                if not match_no.empty:
                    trades.append(1 if outcome == 'NO' else 0)

            if len(trades) >= 10:
                wr = np.mean(trades)
                stats.append({'Threshold': threshold, 'Window': window, 'Trades': len(trades), 'WR': wr})

    s_df = pd.DataFrame(stats).sort_values('WR', ascending=False)
    print("\n--- BNB STRATEGY PERFORMANCE ---")
    print(s_df.head(20).to_string(index=False))

if __name__ == "__main__":
    optimize_bnb()
