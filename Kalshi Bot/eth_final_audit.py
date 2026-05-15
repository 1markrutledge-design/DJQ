import pandas as pd
import numpy as np
from datetime import datetime
import os

CSV_FILE = 'market_history.csv'

def final_audit():
    if not os.path.exists(CSV_FILE):
        print("CSV not found")
        return

    df = pd.read_csv(CSV_FILE)
    eth_df = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth_df.empty:
        print("No ETH data")
        return

    eth_df['t'] = pd.to_datetime(eth_df['timestamp'])
    eth_df['ct'] = pd.to_datetime(eth_df['close_time'])
    eth_df['rem'] = (eth_df['ct'] - eth_df['t']).dt.total_seconds()
    
    # Fill prices
    eth_df['yes_bid'] = pd.to_numeric(eth_df['yes_bid'], errors='coerce').fillna(0)
    eth_df['yes_ask'] = pd.to_numeric(eth_df['yes_ask'], errors='coerce').fillna(100)
    eth_df['last_price'] = pd.to_numeric(eth_df['last_price'], errors='coerce').fillna((eth_df['yes_bid'] + eth_df['yes_ask'])/2)
    
    results = {}
    for ticker, group in eth_df.groupby('ticker'):
        outcome = group['result'].dropna().unique()
        if len(outcome) > 0:
            results[ticker] = outcome[0].upper()
        else:
            # Fallback if result missing
            final_p = group.sort_values('t')['last_price'].iloc[-1]
            if final_p > 70: results[ticker] = 'YES'
            elif final_p < 30: results[ticker] = 'NO'

    print(f"Analyzing {len(results)} ETH Markets...")

    # Strategy 1: The Breakout (Current Bot)
    # Buy @ 80, SL @ 40
    trades_1 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        group = group.sort_values('t')
        
        entry = group[group['yes_bid'] >= 80].head(1)
        if not entry.empty:
            entry_p = entry['yes_ask'].iloc[0]
            # Monitor for SL
            post_entry = group[group['t'] > entry['t'].iloc[0]]
            sl = post_entry[post_entry['yes_bid'] <= 40].head(1)
            
            if not sl.empty:
                pnl = - (entry_p - 40)
            else:
                pnl = 100 - entry_p if res == 'YES' else -entry_p
            trades_1.append(pnl)

    # Strategy 2: Simple Fade
    # Sell YES (Buy NO) at 80
    trades_2 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        group = group.sort_values('t')
        
        entry = group[group['yes_bid'] >= 80].head(1)
        if not entry.empty:
            # We buy NO. Cost = 100 - yes_bid
            cost = 100 - entry['yes_bid'].iloc[0]
            pnl = (100 - cost) if res == 'NO' else -cost
            trades_2.append(pnl)

    # Strategy 3: Scaling Fade
    # Buy NO at 80, 85, 90, 95 (1, 2, 3, 4 units)
    trades_3 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        group = group.sort_values('t')
        
        pnl = 0
        shares = 0
        spent = 0
        triggered = False
        for threshold in [80, 85, 90, 95]:
            entry = group[group['yes_bid'] >= threshold].head(1)
            if not entry.empty:
                triggered = True
                qty = (threshold-75)//5 # 1, 2, 3, 4
                cost = 100 - entry['yes_bid'].iloc[0]
                spent += qty * cost
                shares += qty
        
        if triggered:
            if res == 'NO': pnl = (shares * 100) - spent
            else: pnl = -spent
            trades_3.append(pnl/shares if shares > 0 else 0)

    # Strategy 4: Late Scaling Fade (Only in final 6 mins)
    trades_4 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        group = group.sort_values('t')
        
        pnl = 0
        shares = 0
        spent = 0
        triggered = False
        for threshold in [80, 85, 90, 95]:
            # Must be >= threshold AND rem <= 360
            entry = group[(group['yes_bid'] >= threshold) & (group['rem'] <= 360)].head(1)
            if not entry.empty:
                triggered = True
                qty = (threshold-75)//5
                cost = 100 - entry['yes_bid'].iloc[0]
                spent += qty * cost
                shares += qty
        
        if triggered:
            if res == 'NO': pnl = (shares * 100) - spent
            else: pnl = -spent
            trades_4.append(pnl/shares if shares > 0 else 0)

    # Strategy 5: The ETH Shadow (Following BTC)
    time_windows = {}
    
    # Pre-process BTC data
    btc_df = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    btc_df['t'] = pd.to_datetime(btc_df['timestamp'])
    btc_df['last_price'] = pd.to_numeric(btc_df['last_price'], errors='coerce').fillna((pd.to_numeric(btc_df['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(btc_df['yes_ask'], errors='coerce').fillna(100))/2)
    
    trades_5 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        parts = ticker.split('-')
        if len(parts) < 2: continue
        wid = parts[1] # Time window
        
        # Get BTC for same window
        btc_group = btc_df[btc_df['ticker'].str.contains(wid)]
        if btc_group.empty: continue
        
        btc_group = btc_group.sort_values('t')
        eth_group = group.sort_values('t')
        
        triggered = False
        for i in range(1, len(btc_group)):
            for j in range(i-1, -1, -1):
                if (btc_group.iloc[i]['t'] - btc_group.iloc[j]['t']).total_seconds() <= 30:
                    btc_move = btc_group.iloc[i]['last_price'] - btc_group.iloc[j]['last_price']
                    if abs(btc_move) >= 5:
                        # BTC moved! Check ETH
                        target_t = btc_group.iloc[i]['t']
                        eth_entry = eth_group[abs((eth_group['t'] - target_t).dt.total_seconds()) < 10].head(1)
                        if not eth_entry.empty:
                            if btc_move >= 5: # Follow Up
                                cost = eth_entry['yes_ask'].iloc[0]
                                pnl = (100 - cost) if res == 'YES' else -cost
                                trades_5.append(pnl)
                            else: # Follow Down
                                cost = 100 - eth_entry['yes_bid'].iloc[0]
                                pnl = (100 - cost) if res == 'NO' else -cost
                                trades_5.append(pnl)
                            triggered = True
                            break
                if triggered: break
            if triggered: break

    # Strategy 6: ETH Late Surge
    # Jump above 60c after spending 6+ mins below 40c
    trades_6 = []
    for ticker, group in eth_df.groupby('ticker'):
        if ticker not in results: continue
        res = results[ticker]
        group = group.sort_values('t')
        
        # Condition: Look for first time price > 60
        entry = group[group['yes_bid'] >= 60].head(1)
        if not entry.empty:
            entry_t = entry['t'].iloc[0]
            # Check history before entry_t
            pre_entry = group[group['t'] < entry_t]
            if not pre_entry.empty:
                # Did it spend 6 mins below 40?
                below_40 = pre_entry[pre_entry['yes_ask'] <= 40]
                if not below_40.empty:
                    duration = (below_40['t'].iloc[-1] - below_40['t'].iloc[0]).total_seconds()
                    if duration >= 360:
                        cost = entry['yes_ask'].iloc[0]
                        pnl = (100 - cost) if res == 'YES' else -cost
                        trades_6.append(pnl)

    print("\n--- ETH STRATEGY COMPARISON ---")
    def stats(trades, name):
        if not trades: return
        t = np.array(trades)
        print(f"{name:25}: {len(t)} trades, PnL/Trade: {t.mean():.2f}c, Total: ${t.sum()/100:.2f}")

    stats(trades_1, "Breakout (Current Bot)")
    stats(trades_2, "Simple Fade @ 80")
    stats(trades_3, "Scaling Fade")
    stats(trades_4, "Late Scaling Fade (6m)")
    stats(trades_5, "ETH Shadow (BTC-Led)")
    stats(trades_6, "ETH Late Surge (BTC Pattern)")

if __name__ == "__main__":
    final_audit()
