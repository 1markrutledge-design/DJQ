import os
import time
import json
import base64
import requests
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def get_env_vars():
    vars = {}
    with open('.env.local', 'r') as f:
        for line in f:
            if '=' in line:
                key, val = line.strip().split('=', 1)
                vars[key] = val.strip('"').strip("'").replace('\\n', '\n')
    return vars

def sign_request(method, path):
    env = get_env_vars()
    api_key_id = env.get('KALSHI_API_KEY_ID')
    private_key_pem = env.get('KALSHI_PRIVATE_KEY_PEM')
    if not private_key_pem.startswith('-----BEGIN'):
        private_key_pem = f"-----BEGIN RSA PRIVATE KEY-----\n{private_key_pem}\n-----END RSA PRIVATE KEY-----"
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    clean_path = path.split('?')[0]
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method.upper() + clean_path
    signature = private_key.sign(message.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    return {'KALSHI-ACCESS-KEY': api_key_id, 'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode(), 'KALSHI-ACCESS-TIMESTAMP': timestamp, 'Content-Type': 'application/json'}

def get_kalshi(path, params=None):
    url = f"https://api.elections.kalshi.com{path}"
    headers = sign_request('GET', path)
    resp = requests.get(url, headers=headers, params=params)
    return resp.json() if resp.status_code == 200 else None

def main():
    target_date = "2026-03-31"
    all_fills = []
    cursor = ""
    while True:
        params = {'limit': 1000}
        if cursor: params['cursor'] = cursor
        data = get_kalshi('/trade-api/v2/portfolio/fills', params)
        if not data: break
        fills = data.get('fills', [])
        if not fills: break
        all_fills.extend(fills)
        if fills[-1].get('created_time', '') < target_date: break
        cursor = data.get('cursor')
        if not cursor: break

    ticker_stats = {}
    for f in all_fills:
        created = f.get('created_time', '')
        if not created.startswith(target_date): continue
        ticker = f.get('ticker', '').upper()
        if ticker not in ticker_stats:
            cat = 'other'
            if 'TENNIS' in ticker or ticker.startswith('KXATP') or ticker.startswith('KXWTA'): cat = 'tennis'
            elif ticker.startswith('KXMLBKS'): cat = 'mlb'
            ticker_stats[ticker] = {'buys': [], 'sells': [], 'category': cat, 'fees': 0.0}
        
        fee = float(f.get('fee_cost', '0'))
        # yes_price_fixed is in dollars (0.45)
        price = float(f.get('yes_price_fixed', 0))
        # count_fp is string "1.00"
        count = int(float(f.get('count_fp', 0)))
        
        ticker_stats[ticker]['fees'] += fee
        
        # Bots only care about the YES side of these contracts
        if f.get('side') == 'yes':
            if f.get('action') == 'buy':
                ticker_stats[ticker]['buys'].extend([price] * count)
            else:
                ticker_stats[ticker]['sells'].extend([price] * count)

    bot_summary = {'tennis': {'pnl': 0.0, 'fees': 0.0, 'open': 0, 'trades': 0}, 'mlb': {'pnl': 0.0, 'fees': 0.0, 'open': 0, 'trades': 0}}
    
    print(f"\n--- Ticker Detail for {target_date} ---")
    print(f"{'TICKER':<40} | {'B':<3} | {'S':<3} | {'AVG_B':<6} | {'AVG_S':<6} | {'FEE':<7} | {'PNL':<7}")
    print("-" * 90)

    for ticker, stats in sorted(ticker_stats.items(), key=lambda x: (x[1]['category'], x[0])):
        cat = stats['category']
        if cat not in bot_summary: continue
        
        buys = stats['buys']
        sells = stats['sells']
        num_matched = min(len(buys), len(sells))
        
        realized_raw = sum(sells[:num_matched]) - sum(buys[:num_matched])
        pnl_usd = realized_raw - stats['fees']
        
        bot_summary[cat]['pnl'] += pnl_usd
        bot_summary[cat]['fees'] += stats['fees']
        bot_summary[cat]['open'] += (len(buys) - len(sells))
        bot_summary[cat]['trades'] += (len(buys) + len(sells))
        
        if len(buys) > 0 or len(sells) > 0:
            avg_b = sum(buys)/len(buys) if buys else 0
            avg_s = sum(sells)/len(sells) if sells else 0
            print(f"{ticker:<40} | {len(buys):<3} | {len(sells):<3} | {avg_b:<6.2f} | {avg_s:<6.2f} | ${stats['fees']:<6.2f} | ${pnl_usd:<6.2f}")

    print("\n--- Final Results for {target_date} ---")
    for cat, s in bot_summary.items():
        if s['trades'] > 0:
            print(f"{cat.upper():<10}: PnL=${s['pnl']:<7.2f} (Fees Paid: ${s['fees']:<7.2f}, Total Fills: {s['trades']})")

if __name__ == "__main__":
    main()
