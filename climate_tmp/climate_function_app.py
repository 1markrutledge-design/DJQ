import azure.functions as func
import logging
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient
from shared.strategies.climate_overreaction import ClimateOverreactionStrategy

app = func.FunctionApp()

# ═══════════════════════════════════════════════════════════════════════════════
# CLIMATE OVERREACTION STRATEGY
# Runs every 15 minutes, 24/7
# Handles both Temperature and Rainfall markets
# ═══════════════════════════════════════════════════════════════════════════════

@app.timer_trigger(schedule="0 */15 * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def climate_strategy_timer(myTimer: func.TimerRequest) -> None:
    """
    Runs every 15 minutes:
    1. Polls temperature and rainfall markets
    2. Stores prices for tracking
    3. Checks for entry signals (overreaction drops)
    4. Checks for exit signals and stop losses
    """
    logging.info('Climate Strategy Timer started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        storage = StorageClient()
        strategy = ClimateOverreactionStrategy(client, storage)
        
        # Run buyer logic (includes price tracking)
        strategy.execute_buyer()
        
        # Run seller logic (exits and stop losses)
        strategy.execute_seller()
        
        # Clean up expired cooldowns
        storage.clear_expired_cooldowns()
        
        logging.info('Climate Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in climate_strategy_timer: {e}")
