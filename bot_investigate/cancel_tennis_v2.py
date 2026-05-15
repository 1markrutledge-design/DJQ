import os
import sys
import time
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def load_azure_env():
    """Load credentials from local.settings.json that Azure fetch pulled."""
    settings_path = os.path.join(os.path.dirname(__file__), "local.settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
            vals = settings.get("Values", {})
            
            # Map the Azure environment vars to os.environ so KalshiClient picks them up
            if "KALSHI_API_KEY_ID" in vals:
                os.environ["KALSHI_API_KEY_ID"] = vals["KALSHI_API_KEY_ID"]
            
            # KalshiClient looks for KALSHI_API_PRIVATE_KEY, Azure uses KALSHI_PRIVATE_KEY_PEM
            if "KALSHI_PRIVATE_KEY_PEM" in vals:
                os.environ["KALSHI_API_PRIVATE_KEY"] = vals["KALSHI_PRIVATE_KEY_PEM"]
            
            # Force Production Environment so KalshiClient aims correctly
            os.environ["KALSHI_ENVIRONMENT"] = "prod"
                
        except Exception as e:
            logging.error(f"Failed to read local.settings.json: {e}")

def cleanup():
    # Load env first
    load_azure_env()
    
    # Credentials should be set in environment
    if not os.getenv("KALSHI_API_KEY_ID") or not os.getenv("KALSHI_API_PRIVATE_KEY"):
        logging.error("Missing KALSHI_API_KEY_ID or KALSHI_API_PRIVATE_KEY environment variables.")
        return

    # Add bot_code to path to import shared for local testing
    sys.path.append("/Users/markrutledge/Desktop/bot_code")
    from shared.kalshi_client import KalshiClient

    client = KalshiClient()
    try:
        client.login()
        logging.info("Logged in to Kalshi.")
        
        # 1. Get all resting orders
        resting_orders = client.get_resting_orders()
        if not resting_orders:
            logging.info("No resting orders found.")
            return

        # 2. STRICT Filter for Tennis orders
        tennis_orders = [
            o for o in resting_orders
            if "TENNIS" in o.get("ticker", "").upper() or str(o.get("client_order_id", "")).upper().startswith("TENNIS")
        ]
        
        if not tennis_orders:
            logging.info("No resting Tennis orders found.")
            return

        logging.info(f"Found {len(tennis_orders)} resting Tennis orders. Cancelling...")

        # 3. Cancel each targeted order
        for order in tennis_orders:
            order_id = order["order_id"]
            ticker = order["ticker"]
            try:
                client.cancel_order(order_id)
                logging.info(f"✅ Successfully cancelled order {order_id} for {ticker}")
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"❌ Failed to cancel order {order_id}: {e}")

        logging.info("Tennis order cleanup complete. Your new FinalTennisBot configuration is ready to deploy.")

    except Exception as e:
        logging.error(f"Cleanup failed: {e}")

if __name__ == "__main__":
    cleanup()
