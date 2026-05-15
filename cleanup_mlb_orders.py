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

def call_kalshi(method, path, body=None):
    url = f"https://api.elections.kalshi.com{path}"
    headers = sign_request(method, path)
    if method.upper() == 'GET':
        resp = requests.get(url, headers=headers)
    elif method.upper() == 'DELETE':
        resp = requests.delete(url, headers=headers)
    elif method.upper() == 'POST':
        resp = requests.post(url, headers=headers, json=body)
    
    if resp.status_code not in (200, 201, 204):
        print(f"Error {resp.status_code}: {resp.text}")
        return None
    return resp.json() if resp.status_code != 204 else True

def main():
    print("=== MLB ORDER CLEANUP ===")
    print("Fetching active orders...")
    orders_data = call_kalshi('GET', '/trade-api/v2/portfolio/orders?status=resting&limit=1000')
    if not orders_data:
        print("Could not fetch orders.")
        return

    orders = orders_data.get('orders', [])
    mlb_orders = [o for o in orders if o.get('ticker', '').startswith('KXMLBKS')]
    
    if not mlb_orders:
        print("No active MLB strikeout orders found.")
        return

    print(f"Found {len(mlb_orders)} active MLB orders. Cancelling them...")
    
    cancelled = 0
    for o in mlb_orders:
        oid = o['order_id']
        ticker = o['ticker']
        print(f"Cancelling {ticker} ({oid})...", end=' ')
        if call_kalshi('DELETE', f"/trade-api/v2/portfolio/orders/{oid}"):
            print("Done.")
            cancelled += 1
        else:
            print("FAILED.")
    
    print(f"\nCleanup finished. Cancelled {cancelled} orders.")

if __name__ == "__main__":
    main()
