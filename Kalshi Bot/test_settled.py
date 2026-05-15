import os
import json
from eth_bot.bot import KalshiClient
c = KalshiClient()
res = c.get("/trade-api/v2/markets", {"status": "settled", "series_ticker": "KXETH15M", "limit": 5})
print(json.dumps(res, indent=2))
