import unittest
from unittest.mock import MagicMock, patch
import json
import logging

# Import the logic from function_app
# We'll need to mock the environment and dependencies
with patch.dict('os.environ', {
    "KALSHI_API_KEY_ID": "test",
    "KALSHI_PRIVATE_KEY_PEM": "test",
    "KALSHI_MEMBER_ID": "test",
    "AZURE_STORAGE_CONNECTION_STRING": "test"
}):
    import sys
    sys.path.append('/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot')
    import function_app

class TestMLBSingleOrderLogic(unittest.TestCase):
    
    @patch('function_app.fetch_todays_starters')
    @patch('function_app.fetch_savant_whiff_map')
    @patch('function_app.fetch_pitcher_k9')
    @patch('function_app.fetch_event_markets')
    @patch('function_app.place_limit_buy')
    @patch('function_app.save_order')
    @patch('function_app.mark_sweep_done')
    @patch('function_app._table_client')
    def test_daily_bid_sweep_single_order(self, mock_table, mock_mark_done, mock_save, mock_buy, mock_fetch_markets, mock_k9, mock_whiff, mock_starters):
        # 1. Setup Mock Data
        mock_starters.return_value = [{
            "pitcher_name": "Paul Skenes",
            "mlb_id": 682928,
            "team": "PIT",
            "opponent": "NYM",
            "side": "away",
            "game_time_utc": "2026-03-26T13:15:00Z",
            "game_pk": 123456
        }]
        mock_whiff.return_value = {"682928": 0.30}  # 30% whiff
        mock_k9.return_value = 11.5
        
        # Mock markets: 3 to 7
        mock_fetch_markets.return_value = [
            (3, {"ticker": "TICKER-3", "yes_ask": 80}),
            (4, {"ticker": "TICKER-4", "yes_ask": 70}),
            (5, {"ticker": "TICKER-5", "yes_ask": 60}),
            (6, {"ticker": "TICKER-6", "yes_ask": 50}),
            (7, {"ticker": "TICKER-7", "yes_ask": 40}),
        ]
        
        # 2. Run the sweep
        function_app.Daily_Bid_Sweep()
        
        # 3. Assertions
        # Only ONE call to place_limit_buy should happen.
        
        call_count = mock_buy.call_count
        print(f"DEBUG: place_limit_buy called {call_count} times")
        
        self.assertEqual(call_count, 1, "Should only place ONE order per pitcher")
        
        # Verify it was the anchor tier (highest tier with P >= 70%)
        # For Skenes with K9=11.5, expected Ks is ~7. 70% confidence will be around tier 5 or 6.
        ticker_called = mock_buy.call_args[0][0]
        print(f"DEBUG: Order placed for {ticker_called}")
        
    @patch('function_app.fetch_todays_starters')
    @patch('function_app.fetch_savant_whiff_map')
    @patch('function_app.fetch_pitcher_k9')
    @patch('function_app.fetch_event_markets')
    @patch('function_app.place_limit_buy')
    @patch('function_app.mark_sweep_done')
    def test_daily_bid_sweep_no_greenlight(self, mock_mark_done, mock_buy, mock_fetch_markets, mock_k9, mock_whiff, mock_starters):
        # High tier, low projection
        mock_starters.return_value = [{"pitcher_name": "Bad Pitcher", "mlb_id": 1, "team": "PIT", "opponent": "NYM", "game_time_utc": "2026-03-26T13:15:00Z"}]
        mock_whiff.return_value = {"1": 0.10}
        mock_k9.return_value = 4.0
        mock_fetch_markets.return_value = [(7, {"ticker": "TICKER-7", "yes_ask": 40})]
        
    @patch('function_app.fetch_todays_starters')
    @patch('function_app.fetch_savant_whiff_map')
    @patch('function_app.fetch_pitcher_k9')
    @patch('function_app.fetch_event_markets')
    @patch('function_app.place_limit_buy')
    @patch('function_app.mark_sweep_done')
    @patch('function_app._table_client')
    def test_daily_bid_sweep_share_limit(self, mock_table, mock_mark_done, mock_buy, mock_fetch_markets, mock_k9, mock_whiff, mock_starters):
        # 1. Setup Mock Data with 40 starters
        mock_starters.return_value = [
            {"pitcher_name": f"Pitcher {i}", "mlb_id": i, "team": "PIT", "opponent": "NYM", "game_time_utc": "2026-03-26T13:15:00Z"}
            for i in range(40)
        ]
        mock_whiff.return_value = {str(i): 0.245 for i in range(40)}
        mock_k9.return_value = 15.0
        mock_fetch_markets.return_value = [(5, {"ticker": "TICKER-5", "yes_ask": 50})]
        mock_buy.return_value = "order-id"

        # 2. Run the sweep
        function_app.Daily_Bid_Sweep()

        # 3. Assertions
        # Should stop at 30 shares
        self.assertEqual(mock_buy.call_count, 30, "Should stop after exactly 30 shares")
        print(f"DEBUG: Daily limit test - place_limit_buy called {mock_buy.call_count} times")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
