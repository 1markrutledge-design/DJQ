import pandas as pd
import numpy as np

def analyze_xrp_momentum():
    df = pd.read_csv('market_history.csv')
    xrp = df[df['ticker'].str.contains('KXXRP15M', na=False)].copy()
    if xrp.empty:
        return

    xrp['t'] = pd.to_datetime(xrp['timestamp'])
    xrp['ct'] = pd.to_datetime(xrp['close_time'])
    xrp['rem'] = (xrp['ct'] - xrp['t']).dt.total_seconds() / 60.0
    
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
            lp = group['price'].iloc[0]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    # Filter for tickers with outcomes
    valid_tickers = [t for t in results]
    xrp = xrp[xrp['ticker'].isin(valid_tickers)]

    print(f"Analyzing momentum for {len(valid_tickers)} XRP tickers...")

    # Strategy: Acceleration (Price jump in short time)
    # Target: 10c jump in 60s
    trades = []
    for ticker, group in xrp.groupby('ticker'):
        outcome = results[ticker]
        group = group.sort_values('t')
        
        for i in range(len(group)):
            start_row = group.iloc[i]
            # Look forward 60s
            later = group[(group['t'] > start_row['t']) & (group['t'] <= start_row['t'] + pd.Timedelta(seconds=60))]
            if later.empty: continue
            
            end_row = later.iloc[-1]
            jump = end_row['price'] - start_row['price']
            
            if jump >= 10 and end_row['rem'] >= 2:
                trades.append({'action': 'YES', 'outcome': outcome})
                break
            elif jump <= -10 and end_row['rem'] >= 2:
                trades.append({'action': 'NO', 'outcome': outcome})
                break

    if trades:
        t_df = pd.DataFrame(trades)
        wr = (t_df['action'] == t_df['outcome']).mean()
        print(f"Momentum Trades (10c/60s): {len(t_df)} trades, {wr:.1%} accuracy")
    else:
        print("No momentum trades found.")

if __name__ == "__main__":
    analyze_xrp_momentum()
