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
    try:
        with open('.env.local', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    vars[key] = val.strip('"').strip("'").replace('\\n', '\n')
    except: pass
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
    print(f"Inspecting all fills for {target_date}...")
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

    # {ticker: {buys: [price], sells: [price], fee: float, cat: str}}
    data = {}
    for f in all_fills:
        created = f.get('created_time', '')
        if not created.startswith(target_date): continue
        
        ticker = f.get('ticker', '').upper()
        if ticker not in data:
            cat = 'other'
            if 'TENNIS' in ticker or ticker.startswith('KXATP') or ticker.startswith('KXWTA'): cat = 'tennis'
            elif ticker.startswith('KXMLBKS'): cat = 'mlb'
            data[ticker] = {'buys': [], 'sells': [], 'fee': 0.0, 'cat': cat}
        
        count = int(f.get('count', 0))
        # yes_price is in cents, but sometimes returned as a string or float.
        # yes_price_fixed is usually more reliable.
        price = float(f.get('yes_price_fixed', 0))
        fee = float(f.get('fee_cost', '0'))
        
        data[ticker]['fee'] += fee
        if f.get('action') == 'buy':
            data[ticker]['buys'].extend([price] * count)
        else:
            data[ticker]['sells'].extend([price] * count)

    print(f"\n{'TICKER':<40} | {'B':<3} | {'S':<3} | {'AVG_B':<6} | {'AVG_S':<6} | {'FEE':<7} | {'PNL':<7}")
    print("-" * 90)
    
    cat_summary = {'tennis': {'pnl': 0.0, 'fees': 0.0}, 'mlb': {'pnl': 0.0, 'fees': 0.0}, 'other': {'pnl': 0.0, 'fees': 0.0}}
    
    for ticker, stats in sorted(data.items(), key=lambda x: x[1]['cat']):
        b_count = len(stats['buys'])
        s_count = len(stats['sells'])
        num = min(b_count, s_count)
        
        avg_b = sum(stats['buys'][:num]) / num if num > 0 else 0
        avg_s = sum(stats['sells'][:num]) / num if num > 0 else 0
        
        pnl_cents = (sum(stats['sells'][:num]) - sum(stats['buys'][:num])) - (stats['fee'] * 100)
        pnl_usd = pnl_cents / 100.0
        
        cat = stats['cat']
        cat_summary[cat]['pnl'] += pnl_usd
        cat_summary[cat]['fees'] += stats['fee']
        
        print(f"{ticker:<40} | {b_count:<3} | {s_count:<3} | {avg_b:<6.1f} | {avg_s:<6.1f} | ${stats['fee']:<6.2f} | ${pnl_usd:<6.2f}")

    print("\n--- Summary ---")
    for cat, s in cat_summary.items():
        if s['fees'] > 0:
            print(f"{cat.upper():<10}: PnL=${s['pnl']:<7.2f} (Fees Paid: ${s['fees']:<7.2f})")

if __name__ == "__main__":
    main()
