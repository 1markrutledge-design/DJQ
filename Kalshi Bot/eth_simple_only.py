import pandas as pd
import numpy as np
import os

CSV_FILE = 'market_history.csv'

def find_simple_eth_only():
    if not os.path.exists(CSV_FILE): return
    df = pd.read_csv(CSV_FILE)
    eth_df = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    
    eth_df['t'] = pd.to_datetime(eth_df['timestamp'])
    eth_df['rem'] = (pd.to_datetime(eth_df['close_time']) - eth_df['t']).dt.total_seconds()
    eth_df['yes_bid'] = pd.to_numeric(eth_df['yes_bid'], errors='coerce').fillna(0)
    eth_df['yes_ask'] = pd.to_numeric(eth_df['yes_ask'], errors='coerce').fillna(100)
    
    results = {}
    for ticker, group in eth_df.groupby('ticker'):
        outcome = group['result'].dropna().unique()
        if len(outcome) > 0: results[ticker] = outcome[0].upper()

    simple_stats = []

    # Strategy A: Simple "Lotto" Fade
    # If price hits 90c, buy NO (for ~10c)
    for thresh in [80, 85, 90, 95]:
        for time_gate in [60, 120, 240, 360, 600]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                match = group[(group['yes_bid'] >= thresh) & (group['rem'] <= time_gate)].sort_values('t').head(1)
                if not match.empty:
                    cost = 100 - match['yes_bid'].iloc[0]
                    pnl = (100 - cost) if results[ticker] == 'NO' else -cost
                    trades.append(pnl)
            if len(trades) >= 5:
                simple_stats.append({'Strategy': f"Fade @ {thresh}c in last {time_gate}s", 'Trades': len(trades), 'Profit/Share': np.mean(trades)})

    # Strategy B: Simple Breakout
    for thresh in [60, 70, 80]:
        for time_gate in [120, 240, 360, 600]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                match = group[(group['yes_bid'] >= thresh) & (group['rem'] <= time_gate)].sort_values('t').head(1)
                if not match.empty:
                    cost = match['yes_ask'].iloc[0]
                    pnl = (100 - cost) if results[ticker] == 'YES' else -cost
                    trades.append(pnl)
            if len(trades) >= 5:
                simple_stats.append({'Strategy': f"Breakout @ {thresh}c in last {time_gate}s", 'Trades': len(trades), 'Profit/Share': np.mean(trades)})

    df_res = pd.DataFrame(simple_stats).sort_values('Profit/Share', ascending=False)
    print(df_res.head(10).to_string(index=False))

if __name__ == "__main__":
    find_simple_eth_only()
