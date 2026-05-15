import pandas as pd
import numpy as np
import os

CSV_FILE = 'market_history.csv'

def god_mode_eth_search():
    if not os.path.exists(CSV_FILE): return
    df = pd.read_csv(CSV_FILE)
    eth_df = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    
    eth_df['t'] = pd.to_datetime(eth_df['timestamp'])
    eth_df['rem'] = (pd.to_datetime(eth_df['close_time']) - eth_df['t']).dt.total_seconds()
    eth_df['yes_bid'] = pd.to_numeric(eth_df['yes_bid'], errors='coerce').fillna(0)
    eth_df['yes_ask'] = pd.to_numeric(eth_df['yes_ask'], errors='coerce').fillna(100)
    eth_df['price'] = eth_df['last_price'].fillna((eth_df['yes_bid'] + eth_df['yes_ask'])/2)
    
    results = {}
    for ticker, group in eth_df.groupby('ticker'):
        outcome = group['result'].dropna().unique()
        if len(outcome) > 0: results[ticker] = outcome[0].upper()

    all_strats = []

    # 1. Exhaustive Fade Search
    for thresh in range(70, 99, 2):
        for time_gate in [60, 120, 180, 240, 300, 360, 480, 600]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                match = group[(group['yes_bid'] >= thresh) & (group['rem'] <= time_gate)].sort_values('t').head(1)
                if not match.empty:
                    cost = 100 - match['yes_bid'].iloc[0]
                    pnl = (100 - cost) if results[ticker] == 'NO' else -cost
                    trades.append(pnl)
            if len(trades) >= 10:
                all_strats.append({'Name': f"Fade @ {thresh}c (<{time_gate}s)", 'Trades': len(trades), 'Profit': np.mean(trades)})

    # 2. Velocity Fade Search
    for jump in [5, 10, 15]:
        for window in [15, 30, 60]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                res = results[ticker]
                group = group.sort_values('t')
                found = False
                for i in range(1, len(group)):
                    for j in range(i-1, -1, -1):
                        if (group.iloc[i]['t'] - group.iloc[j]['t']).total_seconds() <= window:
                            if group.iloc[i]['price'] - group.iloc[j]['price'] >= jump:
                                # PRICE JUMPED! Fade it.
                                cost = 100 - group.iloc[i]['yes_bid']
                                pnl = (100-cost) if res == 'NO' else -cost
                                trades.append(pnl)
                                found = True; break
                        else: break
                    if found: break
            if len(trades) >= 10:
                all_strats.append({'Name': f"Fade ETH Velocity ({jump}c/{window}s)", 'Trades': len(trades), 'Profit': np.mean(trades)})

    # 3. Underdog Sniper (Buying at < 15c)
    for thresh in [5, 10, 15, 20]:
        trades = []
        for ticker, group in eth_df.groupby('ticker'):
            if ticker not in results: continue
            match = group[group['yes_ask'] <= thresh].head(1)
            if not match.empty:
                cost = match['yes_ask'].iloc[0]
                pnl = (100 - cost) if results[ticker] == 'YES' else -cost
                trades.append(pnl)
        if len(trades) >= 10:
            all_strats.append({'Name': f"Underdog YES @ {thresh}c", 'Trades': len(trades), 'Profit': np.mean(trades)})

    res_df = pd.DataFrame(all_strats).sort_values('Profit', ascending=False)
    print(res_df.head(20).to_string(index=False))

if __name__ == "__main__":
    god_mode_eth_search()
