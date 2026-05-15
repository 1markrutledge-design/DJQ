import os
import unittest
from unittest.mock import MagicMock
from shared.strategies.ufc_favorite import UFCFavoriteStrategy

class TestUFCFavoriteStrategy(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.strategy = UFCFavoriteStrategy(self.mock_client)
        self.strategy.unit_size = 4

    def test_reconstruction_and_sell(self):
        # 1. Mock fills showing we bought 4 shares of UFC-TICKER-A with strategy prefix
        self.mock_client.get_fills.return_value = [
            {"ticker": "UFC-TICKER-A", "side": "yes", "count": 4, "client_order_id": "88-uuid1"}
        ]
        
        # 2. Mock market price at 85 (triggering full sell)
        self.mock_client.get_markets.return_value = [{"ticker": "UFC-TICKER-A", "yes_bid": 85}]
        
        # 3. Execute seller
        self.strategy.execute_seller()
        
        # 4. Verify order placed to sell 4 shares
        self.mock_client.place_order.assert_called_with(
            ticker="UFC-TICKER-A",
            side="yes",
            action="sell",
            count=4,
            price=85,
            client_order_id=unittest.mock.ANY
        )

    def test_incremental_sell_65(self):
        # Mock owning 4, price is 65
        self.mock_client.get_fills.return_value = [
            {"ticker": "UFC-TICKER-A", "side": "yes", "count": 4, "client_order_id": "88-uuid1"}
        ]
        self.mock_client.get_markets.return_value = [{"ticker": "UFC-TICKER-A", "yes_bid": 65}]
        
        self.strategy.execute_seller()
        
        # Target for 65 is 50% of unit size (Sell 2 shares total)
        # 4 - 2 = 2 shares to sell
        self.mock_client.place_order.assert_called_with(
            ticker="UFC-TICKER-A",
            side="yes",
            action="sell",
            count=2,
            price=65,
            client_order_id=unittest.mock.ANY
        )

    def test_buyer_resting_order_check(self):
        # Mock favorite found
        self.mock_client.get_markets.return_value = [{"ticker": "TICKER-B", "yes_ask": 80}]
        
        # Mock resting order ALREADY exists
        self.mock_client.get_resting_orders.return_value = [
            {"ticker": "TICKER-B", "client_order_id": "88-exists"}
        ]
        
        self.strategy.execute_buyer()
        
        # Should NOT place order
        self.mock_client.place_order.assert_not_called()

    def test_reconstruction_ignore_non_ufc(self):
        # Mock fills showing we bought non-UFC ticker with strategy prefix
        self.mock_client.get_fills.return_value = [
            {"ticker": "MEDVEDEV-SHANG", "side": "yes", "count": 1, "client_order_id": "88-uuid1"}
        ]
        self.mock_client.get_markets.return_value = [{"ticker": "MEDVEDEV-SHANG", "yes_bid": 60}]
        
        self.strategy.execute_seller()
        
        # Verify NO order placed
        self.mock_client.place_order.assert_not_called()

    def test_prevent_duplicate_sell(self):
        # Mock owning UFC shares
        self.mock_client.get_fills.return_value = [
            {"ticker": "UFC-FIGHTER-A", "side": "yes", "count": 4, "client_order_id": "88-uuid1"}
        ]
        self.mock_client.get_markets.return_value = [{"ticker": "UFC-FIGHTER-A", "yes_bid": 85}]
        
        # Mock ALREADY having a resting sell order
        self.mock_client.get_resting_orders.return_value = [
            {"ticker": "UFC-FIGHTER-A", "action": "sell", "count": 4}
        ]
        
        self.strategy.execute_seller()
        
        # Verify NO NEW order placed
        self.mock_client.place_order.assert_not_called()

if __name__ == '__main__':
    unittest.main()
