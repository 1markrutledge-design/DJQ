import pandas as pd
import numpy as np

def debug_btc():
    df = pd.read_csv('market_history.csv')
    btc = df[df['ticker'].str.contains('KXBTC')].copy()
    btc['t'] = pd.to_datetime(btc['timestamp'])
    btc['ct'] = pd.to_datetime(btc['close_time'])
    btc['rem'] = (btc['ct'] - btc['t']).dt.total_seconds() / 60.0
    btc['price'] = btc['last_price'].fillna((btc['yes_bid'].fillna(0) + btc['yes_ask'].fillna(100))/2)

    for ticker, group in btc.groupby('ticker'):
        group = group.sort_values('t')
        start_price = group['price'].iloc[0]
        max_price = group['price'].max()
        if max_price >= 60 and start_price <= 40:
             print(f"Ticker: {ticker}, StartPrice: {start_price}, MaxPrice: {max_price}, FirstRem: {group['rem'].iloc[0]}")

if __name__ == "__main__":
    debug_btc()
