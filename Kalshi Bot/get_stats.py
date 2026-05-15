import os, json, requests, base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Auth Setup
settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
try:
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    key_id = vals["KALSHI_API_KEY_ID"]
    pem_data = vals["KALSHI_PRIVATE_KEY_PEM"]
except Exception: exit(1)

def _load_private_key():
    clean_pem = pem_data.replace('\\n', '\n').replace('"', '').strip()
    h, f = "-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----"
    if h in clean_pem and "\n" not in clean_pem[len(h):len(h)+10]:
        clean_pem = f"{h}\n{clean_pem.replace(h,'').replace(f,'').strip()}\n{f}"
    elif h not in clean_pem:
        clean_pem = f"{h}\n{clean_pem}\n{f}"
    return serialization.load_pem_private_key(clean_pem.encode(), password=None)

def kalshi_get(path, params=None):
    clean_path = path.split("?")[0]
    ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    msg = (ts + "GET" + clean_path).encode()
    sig = _load_private_key().sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    headers = {
        "KALSHI-ACCESS-KEY": key_id.replace('"', "").strip(),
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "Content-Type": "application/json"
    }
    r = requests.get("https://api.elections.kalshi.com" + path, headers=headers, params=params)
    r.raise_for_status()
    return r.json()

# Fetch recent fills (last ~2500 fills should cover last ~5 days if active)
fills = []
cursor = None
min_ts = int((datetime.now(timezone.utc) - timedelta(days=5)).timestamp())
for _ in range(25):
    params = {"limit": 100, "min_ts": min_ts}
    if cursor: params["cursor"] = cursor
    data = kalshi_get("/trade-api/v2/portfolio/fills", params=params)
    fills.extend(data.get("fills", []))
    cursor = data.get("cursor")
    if not cursor: break

# Group by ticker
trades = {}
for f in fills:
    t = f.get("ticker", "")
    if "KXATP" not in t and "KXWTA" not in t and "TENNIS" not in t: continue
    
    if t not in trades:
        trades[t] = {"buys": 0, "sells": 0, "shares_b": 0, "shares_s": 0}
        
    action = f.get("action")
    count = f.get("count", 0)
    # the Kalshi V2 fills API uses 'price' (cents) or 'yes_price' depending on endpoint, fallback handling
    price = f.get("price", f.get("yes_price", 0)) 
    
    if action == "buy":
        trades[t]["buys"] += count * price
        trades[t]["shares_b"] += count
    elif action == "sell":
        trades[t]["sells"] += count * price
        trades[t]["shares_s"] += count

gross_profit = 0
gross_loss = 0
wins = 0
losses = 0

for t, data in trades.items():
    # Only calculate closed/settled loops
    # To keep it simple: assume all bought shares that aren't sold were losses (or settled at 0).
    # If they were settled at 100, we'd need to fetch settlement data, but Stop Losses usually
    # exit before settlement (sell=shares_b).
    net_pnl = data["sells"] - data["buys"]
    net_shares = data["shares_b"] - data["shares_s"]
    
    # If they bought and sold exact amount -> realized trade
    if data["shares_b"] > 0 and data["shares_b"] == data["shares_s"]:
        if net_pnl > 0:
            gross_profit += net_pnl
            wins += 1
        elif net_pnl < 0:
            gross_loss += abs(net_pnl)
            losses += 1
    # What if they didn't sell? Either they are open orders or settled. We'll count them as losses for now unless we do a full settlement check.
    elif data["shares_b"] > 0 and data["shares_s"] == 0:
        # Check market status to see if it settled YES
        try:
            m_data = kalshi_get(f"/trade-api/v2/markets/{t}")
            m = m_data.get("market", {})
            if m.get("status") in ["finalized", "settled"] and m.get("result") == "yes":
                payout = data["shares_b"] * 100
                pnl = payout - data["buys"]
                if pnl > 0:
                    gross_profit += pnl
                    wins += 1
                else:
                    gross_loss += abs(pnl)
                    losses += 1
            elif m.get("status") in ["finalized", "settled"] and m.get("result") == "no":
                pnl = 0 - data["buys"]
                gross_loss += abs(pnl)
                losses += 1
        except Exception:
            pass

total_trades = wins + losses
win_pct = (wins / total_trades * 100) if total_trades > 0 else 0
net_pnl = gross_profit - gross_loss

print(f"Total Tennis Trades Found: {total_trades}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Win Percentage: {win_pct:.2f}%")
print(f"Gross Profit: {gross_profit/100:.2f}$")
print(f"Gross Loss: {gross_loss/100:.2f}$")
print(f"Net PnL: {net_pnl/100:.2f}$")
