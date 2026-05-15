import pandas as pd
import numpy as np

def audit_btc_strategy():
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

    print(f"Auditing BTC Logic for {len(results)} markets...")

    # Strategy 1: Current "Barrier" Logic
    barrier_trades = []
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        barrier_count = 0
        triggered = False
        for i in range(len(group)):
            row = group.iloc[i]
            # First 10 mins (rem >= 5)
            if row['rem'] >= 5:
                if row['price'] <= 40:
                    barrier_count += 5 # Approx 5s per row
                
                if barrier_count >= 360 and row['price'] >= 60:
                    barrier_trades.append(1 if outcome == 'YES' else 0)
                    triggered = True
                    break
    
    if barrier_trades:
        print(f"Current Barrier Strategy: {len(barrier_trades)} trades, {np.mean(barrier_trades):.1%} WR")

    # Strategy 2: Simple High-Profit (Same as BNB 60c)
    simple_60 = []
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        # Cross 60c in final 8 mins
        match = group[(group['price'] >= 60) & (group['rem'] <= 8)].head(1)
        if not match.empty:
            simple_60.append(1 if outcome == 'YES' else 0)
            
    if simple_60:
        print(f"Simple 60c @ 8m Strategy: {len(simple_60)} trades, {np.mean(simple_60):.1%} WR")

    # Strategy 3: Acceleration Sniper (+8c in 15s)
    accel_trades = []
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        for i in range(1, len(group)):
            curr = group.iloc[i]
            prev = group.iloc[i-1]
            dt = (curr['t'] - prev['t']).total_seconds()
            dp = curr['price'] - prev['price']
            
            if 0 < dt <= 20 and dp >= 8:
                accel_trades.append(1 if outcome == 'YES' else 0)
                break
                
    if accel_trades:
        print(f"Acceleration (+8c Velocity): {len(accel_trades)} trades, {np.mean(accel_trades):.1%} WR")

if __name__ == "__main__":
    audit_btc_strategy()
