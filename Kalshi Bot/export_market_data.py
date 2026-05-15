import csv
import os
from collections import defaultdict

# Path to the source data
INPUT_CSV = "market_history.csv"
OUTPUT_DIR = "market_data_exports"

# Target symbols
SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "HYPE", "DOGE", "BNB"]

def export_data():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found.")
        return

    # 1. First pass: Collect all tickers and their final results
    # We want to make sure the result is known for each file
    ticker_results = {}
    with open(INPUT_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker')
            if row.get('result'):
                ticker_results[ticker] = row['result']

    # 2. Second pass: Group data points by ticker
    # ticker_groups[ticker] = list of data rows
    ticker_groups = defaultdict(list)
    
    with open(INPUT_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get('ticker')
            # Only group rows that have actual price data
            if row.get('last_price') or row.get('yes_bid'):
                ticker_groups[ticker].append(row)

    # 3. Create the output structure
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    exported_count = 0
    for ticker, rows in ticker_groups.items():
        # Identify the symbol from the ticker string (e.g., KXBTC15M-...)
        # Logic: find which symbol is in the ticker name
        symbol = "UNKNOWN"
        for s in SYMBOLS:
            if s in ticker:
                symbol = s
                break
        
        # Create subfolder for symbol
        symbol_dir = os.path.join(OUTPUT_DIR, symbol)
        if not os.path.exists(symbol_dir):
            os.makedirs(symbol_dir)

        # Build filename (cleaning up the ticker for a filename)
        # Ticker: KXBTC15M-26APR211400-00 -> BTC_26APR211400.csv
        filename = f"{ticker.replace('KX', '').split('-')[0]}_{ticker.split('-')[1]}.csv"
        file_path = os.path.join(symbol_dir, filename)

        # Write to per-market CSV
        fieldnames = ["timestamp", "yes_bid", "yes_ask", "last_price", "outcome"]
        with open(file_path, 'w', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            
            outcome = ticker_results.get(ticker, "PENDING")
            
            for row in rows:
                writer.writerow({
                    "timestamp": row['timestamp'],
                    "yes_bid": row['yes_bid'],
                    "yes_ask": row['yes_ask'],
                    "last_price": row['last_price'],
                    "outcome": outcome
                })
        
        exported_count += 1

    print(f"✅ Success! Exported {exported_count} market windows to '{OUTPUT_DIR}/'")
    print(f"   Folders created: {', '.join(os.listdir(OUTPUT_DIR))}")

if __name__ == "__main__":
    export_data()
