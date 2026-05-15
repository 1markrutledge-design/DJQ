import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient
from shared.strategies.climate_tracker import ClimateTracker
from shared.strategies.base import BaseStrategy
import uuid

class ClimateOverreactionStrategy(BaseStrategy):
    """
    Climate Overreaction Strategy - handles both Temperature and Rainfall markets.
    
    Temperature: Phoenix, Las Vegas, Austin, Miami, Chicago, NYC
    - Entry tranches: 30% at 45¢, 40% at 40¢, 30% at 35¢
    
    Rainfall: Miami, Tampa, Houston, New Orleans, Seattle
    - Entry tranches: 35% at 45¢, 40% at 40¢, 25% at 35¢
    """
    
    STRATEGY_PREFIX = "CL-"
    
    # Temperature tranches (30-40-30)
    TEMP_ENTRY_TRANCHES = [
        (45, 0.30),
        (40, 0.40),
        (35, 0.30),
    ]
    
    # Rainfall tranches (35-40-25)
    RAIN_ENTRY_TRANCHES = [
        (45, 0.35),
        (40, 0.40),
        (35, 0.25),
    ]
    
    # Exit levels (same for both)
    EXIT_LEVELS = [
        (55, 0.20),
        (65, 0.25),
        (75, 0.30),
        (85, 0.25),
    ]
    
    def __init__(self, kalshi_client: KalshiClient, storage_client: StorageClient):
        super().__init__(kalshi_client)
        self.storage = storage_client
        self.tracker = ClimateTracker(kalshi_client, storage_client)
        
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        self.max_dollars = float(os.getenv("CLIMATE_MAX_DOLLARS", "1"))
    
    def execute_buyer(self):
        """Main entry logic for both temperature and rainfall."""
        logging.info("[CLIMATE] Executing Climate Overreaction Buyer...")
        
        temp_markets, rain_markets = self.tracker.poll_and_store_prices()
        
        # Process temperature markets
        self._process_markets(temp_markets, "temperature", self.TEMP_ENTRY_TRANCHES)
        
        # Process rainfall markets
        self._process_markets(rain_markets, "rainfall", self.RAIN_ENTRY_TRANCHES)
    
    def _process_markets(self, markets: List[Dict], market_type: str, tranches: List):
        """Process a list of markets for entry signals."""
        for market in markets:
            ticker = market["ticker"]
            city = market["city"]
            
            yes_bid = market.get("yes_bid", 0) or 0
            yes_ask = market.get("yes_ask", 0) or 0
            
            if yes_bid == 0 and yes_ask == 0:
                continue
            
            midpoint = (yes_bid + yes_ask) / 2
            spread = yes_ask - yes_bid
            
            # Check existing position
            storage_key = f"{city}_{market_type}"
            existing = self.storage.get_position(storage_key)
            if existing:
                continue
            
            # Check eligibility
            eligible, reason = self.tracker.check_eligibility(
                ticker, city, market_type, midpoint, spread
            )
            if not eligible:
                logging.debug(f"[CLIMATE] {ticker} not eligible: {reason}")
                continue
            
            # Check for overreaction
            is_overreaction, drop = self.tracker.detect_overreaction(ticker, midpoint)
            if not is_overreaction:
                continue
            
            # Execute entry
            self._execute_entry(ticker, city, market_type, midpoint, tranches)
    
    def _execute_entry(self, ticker: str, city: str, market_type: str, 
                       current_price: float, tranches: List):
        """Execute entry orders based on tranches."""
        logging.info(f"[CLIMATE] Entering {market_type} position: {city} ({ticker}) at {current_price:.0f}¢")
        
        storage_key = f"{city}_{market_type}"
        tranches_filled = []
        entry_prices = []
        total_shares = 0
        total_cost = 0
        
        for tranche_price, tranche_pct in tranches:
            if current_price <= tranche_price:
                tranche_dollars = self.max_dollars * tranche_pct
                shares = int(tranche_dollars / (tranche_price / 100))
                
                if shares <= 0:
                    continue
                
                client_id = f"{self.STRATEGY_PREFIX}{city[:3]}-{uuid.uuid4().hex[:6]}"
                
                if self.dry_run:
                    logging.info(f"[DRY RUN] Would buy {shares} shares of {ticker} at {tranche_price}¢ (${tranche_dollars:.2f})")
                    self.storage.log_trade("CLIMATE", ticker, "buy", shares, tranche_price, True)
                else:
                    try:
                        self.client.place_order(
                            ticker=ticker,
                            side="yes",
                            action="buy",
                            count=shares,
                            price=tranche_price,
                            client_order_id=client_id
                        )
                        logging.info(f"[CLIMATE] Placed buy: {shares}x {ticker} at {tranche_price}¢")
                        self.storage.log_trade("CLIMATE", ticker, "buy", shares, tranche_price, False)
                    except Exception as e:
                        logging.error(f"[CLIMATE] Failed to place order: {e}")
                        continue
                
                tranches_filled.append(tranche_price)
                entry_prices.append(tranche_price)
                total_shares += shares
                total_cost += shares * (tranche_price / 100)
        
        if total_shares > 0:
            self.storage.save_position(
                city=storage_key,
                ticker=ticker,
                tranches_filled=tranches_filled,
                entry_prices=entry_prices,
                total_shares=total_shares,
                total_cost=total_cost
            )
            logging.info(f"[CLIMATE] Opened position: {storage_key} - {total_shares} shares, ${total_cost:.2f}")
    
    def execute_seller(self):
        """Main exit logic - check for exits and stop losses."""
        logging.info("[CLIMATE] Executing Climate Overreaction Seller...")
        
        positions = self.storage.get_all_positions()
        
        for storage_key, position in positions.items():
            ticker = position.get("Ticker", position.get("ticker"))
            if not ticker:
                continue
            
            try:
                markets = self.client.get_markets(ticker=ticker)
                if not markets:
                    continue
                market = markets[0]
            except:
                continue
            
            current_bid = market.get("yes_bid", 0) or 0
            current_ask = market.get("yes_ask", 0) or 0
            midpoint = (current_bid + current_ask) / 2 if (current_bid and current_ask) else 0
            spread = current_ask - current_bid if (current_bid and current_ask) else 999
            
            close_time_str = market.get("close_time") or market.get("expiration_time")
            hours_to_event = self._hours_until(close_time_str)
            
            # Check stop-loss
            stop_reason = self._check_stop_loss(ticker, midpoint, spread, hours_to_event)
            if stop_reason:
                self._execute_full_exit(storage_key, position, midpoint, f"STOP: {stop_reason}")
                continue
            
            # Check scale-out exits
            self._execute_scaled_exit(storage_key, position, midpoint)
    
    def _check_stop_loss(self, ticker: str, midpoint: float, spread: float, 
                         hours_to_event: float) -> Optional[str]:
        """Check stop-loss conditions."""
        if midpoint < 30:
            return f"Price {midpoint:.0f}¢ < 30¢"
        
        if spread > 5:
            return f"Spread {spread:.0f}¢ > 5¢"
        
        if hours_to_event < 48 and midpoint < 50:
            return f"<48h to event and price {midpoint:.0f}¢ < 50¢"
        
        if hours_to_event < 24:
            return f"<24h to settlement"
        
        return None
    
    def _hours_until(self, close_time_str: str) -> float:
        """Calculate hours until event."""
        if not close_time_str:
            return 999
        try:
            close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=close_time.tzinfo)
            delta = close_time - now
            return delta.total_seconds() / 3600
        except:
            return 999
    
    def _execute_full_exit(self, storage_key: str, position: Dict, 
                           current_price: float, reason: str):
        """Exit entire position."""
        ticker = position.get("Ticker", position.get("ticker"))
        total_shares = position.get("TotalShares", position.get("total_shares", 0))
        
        logging.warning(f"[CLIMATE] Full exit for {storage_key}: {reason}")
        
        if total_shares > 0:
            client_id = f"{self.STRATEGY_PREFIX}EXIT-{uuid.uuid4().hex[:6]}"
            
            if self.dry_run:
                logging.info(f"[DRY RUN] Would sell ALL {total_shares} shares of {ticker}")
                self.storage.log_trade("CLIMATE", ticker, "sell", total_shares, current_price, True)
            else:
                try:
                    self.client.place_order(
                        ticker=ticker,
                        side="yes",
                        action="sell",
                        count=total_shares,
                        price=int(current_price),
                        client_order_id=client_id
                    )
                    self.storage.log_trade("CLIMATE", ticker, "sell", total_shares, current_price, False)
                except Exception as e:
                    logging.error(f"[CLIMATE] Failed to sell: {e}")
        
        self.storage.close_position(storage_key)
    
    def _execute_scaled_exit(self, storage_key: str, position: Dict, current_price: float):
        """Execute scaled exit based on price levels."""
        ticker = position.get("Ticker", position.get("ticker"))
        total_shares = position.get("TotalShares", position.get("total_shares", 0))
        
        if total_shares <= 0:
            return
        
        for exit_price, exit_pct in self.EXIT_LEVELS:
            if current_price >= exit_price:
                shares_to_sell = int(total_shares * exit_pct)
                if shares_to_sell <= 0:
                    continue
                
                client_id = f"{self.STRATEGY_PREFIX}{exit_price}-{uuid.uuid4().hex[:6]}"
                
                if self.dry_run:
                    logging.info(f"[DRY RUN] Would sell {shares_to_sell} shares at {exit_price}¢")
                    self.storage.log_trade("CLIMATE", ticker, "sell", shares_to_sell, exit_price, True)
                else:
                    try:
                        self.client.place_order(
                            ticker=ticker,
                            side="yes",
                            action="sell",
                            count=shares_to_sell,
                            price=exit_price,
                            client_order_id=client_id
                        )
                        self.storage.log_trade("CLIMATE", ticker, "sell", shares_to_sell, exit_price, False)
                    except Exception as e:
                        logging.error(f"[CLIMATE] Failed to sell: {e}")
                
                remaining = total_shares - shares_to_sell
                if remaining <= 0:
                    self.storage.close_position(storage_key)
                else:
                    self.storage.save_position(
                        city=storage_key,
                        ticker=ticker,
                        tranches_filled=position.get("TranchesFilled", []),
                        entry_prices=position.get("EntryPrices", []),
                        total_shares=remaining,
                        total_cost=position.get("TotalCost", 0)
                    )
                break
