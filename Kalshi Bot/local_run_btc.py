import sys, os, time, logging
sys.path.append('/Users/markrutledge/Documents/DjQueue/Kalshi Bot')
from function_app import load_state, sync_portfolio_to_state, btc_hourly_bot_logic, save_state, BTC_BLOB_NAME, BTC_HOURLY_SERIES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_cycle():
    try:
        logging.info("--- START LOCAL CYCLE ---")
        state = load_state(BTC_BLOB_NAME)
        state = sync_portfolio_to_state(state, allowed_prefixes=(BTC_HOURLY_SERIES,), target_exit_price=None)
        state = btc_hourly_bot_logic(state)
        save_state(state, BTC_BLOB_NAME)
        logging.info("--- CYCLE COMPLETE ---")
    except Exception as e:
        logging.error(f"Cycle failed: {e}")

if __name__ == "__main__":
    while True:
        run_cycle()
        time.sleep(60)
