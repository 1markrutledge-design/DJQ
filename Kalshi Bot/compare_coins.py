import pandas as pd
import numpy as np

def compare_sol_btc():
    df = pd.read_csv('market_history.csv')
    
    results = {}
    # Use simpler outcome identification for speed
    df['mid'] = (df['yes_bid'].fillna(0) + df['yes_ask'].fillna(100)) / 2.0
    df['price'] = df['last_price'].fillna(df['mid'])
    df['t'] = pd.to_datetime(df['timestamp'])
    df['ct'] = pd.to_datetime(df['close_time'])
    df['rem'] = (df['ct'] - df['t']).dt.total_seconds() / 60.0

    for ticker, group in df.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty:
            results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'
    
    for coin in ['KXSOL', 'KXBTC']:
        coin_df = df[df['ticker'].str.contains(coin, na=False)].copy()
        coin_trades = []
        
        for ticker, group in coin_df.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            group = group.sort_values('t')
            
            # Strategy: Taker at 70 (YES) or 30 (NO)
            subset = group[(group['rem'] >= 2) & (group['rem'] <= 12)]
            for _, row in subset.iterrows():
                if row['price'] >= 70:
                    coin_trades.append({'outcome': outcome, 'action': 'YES'})
                    break
                elif row['price'] <= 30:
                    coin_trades.append({'outcome': outcome, 'action': 'NO'})
                    break
        
        if coin_trades:
            t_df = pd.DataFrame(coin_trades)
            acc = (t_df['action'] == t_df['outcome']).mean()
            print(f"\n--- {coin} Strategy Performance ---")
            print(f"Total Triggers: {len(t_df)}")
            print(f"Accuracy: {acc:.1%}")
            
            # Calculate volatility (avg drawdown of winners)
            # (Just for YES trades)
            yes_wins = []
            for ticker, group in coin_df.groupby('ticker'):
                if ticker not in results or results[ticker] != 'YES': continue
                group = group.sort_values('t')
                trigger = group[group['price'] >= 70]
                if trigger.empty: continue
                entry_time = trigger.iloc[0]['t']
                post = group[group['t'] > entry_time]
                if not post.empty:
                    yes_wins.append(post['price'].min())
            
            if yes_wins:
                print(f"Avg Drawdown of Winners: {70 - np.mean(yes_wins):.1f}¢")

if __name__ == "__main__":
    compare_sol_btc()
