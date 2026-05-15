import os
import sys
import logging
from shared.kalshi_client import KalshiClient

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def cleanup():
    # Credentials should be set in environment
    if not os.getenv("KALSHI_API_KEY_ID") or not os.getenv("KALSHI_API_PRIVATE_KEY"):
        logging.error("Missing KALSHI_API_KEY_ID or KALSHI_API_PRIVATE_KEY environment variables.")
        return

    client = KalshiClient()
    try:
        client.login()
        logging.info("Logged in to Kalshi.")
        
        # 1. Get all resting orders
        resting_orders = client.get_resting_orders()
        if not resting_orders:
            logging.info("No resting orders found.")
            return

        # 2. Filter for Tennis orders
        tennis_orders = [o for o in resting_orders if "TENNIS" in o.get("ticker", "").upper()]
        
        if not tennis_orders:
            logging.info("No resting Tennis orders found.")
            return

        logging.info(f"Found {len(tennis_orders)} resting Tennis orders. Cancelling...")

        # 3. Cancel each order
        for order in tennis_orders:
            order_id = order["order_id"]
            ticker = order["ticker"]
            try:
                client.cancel_order(order_id)
                logging.info(f"Successfully cancelled order {order_id} for {ticker}")
            except Exception as e:
                logging.error(f"Failed to cancel order {order_id}: {e}")

        logging.info("Tennis order cleanup complete.")

    except Exception as e:
        logging.error(f"Cleanup failed: {e}")

if __name__ == "__main__":
    # Add bot_code to path to import shared
    sys.path.append("/Users/markrutledge/Desktop/bot_code")
    cleanup()
