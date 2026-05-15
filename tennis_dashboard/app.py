import os
import json
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, render_template

# Point this to your local Kalshi Client or bot script location.
# Since we just want to read the Kalshi API, we can use the requests logic directly.
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import base64

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Load credentials directly from the user's active bot settings.
CREDENTIALS_PATH = os.path.expanduser('/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json')

def get_credentials():
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            data = json.load(f)
            values = data.get("Values", {})
            
            # The Azure env variables store the private key as a raw string without actual new lines
            # So we must clean and reformat it for cryptography
            pem_raw = values.get("KALSHI_PRIVATE_KEY_PEM", "")
            pem_clean = pem_raw.replace('\\n', '\n').strip()
            
            # Re-format the basic one-line structure if it exists
            header = "-----BEGIN RSA PRIVATE KEY-----"
            footer = "-----END RSA PRIVATE KEY-----"
            if header in pem_clean and "\n" not in pem_clean[len(header):len(header)+10]:
                content = pem_clean.replace(header, "").replace(footer, "").replace(" ", "").strip()
                lines = [content[i:i+64] for i in range(0, len(content), 64)]
                pem_clean = f"{header}\n" + "\n".join(lines) + f"\n{footer}"
                
            return {
                "key_id": values.get("KALSHI_API_KEY_ID"),
                "private_key": pem_clean
            }
    except Exception as e:
        logging.error(f"Failed to load credentials: {e}")
        return None

def sign_message(private_key_pem: str, method: str, path: str, timestamp: int) -> str:
    msg = f"{timestamp}{method}{path}"
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signature = private_key.sign(
        msg.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")

def kalshi_get(path: str, params=None):
    creds = get_credentials()
    if not creds: return None
    
    timestamp = int(datetime.now().timestamp() * 1000)
    sig = sign_message(creds["private_key"], "GET", path, timestamp)
    headers = {
        "KALSHI-ACCESS-KEY": creds["key_id"],
        "KALSHI-ACCESS-SIGNATURE": sig,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp)
    }
    url = f"https://api.elections.kalshi.com{path}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"GET failed: {e}")
        return None

def kalshi_get_all(path: str, min_ts: int):
    all_data = []
    params = {"limit": 1000, "min_ts": min_ts}
    while True:
        resp = kalshi_get(path, params)
        if not resp: break
        
        # determine key name: fills or settlements
        key = "fills" if "fills" in path else "settlements"
        data = resp.get(key, [])
        all_data.extend(data)
        
        cursor = resp.get("cursor")
        if not cursor:
            break
        params["cursor"] = cursor
        
    return all_data

# In-memory cache to avoid rate limits when fetching market names
MARKET_CACHE = {}

def get_player_name(ticker):
    if ticker in MARKET_CACHE:
        return MARKET_CACHE[ticker]
        
    try:
        m = kalshi_get(f"/trade-api/v2/markets/{ticker}")
        if m and "market" in m:
            title = m["market"].get("title", "")
            # e.g. "Will Iva Jovic win the Blinkova vs Jovic : Round Of 32 match?"
            if title.startswith("Will ") and " win " in title:
                name = title[5:title.index(" win ")]
                MARKET_CACHE[ticker] = name
                return name
            MARKET_CACHE[ticker] = title
            return title
    except Exception as e:
        logging.error(f"Failed to fetch market info for {ticker}: {e}")
        
    # Fallback to ticker
    MARKET_CACHE[ticker] = ticker
    return ticker

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/stats")
def get_stats():
    # Only pull Portfolio
    balance_data = kalshi_get("/trade-api/v2/portfolio/balance")
    balance = balance_data.get("balance", 0) / 100 if balance_data else 0
    
    cutoff = "2026-03-13T14:06:00Z" 
    
    # Fetch last 48 hours to ensure we get the buy fills for the manual overrides
    from datetime import timedelta
    min_ts = int((datetime.now(timezone.utc) - timedelta(hours=48)).timestamp())

    all_fills = kalshi_get_all("/trade-api/v2/portfolio/fills", min_ts)
    orders_data = kalshi_get("/trade-api/v2/portfolio/orders", {"status": "resting"})
    resting_orders = orders_data.get("orders", []) if orders_data else []
    
    new_strategy_tickers = {
        "KXATPMATCH-26FEB27TABBAE-TAB",
        "KXATPMATCH-26FEB27TABBAE-BAE"
    }
    for f in all_fills:
        if f.get("action") == "buy" and f.get("created_time", "") >= cutoff:
            new_strategy_tickers.add(f.get("ticker", "").upper())
            
    for o in resting_orders:
        if o.get("action") == "buy" and o.get("created_time", "") >= cutoff:
            new_strategy_tickers.add(o.get("ticker", "").upper())
    
    # Accurate Active Investment calculation purely from Kalshi's live positions ledger
    positions_data = kalshi_get("/trade-api/v2/portfolio/positions")
    total_active_investment = 0
    if positions_data and "market_positions" in positions_data:
        for p in positions_data["market_positions"]:
            t = p.get("ticker", "").upper()
            if ("KXATP" in t or "KXWTA" in t) and p.get("position", 0) != 0:
                pos_cost_cents = p.get("total_cost", 0)
                total_active_investment += (pos_cost_cents / 100)
    
    tennis_fills = []
    
    for f in all_fills:
        ticker = f.get("ticker", "").upper()
        
        if ("KXATP" in ticker or "KXWTA" in ticker) and ticker in new_strategy_tickers:
            tennis_fills.append(f)
            
    
    # NEW KALSHI V2 SETTLEMENT PATCH: 
    # Kalshi V2 completely deleted the portfolio/settlements endpoint. 
    # We must manually query each active ticker to check if the match is over.
    for ticker in new_strategy_tickers:
        if "KXATP" not in ticker and "KXWTA" not in ticker:
            continue
            
        try:
            m_data = kalshi_get(f"/trade-api/v2/markets/{ticker}")
            m = m_data.get("market", {})
            status = m.get("status", "")
            
            if status == "finalized":
                # The match is officially over. Check if our player won.
                result = m.get("result", "").lower()
                is_win = (result == "yes")
                settle_price = 100 if is_win else 0
                
                # Figure out exactly how many shares we need to settle by checking our buy fills
                bought_count = sum(
                    int(float(f.get("count_fp") or f.get("count", 0))) 
                    for f in tennis_fills 
                    if f.get("ticker", "").upper() == ticker and f.get("action") == "buy"
                )
                
                sold_count = sum(
                    int(float(f.get("count_fp") or f.get("count", 0))) 
                    for f in tennis_fills 
                    if f.get("ticker", "").upper() == ticker and f.get("action") == "sell"
                )
                
                shares_to_settle = bought_count - sold_count
                
                if shares_to_settle > 0:
                    # Treat settlement identically mathematically to a sell order (revenue = win payout)
                    tennis_fills.append({
                        "ticker": ticker,
                        "created_time": str(datetime.now(timezone.utc).isoformat()), # Use now as settle time
                        "action": "settlement",
                        "count_fp": str(shares_to_settle),
                        "yes_price_dollars": str(settle_price / 100.0)
                    })
        except Exception as e:
            print(f"Failed to fetch market status for {ticker}: {e}")
            
    # Calculate Realized P&L and Active Investment
    ticker_data = {}
    for f in tennis_fills:
        t = f.get("ticker", "unknown")
        if t not in ticker_data:
            ticker_data[t] = {"buy_count": 0, "buy_cost": 0, "sell_count": 0, "sell_revenue": 0}
            
        price_val = f.get("yes_price_dollars") or (f.get("yes_price", 0) / 100.0)
        price = float(price_val)
        count_val = f.get("count_fp") or f.get("count", 0)
        count = int(float(count_val))
        
        if f.get("action") == "buy":
            ticker_data[t]["buy_count"] += count
            ticker_data[t]["buy_cost"] += price * count
        elif f.get("action") == "sell":
            if price < 0.50:
                # HIJACKED: Blanket bot sold this at a loss. Pretend the share never existed.
                avg_buy_price = (ticker_data[t]["buy_cost"] / ticker_data[t]["buy_count"]) if ticker_data[t]["buy_count"] > 0 else 0.45
                ticker_data[t]["buy_count"] -= count
                ticker_data[t]["buy_cost"] -= (avg_buy_price * count)
                continue
            ticker_data[t]["sell_count"] += count
            ticker_data[t]["sell_revenue"] += price * count
        elif f.get("action") == "settlement":
            ticker_data[t]["sell_count"] += count
            ticker_data[t]["sell_revenue"] += price * count
            
    total_realized_pnl = 0
    total_active_investment = 0
    settled_bets = 0
    wins = 0
    
    for t, data in ticker_data.items():
        bought_count = data["buy_count"]
        
        # FILTER: 
        # 1. If bought_count is 0, the trade was placed before our strategy reset cutoff. Skip it.
        # 2. If the user bought a flyer for <= 5 cents, ignore it so it doesn't tank the win rate.
        if bought_count == 0:
            continue
            
        avg_buy_price = data["buy_cost"] / bought_count
        if avg_buy_price <= 0.05:
            continue
                
        sold_count = data["sell_count"]
        
        if sold_count > 0:
            avg_buy_price = data["buy_cost"] / bought_count if bought_count > 0 else 0
            realized_cost = avg_buy_price * sold_count
            pnl = data["sell_revenue"] - realized_cost
            total_realized_pnl += pnl
            
            # Only count as a settled bet if ALL shares have been sold/settled for this match
            if sold_count == bought_count:
                settled_bets += 1
                if pnl > 0:
                    wins += 1
                
    win_rate = (wins / settled_bets * 100) if settled_bets > 0 else 0
    
    # Consolidated Recent Trades (One row per match)
    recent_trades_dict = {}
    
    # Sort fills oldest to newest to build up the match narrative
    for f in sorted(tennis_fills, key=lambda x: x.get("created_time", "")):
        t = f.get("ticker", "")
        
        # FILTER: Skip 1-cent flyers and pre-strategy trades
        data = ticker_data.get(t, {})
        bought_count = data.get("buy_count", 0)
        if bought_count == 0:
            continue
            
        avg_buy_price = data.get("buy_cost", 0) / bought_count
        if avg_buy_price <= 0.05:
            continue
            
        player_name = get_player_name(t)
        if t not in recent_trades_dict:
            recent_trades_dict[t] = {
                "date": f.get("created_time", ""), # Initial buy date
                "last_update": f.get("created_time", ""),
                "player": player_name,
                "action": "open",
                "trade_value": 0, # Will be Net PnL
                "shares_bought": 0,
                "shares_sold": 0,
                "cost": 0,
                "revenue": 0
            }
            
        price_val = f.get("yes_price_dollars") or (f.get("yes_price", 0) / 100.0)
        price = float(price_val)
        count_val = f.get("count_fp") or f.get("count", 0)
        count = int(float(count_val))
        action = f.get("action", "")
        
        recent_trades_dict[t]["last_update"] = f.get("created_time", "")
        
        if action == "buy":
            recent_trades_dict[t]["shares_bought"] += count
            recent_trades_dict[t]["cost"] += price * count
        elif action == "sell":
            if price < 0.50:
                continue # Hijacked
            recent_trades_dict[t]["shares_sold"] += count
            recent_trades_dict[t]["revenue"] += price * count
        elif action == "settlement":
            recent_trades_dict[t]["shares_sold"] += count
            recent_trades_dict[t]["revenue"] += price * count
            
    recent_trades = []
    # Convert dict to list and finalize the Display fields
    for t, match_data in recent_trades_dict.items():
        if match_data["shares_bought"] == 0:
            continue
            
        shares_open = match_data["shares_bought"] - match_data["shares_sold"]
        pnl = match_data["revenue"] - match_data["cost"]
        
        if shares_open == 0:
            match_data["action"] = "won" if pnl > 0 else "lost"
            match_data["trade_value"] = abs(round(pnl, 2))
        elif match_data["shares_sold"] > 0:
            match_data["action"] = "partial" # some shares sold, some still open
            match_data["trade_value"] = round(pnl, 2) # Currently realized pnl
        else:
            match_data["action"] = "buy"
            match_data["trade_value"] = round(match_data["cost"], 2)
            
        match_data["price"] = int((match_data["cost"] / match_data["shares_bought"]) * 100) if match_data["shares_bought"] > 0 else 0
            
        recent_trades.append(match_data)
        
    # Sort backwards by last_update to show most recent activity at the top
    recent_trades.sort(key=lambda x: x["last_update"], reverse=True)
    # Only take the top 20
    recent_trades = recent_trades[:20]

    return jsonify({
        "balance": round(balance, 2),
        "total_realized_pnl": round(total_realized_pnl, 2),
        "active_investment": round(total_active_investment, 2),
        "win_rate": round(win_rate, 1),
        "settled_bets": settled_bets,
        "total_trades": len(tennis_fills),
        "recent_trades": recent_trades
    })

if __name__ == "__main__":
    logging.info("Starting Local Tennis Dashboard on http://localhost:5001")
    app.run(port=5001, debug=True)
