import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient
from shared.strategies.weather_tracker import WeatherTracker
from shared.strategies.base import BaseStrategy
import uuid

class WeatherOverreactionStrategy(BaseStrategy):
    """
    Weather Overreaction Strategy:
    - Targets temperature markets in Phoenix, Las Vegas, Dallas, Houston, Miami, Tampa
    - Enters on 20+ point drops from 12-hour high when price is 35-45%
    - Builds position in 3 tranches (30% at 45%, 40% at 40%, 30% at 35%)
    - Exits by scaling out (20% at 55%, 25% at 65%, 30% at 75%, 25% at 85%)
    - Multiple stop-loss conditions
    """
    
    STRATEGY_PREFIX = "WX-"
    
    # Entry tranches: (threshold, percentage of max position)
    ENTRY_TRANCHES = [
        (45, 0.30),  # 30% at 45¢
        (40, 0.40),  # 40% at 40¢
        (35, 0.30),  # 30% at 35¢
    ]
    
    # Exit levels: (threshold, percentage of position to sell)
    EXIT_LEVELS = [
        (55, 0.20),  # 20% at 55¢
        (65, 0.25),  # 25% at 65¢
        (75, 0.30),  # 30% at 75¢
        (85, 0.25),  # 25% at 85¢
    ]
    
    def __init__(self, kalshi_client: KalshiClient, storage_client: StorageClient):
        super().__init__(kalshi_client)
        self.storage = storage_client
        self.tracker = WeatherTracker(kalshi_client, storage_client)
        
        # Configuration from environment
        self.max_per_market_pct = float(os.getenv("WEATHER_PER_MARKET_PCT", "5")) / 100
        self.max_exposure_pct = float(os.getenv("WEATHER_MAX_EXPOSURE_PCT", "25")) / 100
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
        
        # Fixed dollar amount per trade (overrides percentage if set)
        self.max_dollars_per_trade = float(os.getenv("WEATHER_MAX_DOLLARS", "3"))
    
    def get_account_balance(self) -> float:
        """Fetch available balance from Kalshi."""
        try:
            # This requires adding get_balance to KalshiClient
            balance_data = self.client.get_balance()
            return balance_data.get("available_balance", 0) / 100  # Convert cents to dollars
        except Exception as e:
            logging.warning(f"[WEATHER] Could not fetch balance: {e}. Using fallback.")
            return 10000  # Fallback for testing
    
    def calculate_max_position(self, balance: float) -> float:
        """Calculate max position size for a single market."""
        # Use fixed dollar amount if set, otherwise use percentage
        if self.max_dollars_per_trade > 0:
            return self.max_dollars_per_trade
        return balance * self.max_per_market_pct
    
    def calculate_total_exposure(self) -> float:
        """Calculate current total exposure across all weather positions."""
        positions = self.storage.get_all_positions()
        total = sum(pos.get("TotalCost", pos.get("total_cost", 0)) for pos in positions.values())
        return total
    
    def execute_tracker(self):
        """Run the price tracker to store current prices."""
        logging.info("[WEATHER] Running price tracker...")
        return self.tracker.poll_and_store_prices()
    
    def execute_buyer(self):
        """
        Main entry logic - runs every 15 minutes.
        1. Poll and store prices
        2. Check each market for entry signals
        3. Execute tranche entries
        """
        logging.info("[WEATHER] Executing Weather Overreaction Buyer...")
        
        # 1. Poll prices
        markets = self.execute_tracker()
        
        # 2. Get balance and calculate limits
        balance = self.get_account_balance()
        max_per_market = self.calculate_max_position(balance)
        current_exposure = self.calculate_total_exposure()
        max_total = balance * self.max_exposure_pct
        
        logging.info(f"[WEATHER] Balance: ${balance:.2f}, Max/Market: ${max_per_market:.2f}, Exposure: ${current_exposure:.2f}/{max_total:.2f}")
        
        # 3. Check each market for entry signals
        for market in markets:
            ticker = market["ticker"]
            city = market["city"]
            midpoint = market["midpoint"]
            spread = market["spread"]
            
            # Check if we already have a position
            existing_position = self.storage.get_position(city)
            if existing_position:
                logging.debug(f"[WEATHER] Skipping {city}: Already have position")
                continue
            
            # Check eligibility
            eligible, reason = self.tracker.check_eligibility_criteria(ticker, city, midpoint, spread)
            if not eligible:
                logging.debug(f"[WEATHER] {ticker} not eligible: {reason}")
                continue
            
            # Check for overreaction
            is_overreaction, drop = self.tracker.detect_overreaction(ticker, midpoint)
            if not is_overreaction:
                continue
            
            # Check total exposure cap
            if current_exposure >= max_total:
                logging.warning(f"[WEATHER] Max exposure reached (${current_exposure:.2f}). Skipping entry.")
                continue
            
            # Execute entry tranches
            self._execute_entry(ticker, city, midpoint, max_per_market, spread)
    
    def _execute_entry(self, ticker: str, city: str, current_price: float, max_position: float, spread: float):
        """Execute entry orders based on current price and tranches."""
        logging.info(f"[WEATHER] Entering position for {city} ({ticker}) at {current_price:.0f}¢")
        
        tranches_filled = []
        entry_prices = []
        total_shares = 0
        total_cost = 0
        
        for tranche_price, tranche_pct in self.ENTRY_TRANCHES:
            if current_price <= tranche_price:
                # Calculate shares for this tranche
                tranche_dollars = max_position * tranche_pct
                shares = int(tranche_dollars / (tranche_price / 100))
                
                if shares <= 0:
                    continue
                
                # Place order
                client_id = f"{self.STRATEGY_PREFIX}{city[:3]}-{uuid.uuid4().hex[:6]}"
                
                if self.dry_run:
                    logging.info(f"[DRY RUN] Would buy {shares} shares of {ticker} at {tranche_price}¢ (${tranche_dollars:.2f})")
                    self.storage.log_trade("WEATHER", ticker, "buy", shares, tranche_price, True)
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
                        logging.info(f"[WEATHER] Placed buy: {shares} shares of {ticker} at {tranche_price}¢")
                        self.storage.log_trade("WEATHER", ticker, "buy", shares, tranche_price, False)
                    except Exception as e:
                        logging.error(f"[WEATHER] Failed to place order: {e}")
                        continue
                
                tranches_filled.append(tranche_price)
                entry_prices.append(tranche_price)
                total_shares += shares
                total_cost += shares * (tranche_price / 100)
        
        # Save position
        if total_shares > 0:
            self.storage.save_position(
                city=city,
                ticker=ticker,
                tranches_filled=tranches_filled,
                entry_prices=entry_prices,
                total_shares=total_shares,
                total_cost=total_cost
            )
            logging.info(f"[WEATHER] Opened position: {city} - {total_shares} shares, cost ${total_cost:.2f}")
    
    def execute_seller(self):
        """
        Main exit logic - runs every 15 minutes.
        1. Check each open position for exit signals
        2. Check stop-loss conditions
        3. Execute exits
        """
        logging.info("[WEATHER] Executing Weather Overreaction Seller...")
        
        # Get all open positions
        positions = self.storage.get_all_positions()
        
        for city, position in positions.items():
            ticker = position.get("Ticker", position.get("ticker"))
            
            if not ticker:
                continue
            
            # Get current market data
            try:
                markets = self.client.get_markets(ticker=ticker)
                if not markets:
                    continue
                market = markets[0]
            except Exception as e:
                logging.error(f"[WEATHER] Error fetching market {ticker}: {e}")
                continue
            
            current_bid = market.get("yes_bid", 0)
            current_ask = market.get("yes_ask", 0)
            midpoint = (current_bid + current_ask) / 2 if (current_bid and current_ask) else 0
            spread = current_ask - current_bid if (current_bid and current_ask) else 999
            
            # Get event time
            close_time_str = market.get("close_time") or market.get("expiration_time")
            hours_to_event = self._hours_until(close_time_str)
            
            # Check stop-loss conditions
            stop_reason = self._check_stop_loss(ticker, city, midpoint, spread, hours_to_event)
            if stop_reason:
                self._execute_full_exit(city, position, midpoint, f"STOP LOSS: {stop_reason}")
                continue
            
            # Check exit levels (scaling out)
            self._execute_scaled_exit(city, position, midpoint)
    
    def _check_stop_loss(self, ticker: str, city: str, midpoint: float, spread: float, hours_to_event: float) -> Optional[str]:
        """Check all stop-loss conditions. Returns reason if triggered, None otherwise."""
        
        # 1. Price < 30%
        if midpoint < 30:
            return f"Price {midpoint:.0f}¢ < 30¢"
        
        # 2. Spread > 5¢
        if spread > 5:
            return f"Spread {spread:.0f}¢ > 5¢"
        
        # 3. < 48 hours to event AND price < 50%
        if hours_to_event < 48 and midpoint < 50:
            return f"<48h to event ({hours_to_event:.0f}h) and price {midpoint:.0f}¢ < 50¢"
        
        # 4. < 24 hours to event (auto-exit)
        if hours_to_event < 24:
            return f"Auto-exit: <24h to settlement ({hours_to_event:.0f}h)"
        
        # 5. Price < 35% for 24 consecutive hours (would need history tracking)
        # TODO: Implement this check using price history
        
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
    
    def _execute_full_exit(self, city: str, position: Dict, current_price: float, reason: str):
        """Exit entire position immediately."""
        ticker = position.get("Ticker", position.get("ticker"))
        total_shares = position.get("TotalShares", position.get("total_shares", 0))
        
        logging.warning(f"[WEATHER] Full exit for {city}: {reason}")
        
        if total_shares > 0:
            client_id = f"{self.STRATEGY_PREFIX}{city[:3]}-EXIT-{uuid.uuid4().hex[:6]}"
            
            if self.dry_run:
                logging.info(f"[DRY RUN] Would sell ALL {total_shares} shares of {ticker} at {current_price:.0f}¢")
                self.storage.log_trade("WEATHER", ticker, "sell", total_shares, current_price, True)
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
                    logging.info(f"[WEATHER] Sold {total_shares} shares of {ticker} at {current_price:.0f}¢")
                    self.storage.log_trade("WEATHER", ticker, "sell", total_shares, current_price, False)
                except Exception as e:
                    logging.error(f"[WEATHER] Failed to sell: {e}")
        
        # Close position and set cooldown
        self.storage.close_position(city)
    
    def _execute_scaled_exit(self, city: str, position: Dict, current_price: float):
        """Execute scaled exit based on current price level."""
        ticker = position.get("Ticker", position.get("ticker"))
        total_shares = position.get("TotalShares", position.get("total_shares", 0))
        
        if total_shares <= 0:
            return
        
        for exit_price, exit_pct in self.EXIT_LEVELS:
            if current_price >= exit_price:
                shares_to_sell = int(total_shares * exit_pct)
                
                if shares_to_sell <= 0:
                    continue
                
                # Check if we already sold at this level (would need exit tracking)
                # For now, we'll sell proportionally
                
                client_id = f"{self.STRATEGY_PREFIX}{city[:3]}-{exit_price}-{uuid.uuid4().hex[:6]}"
                
                if self.dry_run:
                    logging.info(f"[DRY RUN] Would sell {shares_to_sell} shares ({exit_pct*100:.0f}%) of {ticker} at {exit_price}¢")
                    self.storage.log_trade("WEATHER", ticker, "sell", shares_to_sell, exit_price, True)
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
                        logging.info(f"[WEATHER] Sold {shares_to_sell} shares of {ticker} at {exit_price}¢")
                        self.storage.log_trade("WEATHER", ticker, "sell", shares_to_sell, exit_price, False)
                    except Exception as e:
                        logging.error(f"[WEATHER] Failed to sell: {e}")
                
                # Update position
                remaining = total_shares - shares_to_sell
                if remaining <= 0:
                    self.storage.close_position(city)
                else:
                    # Update with reduced shares
                    self.storage.save_position(
                        city=city,
                        ticker=ticker,
                        tranches_filled=position.get("TranchesFilled", position.get("tranches_filled", [])),
                        entry_prices=position.get("EntryPrices", position.get("entry_prices", [])),
                        total_shares=remaining,
                        total_cost=position.get("TotalCost", position.get("total_cost", 0))
                    )
                
                break  # Only one exit level per cycle
