import pandas as pd
import numpy as np

def analyze_all():
    df = pd.read_csv('market_history.csv')
    # Filter for all 15M crypto markets
    crypto_df = df[df['ticker'].str.contains('15M', na=False)].copy()
    if crypto_df.empty: return

    crypto_df['t'] = pd.to_datetime(crypto_df['timestamp'])
    crypto_df['ct'] = pd.to_datetime(crypto_df['close_time'])
    crypto_df['rem'] = (crypto_df['ct'] - crypto_df['t']).dt.total_seconds() / 60.0
    
    crypto_df['mid'] = (crypto_df['yes_bid'].fillna(0) + crypto_df['yes_ask'].fillna(100)) / 2.0
    crypto_df['price'] = crypto_df['last_price'].fillna(crypto_df['mid'])
    
    results = {}
    for ticker, group in crypto_df.groupby('ticker'):
        outcome = group['result'].dropna()
        if not outcome.empty:
            results[ticker] = outcome.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    print(f"Outcome identified for {len(results)} total tickers across all markets.")

    all_trades = []
    # Test Strategy: Bet on the TREND as soon as it clears a threshold
    for ticker, group in crypto_df.groupby('ticker'):
        if ticker not in results: continue
        outcome = results[ticker]
        group = group.sort_values('t')
        
        # Check for trigger: First time price clears a threshold between 12m and 2m remaining
        # Higher threshold for YES, lower for NO
        yes_triggered = False
        no_triggered = False
        
        subset = group[(group['rem'] >= 2) & (group['rem'] <= 12)]
        for _, row in subset.iterrows():
            if row['price'] >= 60:
                all_trades.append({'ticker': ticker, 'outcome': outcome, 'action': 'YES', 'price': row['price']})
                yes_triggered = True
                break
            elif row['price'] <= 40:
                all_trades.append({'ticker': ticker, 'outcome': outcome, 'action': 'NO', 'price': row['price']})
                no_triggered = True
                break
                
    trades_df = pd.DataFrame(all_trades)
    print(f"Total Triggers: {len(trades_df)}")
    
    if not trades_df.empty:
        accuracy = (trades_df['action'] == trades_df['outcome']).mean()
        print(f"Overall Accuracy: {accuracy:.1%}")
        
        # Break down by coin type
        trades_df['coin'] = trades_df['ticker'].apply(lambda x: x[2:5])
        for coin, c_df in trades_df.groupby('coin'):
            c_acc = (c_df['action'] == c_df['outcome']).mean()
            print(f"- {coin}: {len(c_df)} trades, {c_acc:.1%} WR")

if __name__ == "__main__":
    analyze_all()
