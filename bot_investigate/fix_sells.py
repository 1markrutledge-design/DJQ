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

orders = []
cursor = None
while True:
    params = {"status": "resting", "limit": 200}
    if cursor: params["cursor"] = cursor
    res = c._request("GET", "/portfolio/orders", params=params).json()
    orders.extend(res.get("orders", []))
    cursor = res.get("cursor")
    if not cursor: break

tennis_orders = [o for o in orders if any(p in o.get('ticker','').upper() for p in ['KXATP','KXWTA','TENNIS'])]

print(f"Total resting tennis orders found: {len(tennis_orders)}")

for o in tennis_orders:
    if o.get("action") == "sell" and o.get("yes_price") != 99:
        ticker = o["ticker"]
        old_price = o.get("yes_price")
        rem_count = o.get("remaining_count", 1)
        
        print(f"Cancelling sell order {o['order_id']} at {old_price}¢ for {ticker}...")
        try:
            c.cancel_order(o["order_id"])
        except Exception as e:
            print(f"Failed to cancel {o['order_id']}: {e}")
            continue
            
        time.sleep(0.5)
        
        print(f"Replacing {ticker} with 99¢ sell order...")
        try:
            c.place_order(
                ticker=ticker,
                side=o["side"],
                action="sell",
                count=rem_count,
                price=99,
                client_order_id=f"TENNIS-REPLACE-{int(time.time()*1000)}"
            )
            print(f"✅ Successfully replaced {ticker} at 99¢")
        except Exception as e:
            print(f"❌ Failed to place new order for {ticker}: {e}")
            
        time.sleep(1.0)
        
print("Done checking and replacing all tennis sell orders.")
