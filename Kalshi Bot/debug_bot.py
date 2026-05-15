import os, sys, json, requests, base64, time
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Load local settings for auth
def _load_private_key():
    pem_data = open('/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json').read().split('KALSHI_PRIVATE_KEY_PEM": "')[1].split('"')[0].replace('\\n', '\n')
    return serialization.load_pem_private_key(pem_data.encode(), password=None)

key = _load_private_key()

def kalshi_get(path, params=None):
    url = 'https://api.elections.kalshi.com' + path
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    clean_path = path.split('?')[0]
    msg = (ts_ms + 'GET' + clean_path).encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    headers = {
        'KALSHI-ACCESS-KEY': '6af327e0-1b7c-4bfc-95ce-7d388824ca5f',
        'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
        'KALSHI-ACCESS-TIMESTAMP': ts_ms,
        'Content-Type': 'application/json'
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    return resp.json()

# 1. Fetch State
from azure.storage.blob import BlobServiceClient
conn = open('/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json').read().split('AZURE_STORAGE_CONNECTION_STRING": "')[1].split('"')[0]
service = BlobServiceClient.from_connection_string(conn)
container = service.get_container_client('tennis-bot-state')
blob = container.get_blob_client('validated_targets.json')
data = blob.download_blob().readall()
state = json.loads(data)

print(f"🔍 Auditing {len(state)} active targets...")

# 2. Check each target
for ticker, info in state.items():
    m_data = kalshi_get(f'/trade-api/v2/markets/{ticker}')
    m = m_data.get('market', {})
    status = m.get('status', 'unknown')
    bid = m.get('yes_bid', 0)
    ask = m.get('yes_ask', 0)
    print(f"[{info['status']}] {ticker} | Status: {status} | Bid: {bid}c | Ask: {ask}c")

print("\n✨ Audit complete.")
