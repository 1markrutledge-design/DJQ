import sys, os, json, time
from datetime import datetime, timezone
import requests

# Set up the same auth logic as the bot
API_BASE = "https://api.elections.kalshi.com"
TARGET_SERIES = [
    "KXSOL15M", "KXBTC15M", "KXXRP15M", "KXHYPE15M", 
    "KXDOGE15M", "KXBNB15M", "KXETH15M"
]

def get_headers():
    # Attempt to load keys from env
    key_id = os.environ.get("KALSHI_API_KEY_ID")
    if not key_id:
        return {}
        
    # We need the signing logic, but for a quick check we can just use the bot's session if it provides a way
    # Or just use the REST client if we can instantiate it.
    pass

# Simplified diagnostic: just check the bot_status.json if it exists
def check_status_file():
    if not os.path.exists("bot_status.json"):
        print("bot_status.json not found.")
        return
    with open("bot_status.json", "r") as f:
        data = json.load(f)
    
    print(f"Last Updated: {data.get('last_updated')}")
    print(f"Total P&L: {data.get('total_pl_dollars')}")
    print(f"Balance: ${data.get('balance_cents', 0)/100:.2f}")
    
    markets = data.get("markets", {})
    print(f"\nTracked Markets: {len(markets)}")
    for ticker, state in markets.items():
        print(f" - {ticker}: {state['status']} | {state['mins_to_close']}m left")
        if 'last_bid' in state: # Not in my code but maybe added?
            pass

if __name__ == "__main__":
    check_status_file()
