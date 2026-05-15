#!/usr/bin/env python3
"""Quick test: connect and print live YES bid prices."""
import asyncio, base64, json, os, sys, time
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import websockets

KEY_ID   = os.environ["KALSHI_API_KEY_ID"]
KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "kalshi_private.pem")

with open(KEY_PATH, "rb") as f:
    PRIVATE_KEY = serialization.load_pem_private_key(f.read(), password=None)

def sign(path):
    ts  = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    sig = PRIVATE_KEY.sign(
        (ts + "GET" + path).encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY":       KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }

async def main():
    import requests
    r = requests.get(
        "https://api.elections.kalshi.com/trade-api/v2/markets",
        params={"series_ticker": "KXBTC15M", "status": "open", "limit": 1},
        headers=sign("/trade-api/v2/markets"),
    )
    markets = r.json().get("markets", [])
    if not markets:
        print("No open KXBTC15M markets right now"); return
    ticker = markets[0]["ticker"]
    print(f"Subscribing to: {ticker}")

    yes_bids = {}
    no_bids  = {}

    async with websockets.connect(
        "wss://api.elections.kalshi.com/trade-api/ws/v2",
        additional_headers=sign("/trade-api/ws/v2"),
    ) as ws:
        await ws.send(json.dumps({"id": 1, "cmd": "subscribe",
            "params": {"channels": ["orderbook_delta"], "market_tickers": [ticker]}}))
        print("Connected. Watching prices (Ctrl-C to stop)...\n")
        async for raw in ws:
            print(f"\nRAW: {raw[:400]}")

asyncio.run(main())
