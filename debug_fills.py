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
    data = get_kalshi('/trade-api/v2/portfolio/fills', {'limit': 1000})
    fills = data.get('fills', [])
    
    print(f"Checking first 5 fills for {target_date}...")
    count_found = 0
    for f in fills:
        created = f.get('created_time', '')
        if not created.startswith(target_date): continue
        count_found += 1
        if count_found > 10: break
        print(f"Ticker: {f.get('ticker')} | Action: {f.get('side')} / {f.get('action')} | Count: {f.get('count')} | Fee: {f.get('fee_cost')}")

if __name__ == "__main__":
    main()
