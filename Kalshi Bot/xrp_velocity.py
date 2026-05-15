import pandas as pd
import numpy as np

def analyze_xrp_velocity():
    df = pd.read_csv('market_history.csv')
    xrp = df[df['ticker'].str.contains('KXXRP15M')].copy()
    if xrp.empty:
        return
        
    xrp['t'] = pd.to_datetime(xrp['timestamp'])
    xrp['ct'] = pd.to_datetime(xrp['close_time'])
    xrp['rem'] = (xrp['ct'] - xrp['t']).dt.total_seconds() / 60.0
    
    # Fill price: prioritize last_price, then mid
    xrp['mid'] = (xrp['yes_bid'].fillna(0) + xrp['yes_ask'].fillna(100)) / 2.0
    xrp['price'] = xrp['last_price'].fillna(xrp['mid'])
    
    results = {}
    for ticker, group in xrp.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty:
            val = res.iloc[0]
            if isinstance(val, str): results[ticker] = val
            else: results[ticker] = 'YES' if val > 0 else 'NO'
        else:
            group = group.sort_values('rem')
            lp = group['price'].iloc[0] # closest to end
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print("--- XRP Velocity Strategy (Price jump > 15¢ in 2 mins) ---")
    
    trades = []
    for ticker, group in xrp.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        if len(group) < 2: continue
        
        # Check every sliding window
        for i in range(len(group)):
            start_row = group.iloc[i]
            # Find row ~2 mins later
            later = group[(group['t'] > start_row['t']) & (group['t'] <= start_row['t'] + pd.Timedelta(minutes=2))]
            if later.empty: continue
            
            end_row = later.iloc[-1]
            jump = end_row['price'] - start_row['price']
            
            # UP VELOCITY
            if jump >= 15 and end_row['rem'] >= 2:
                trades.append({'action': 'YES', 'outcome': results[ticker], 'time': end_row['rem']})
                break 
            # DOWN VELOCITY
            elif jump <= -15 and end_row['rem'] >= 2:
                trades.append({'action': 'NO', 'outcome': results[ticker], 'time': end_row['rem']})
                break

    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['action'] == t_df['outcome']).mean()
        print(f"Velocity Trades: {len(t_df)} trades, {acc:.1%} Accuracy")
        print(f"Breakdown:")
        for action, group in t_df.groupby('action'):
            a_acc = (group['action'] == group['outcome']).mean()
            print(f"- {action}: {len(group)} trades, {a_acc:.1%} Accuracy")
    else:
        print("No velocity trades found.")

if __name__ == "__main__":
    analyze_xrp_velocity()
