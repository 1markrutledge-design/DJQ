import os
import requests
import json
import base64
import time
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Configuration from btc_bot
KEY_ID = "6af327e0-1b7c-4bfc-95ce-7d388824ca5f"
KEY_PATH = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/btc_bot/kalshi_private.pem"
API_BASE = "https://api.elections.kalshi.com"

def load_key():
    with open(KEY_PATH, "rb") as f:
        pem_data = f.read()
    return serialization.load_pem_private_key(pem_data, password=None)

def sign(method, path, private_key):
    clean_path = path.split("?")[0]
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (ts_ms + method.upper() + clean_path).encode()
    sig = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "Content-Type": "application/json",
    }

def request(method, path, private_key, params=None):
    url = API_BASE + path
    hdrs = sign(method, path, private_key)
    resp = requests.request(method, url, headers=hdrs, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def analyze_music_markets():
    private_key = load_key()
    
    prefixes = [
        "KXSPOTSTREAMSUSA", "KXSPOTSTREAMGLOBAL", "KXSPOTIFYD", 
        "KXSPOTIFYGLOBALD", "KXSPOTIFYARTISTD", "KXARTISTSTREAMS",
        "KXTOPSONG", "KXTOPALBUM", "KXRANKLISTSONGTOP10", 
        "KXBBCHARTPOSITIONSONG", "KXBBCHARTPOSITIONALBUM", "KXBBCHART",
        "KXSPOTIFYW", "KXSPOTIFYARTISTW", "KXSPOTIFYALBUMW",
        "KXBOXOFFICE", "KXROTTEN", "KXGT", "KXMEDIA", "KXSHOW", 
        "KXACTOR", "KXPERFORM", "KXBOND", "KXGTAPRICE", "KXMEDIARELEASE",
        "KXMETACRITIC", "KXCOACHELLA", "KXGLASTONBURY", "KXGAMING",
        "KXOSCARS", "KXGRAMMYS", "KXEMMYS", "KXTONYS", "KXSTRMRS",
        "KXYOUTUBE", "KXTWITCH", "KXSTREAMER", "KXMRBEAST", "KXSPEED", 
        "KXKAICENAT", "KXX", "KXTAYLOR", "KXKELCE", "KXYTUBESUBS", 
        "KXTRAVISKELCE", "KXTAYLORSWIFT", "KXSWIFTKELCE", "KXTWITTER", "KXSTREAMS",
        "KXBILLBOARD", "KXSPOTSEASON", "KXSTREAMERS", "KXYTUBES", "KXYTUBE", "KXBB",
        "KXALBUMW", "KXSONGW"
    ]
    
    print(f"Fetching targeted series...")
    music_markets = []
    for series in prefixes:
        try:
            res = request("GET", "/trade-api/v2/markets", private_key, params={"series_ticker": series, "status": "open"})
            batch = res.get("markets", [])
            if batch:
                music_markets.extend(batch)
        except Exception as e:
            pass
            
    today_str = datetime.now(timezone.utc).strftime("%y%b%d").upper()
    print(f"\nTotal music markets found: {len(music_markets)}")
    print(f"Current Filter Date: {today_str}")
    
    today_markets = [m for m in music_markets if today_str in m.get("ticker", "")]
    print(f"Count MATCHING filter: {len(today_markets)}")
    
    non_today_music = [m for m in music_markets if today_str not in m.get("ticker", "")]
    print(f"Count BLOCKED by filter: {len(non_today_music)}")
    
    higher_prob = [m for m in music_markets if (m.get("yes_bid") or int(float(m.get("yes_bid_dollars", 0))*100)) >= 81 or (m.get("no_bid") or int(float(m.get("no_bid_dollars", 0))*100)) >= 81]
    print(f"Total candidates with bid >= 81: {len(higher_prob)}")
    
    blocked_candidates = [m for m in higher_prob if today_str not in m.get("ticker", "")]
    print(f"Candidates BLOCKED by filter: {len(blocked_candidates)}")
    
    if blocked_candidates:
        print("\nSample BLOCKED CANDIDATES:")
        for m in blocked_candidates[:10]:
            yes_bid = m.get("yes_bid") or int(float(m.get("yes_bid_dollars", 0)) * 100)
            no_bid = m.get("no_bid") or int(float(m.get("no_bid_dollars", 0)) * 100)
            print(f"  {m.get('ticker')}: YesBid={yes_bid}, NoBid={no_bid}")

if __name__ == "__main__":
    analyze_music_markets()
