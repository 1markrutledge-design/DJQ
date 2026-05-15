import os
import time
import json
import base64
import requests
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

def get_kalshi(path):
    url = f"https://api.elections.kalshi.com{path}"
    headers = sign_request('GET', path)
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        return None
    return resp.json()

def main():
    print("Fetching fills for Dedura-Palomero...")
    fills_data = get_kalshi('/trade-api/v2/portfolio/fills?limit=1000')
    fills = fills_data.get('fills', [])
    dedrat_fills = [f for f in fills if 'DEDRAT' in f.get('ticker', '').upper()]
    
    print("\nFetching orders for BINTAK-TAK...")
    orders_data = get_kalshi('/trade-api/v2/portfolio/orders?ticker=KXATPCHALLENGERMATCH-26FEB23BINTAK-TAK&limit=100')
    if orders_data:
        orders = orders_data.get('orders', [])
        for o in orders:
            print(f"Order: {o['ticker']} | {o['action']} | {o.get('count', 1)} shares @ {o.get('yes_price')}c | CID: {o.get('client_order_id')}")

    print("\nFetching orders for PELBAR-BAR...")
    orders_data2 = get_kalshi('/trade-api/v2/portfolio/orders?ticker=KXATPMATCH-26FEB23PELBAR-BAR&limit=100')
    if orders_data2:
        orders = orders_data2.get('orders', [])
        for o in orders:
            print(f"Order: {o['ticker']} | {o['action']} | {o.get('count', 1)} shares @ {o.get('yes_price')}c | CID: {o.get('client_order_id')}")

if __name__ == "__main__":
    main()
