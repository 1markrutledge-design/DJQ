import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

def debug_eth_prices():
    df = pd.read_csv('market_history.csv')
    eth = df[df['ticker'].str.contains('KXETH15M', na=False)].copy()
    if eth.empty: return
    eth['t'] = pd.to_datetime(eth['timestamp'], utc=True)
    now = eth['t'].max()
    eth_recent = eth[eth['t'] >= (now - timedelta(hours=24))].copy()
    eth_recent['price'] = eth_recent['last_price'].fillna((pd.to_numeric(eth_recent['yes_bid'], errors='coerce').fillna(0) + pd.to_numeric(eth_recent['yes_ask'], errors='coerce').fillna(100))/2)

    print(f"Stats for {len(eth_recent.groupby('ticker'))} ETH markets in last 24h:")
    p_min = eth_recent['price'].min()
    p_max = eth_recent['price'].max()
    p_mean = eth_recent['price'].mean()
    print(f"Global Price Range: {p_min:.1f} - {p_max:.1f} (Avg: {p_mean:.1f})")

    for ticker, group in eth_recent.groupby('ticker'):
        print(f"{ticker}: {group['price'].min():.1f} - {group['price'].max():.1f}")
        break # Just see one

if __name__ == "__main__":
    debug_eth_prices()
