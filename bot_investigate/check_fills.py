import sys, os, json, time
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from shared.kalshi_client import KalshiClient

def load_azure_env():
    settings_path = "/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json"
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
    os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
    os.environ["KALSHI_ENVIRONMENT"] = "prod"

load_azure_env()
c = KalshiClient()
c.login()

# Check fills
try:
    res = c._request("GET", "/portfolio/fills", params={"limit": 10})
    fills = res.json().get("fills", [])
    if not fills:
        print("No fills found.")
    for f in fills:
        print(f"FILL FOUND: {f.get('ticker')} | Price: {f.get('yes_price')}¢ | Side: {f.get('side')}")
except Exception as e:
    print(f"Error: {e}")
