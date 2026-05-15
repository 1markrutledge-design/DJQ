import pandas as pd
import numpy as np

def analyze_eth_unique_patterns():
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

    print(f"Searching for unique patterns in {len(results)} ETH markets...")

    # Pattern 1: The "Pinch Break" (Consolidation before move)
    pinch_results = []
    for ticker, group in eth.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        # Look for 180s of low volatility (< 5c range)
        for i in range(len(group)):
            start_row = group.iloc[i]
            # Consolidation window: 3 mins
            window_end = start_row['t'] + pd.Timedelta(seconds=180)
            window = group[(group['t'] >= start_row['t']) & (group['t'] <= window_end)]
            if len(window) < 5: continue
            
            p_range = window['price'].max() - window['price'].min()
            if p_range <= 5: # Pinched!
                # Now look for a breakout in the next 60s
                breakout_start = window_end
                breakout_end = window_end + pd.Timedelta(seconds=60)
                breakout_window = group[(group['t'] > breakout_start) & (group['t'] <= breakout_end)]
                if breakout_window.empty: continue
                
                initial_p = window['price'].iloc[-1]
                final_p = breakout_window['price'].iloc[-1]
                move = final_p - initial_p
                
                if move >= 10: # Upside break
                    pinch_results.append({'action': 'YES', 'outcome': outcome})
                    break
                elif move <= -10: # Downside break
                    pinch_results.append({'action': 'NO', 'outcome': outcome})
                    break

    if pinch_results:
        p_df = pd.DataFrame(pinch_results)
        wr = (p_df['action'] == p_df['outcome']).mean()
        print(f"Pinch Break Strategy: {len(p_df)} trades, {wr:.1%} WR")

    # Pattern 2: Parabolic Reversal (The "Blowoff Top")
    # Logic: Price jumps 20c in 60s, then stalls. Fade it.
    fade_results = []
    for ticker, group in eth.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        for i in range(len(group)):
            start_row = group.iloc[i]
            window_end = start_row['t'] + pd.Timedelta(seconds=60)
            window = group[(group['t'] >= start_row['t']) & (group['t'] <= window_end)]
            if window.empty: continue
            
            move = window['price'].iloc[-1] - window['price'].iloc[0]
            if abs(move) >= 20: # Parabolic move
                # Check for "stall" (next 30s moves < 5c in same direction)
                stall_end = window_end + pd.Timedelta(seconds=30)
                stall_window = group[(group['t'] > window_end) & (group['t'] <= stall_end)]
                if stall_window.empty: continue
                
                stall_move = stall_window['price'].iloc[-1] - window['price'].iloc[-1]
                if (move > 0 and stall_move < 5) or (move < 0 and stall_move > -5):
                    side = 'NO' if move > 0 else 'YES'
                    fade_results.append({'action': side, 'outcome': outcome})
                    break

    if fade_results:
        f_df = pd.DataFrame(fade_results)
        wr = (f_df['action'] == f_df['outcome']).mean()
        print(f"Parabolic Fade Strategy: {len(f_df)} trades, {wr:.1%} WR")

if __name__ == "__main__":
    analyze_eth_unique_patterns()
