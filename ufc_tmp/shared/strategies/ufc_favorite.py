import os
import logging
import uuid
from typing import List, Dict
from shared.strategies.base import BaseStrategy

class UFCFavoriteStrategy(BaseStrategy):
    STRATEGY_PREFIX = "88-"
    
    def __init__(self, client, storage_client=None):
        super().__init__(client)
        self.storage = storage_client
        # User requested 4 shares per market
        self.unit_size = int(os.getenv("UFC_FAVORITE_UNIT_SIZE", "4"))
        # Added knobs for flexibility
        self.threshold = int(os.getenv("UFC_FAVORITE_THRESHOLD", "73"))
        self.buy_price = int(os.getenv("UFC_FAVORITE_BUY_PRICE", "45"))
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    def execute_buyer(self):
        """
        Runs at 10 AM ET.
        1. Finds UFC markets.
        2. Identifies favorites (Yes price >= 75).
        3. Places limit buy order at 45 if no resting order exists.
        """
        logging.info("Executing UFC Favorite Buyer strategy...")
        
        # 1. Get UFC series markets (ACTIVE ONLY)
        markets = self.client.get_markets(series_ticker="KXUFCFIGHT", status="active")
        
        for market in markets:
            ticker = market["ticker"]
            yes_price = market["yes_ask"]
            
            # Skip if market is likely settled (Price near 100) or closed
            if yes_price >= 99:
                 continue

            if yes_price >= self.threshold:
                logging.info(f"Market {ticker} identified as favorite (Price: {yes_price})")
                
                # 2. Check for resting orders
                resting_orders = self.client.get_resting_orders(ticker=ticker)
                has_strategy_order = any(o.get("client_order_id", "").startswith(self.STRATEGY_PREFIX) for o in resting_orders)
                
                if has_strategy_order:
                    logging.info(f"Skipping {ticker}: Resting order with prefix {self.STRATEGY_PREFIX} already exists.")
                    continue
                
                # 3. Place Limit Order at 45 (Buying 4 shares as requested)
                client_id = f"{self.STRATEGY_PREFIX}{uuid.uuid4().hex[:8]}"
                try:
                    self.client.place_order(
                        ticker=ticker,
                        side="yes",
                        action="buy",
                        count=self.unit_size,
                        price=self.buy_price,
                        client_order_id=client_id
                    )
                    logging.info(f"Placed limit buy for {ticker} at {self.buy_price} with CID {client_id}")
                    
                    if self.storage:
                        self.storage.log_trade("UFC", ticker, "buy", self.unit_size, self.buy_price, self.dry_run)
                        
                except Exception as e:
                    logging.error(f"Failed to place order for {ticker}: {e}")

    def execute_seller(self):
        """
        Runs every 3 minutes (5 PM - 1:30 AM ET).
        1. Reconstructs quantity owned by strategy 88-.
        2. Sells incrementally (25% at 55c, 65c, 75c, 85c).
        """
        logging.info("Executing UFC Favorite Seller strategy...")
        
        # 1. Get all fills for the account
        all_fills = self.client.get_fills()
        
        # 2. Reconstruct quantity per ticker for this strategy
        strategy_positions = {} 
        
        for fill in all_fills:
            cid = fill.get("client_order_id", "")
            if cid.startswith(self.STRATEGY_PREFIX):
                ticker = fill["ticker"]
                side = fill["side"]
                count = fill["count"]
                
                if ticker not in strategy_positions:
                    strategy_positions[ticker] = 0
                
                if side == "yes": 
                    strategy_positions[ticker] += count
                else: 
                    strategy_positions[ticker] -= count

        # 3. Process each ticker we have a position in
        for ticker, qty in strategy_positions.items():
            if qty <= 0:
                continue
                
            logging.info(f"Strategy {self.STRATEGY_PREFIX} owns {qty} shares of {ticker}")
            
            # Get current market price
            market_data = self.client.get_markets(ticker=ticker)
            if not market_data:
                continue
                
            current_price = market_data[0]["yes_bid"]
            
            # Thresholds: 55, 65, 75, 85
            # User: "sell 25% or 1 share at 55% and sell 25% of the shares for each step"
            # Target Qty:
            # Price < 55 -> 4 shares (100%)
            # 55-64 -> 3 shares (75%)
            # 65-74 -> 2 shares (50%)
            # 75-84 -> 1 share (25%)
            # 85+ -> 0 shares (0%)
            
            target_qty = qty
            if 55 <= current_price < 65:
                # We should have 75% of unit_size left
                target_qty = self.unit_size * 0.75
            elif 65 <= current_price < 75:
                # We should have 50% left
                target_qty = self.unit_size * 0.50
            elif 75 <= current_price < 85:
                # We should have 25% left
                target_qty = self.unit_size * 0.25
            elif current_price >= 85:
                # We should have 0% left
                target_qty = 0
            
            shares_to_sell = int(qty - target_qty)
            
            if shares_to_sell > 0:
                client_id = f"{self.STRATEGY_PREFIX}sell-{uuid.uuid4().hex[:8]}"
                try:
                    self.client.place_order(
                        ticker=ticker,
                        side="yes",
                        action="sell",
                        count=shares_to_sell,
                        price=current_price,
                        client_order_id=client_id
                    )
                    logging.info(f"Sold {shares_to_sell} shares of {ticker} at {current_price} (CID: {client_id})")
                    
                    if self.storage:
                        self.storage.log_trade("UFC", ticker, "sell", shares_to_sell, current_price, self.dry_run)
                        
                except Exception as e:
                    logging.error(f"Failed to sell {ticker}: {e}")
