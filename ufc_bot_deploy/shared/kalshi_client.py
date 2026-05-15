import os
import requests
import logging
import uuid
import base64
import time
import re
import tempfile
from typing import List, Dict, Optional

# Import cryptography for RSA signing
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

class KalshiClient:
    """
    Kalshi API Client using RSA-PSS signatures.
    Based on: https://trading-api.kalshi.com/trade-api/v2/
    
    Signature format: timestamp_ms + method + path (no query params)
    Headers required: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE
    """
    
    def __init__(self):
        self.api_key_id = os.getenv("KALSHI_API_KEY_ID")
        self.api_private_key = os.getenv("KALSHI_API_PRIVATE_KEY")
        self.env = os.getenv("KALSHI_ENVIRONMENT", "demo").lower()
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        # Kalshi API endpoints (Updated Jan 2026 - API moved to new domain)
        if self.env == "prod":
            self.host = "https://api.elections.kalshi.com"
        else:
            self.host = "https://demo-api.kalshi.co"
        
        self.session = requests.Session()
        self._private_key = None
        
        if self.api_private_key:
            self._load_private_key()

    def _load_private_key(self):
        """Load and parse the RSA private key from environment variable."""
        try:
            # Step 1: Get the raw key content
            key_content = self.api_private_key
            
            # Step 2: Handle escaped newlines (from Azure env vars)
            key_content = key_content.replace("\\n", "\n")
            
            # Step 3: Check if it has proper PEM headers
            if "-----BEGIN" not in key_content:
                # Key is just base64 content, need to add headers
                # Remove any whitespace/newlines first
                b64_only = re.sub(r"[^A-Za-z0-9+/=]", "", key_content)
                # Format into 64-char lines
                lines = [b64_only[i:i+64] for i in range(0, len(b64_only), 64)]
                key_content = "-----BEGIN RSA PRIVATE KEY-----\n"
                key_content += "\n".join(lines)
                key_content += "\n-----END RSA PRIVATE KEY-----\n"
            else:
                # Has headers, but might need cleaning
                # Extract just the base64 part and rebuild
                clean_content = re.sub(r"-----BEGIN [A-Z ]+-----", "", key_content)
                clean_content = re.sub(r"-----END [A-Z ]+-----", "", clean_content)
                b64_only = re.sub(r"[^A-Za-z0-9+/=]", "", clean_content)
                lines = [b64_only[i:i+64] for i in range(0, len(b64_only), 64)]
                key_content = "-----BEGIN RSA PRIVATE KEY-----\n"
                key_content += "\n".join(lines)
                key_content += "\n-----END RSA PRIVATE KEY-----\n"
            
            # Step 4: Load the key
            self._private_key = serialization.load_pem_private_key(
                key_content.encode('utf-8'),
                password=None
            )
            logging.info("RSA Private Key loaded successfully.")
            
        except Exception as e:
            logging.error(f"Failed to load private key: {e}")
            self._private_key = None

    def _sign_request(self, method: str, path: str) -> tuple:
        """
        Create the signature for a Kalshi API request.
        
        Returns: (timestamp_str, signature_b64)
        """
        # Timestamp in milliseconds as string
        timestamp = str(int(time.time() * 1000))
        
        # Message to sign: timestamp + method + path
        # Path MUST include /trade-api/v2 prefix
        # Path MUST NOT include query parameters
        message = timestamp + method + path
        
        # Sign with RSA-PSS, SHA256
        signature = self._private_key.sign(
            message.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        # Base64 encode the signature
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return timestamp, signature_b64

    def _request(self, method: str, path: str, params: Dict = None, json_data: Dict = None) -> requests.Response:
        """Make an authenticated request to the Kalshi API."""
        
        # Full path for signing (includes /trade-api/v2)
        full_path = "/trade-api/v2" + path
        
        # Sign the request
        timestamp, signature = self._sign_request(method, full_path)
        
        # Build headers
        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Build URL
        url = self.host + full_path
        
        # Make request
        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data
        )
        
        # Log errors for debugging
        if response.status_code == 401:
            logging.error(f"401 Unauthorized - Path: {full_path}, Timestamp: {timestamp}")
            logging.error(f"Response: {response.text}")
        
        response.raise_for_status()
        return response

    def login(self):
        """Verify credentials are loaded."""
        if not self.api_key_id:
            raise ValueError("KALSHI_API_KEY_ID is not set!")
        if not self._private_key:
            raise ValueError("KALSHI_API_PRIVATE_KEY is missing or invalid!")
        logging.info("RSA credentials verified. Ready to trade.")

    def get_markets(self, ticker: str = None, event_ticker: str = None, series_ticker: str = None) -> List[Dict]:
        """Fetches markets based on filters."""
        params = {}
        if ticker:
            params["ticker"] = ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        
        response = self._request("GET", "/markets", params=params)
        return response.json().get("markets", [])

    def place_order(self, ticker: str, side: str, action: str, count: int, price: int, client_order_id: str) -> Dict:
        """Places a limit order (or simulates it in dry run mode)."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would place {action} order: {count}x {ticker} @ {price}c (ID: {client_order_id})")
            return {"order_id": f"dry-run-{client_order_id}", "status": "simulated"}

        payload = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": "limit",
            "yes_price": price if side == "yes" else 100 - price,
            "client_order_id": client_order_id
        }
        
        response = self._request("POST", "/portfolio/orders", json_data=payload)
        return response.json()

    def get_resting_orders(self, ticker: str = None) -> List[Dict]:
        """Gets all resting orders."""
        params = {"status": "resting"}
        if ticker:
            params["ticker"] = ticker
        
        response = self._request("GET", "/portfolio/orders", params=params)
        return response.json().get("orders", [])

    def get_positions(self) -> List[Dict]:
        """Gets all open positions."""
        response = self._request("GET", "/portfolio/positions")
        return response.json().get("market_positions", [])

    def get_fills(self, ticker: str = None) -> List[Dict]:
        """Gets order fills."""
        params = {}
        if ticker:
            params["ticker"] = ticker
        
        response = self._request("GET", "/portfolio/fills", params=params)
        return response.json().get("fills", [])

    def get_balance(self) -> Dict:
        """Gets account balance."""
        try:
            response = self._request("GET", "/portfolio/balance")
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching balance: {e}")
            return {"balance": 0, "payout": 0}

    def cancel_order(self, order_id: str) -> Dict:
        """Cancels a resting order."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would cancel order: {order_id}")
            return {"status": "simulated"}
            
        response = self._request("DELETE", f"/portfolio/orders/{order_id}")
        return response.json()
