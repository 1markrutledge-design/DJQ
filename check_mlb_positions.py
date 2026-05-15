import os
import time
import json
import base64
import requests
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

def get_env_vars():
    vars = {}
    try:
        with open('.env.local', 'r') as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    vars[key] = val.strip('"').strip("'")
    except:
        pass
    return vars

def sign_request(method, path):
    env = get_env_vars()
    api_key_id = env.get('KALSHI_API_KEY_ID')
    private_key_pem = env.get('KALSHI_PRIVATE_KEY_PEM')
    
    if not api_key_id or not private_key_pem:
        raise Exception("Missing Kalshi API credentials in .env.local")

    private_key_pem = private_key_pem.replace('\\n', '\n').strip()
    if not private_key_pem.startswith('-----BEGIN'):
        private_key_pem = f"-----BEGIN RSA PRIVATE KEY-----\n{private_key_pem}\n-----END RSA PRIVATE KEY-----"

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None
    )
    clean_path = path.split('?')[0]
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method.upper() + clean_path
    signature = private_key.sign(
        message.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return {
        'KALSHI-ACCESS-KEY': api_key_id,
        'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode(),
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'Content-Type': 'application/json'
    }

def get_kalshi(path, params=None):
    url = f"https://api.elections.kalshi.com{path}"
    headers = sign_request('GET', path)
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        return None
    return resp.json()

def main():
    print("=== KALSHI PORTFOLIO AUDIT ===")
    
    print("\n1. Active Positions (Non-zero):")
    pos_data = get_kalshi('/trade-api/v2/portfolio/positions', params={'limit': 1000})
    if pos_data:
        positions = [p for p in pos_data.get('positions', []) if p.get('position', 0) != 0]
        if not positions:
            print("   No active positions.")
        for p in positions:
            print(f"   {p['ticker']:40s} | Position: {p['position']:3d} | Market: {p.get('market_v2_id')}")

    print("\n2. Resting Orders:")
    orders_data = get_kalshi('/trade-api/v2/portfolio/orders', params={'status': 'resting', 'limit': 1000})
    if orders_data:
        orders = orders_data.get('orders', [])
        if not orders:
            print("   No resting orders.")
        for o in orders:
            print(f"   {o.get('ticker', 'N/A'):40s} | {o.get('action', 'N/A').upper():4s} {o.get('count', 0):3d} @ {o.get('yes_price')}c | CID: {o.get('client_order_id')}")

    print("\n3. Recent Fills (Last 100):")
    fills_data = get_kalshi('/trade-api/v2/portfolio/fills', params={'limit': 100})
    if fills_data:
        fills = fills_data.get('fills', [])
        if not fills:
            print("   No recent fills.")
        for f in fills:
            print(f"   {f.get('ticker', 'N/A'):40s} | {f.get('action', 'N/A').upper():4s} {f.get('count', 0):3d} @ {f.get('yes_price')}c | Time: {f.get('created_time')}")

    print("\n4. All Orders (Last 50):")
    all_orders_data = get_kalshi('/trade-api/v2/portfolio/orders', params={'limit': 50})
    if all_orders_data:
        all_orders = all_orders_data.get('orders', [])
        for i, o in enumerate(all_orders):
             print(f"   {o.get('ticker', 'N/A'):40s} | {o.get('status', 'N/A'):10s} | {o.get('action', 'N/A').upper():4s} {o.get('count', 0):3d} @ {o.get('yes_price')}c | CID: {o.get('client_order_id')}")
             if i < 3:
                 print(f"      DEBUG RAW: {json.dumps(o)}")

if __name__ == "__main__":
    main()
