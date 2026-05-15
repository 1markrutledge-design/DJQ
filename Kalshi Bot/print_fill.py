import sys, os, json
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

settings_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json"
with open(settings_path, "r") as f:
    vals = json.load(f).get("Values", {})
os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
os.environ["KALSHI_ENVIRONMENT"] = "prod"

c = KalshiClient()
c.login()
res = c._request("GET", "/portfolio/fills", params={"limit": 5}).json()
print("FILLS KEYS:", res.get("fills", [{}])[0].keys())
print("FIRST TENNIS FILL:")
for f in res.get("fills", []):
    if "KXATP" in f.get("ticker", "") or "KXWTA" in f.get("ticker", ""):
        print(json.dumps(f, indent=2))
        break
