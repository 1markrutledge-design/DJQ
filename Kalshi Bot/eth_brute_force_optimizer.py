import pandas as pd
import numpy as np
from datetime import datetime
import os

CSV_FILE = 'market_history.csv'

def optimize_eth():
    if not os.path.exists(CSV_FILE):
        print("CSV not found")
        return

    df = pd.read_csv(CSV_FILE)
    eth_df = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    btc_df = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    
    if eth_df.empty:
        print("No ETH data")
        return

    # Pre-process ETH
    eth_df['t'] = pd.to_datetime(eth_df['timestamp'])
    eth_df['rem'] = (pd.to_datetime(eth_df['close_time']) - eth_df['t']).dt.total_seconds()
    eth_df['yes_bid'] = pd.to_numeric(eth_df['yes_bid'], errors='coerce').fillna(0)
    eth_df['yes_ask'] = pd.to_numeric(eth_df['yes_ask'], errors='coerce').fillna(100)
    eth_df['price'] = eth_df['last_price'].fillna((eth_df['yes_bid'] + eth_df['yes_ask'])/2)
    
    # Pre-process BTC
    btc_df['t'] = pd.to_datetime(btc_df['timestamp'])
    btc_df['price'] = btc_df['last_price'].fillna((pd.to_numeric(btc_df['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(btc_df['yes_ask'], errors='coerce').fillna(100))/2)

    # Map Tickers to Outcomes
    results = {}
    for ticker, group in eth_df.groupby('ticker'):
        outcome = group['result'].dropna().unique()
        if len(outcome) > 0:
            results[ticker] = outcome[0].upper()
    
    print(f"Optimizing across {len(results)} ETH Markets...")

    top_strategies = []

    # 1. Parameter Sweep: ETH Price Breakout (Trend)
    for trigger in [60, 65, 70, 75, 80]:
        for min_rem in [120, 240, 360, 600]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                res = results[ticker]
                # Entry: Price hits trigger within timeframe
                match = group[(group['yes_bid'] >= trigger) & (group['rem'] <= min_rem)].sort_values('t').head(1)
                if not match.empty:
                    cost = match['yes_ask'].iloc[0]
                    pnl = (100 - cost) if res == 'YES' else -cost
                    trades.append(pnl)
            
            if len(trades) >= 10:
                top_strategies.append({
                    'Name': f"Breakout @ {trigger}c (<{min_rem}s left)",
                    'Trades': len(trades),
                    'WR': f"{(np.array(trades)>0).mean():.1%}",
                    'PnL': np.mean(trades)
                })

    # 2. Parameter Sweep: ETH Price Fade (Mean Reversion)
    for trigger in [75, 80, 85, 90, 95]:
        for min_rem in [120, 240, 360, 600]:
            trades = []
            for ticker, group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                res = results[ticker]
                # Entry: Price hits trigger, bet NO
                match = group[(group['yes_bid'] >= trigger) & (group['rem'] <= min_rem)].sort_values('t').head(1)
                if not match.empty:
                    cost = 100 - match['yes_bid'].iloc[0]
                    pnl = (100 - cost) if res == 'NO' else -cost
                    trades.append(pnl)
            
            if len(trades) >= 10:
                top_strategies.append({
                    'Name': f"Fade (Sell YES) @ {trigger}c (<{min_rem}s left)",
                    'Trades': len(trades),
                    'WR': f"{(np.array(trades)>0).mean():.1%}",
                    'PnL': np.mean(trades)
                })

    # 3. Parameter Sweep: BTC Shadow (Correlation)
    for btc_move_thresh in [3, 5, 8]:
        for btc_window in [15, 30, 60]:
            trades = []
            for ticker, eth_group in eth_df.groupby('ticker'):
                if ticker not in results: continue
                res = results[ticker]
                parts = ticker.split('-')
                if len(parts) < 2: continue
                wid = parts[1]
                
                btc_group = btc_df[btc_df['ticker'].str.contains(wid)].sort_values('t')
                if btc_group.empty: continue
                
                eth_group = eth_group.sort_values('t')
                
                triggered = False
                for i in range(1, len(btc_group)):
                    for j in range(i-1, -1, -1):
                        if (btc_group.iloc[i]['t'] - btc_group.iloc[j]['t']).total_seconds() <= btc_window:
                            move = btc_group.iloc[i]['price'] - btc_group.iloc[j]['price']
                            if abs(move) >= btc_move_thresh:
                                # BTC moved! Find ETH at same time
                                target_t = btc_group.iloc[i]['t']
                                eth_match = eth_group[abs((eth_group['t'] - target_t).dt.total_seconds()) < 15].head(1)
                                if not eth_match.empty:
                                    if move > 0: # Buy YES
                                        cost = eth_match['yes_ask'].iloc[0]
                                        pnl = (100-cost) if res == 'YES' else -cost
                                    else: # Buy NO
                                        cost = 100 - eth_match['yes_bid'].iloc[0]
                                        pnl = (100-cost) if res == 'NO' else -cost
                                    trades.append(pnl)
                                    triggered = True; break
                        if triggered: break
                    if triggered: break
            
            if len(trades) >= 10:
                top_strategies.append({
                    'Name': f"BTC Shadow (Move {btc_move_thresh}c in {btc_window}s)",
                    'Trades': len(trades),
                    'WR': f"{(np.array(trades)>0).mean():.1%}",
                    'PnL': np.mean(trades)
                })

    # Output top 10 results
    top_strategies.sort(key=lambda x: x['PnL'], reverse=True)
    print("\n--- TOP 15 OPTIMIZED STRATEGIES FOR ETH ---")
    print(pd.DataFrame(top_strategies).head(15).to_string(index=False))

if __name__ == "__main__":
    optimize_eth()
