import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings('ignore')

def analyze_btc_recent():
    print("Loading data...")
    df = pd.read_csv('market_history.csv')
    
    # Filter to only BTC 15M markets
    btc_df = df[df['ticker'].str.contains('KXBTC15M', na=False)].copy()
    if btc_df.empty: 
        print("No BTC markets found.")
        return

    # Parse timestamps
    btc_df['t'] = pd.to_datetime(btc_df['timestamp'], utc=True)
    
    # Filter to last 2 days of valid data
    valid_ts = btc_df.dropna(subset=['yes_bid', 'last_price'], how='all')['t']
    if valid_ts.empty:
        print("No valid price data found.")
        return
        
    max_ts = valid_ts.max()
    cutoff = max_ts - timedelta(days=2)
    btc_df = btc_df[btc_df['t'] >= cutoff]
    
    print(f"Data timeframe: {cutoff} to {max_ts}")
    
    # Calculate remaining time using max timestamp per ticker
    btc_df['ct'] = btc_df.groupby('ticker')['t'].transform('max')
    btc_df['rem'] = (btc_df['ct'] - btc_df['t']).dt.total_seconds() / 60.0
    btc_df['mid'] = (btc_df['yes_bid'].fillna(0) + btc_df['yes_ask'].fillna(100)) / 2.0
    btc_df['price'] = btc_df['last_price'].fillna(btc_df['mid'])

    # Get market outcomes
    results = {}
    for ticker, group in btc_df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty:
            results[ticker] = res.iloc[0].upper()
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'
            
    print(f"Analyzing {len(results)} total BTC markets over the last 2 days.\n")

    strategies = []
    
    # 1. Fixed Price Entry (YES)
    for p in [40, 50, 55, 60, 65, 70, 75]:
        strategies.append({
            'name': f'Fixed YES @ {p}¢ (Anytime)',
            'type': 'fixed',
            'side': 'YES',
            'threshold': p,
            'start_rem': 14.9,
            'end_rem': 0.1
        })
        
    for p in [40, 50, 55, 60, 65, 70, 75]:
        strategies.append({
            'name': f'Fixed YES @ {p}¢ (Window 8m-3m)',
            'type': 'fixed',
            'side': 'YES',
            'threshold': p,
            'start_rem': 8.0,
            'end_rem': 3.0
        })

    # 2. Reversion / Value Fades
    for p in [20, 25, 30]:
        strategies.append({
            'name': f'Value YES (Buy YES if price < {p}¢)',
            'type': 'fixed_value',
            'side': 'YES',
            'threshold': p,
            'start_rem': 12.0,
            'end_rem': 3.0
        })

    # 3. NO Value Fades
    for p in [70, 75, 80]:
        strategies.append({
            'name': f'Value NO (Buy NO if YES price > {p}¢)',
            'type': 'fixed_value_no',
            'side': 'NO',
            'threshold': p,
            'start_rem': 10.0,
            'end_rem': 2.0
        })

    # Evaluate strategies
    strat_results = []

    for strat in strategies:
        trades = 0
        wins = 0
        total_pnl = 0
        
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            
            # Sort by time
            g = group.sort_values('t')
            
            # Filter by allowed time window
            window = g[(g['rem'] <= strat['start_rem']) & (g['rem'] >= strat['end_rem'])]
            if window.empty: continue
            
            trigger_price = None
            
            if strat['type'] == 'fixed':
                # First time price >= threshold
                t_rows = window[window['price'] >= strat['threshold']]
                if not t_rows.empty:
                    # Execute trade at the ask if available, otherwise just use threshold
                    first_trigger = t_rows.iloc[0]
                    trigger_price = first_trigger['yes_ask'] if pd.notna(first_trigger['yes_ask']) else first_trigger['price']
                    if pd.isna(trigger_price) or trigger_price <= 0: trigger_price = strat['threshold']

            elif strat['type'] == 'fixed_value':
                t_rows = window[window['price'] <= strat['threshold']]
                if not t_rows.empty:
                    first_trigger = t_rows.iloc[0]
                    trigger_price = first_trigger['yes_ask'] if pd.notna(first_trigger['yes_ask']) else first_trigger['price']
                    if pd.isna(trigger_price) or trigger_price <= 0: trigger_price = strat['threshold']

            elif strat['type'] == 'fixed_value_no': # Buying NO -> cost is 100 - yes_bid
                t_rows = window[window['price'] >= strat['threshold']]
                if not t_rows.empty:
                    first_trigger = t_rows.iloc[0]
                    yes_bid = first_trigger['yes_bid'] if pd.notna(first_trigger['yes_bid']) else first_trigger['price']
                    if yes_bid is None or pd.isna(yes_bid): yes_bid = strat['threshold']
                    trigger_price = 100 - yes_bid
                    
            if trigger_price is not None:
                trades += 1
                if outcome == strat['side']:
                    wins += 1
                    total_pnl += (100 - trigger_price)
                else:
                    total_pnl -= trigger_price

        if trades > 0:
            win_rate = wins / trades
            avg_profit = total_pnl / trades
            strat_results.append({
                'Strategy': strat['name'],
                'Trades': trades,
                'Win Rate (%)': win_rate * 100.0,
                'Total PnL (cents)': total_pnl,
                'Profit per Share (cents)': avg_profit
            })

    # Sort and print results
    strat_results.sort(key=lambda x: x['Profit per Share (cents)'], reverse=True)
    
    print(f"{'Strategy':<45} | {'Trades':<6} | {'Win Rate':<9} | {'Profit/Share'}")
    print("-" * 80)
    for r in strat_results:
        print(f"{r['Strategy']:<45} | {r['Trades']:<6} | {r['Win Rate (%)']:5.1f}%    | {r['Profit per Share (cents)']:>5.1f}¢")

if __name__ == '__main__':
    analyze_btc_recent()
