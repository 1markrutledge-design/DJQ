import pandas as pd
import numpy as np

def analyze_btc_v2():
    df = pd.read_csv('market_history.csv')
    btc_df = df[df['ticker'].str.contains('KXBTC', na=False)].copy()
    
    btc_df['mid'] = (btc_df['yes_bid'].fillna(0) + btc_df['yes_ask'].fillna(100)) / 2.0
    btc_df['price'] = btc_df['last_price'].fillna(btc_df['mid'])
    btc_df['t'] = pd.to_datetime(btc_df['timestamp'])
    btc_df['ct'] = pd.to_datetime(btc_df['close_time'])
    btc_df['rem'] = (btc_df['ct'] - btc_df['t']).dt.total_seconds() / 60.0

    results = {}
    for ticker, group in btc_df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print(f"BTC Tickers Analyzed: {len(results)}")

    archetypes = []

    for ticker, group in btc_df.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        # 1. Momentum (Buy YES if clears 65)
        m_70 = group[(group['rem'] > 2) & (group['price'] >= 65)]
        if not m_70.empty:
            archetypes.append({'ticker': ticker, 'outcome': outcome, 'type': 'Momentum (65)', 'action': 'YES', 'price': m_70.iloc[0]['price']})

        # 2. Contrarian (Buy NO if YES > 85 late)
        c_85 = group[(group['rem'] < 4) & (group['price'] >= 85)]
        if not c_85.empty:
             archetypes.append({'ticker': ticker, 'outcome': outcome, 'type': 'Contrarian (NO@85)', 'action': 'NO', 'price': 100 - c_85.iloc[0]['price']})

        # 3. Early Dip (Buy YES if starts low but hits 40 early)
        e_40 = group[(group['rem'] > 10) & (group['price'] >= 40)]
        if not e_40.empty:
             archetypes.append({'ticker': ticker, 'outcome': outcome, 'type': 'Early Breakout (40)', 'action': 'YES', 'price': e_40.iloc[0]['price']})

    arc_df = pd.DataFrame(archetypes)
    for name, a_df in arc_df.groupby('type'):
        pos = a_df[a_df['action'] == 'YES']
        neg = a_df[a_df['action'] == 'NO']
        
        if not pos.empty:
            acc = (pos['outcome'] == 'YES').mean()
            ev = (acc * (100 - pos['price'].mean())) - ((1 - acc) * pos['price'].mean())
            print(f"\n{name}: n={len(pos)}, Accuracy={acc:.1%}, Expected Value={ev:.1f}¢")
        
        if not neg.empty:
            acc = (neg['outcome'] == 'NO').mean()
            ev = (acc * (100 - neg['price'].mean())) - ((1 - acc) * neg['price'].mean())
            print(f"\n{name}: n={len(neg)}, Accuracy={acc:.1%}, Expected Value={ev:.1f}¢")

if __name__ == "__main__":
    analyze_btc_v2()
