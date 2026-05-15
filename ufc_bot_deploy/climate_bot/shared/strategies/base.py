from abc import ABC, abstractmethod
from shared.kalshi_client import KalshiClient

class BaseStrategy(ABC):
    def __init__(self, client: KalshiClient):
        self.client = client

    @abstractmethod
    def execute_buyer(self):
        """Logic for buying shares."""
        pass

    @abstractmethod
    def execute_seller(self):
        """Logic for selling shares."""
        pass
