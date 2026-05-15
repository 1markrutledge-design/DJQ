"""
kalshi_client.py
Handles all Kalshi REST API interactions for the weather bot.
"""

import time
import base64
import hashlib
import json
import os
import logging
from typing import Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    def __init__(self, api_key_id: str, private_key_pem: str):
        """
        api_key_id      : Your Kalshi API Key ID (UUID string)
        private_key_pem : RSA private key in PEM format (the full -----BEGIN... block)
        """
        self.api_key_id = api_key_id
        self.private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _sign(self, timestamp_ms: str, method: str, path: str) -> str:
        """Generate RSA-PSS SHA256 signature for request auth."""
        message = timestamp_ms + method.upper() + path
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _auth_headers(self, method: str, path: str) -> dict:
        ts = str(int(time.time() * 1000))
        # Kalshi V2 requires the signature path to start with /trade-api/v2
        full_path = "/trade-api/v2" + path
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method, full_path),
        }

    # ------------------------------------------------------------------
    # Generic request
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, params: dict = None, body: dict = None) -> dict:
        url = BASE_URL + path
        headers = self._auth_headers(method, path)

        try:
            resp = self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=body,
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code} on {method} {path}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request error on {method} {path}: {e}")
            raise

    # ------------------------------------------------------------------
    # Markets
    # ------------------------------------------------------------------

    def get_markets_for_series(self, series_ticker: str, status: str = "open") -> list[dict]:
        """Return all open markets belonging to a given series (e.g. KXHIGHNY)."""
        path = "/markets"
        params = {
            "series_ticker": series_ticker,
            "status": status,
            "limit": 100,
        }
        data = self._request("GET", path, params=params)
        return data.get("markets", [])

    def get_market(self, ticker: str) -> dict:
        """Return a single market by its full ticker."""
        path = f"/markets/{ticker}"
        return self._request("GET", path).get("market", {})

    def get_orderbook(self, ticker: str, depth: int = 1) -> dict:
        """Return order book for a market."""
        path = f"/markets/{ticker}/orderbook"
        return self._request("GET", path, params={"depth": depth})

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict]:
        """Return all open event positions."""
        path = "/portfolio/positions"
        data = self._request("GET", path)
        return data.get("market_positions", [])

    def get_position_for_ticker(self, ticker: str) -> Optional[dict]:
        """Return position dict for a single ticker, or None."""
        positions = self.get_positions()
        for p in positions:
            if p.get("ticker") == ticker:
                return p
        return None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self, ticker: str = None, status: str = "resting") -> list[dict]:
        """Return open/resting orders, optionally filtered by ticker."""
        path = "/portfolio/orders"
        params = {"status": status}
        if ticker:
            params["ticker"] = ticker
        data = self._request("GET", path, params=params)
        return data.get("orders", [])

    def place_limit_order(
        self,
        ticker: str,
        side: str,           # "yes" or "no"
        count: int,          # number of contracts
        limit_price: int,    # price in cents, 1-99
        order_type: str = "limit",
        time_in_force: str = "GTC",  # GTC = good-till-cancelled (resting maker)
    ) -> dict:
        import uuid
        order_id = str(uuid.uuid4())
        
        path = "/portfolio/orders"
        body = {
            "ticker": ticker,
            "action": "buy",
            "type": "limit",
            "count": int(count),
            "side": "yes",
            "client_order_id": order_id,
            "yes_price": int(limit_price)
        }

        logger.info(f"Placing limit order: {body}")
        data = self._request("POST", path, body=body)
        return data.get("order", {})


    def place_market_order(
        self,
        ticker: str,
        side: str,    # "yes" or "no"
        count: int,
        action: str = "sell",
    ) -> dict:
        """
        Place a 'market' (taker) order by using a limit order with a 1c floor.
        Ensures immediate execution and compatibility with Kalshi v2 API.
        """
        import uuid
        order_id = str(uuid.uuid4())
        
        path = "/portfolio/orders"
        body = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "type": "limit",
            "count": int(count),
            "client_order_id": order_id,
        }
        
        # For selling YES, a limit of 1c ensures we hit the best available bid.
        if side == "yes":
            body["yes_price"] = 1
        else:
            # For selling NO, buying YES at 99c ensures we hit the best NO bid.
            body["yes_price"] = 99

        logger.info(f"Placing taker (market) order: {body}")
        data = self._request("POST", path, body=body)
        return data.get("order", {})

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a resting order by its order ID."""
        path = f"/portfolio/orders/{order_id}"
        return self._request("DELETE", path)
