import pandas as pd
import numpy as np

def find_highest_profit_eth():
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

    stats = []
    # Test entry prices from 10 to 90
    for entry_p in range(10, 95, 5):
        # Test side (YES)
        trades_yes = []
        for ticker, group in eth.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            # Entry: Price hits entry_p (Taker Ask)
            match = group[group['price'] <= entry_p].sort_values('rem', ascending=False).head(1)
            if not match.empty:
                cost = entry_p
                p_p_s = (100 - cost) if outcome == 'YES' else -cost
                trades_yes.append(p_p_s)
        
        if len(trades_yes) >= 10:
            stats.append({'Side': 'YES', 'Entry': entry_p, 'Profit/Share': np.mean(trades_yes), 'WR': (np.array(trades_yes)>0).mean(), 'Trades': len(trades_yes)})

        # Test side (NO)
        trades_no = []
        for ticker, group in eth.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            # Entry: Price hits (100 - entry_p) (Taker Bid)
            match = group[group['price'] >= (100 - entry_p)].sort_values('rem', ascending=False).head(1)
            if not match.empty:
                cost = entry_p
                p_p_s = (100 - cost) if outcome == 'NO' else -cost
                trades_no.append(p_p_s)
        
        if len(trades_no) >= 10:
            stats.append({'Side': 'NO', 'Entry': entry_p, 'Profit/Share': np.mean(trades_no), 'WR': (np.array(trades_no)>0).mean(), 'Trades': len(trades_no)})

    s_df = pd.DataFrame(stats).sort_values('Profit/Share', ascending=False)
    print("\n--- ETH HIGHEST PROFIT PER SHARE (RAW) ---")
    print(s_df.head(20).to_string(index=False))

if __name__ == "__main__":
    find_highest_profit_eth()
