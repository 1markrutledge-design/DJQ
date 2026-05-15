import sys, os, json, time
from datetime import datetime, timezone, timedelta
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

# Check resting orders
try:
    res = c._request("GET", "/portfolio/orders", params={"status": "resting"})
    orders = res.json().get("orders", [])
    if not orders:
        print("No resting orders found.")
    for o in orders:
        print(json.dumps(o, indent=2))
except Exception as e:
    print(f"Error: {e}")
