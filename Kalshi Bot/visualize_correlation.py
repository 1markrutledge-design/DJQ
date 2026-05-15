import pandas as pd
import numpy as np
import os

CSV_FILE = 'market_history.csv'

def prove_correlation():
    if not os.path.exists(CSV_FILE): return
    df = pd.read_csv(CSV_FILE)
    
    # Filter for BTC and ETH
    crypto = df[df['ticker'].str.contains('KXBTC15M|KXETH15M', na=False)].copy()
    crypto['asset'] = crypto['ticker'].apply(lambda x: 'BTC' if 'BTC' in x else 'ETH')
    crypto['window'] = crypto['ticker'].apply(lambda x: x.split('-')[1])
    
    # Fill prices
    crypto['yes_bid'] = pd.to_numeric(crypto['yes_bid'], errors='coerce').fillna(0)
    crypto['yes_ask'] = pd.to_numeric(crypto['yes_ask'], errors='coerce').fillna(100)
    crypto['price'] = crypto['last_price'].fillna((crypto['yes_bid'] + crypto['yes_ask'])/2)
    
    # Pivot to compare side-by-side
    # We aggregate by window and timestamp (approximate to 5s buckets)
    crypto['t_bucket'] = pd.to_datetime(crypto['timestamp']).dt.round('5s')
    
    pivoted = crypto.pivot_table(index=['window', 't_bucket'], columns='asset', values='price')
    pivoted = pivoted.dropna() # Only rows with both BTC and ETH values
    
    if pivoted.empty:
        print("No overlapping data found.")
        return

    correlation = pivoted['BTC'].corr(pivoted['ETH'])
    
    print(f"--- CRYPTO CORRELATION ANALYSIS ---")
    print(f"Data Points analyzed: {len(pivoted)}")
    print(f"BTC vs ETH Correlation: {correlation:.3f}")
    
    if correlation > 0.8:
        print("\nConclusion: The correlation is EXTREMELY high (>0.8).")
        print("When Bitcoin moves, Ethereum follows it like a shadow.")
        print("This is why BTC is a 'leading indicator' for ETH trades.")
    
    # Show a few examples of movement
    print("\nRecent price movement examples (Last 5 snapshots):")
    print(pivoted.tail(5))

if __name__ == "__main__":
    prove_correlation()
