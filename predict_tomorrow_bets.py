import io
import os
import csv
import math
import time
import requests
import base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# --- Constants from function_app.py ---
KALSHI_BASE     = "https://api.elections.kalshi.com"
MLB_API_BASE    = "https://statsapi.mlb.com/api/v1"
SAVANT_BASE     = "https://baseballsavant.mlb.com"
SERIES_TICKER   = "KXMLBKS"
ET_OFFSET       = -4
CONFIDENCE_FLOOR = 0.70
MIN_TIER        = 3
EXPECTED_INNINGS = 5.5
LEAGUE_AVG_WHIFF = 0.245
CURRENT_SEASON   = 2025
DAILY_SHARE_LIMIT = 30

# --- Auth Helpers ---
def get_env_vars():
    vars = {}
    try:
        with open('/Users/markrutledge/Documents/DjQueue/.env.local', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    vars[key] = val.strip('\"').strip("'")
    except: pass
    return vars

def sign_request(method, path):
    env = get_env_vars()
    api_key_id = env.get('KALSHI_API_KEY_ID')
    private_key_pem = env.get('KALSHI_PRIVATE_KEY_PEM')
    if not api_key_id or not private_key_pem: return None
    
    private_key_pem = private_key_pem.replace('\\n', '\n').strip()
    if not private_key_pem.startswith('-----BEGIN'):
        private_key_pem = f"-----BEGIN RSA PRIVATE KEY-----\n{private_key_pem}\n-----END RSA PRIVATE KEY-----"
    
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    clean_path = path.split('?')[0]
    ts_ms = str(int(time.time() * 1000))
    msg = (ts_ms + method.upper() + clean_path).encode()
    sig = private_key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    return {
        "KALSHI-ACCESS-KEY": api_key_id, 
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(), 
        "KALSHI-ACCESS-TIMESTAMP": ts_ms, 
        "Content-Type": "application/json"
    }

def kalshi_get(path, params=None):
    headers = sign_request("GET", path)
    if not headers: return {}
    try:
        resp = requests.get(KALSHI_BASE + path, headers=headers, params=params, timeout=30)
        return resp.json()
    except: return {}

def fetch_kalshi_prices():
    prices = {}
    cursor = None
    for _ in range(5):
        params = {"series_ticker": SERIES_TICKER, "status": "open", "limit": 200}
        if cursor: params["cursor"] = cursor
        data = kalshi_get("/trade-api/v2/markets", params=params)
        markets = data.get("markets", [])
        for m in markets:
            prices[m.get("ticker")] = m.get("yes_ask", 0)
        cursor = data.get("cursor")
        if not cursor or not markets: break
    return prices

# --- Strategy Helpers ---
def _poisson_pmf(k, lam):
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def _poisson_cdf(n, lam):
    return sum(_poisson_pmf(k, lam) for k in range(n + 1))

def prob_k_or_more(n, k9, whiff_pct):
    raw_lam      = k9 * (EXPECTED_INNINGS / 9.0)
    whiff_factor = whiff_pct / LEAGUE_AVG_WHIFF if whiff_pct > 0 else 1.0
    whiff_factor = max(0.70, min(1.40, whiff_factor))
    lam_adj      = raw_lam * whiff_factor
    return 1.0 - _poisson_cdf(n - 1, lam_adj)

def fetch_pitcher_k9(mlb_id):
    try:
        resp = requests.get(f"{MLB_API_BASE}/people/{mlb_id}/stats",
                            params={"stats": "season", "group": "pitching", "season": CURRENT_SEASON, "sportId": 1}, timeout=15)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        if splits:
            stat = splits[0].get("stat", {})
            return float(stat.get("strikeoutsPer9Inn", 0))
    except: pass
    return None

def fetch_savant_whiff_map():
    url = f"{SAVANT_BASE}/leaderboards/arsenal-stats?type=pitcher&year={CURRENT_SEASON}&min=100&csv=true"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/123.0.0.0 Safari/537.36"}
    result = {}
    try:
        resp = requests.get(url, headers=headers, timeout=35)
        if resp.ok and not resp.text.strip().startswith("<!"):
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                pid = row.get("pitcher_id")
                raw = row.get("whiff_percent")
                if pid and raw:
                    pct = float(str(raw).replace("%", "").strip())
                    result[str(pid)] = pct / 100.0 if pct > 1.0 else pct
    except: pass
    return result

def main():
    tomorrow_et_dt = datetime.now(timezone.utc) + timedelta(hours=ET_OFFSET) + timedelta(days=1)
    tomorrow_et = tomorrow_et_dt.strftime("%Y-%m-%d")
    print(f"--- POTENTIAL SPEND ESTIMATE UNTIL {tomorrow_et} ---")
    
    # 1. Fetch Starters
    resp = requests.get(f"{MLB_API_BASE}/schedule", params={"sportId": 1, "date": tomorrow_et, "hydrate": "probablePitcher,team"}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    whiff_map = fetch_savant_whiff_map()
    market_prices = fetch_kalshi_prices()
    
    predictions = []
    total_estimated_spend = 0
    bet_count = 0
    
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            for side in ("home", "away"):
                team_data = game.get("teams", {}).get(side, {})
                probable = team_data.get("probablePitcher")
                if not probable: continue
                
                name = probable.get("fullName")
                mlb_id = probable.get("id")
                k9 = fetch_pitcher_k9(mlb_id)
                whiff = whiff_map.get(str(mlb_id), LEAGUE_AVG_WHIFF)
                if not k9: continue
                
                # Best tier logic
                best_tier = None
                for t in range(10, MIN_TIER - 1, -1):
                    if prob_k_or_more(t, k9, whiff) >= CONFIDENCE_FLOOR:
                        best_tier = t
                        break
                
                if best_tier and bet_count < DAILY_SHARE_LIMIT:
                    # Estimate cost
                    est_cost = 55 
                    total_estimated_spend += est_cost
                    bet_count += 1
                    predictions.append({"pitcher": name, "tier": best_tier, "cost": est_cost})

    print(f"Predicted Bets: {bet_count}")
    print(f"Estimated Total Spend: ${total_estimated_spend / 100.0:.2f}")
    print(f"(Assumes average cost of $0.55 per share across {bet_count} pitchers)")

if __name__ == "__main__":
    main()
