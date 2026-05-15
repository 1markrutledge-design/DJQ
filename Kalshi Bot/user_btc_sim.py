import pandas as pd
import numpy as np

def sim_user_btc_strat_v2():
    df = pd.read_csv('market_history.csv')
    btc = df[df['ticker'].str.contains('KXBTC')].copy()
    btc['t'] = pd.to_datetime(btc['timestamp'])
    btc['ct'] = pd.to_datetime(btc['close_time'])
    btc['rem'] = (btc['ct'] - btc['t']).dt.total_seconds() / 60.0
    btc['price'] = btc['last_price'].fillna((btc['yes_bid'].fillna(0) + btc['yes_ask'].fillna(100))/2)

    results = {}
    for ticker, group in btc.groupby('ticker'):
        res = group['result'].dropna()
        if not res.empty: results[ticker] = res.iloc[0]
        else:
            lp = group.sort_values('t')['price'].iloc[-1]
            if lp > 70: results[ticker] = 'YES'
            elif lp < 30: results[ticker] = 'NO'

    trades = []
    
    for ticker, group in btc.groupby('ticker'):
        if ticker not in results: continue
        group = group.sort_values('t')
        outcome = results[ticker]
        
        # We need a trigger at >= 60
        trigger = group[group['price'] >= 60]
        if trigger.empty: continue
        
        trigger_t = trigger.iloc[0]['t']
        trigger_p = trigger.iloc[0]['price']
        
        # USER CONFIG:
        # 1. Under 40 for at least 6 minutes total observation?
        # 2. Ceiling 94
        if trigger_p > 94: continue
        
        # How long was it under observation BEFORE the trigger?
        obs_start_t = group['t'].iloc[0]
        obs_dur = (trigger_t - obs_start_t).total_seconds() / 60.0
        
        if obs_dur >= 6.0:
            # Was it < 40 the whole time before the trigger?
            period = group[group['t'] < trigger_t]
            if (period['price'] <= 40).all():
                trades.append({'outcome': outcome, 'price': trigger_p})
    
    if trades:
        t_df = pd.DataFrame(trades)
        acc = (t_df['outcome'] == 'YES').mean()
        print(f"Audit: {len(t_df)} trades, {acc:.1%} Accuracy")
    else:
        print("Still 0 trades found. This means BTC almost never stays < 40¢ for 6 straight minutes after your bot sees it.")

if __name__ == "__main__":
    sim_user_btc_strat_v2()
