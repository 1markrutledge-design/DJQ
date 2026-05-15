import pandas as pd
import numpy as np

def analyze_btc_window_real():
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

    print("--- BTC Window Analysis (Observation Duration) ---")
    
    # We want to know: "If it was < 40 for at least X minutes of observation, then surges"
    for min_obs_len in [2, 3, 5, 8]:
        trades = []
        for ticker, group in btc_df.groupby('ticker'):
            if ticker not in results: continue
            outcome = results[ticker]
            group = group.sort_values('t')
            
            # Start of observation for this ticker in our file
            obs_start_t = group['t'].iloc[0]
            
            # Look for trigger (price hits 60)
            trigger = group[group['price'] >= 60]
            if trigger.empty: continue
            
            trigger_t = trigger.iloc[0]['t']
            
            # Duration it was under observation BEFORE hitting 60
            obs_before_trigger = (trigger_t - obs_start_t).total_seconds() / 60.0
            
            if obs_before_trigger >= min_obs_len:
                # Check if it stayed < 40 for that period
                period = group[(group['t'] >= obs_start_t) & (group['t'] < trigger_t)]
                if not period.empty and (period['price'] <= 40).all():
                    trades.append({'outcome': outcome})

        if trades:
            t_df = pd.DataFrame(trades)
            acc = (t_df['outcome'] == 'YES').mean()
            print(f"Stays <40¢ for {min_obs_len}m of observation: {len(t_df)} trades, {acc:.1%} Accuracy")

if __name__ == "__main__":
    analyze_btc_window_real()
