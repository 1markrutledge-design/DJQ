import os
import logging
from shared.kalshi_client import KalshiClient

# Setup logging
logging.basicConfig(level=logging.INFO)

def audit_orders():
    client = KalshiClient()
    client.login()
    
    logging.info("Fetching current positions...")
    positions = client.get_positions()
    fills = client.get_fills()
    
    # Map ticker to its buy CIDs
    ticker_to_buys = {}
    for f in fills:
        if f.get('action') == 'buy':
            t = f.get('ticker')
            if t not in ticker_to_buys: ticker_to_buys[t] = []
            ticker_to_buys[t].append(f.get('client_order_id', 'N/A'))

    print(f"\nOpen Positions:")
    for p in positions:
        ticker = p.get('ticker', 'N/A')
        count = p.get('position', 0)
        
        # Try to find the buy CID for this ticker
        buy_cids = ticker_to_buys.get(ticker, ["Unknown"])
        
        print(f"- {ticker}: {count} shares | Buy CIDs: {', '.join(buy_cids[:3])}")

if __name__ == "__main__":
    import sys
    sys.path.append("/Users/markrutledge/Desktop/bot_code")
    audit_orders()
