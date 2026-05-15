"""
Root-level function_app.py for the Weather Bot Azure Function App.

Azure Functions v2 Python model requires the FunctionApp to be defined
at the root level. This file imports and re-exports the weather bot's
timer trigger so Azure can discover it.

NOTE: If you are running weather_bot as a STANDALONE Function App (its own
Azure resource), use this file as-is.

If you are adding the weather bot to the EXISTING Kalshi Bot Function App
(which already has a root function_app.py), instead paste the @app.timer_trigger
block from weather_bot/function_app.py into the existing root function_app.py
and update the imports accordingly.
"""

import os
import logging
import azure.functions as func

from weather_bot.kalshi_client import KalshiClient
from weather_bot.state import PositionState
from weather_bot.strategy import run_strategy

logger = logging.getLogger(__name__)

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 */15 * * * *",
    arg_name="timer",
    run_on_startup=True,
    use_monitor=False,
)
def weather_bot_timer(timer: func.TimerRequest) -> None:
    """
    Triggered every 15 minutes.
    Scans all Kalshi daily-temperature weather markets and executes
    the 90¢ maker-entry / 70¢ taker-stop strategy across all cities.
    """
    if timer.past_due:
        logger.warning("Timer is past due — running anyway")

    logger.info("=== Weather Bot triggered ===")

    api_key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    private_key_pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "").strip()
    storage_conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()

    if not api_key_id or not private_key_pem:
        logger.error("KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY_PEM not set — aborting")
        return

    if not storage_conn:
        logger.error("AZURE_STORAGE_CONNECTION_STRING not set — aborting")
        return

    # Normalize escaped newlines (common when pasting PEM into Azure env vars)
    if "\\n" in private_key_pem:
        private_key_pem = private_key_pem.replace("\\n", "\n")

    try:
        client = KalshiClient(api_key_id=api_key_id, private_key_pem=private_key_pem)
        state = PositionState(connection_string=storage_conn)
    except Exception as e:
        logger.error(f"Client initialization failed: {e}", exc_info=True)
        return

    try:
        run_strategy(client=client, state=state)
    except Exception as e:
        logger.error(f"Strategy run failed: {e}", exc_info=True)
