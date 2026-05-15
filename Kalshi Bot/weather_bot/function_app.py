"""
function_app.py  (weather_bot)
Azure Function App — Timer Trigger every 15 minutes.

Environment variables required (set in Azure Function App Configuration):
  KALSHI_API_KEY_ID       — Your Kalshi API Key ID (UUID)
  KALSHI_PRIVATE_KEY_PEM  — RSA private key PEM (full block, newlines as \n)
  AZURE_STORAGE_CONNECTION_STRING — Storage account connection string for state persistence
"""

import os
import logging
import azure.functions as func
from kalshi_client import KalshiClient
from state import PositionState
from strategy import run_strategy

logger = logging.getLogger(__name__)

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 */15 * * * *",  # Every 15 minutes, on the :00 :15 :30 :45
    arg_name="timer",
    run_on_startup=False,         # Run immediately when Function starts (useful for testing)
    use_monitor=False,
)
def weather_bot_timer(timer: func.TimerRequest) -> None:
    """
    Main entry point triggered every 15 minutes.
    Scans all Kalshi daily-temperature markets and executes the
    90¢ maker-entry / 70¢ taker-stop strategy.
    """
    if timer.past_due:
        logger.warning("Timer is past due — running anyway")

    logger.info("Weather bot timer triggered")

    # ------------------------------------------------------------------
    # Load credentials from environment
    # ------------------------------------------------------------------
    api_key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    private_key_pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "").strip()
    storage_conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()

    if not api_key_id or not private_key_pem:
        logger.error("Missing KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY_PEM — aborting")
        return

    if not storage_conn:
        logger.error("Missing AZURE_STORAGE_CONNECTION_STRING — cannot persist state, aborting")
        return

    # PEM keys stored as env vars often have literal \n — normalize them
    if "\\n" in private_key_pem:
        private_key_pem = private_key_pem.replace("\\n", "\n")

    # ------------------------------------------------------------------
    # Initialize clients
    # ------------------------------------------------------------------
    try:
        client = KalshiClient(api_key_id=api_key_id, private_key_pem=private_key_pem)
        state = PositionState(connection_string=storage_conn)
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        return

    # ------------------------------------------------------------------
    # Run the strategy
    # ------------------------------------------------------------------
    try:
        run_strategy(client=client, state=state)
    except Exception as e:
        logger.error(f"Unhandled error in strategy run: {e}", exc_info=True)
