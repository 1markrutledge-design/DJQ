import os
import time
import json
import base64
import logging
import requests
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def clean_pem(pem_data: str) -> str:
    """Ensure the PEM has proper newlines and headers."""
    # Strip any surrounding quotes and whitespace
    pem_data = pem_data.strip().strip('"')
    
    # Handle literal \n text
    pem_data = pem_data.replace("\\n", "\n")
    
    # Ensure it starts and ends with headers
    if "BEGIN RSA PRIVATE KEY" not in pem_data:
        logging.warning("PEM might be missing headers or in wrong format")
        
    return pem_data

def sign_request(key_id: str, private_key_pem: str, method: str, path: str):
    timestamp_ms = str(int(time.time() * 1000))
    message = (timestamp_ms + method.upper() + path).encode()
    
    # Load Key
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None
    )
    
    # Sign
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256().digest_size
        ),
        hashes.SHA256()
    )
    
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms
    }

def test_api(name: str, base_url: str, key_id: str, private_key_pem: str):
    path = "/trade-api/v2/portfolio/balance"
    url = base_url + path
    
    logging.info(f"Testing {name} API...")
    try:
        headers = sign_request(key_id, private_key_pem, "GET", path)
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            logging.info(f"✅ {name} SUCCESS! Balance: {resp.json().get('balance', 'N/A')}")
            return True
        else:
            logging.error(f"❌ {name} FAILED: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logging.error(f"❌ {name} ERROR: {e}")
        return False

if __name__ == "__main__":
    # YOU MUST SET THESE LOCALLY OR IN YOUR SHELL
    KEY_ID = os.getenv("KALSHI_API_KEY_ID")
    PRIVATE_KEY = os.getenv("KALSHI_PRIVATE_KEY_PEM")
    
    if not KEY_ID or not PRIVATE_KEY:
        logging.error("Missing environment variables: KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PEM")
        print("\nHow to run:")
        print("KALSHI_API_KEY_ID='your-id' KALSHI_PRIVATE_KEY_PEM=\"$(cat your-key.key)\" python3 test_kalshi_auth.py")
    else:
        cleaned_key = clean_pem(PRIVATE_KEY)
        
        # Test Prod
        test_api("PRODUCTION", "https://trading-api.kalshi.com", KEY_ID, cleaned_key)
        
        # Test Demo
        test_api("DEMO", "https://demo-api.kalshi.co", KEY_ID, cleaned_key)
