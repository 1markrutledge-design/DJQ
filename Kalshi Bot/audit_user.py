import pandas as pd
import numpy as np

def audit_user_strats():
    df = pd.read_csv('market_history.csv')
    df['mid'] = (df['yes_bid'].fillna(0) + df['yes_ask'].fillna(100)) / 2.0
    df['price'] = df['last_price'].fillna(df['mid'])
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0

    # Ticker results
    results = {}
    for ticker, group in df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    # --- Audit SOL 70/70 ---
    sol = df[df['ticker'].str.contains('KXSOL')].copy()
    sol_trades = []
    for ticker, group in sol.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        # Rule: Min 2 to 15 (rem 13 to 0). 70 Bid.
        # Check YES Bid >= 70 or NO Bid >= 70 (YES <= 30)
        window = group[(group['rem'] <= 13)]
        for _, row in window.iterrows():
            if row['yes_bid'] >= 70:
                sol_trades.append({'outcome': outcome, 'action': 'YES'})
                break
            elif row['yes_bid'] <= 30: # NO bid >= 70
                sol_trades.append({'outcome': outcome, 'action': 'NO'})
                break
    
    if sol_trades:
        s_df = pd.DataFrame(sol_trades)
        s_acc = (s_df['action'] == s_df['outcome']).mean()
        print(f"SOL 70/70 Audit: n={len(s_df)}, Accuracy={s_acc:.1%}")

    # --- Audit BTC Sniper (+8c in 15s) ---
    btc = df[df['ticker'].str.contains('KXBTC')].copy()
    btc_trades = []
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        # Rule: Min 2 to 13 (rem 13 to 2)
        window = group[(group['rem'] <= 13) & (group['rem'] >= 2)]
        if len(window) < 2: continue
        
        for i in range(1, len(window)):
            row = window.iloc[i]
            prev = window.iloc[i-1]
            # Check price jump in short interval
            dt = (row['t'] - prev['t']).total_seconds()
            dp = row['price'] - prev['price']
            
            if dt <= 30 and dp >= 8: # Approximating 15s with 30s as logs might be sparse
                 btc_trades.append({'outcome': outcome})
                 break

    if btc_trades:
        b_df = pd.DataFrame(btc_trades)
        b_acc = (b_df['outcome'] == 'YES').mean()
        print(f"BTC Sniper Audit (+8c/short): n={len(b_df)}, Accuracy={b_acc:.1%}")

    # --- Audit BNB Trend Rider (80c Bid, Final 5m) ---
    bnb = df[df['ticker'].str.contains('KXBNB')].copy()
    bnb_trades = []
    for ticker, group in bnb.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        # Rule: Final 5m (rem <= 5)
        window = group[group['rem'] <= 5]
        for _, row in window.iterrows():
            if row['yes_bid'] >= 80:
                bnb_trades.append({'outcome': outcome, 'action': 'YES'})
                break
            elif row['yes_bid'] <= 20: # NO bid >= 80
                bnb_trades.append({'outcome': outcome, 'action': 'NO'})
                break
                
    if bnb_trades:
        bn_df = pd.DataFrame(bnb_trades)
        bn_acc = (bn_df['action'] == bn_df['outcome']).mean()
        print(f"BNB Trend Rider Audit (80c/Late): n={len(bn_df)}, Accuracy={bn_acc:.1%}")

if __name__ == "__main__":
    audit_user_strats()
