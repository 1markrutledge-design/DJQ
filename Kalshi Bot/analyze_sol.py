import pandas as pd
import glob
import os
from datetime import datetime

def analyze_sol_data():
    files = glob.glob('market_data_exports/SOL/*.csv')
    all_stats = []

    for file in files:
        df = pd.read_csv(file)
        if df.empty:
            continue
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Calculate relative time in seconds from start
        start_time = df['timestamp'].iloc[0]
        df['seconds'] = (df['timestamp'] - start_time).dt.total_seconds()
        
        outcome = df['outcome'].iloc[0]
        
        # Capture price at specific intervals (closest to 2m, 5m, 10m)
        def get_price_at(seconds):
            idx = (df['seconds'] - seconds).abs().idxmin()
            return df.loc[idx, 'last_price']

        def get_bid_ask_at(seconds):
            idx = (df['seconds'] - seconds).abs().idxmin()
            return df.loc[idx, 'yes_bid'], df.loc[idx, 'yes_ask']

        p2 = get_price_at(120)
        p5 = get_price_at(300)
        p10 = get_price_at(600)
        
        b2, a2 = get_bid_ask_at(120)
        b5, a5 = get_bid_ask_at(300)
        b10, a10 = get_bid_ask_at(600)
        
        all_stats.append({
            'file': os.path.basename(file),
            'outcome': outcome,
            'p2': p2,
            'p5': p5,
            'p10': p10,
            'spread2': a2 - b2,
            'spread5': a5 - b5,
            'spread10': a10 - b10,
            'momentum5_2': p5 - p2,
            'momentum10_5': p10 - p5
        })

    stats_df = pd.DataFrame(all_stats)
    
    print("--- SOL Market Analysis Summary ---")
    numeric_stats = stats_df.drop(columns=['file'])
    print(numeric_stats.groupby('outcome').mean())
    print("\n--- Outcome Correlation with p5 ---")
    print(numeric_stats.groupby('outcome')['p5'].describe())
    
    # Calculate win rates for potential thresholds
    print("\n--- Win Rates by Thresholds ---")
    # Threshold 1: Price > 60 at 5 mins
    stats_df['p5_gt_60'] = stats_df['p5'] > 60
    # Threshold 2: Momentum (p5 - p2) > 10
    stats_df['mom_p5p2_gt_10'] = (stats_df['p5'] - stats_df['p2']) > 10
    # Threshold 3: Spread at 5m < 5
    stats_df['tight_spread_5'] = stats_df['spread5'] < 5

    for col in ['p5_gt_60', 'mom_p5p2_gt_10', 'tight_spread_5']:
        win_rate = stats_df[stats_df[col]]['outcome'].value_counts(normalize=True).get('YES', 0)
        sample_size = len(stats_df[stats_df[col]])
        print(f"Win Rate for {col}: {win_rate:.2%} (n={sample_size})")

if __name__ == "__main__":
    analyze_sol_data()
