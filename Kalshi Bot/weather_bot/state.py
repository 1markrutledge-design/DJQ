"""
state.py
Manages open position state using Azure Blob Storage as a lightweight
persistent store.  This keeps track of:

  - Which markets we currently hold a position in
  - The entry order ID (so we can detect partial fills)
  - Whether the resting entry order is still open or filled

Schema stored as JSON blob:
{
  "<ticker>": {
    "status": "resting" | "filled",
    "order_id": "<kalshi_order_id>",
    "entry_price": 90,
    "contracts": 1,
    "stop_armed": true | false,
    "entered_at": "<iso8601>",
    "series": "KXHIGHNY"
  },
  ...
}
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)

CONTAINER_NAME = "weather-bot-state"
BLOB_NAME = "positions.json"


class PositionState:
    def __init__(self, connection_string: str):
        self._blob_service = BlobServiceClient.from_connection_string(connection_string)
        self._container: ContainerClient = self._blob_service.get_container_client(CONTAINER_NAME)
        self._ensure_container()

    def _ensure_container(self):
        try:
            self._container.create_container()
            logger.info(f"Created blob container: {CONTAINER_NAME}")
        except Exception:
            pass  # Already exists

    def _blob(self) -> BlobClient:
        return self._container.get_blob_client(BLOB_NAME)

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load full positions dict from blob. Returns {} if not found."""
        try:
            data = self._blob().download_blob().readall()
            return json.loads(data)
        except ResourceNotFoundError:
            return {}
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}

    def save(self, positions: dict):
        """Overwrite blob with full positions dict."""
        try:
            self._blob().upload_blob(
                json.dumps(positions, indent=2).encode("utf-8"),
                overwrite=True,
            )
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            raise

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def has_position(self, ticker: str) -> bool:
        return ticker in self.load()

    def add_resting_order(self, ticker: str, order_id: str, series: str):
        positions = self.load()
        positions[ticker] = {
            "status": "resting",
            "order_id": order_id,
            "entry_price": 90,
            "contracts": 1,
            "stop_armed": False,
            "entered_at": datetime.now(timezone.utc).isoformat(),
            "series": series,
        }
        self.save(positions)
        logger.info(f"[STATE] Added resting order for {ticker} (order_id={order_id})")

    def mark_filled(self, ticker: str):
        positions = self.load()
        if ticker in positions:
            positions[ticker]["status"] = "filled"
            positions[ticker]["stop_armed"] = True
            self.save(positions)
            logger.info(f"[STATE] Marked {ticker} as FILLED — stop-loss now armed")

    def remove_position(self, ticker: str):
        positions = self.load()
        if ticker in positions:
            del positions[ticker]
            self.save(positions)
            logger.info(f"[STATE] Removed position for {ticker}")

    def all_positions(self) -> dict:
        return self.load()

    def get(self, ticker: str) -> Optional[dict]:
        return self.load().get(ticker)
