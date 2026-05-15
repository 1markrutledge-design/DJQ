import azure.functions as func
import logging
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient
from shared.strategies.ufc_favorite import UFCFavoriteStrategy

app = func.FunctionApp()

# ═══════════════════════════════════════════════════════════════════════════════
# UFC FAVORITE STRATEGY
# ═══════════════════════════════════════════════════════════════════════════════

@app.timer_trigger(schedule="0 0 14-21 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def buyer_timer(myTimer: func.TimerRequest) -> None:
    logging.info('UFC Buyer Timer trigger function started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        # Initialize storage client for logging
        storage = StorageClient()
        
        strategy = UFCFavoriteStrategy(client, storage)
        strategy.execute_buyer()
        
        logging.info('UFC Buyer Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in buyer_timer: {e}")

@app.timer_trigger(schedule="0 */3 17-23,0,1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def seller_timer(myTimer: func.TimerRequest) -> None:
    logging.info('UFC Seller Timer trigger function started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        # Initialize storage client for logging
        storage = StorageClient()
        
        strategy = UFCFavoriteStrategy(client, storage)
        strategy.execute_seller()
        
        logging.info('UFC Seller Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in seller_timer: {e}")
