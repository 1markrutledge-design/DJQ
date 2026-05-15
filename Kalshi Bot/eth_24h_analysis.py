import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

def analyze_eth_last_24h():
    df = pd.read_csv('market_history.csv')
    eth = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth.empty: return

    eth['t'] = pd.to_datetime(eth['timestamp'], utc=True)
    
    # Filter for last 24 hours
    now = eth['t'].max()
    yesterday = now - timedelta(hours=24)
    eth_recent = eth[eth['t'] >= yesterday].copy()
    
    if eth_recent.empty:
        print("No ETH data found in the last 24 hours.")
        return

    eth_recent['ct'] = pd.to_datetime(eth_recent['close_time'], utc=True)
    eth_recent['rem'] = (eth_recent['ct'] - eth_recent['t']).dt.total_seconds() / 60.0
    eth_recent['price'] = eth_recent['last_price'].fillna((pd.to_numeric(eth_recent['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(eth_recent['yes_ask'], errors='coerce').fillna(100))/2)

    results = {}
    for ticker, group in eth_recent.groupby('ticker'):
        # Determine result by looking at final recorded price
        res = group['result'].dropna()
        if not res.empty: 
            results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print(f"Analyzing {len(results)} ETH markets from last 24h...")

    stats = []
    # Test different strategies for ETH in the last 24h
    for threshold in [40, 50, 60, 70, 80]:
        for window in [2, 5, 8, 12]:
            trades = []
            for ticker, group in eth_recent.groupby('ticker'):
                if ticker not in results: continue
                outcome = results[ticker]
                
                # Check for Breakout (Trend Following)
                match = group[(group['price'] >= threshold) & (group['rem'] <= window)].head(1)
                if not match.empty:
                    trades.append(1 if outcome == 'YES' else 0)
            
            if len(trades) >= 5:
                stats.append({'Threshold': threshold, 'Window': window, 'Trades': len(trades), 'WR': np.mean(trades)})
    
    s_df = pd.DataFrame(stats).sort_values('WR', ascending=False)
    print("\n--- ETH RECENT TREND PERFORMANCE ---")
    print(s_df.head(15).to_string(index=False))

    # Test "Phoenix" (Dip Buying)
    phoenix_trades = []
    for ticker, group in eth_recent.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        # Hits 25c between 3-10m
        match = group[(group['price'] <= 30) & (group['rem'] >= 3) & (group['rem'] <= 10)].head(1)
        if not match.empty:
            phoenix_trades.append(1 if outcome == 'YES' else 0)
    
    if phoenix_trades:
        print(f"\nETH Phoenix Test (25c Dip): {len(phoenix_trades)} trades, {np.mean(phoenix_trades):.1%} WR")

    # Test "Fade" (Reversion)
    fade_trades = []
    for ticker, group in eth_recent.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        # Hits 85c between 6-12m
        match = group[(group['price'] >= 85) & (group['rem'] >= 6)].head(1)
        if not match.empty:
            fade_trades.append(1 if outcome == 'NO' else 0)
            
    if fade_trades:
        print(f"ETH Fade Test (85c Reject): {len(fade_trades)} trades, {np.mean(fade_trades):.1%} WR")

if __name__ == "__main__":
    analyze_eth_last_24h()
