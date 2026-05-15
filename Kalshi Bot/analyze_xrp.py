import pandas as pd
import glob
import os
from datetime import datetime

def analyze_xrp_data():
    files = glob.glob('market_data_exports/XRP/*.csv')
    if not files:
        print("No XRP data files found.")
        return
        
    all_stats = []

    for file in files:
        df = pd.read_csv(file)
        if df.empty or 'timestamp' not in df.columns:
            continue
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Calculate relative time in seconds from start
        start_time = df['timestamp'].iloc[0]
        df['seconds'] = (df['timestamp'] - start_time).dt.total_seconds()
        
        if 'outcome' not in df.columns:
            # Try to infer outcome from file name or last row if available
            # In these files, 'outcome' seems to be a column
            continue
            
        outcome = df['outcome'].iloc[0]
        
        # Capture price at specific intervals (closest to 2m, 5m, 8m, 10m, 12m)
        def get_price_at(seconds):
            if df['seconds'].max() < seconds:
                return None
            idx = (df['seconds'] - seconds).abs().idxmin()
            return df.loc[idx, 'last_price']

        def get_bid_ask_at(seconds):
            if df['seconds'].max() < seconds:
                return None, None
            idx = (df['seconds'] - seconds).abs().idxmin()
            return df.loc[idx, 'yes_bid'], df.loc[idx, 'yes_ask']

        p2 = get_price_at(120)
        p5 = get_price_at(300)
        p8 = get_price_at(480)
        p10 = get_price_at(600)
        p12 = get_price_at(720)
        
        b5, a5 = get_bid_ask_at(300)
        b10, a10 = get_bid_ask_at(600)
        
        all_stats.append({
            'file': os.path.basename(file),
            'outcome': outcome,
            'p2': p2,
            'p5': p5,
            'p8': p8,
            'p10': p10,
            'p12': p12,
            'spread5': (a5 - b5) if a5 and b5 else None,
            'spread10': (a10 - b10) if a10 and b10 else None
        })

    stats_df = pd.DataFrame(all_stats)
    
    print(f"--- XRP Market Analysis Summary (n={len(stats_df)}) ---")
    if stats_df.empty:
        return

    numeric_columns = ['p2', 'p5', 'p8', 'p10', 'p12', 'spread5', 'spread10']
    
    # Calculate means grouped by outcome
    print("\n--- Averages by Outcome ---")
    print(stats_df.groupby('outcome')[numeric_columns].mean())
    
    # Calculate win rates for potential thresholds
    print("\n--- Win Rates for Strategies ---")
    
    strategies = [
        ('p5_gt_70', lambda d: d['p5'] >= 70),
        ('p8_gt_80', lambda d: d['p8'] >= 80),
        ('p10_gt_90', lambda d: d['p10'] >= 90),
        ('p5_lt_30_FADE', lambda d: d['p5'] <= 30),
        ('momentum_p5_p2_gt_15', lambda d: (d['p5'] - d['p2']) >= 15),
        ('late_surge_p10_p8_gt_10', lambda d: (d['p10'] - d['p8']) >= 10)
    ]

    for name, func in strategies:
        try:
            mask = func(stats_df)
            filtered = stats_df[mask]
            if len(filtered) > 0:
                win_rate = filtered['outcome'].value_counts(normalize=True).get('YES', 0)
                print(f"Win Rate for {name:25}: {win_rate:.2%} (n={len(filtered)})")
            else:
                print(f"Strategy {name:25}: No occurrences found.")
        except Exception as e:
            print(f"Error calculating {name}: {e}")

if __name__ == "__main__":
    analyze_xrp_data()
