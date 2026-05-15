import os
import requests
import logging
import uuid
import base64
import hashlib
import hmac
import time
import re
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from typing import List, Dict, Optional

class KalshiClient:
    def __init__(self):
        # 1. Capture and Clean Environment Variables
        self.api_key_id = (os.getenv("KALSHI_API_KEY_ID") or "").strip()
        self.api_private_key = os.getenv("KALSHI_API_PRIVATE_KEY")
        self.env = os.getenv("KALSHI_ENVIRONMENT", "demo").lower().strip()
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        # 2. Setup Host and Path
        # Use main trading API for UFC
        self.path_prefix = "/trade-api/v2"
        if self.env == "prod":
            self.host = "https://api.elections.kalshi.com"
        else:
            self.host = "https://demo-trading-api.kalshi.com"
            
        self.base_url = self.host + self.path_prefix
        self.session = requests.Session()
        self._private_key_obj = None
        
        # 3. Deep Clean & Load RSA Key
        if self.api_private_key:
            try:
                # Remove common pasting errors
                dirty_key = self.api_private_key.replace("\\n", "\n").strip()
                
                # Extract pure base64
                header = "-----BEGIN RSA PRIVATE KEY-----"
                footer = "-----END RSA PRIVATE KEY-----"
                content = dirty_key
                if header in dirty_key:
                    content = dirty_key.split(header)[1].split(footer)[0]
                
                # Strip ALL non-base64 characters
                b64_only = re.sub(r"[^A-Za-z0-9+/=]", "", content)
                
                # Reconstruct PEM
                final_pem = f"{header}\n"
                for i in range(0, len(b64_only), 64):
                    final_pem += b64_only[i:i+64] + "\n"
                final_pem += f"{footer}\n"
                
                self._private_key_obj = serialization.load_pem_private_key(
                    final_pem.encode(),
                    password=None
                )
                logging.info(f"[AUTH] RSA Key loaded successfully. (ID: ...{self.api_key_id[-4:]})")
                logging.info(f"[AUTH] Targeting Environment: {self.env.upper()}")
            except Exception as e:
                logging.error(f"[AUTH] Failed to parse Private Key: {e}")

    def login(self):
        """Mandatory check."""
        if not self.api_key_id:
            raise ValueError("KALSHI_API_KEY_ID is missing in Azure Settings!")
        if not self._private_key_obj:
            raise ValueError("KALSHI_API_PRIVATE_KEY is missing or invalid in Azure Settings!")
        logging.info("[AUTH] Verification complete. Bot is ready.")

    def _request(self, method: str, path_suffix: str, params: Dict = None, json: Dict = None) -> requests.Response:
        """Signs the request using Kalshi V2 Protocol."""
        # 1. Generate Timestamp (ms)
        timestamp = str(int(time.time() * 1000))
        
        # 2. Construct paths: one for signing (no query params), one for the actual request
        path_for_signing = self.path_prefix + path_suffix.split("?")[0]
        
        # Build full URL with query params
        if params:
            from urllib.parse import urlencode
            query_string = urlencode(params)
            full_url = self.host + self.path_prefix + path_suffix + "?" + query_string
        else:
            full_url = self.host + self.path_prefix + path_suffix
        
        # 3. Create Signing Message: timestamp + METHOD + path (NO query params!)
        msg = timestamp + method.upper() + path_for_signing
        
        # 4. Sign with RSA-PSS SHA256
        signature = self._private_key_obj.sign(
            msg.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        b64_signature = base64.b64encode(signature).decode("utf-8")
        
        # 5. Build Headers
        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": b64_signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }
        
        # Diagnostic Log
        logging.info(f"[API] {method} {path_for_signing} | Signing String: '{msg}'")
        
        # 6. Execute Request
        response = self.session.request(method, full_url, headers=headers, json=json)
        
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logging.error(f"[CRITICAL 401] Access Denied! Does Key ID (...{self.api_key_id[-4:]}) match the {self.env.upper()} environment?")
            raise
            
        return response

    def get_markets(self, ticker: str = None, event_ticker: str = None, series_ticker: str = None, status: str = None) -> List[Dict]:
        """Fetches markets based on filters."""
        params = {}
        if ticker: params["ticker"] = ticker
        if event_ticker: params["event_ticker"] = event_ticker
        if series_ticker: params["series_ticker"] = series_ticker
        if status: params["status"] = status
        
        response = self._request("GET", "/markets", params=params)
        markets = response.json().get("markets", [])
        logging.info(f"[DATA] Found {len(markets)} markets{f' (status={status})' if status else ''}.")
        return markets

    def place_order(self, ticker: str, side: str, action: str, count: int, price: int, client_order_id: str) -> Dict:
        """Places a limit order (or simulates it in dry run mode)."""
        if self.dry_run:
            logging.info(f"[DRY RUN] Would place {action} order: {count} shares of {ticker} at {price}c (CID: {client_order_id})")
            return {"order_id": f"simulated-{uuid.uuid4()}", "status": "simulated"}

        payload = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": "limit",
            "yes_price": price if side == "yes" else 100 - price,
            "client_order_id": client_order_id
        }
        
        response = self._request("POST", "/portfolio/orders", json=payload)
        return response.json()

    def get_resting_orders(self, ticker: str = None) -> List[Dict]:
        """Gets all resting orders."""
        params = {"status": "resting"}
        if ticker: params["ticker"] = ticker
        
        response = self._request("GET", "/portfolio/orders", params=params)
        return response.json().get("orders", [])

    def get_positions(self) -> List[Dict]:
        """Gets all open positions."""
        response = self._request("GET", "/portfolio/positions")
        return response.json().get("positions", [])

    def get_fills(self, ticker: str = None) -> List[Dict]:
        """Gets order fills."""
        params = {}
        if ticker: params["ticker"] = ticker
        
        response = self._request("GET", "/portfolio/fills", params=params)
        return response.json().get("fills", [])

    def get_balance(self) -> Dict:
        """Gets account balance information."""
        response = self._request("GET", "/portfolio/balance")
        return response.json()

