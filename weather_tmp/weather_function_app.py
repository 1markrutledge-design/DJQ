import azure.functions as func
import logging
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient
from shared.strategies.weather_overreaction import WeatherOverreactionStrategy

app = func.FunctionApp()

# ═══════════════════════════════════════════════════════════════════════════════
# WEATHER OVERREACTION STRATEGY
# Runs every 15 minutes, 24/7
# ═══════════════════════════════════════════════════════════════════════════════

@app.timer_trigger(schedule="0 */15 * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def weather_strategy_timer(myTimer: func.TimerRequest) -> None:
    """
    Runs every 15 minutes:
    1. Polls and stores prices for eligible weather markets
    2. Checks for entry signals (overreaction drops)
    3. Checks for exit signals and stop losses
    """
    logging.info('Weather Strategy Timer started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        storage = StorageClient()
        strategy = WeatherOverreactionStrategy(client, storage)
        
        # Run buyer logic (includes price tracking)
        strategy.execute_buyer()
        
        # Run seller logic (exits and stop losses)
        strategy.execute_seller()
        
        # Clean up expired cooldowns
        storage.clear_expired_cooldowns()
        
        logging.info('Weather Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in weather_strategy_timer: {e}")
