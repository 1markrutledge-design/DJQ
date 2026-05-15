import os
import logging
from shared.kalshi_client import KalshiClient

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_markets():
    client = KalshiClient()
    client.login()
    
    logging.info("Fetching markets with series_ticker='UFC'...")
    ufc_markets = client.get_markets(series_ticker="UFC")
    
    print(f"\nFound {len(ufc_markets)} UFC markets.")
    for m in ufc_markets[:5]:
        print(f"- {m['ticker']} ({m['title']})")
        
    # Check if any tennis is here
    tennis_in_ufc = [m for m in ufc_markets if "TENNIS" in m['ticker'].upper() or "ATPMATCH" in m['ticker'].upper()]
    if tennis_in_ufc:
        print(f"\n⚠️ WARNING: Found {len(tennis_in_ufc)} TENNIS markets in UFC series!")
        for m in tennis_in_ufc:
            print(f"  - {m['ticker']}")
    else:
        print("\n✅ No tennis markets found in UFC series.")

if __name__ == "__main__":
    import sys
    sys.path.append("/Users/markrutledge/Desktop/bot_code")
    test_markets()
