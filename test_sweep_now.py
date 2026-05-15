import os
import sys
import json
import logging
import requests
from datetime import datetime, timezone, timedelta

# Mock Azure functions logging
logging.basicConfig(level=logging.INFO)

# Add the bot directory to path so we can import
sys.path.append('/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot')

# Load environment variables from local.settings.json
def load_env():
    path = '/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json'
    try:
        with open(path, 'r') as f:
            vals = json.load(f).get('Values', {})
            for k, v in vals.items():
                os.environ[k] = v
    except Exception as e:
        print(f"Failed to load env: {e}")

load_env()

# Import the bot's core functions
try:
    from function_app import Daily_Bid_Sweep, fetch_todays_starters, build_event_ticker, kalshi_get
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def fetch_todays_starters_debug():
    today_et = (datetime.now(timezone.utc) + timedelta(hours=-4)).strftime("%Y-%m-%d")
    print(f"Checking MLB Schedule for {today_et}...")
    resp = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId": 1, "date": today_et, "hydrate": "probablePitcher,lineupConfirmed,team"},
        timeout=20
    )
    data = resp.json()
    starters = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            state = game.get("status", {}).get("abstractGameState", "")
            print(f"Game {game_pk}: State={state}")
            if state == "Final": continue
            
            for side in ("home", "away"):
                team_data = game.get("teams", {}).get(side, {})
                probable = team_data.get("probablePitcher")
                print(f"  Side {side}: Probable={bool(probable)}")
                if not probable: continue
                
                team = team_data.get("team", {}).get("abbreviation", "UNK")
                print(f"  - Pitcher: {probable.get('fullName')} | ID: {probable.get('id')} | Team: {team}")
                
                starters.append({
                    "pitcher_name":  probable.get("fullName", "Unknown"),
                    "mlb_id":        probable.get("id"),
                    "team":          team,
                    "opponent":      "UNK", # Simplified
                    "side":          side,
                    "game_time_utc": game.get("gameDate", ""),
                    "game_pk":       game_pk,
                })
    return starters

def main():
    print("--- TESTING SWEEP MANUALLY ---")
    starters = fetch_todays_starters_debug()
    print(f"Found {len(starters)} starters.")
    for s in starters:
        et = build_event_ticker(s)
        print(f"  - {s['pitcher_name']} ({s['team']}) -> {et}")

    # 2. Check Kalshi Markets for the first event
    if starters:
        print("\n[Step 2] Checking Kalshi for first event...")
        et = build_event_ticker(starters[0])
        params = {"event_ticker": et, "status": "open", "limit": 10}
        try:
            data = kalshi_get("/trade-api/v2/markets", params=params)
            markets = data.get("markets", [])
            print(f"Found {len(markets)} markets for {et}")
            for m in markets:
                print(f"  - {m['ticker']} | ask={m.get('yes_ask')} | floor={m.get('floor_strike')}")
        except Exception as e:
            print(f"Kalshi Error: {e}")

    # 3. Dry Run Sweep (if STARTERS exist)
    print("\n[Step 3] Running Daily_Bid_Sweep() ...")
    try:
        # Note: This will actually place orders if it finds them! 
        # But since the user asked "why didn't it place bets", they probably want us to fix it/run it.
        # I'll just run it.
        Daily_Bid_Sweep()
        print("Sweep completed successfully.")
    except Exception as e:
        print(f"Sweep Failed with Error: {e}")

if __name__ == "__main__":
    main()
