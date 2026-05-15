import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient

class WeatherTracker:
    """
    Tracks prices for weather temperature markets in target cities.
    Polls every 15 minutes and stores 72-hour rolling history.
    """
    
    # Target cities for temperature markets
    TARGET_CITIES = ["Phoenix", "Las Vegas", "Dallas", "Houston", "Miami", "Tampa"]
    
    # Map city names to potential ticker patterns
    CITY_PATTERNS = {
        "Phoenix": ["PHX", "PHOENIX"],
        "Las Vegas": ["LAS", "VEGAS", "LV"],
        "Dallas": ["DAL", "DALLAS", "DFW"],
        "Houston": ["HOU", "HOUSTON", "IAH"],
        "Miami": ["MIA", "MIAMI"],
        "Tampa": ["TPA", "TAMPA"]
    }
    
    def __init__(self, kalshi_client: KalshiClient, storage_client: StorageClient):
        self.kalshi = kalshi_client
        self.storage = storage_client
    
    def identify_city(self, ticker: str, title: str = "") -> Optional[str]:
        """Identify which target city a market belongs to."""
        search_text = (ticker + " " + title).upper()
        
        for city, patterns in self.CITY_PATTERNS.items():
            for pattern in patterns:
                if pattern in search_text:
                    return city
        return None
    
    def get_eligible_markets(self) -> List[Dict]:
        """
        Fetch all temperature markets that meet basic criteria:
        - Event date 3-10 days in the future
        - Volume >= $20,000
        - In one of our target cities
        """
        eligible = []
        
        try:
            # City-specific series tickers for high temperature markets
            city_series = [
                "KXHIGHPHX",  # Phoenix
                "KXHIGHLV",   # Las Vegas
                "KXHIGHDAL",  # Dallas
                "KXHIGHDFW",  # Dallas (alternate)
                "KXHIGHHOU",  # Houston
                "KXHIGHMIA",  # Miami
                "KXHIGHTPA",  # Tampa
            ]
            
            # Also try generic tickers
            generic_tickers = ["HIGHTEMP", "KXHIGHTEMP", "KXTEMP", "TEMP"]
            
            all_markets = []
            
            # Search city-specific series first
            for series in city_series:
                try:
                    markets = self.kalshi.get_markets(series_ticker=series, status="active")
                    if markets:
                        logging.info(f"[TRACKER] Found {len(markets)} markets for series {series}")
                        all_markets.extend(markets)
                except Exception as e:
                    logging.debug(f"[TRACKER] No markets for series {series}")
            
            # Then try generic tickers
            for series in generic_tickers:
                try:
                    markets = self.kalshi.get_markets(series_ticker=series, status="active")
                    if markets:
                        logging.info(f"[TRACKER] Found {len(markets)} markets for series {series}")
                        all_markets.extend(markets)
                except Exception as e:
                    logging.debug(f"[TRACKER] No markets for series {series}")
            
            # If no specific series found, try getting all markets and filtering by title
            if not all_markets:
                logging.info("[TRACKER] No weather series found, trying to fetch all markets...")
                try:
                    all_available = self.kalshi.get_markets(status="active")
                    # Filter for temperature-related markets
                    for m in all_available:
                        title = (m.get("title", "") + " " + m.get("ticker", "")).upper()
                        if any(kw in title for kw in ["TEMP", "DEGREE", "WEATHER", "HIGH"]):
                            all_markets.append(m)
                    logging.info(f"[TRACKER] Found {len(all_markets)} potential weather markets from all markets")
                except:
                    pass
            
            now = datetime.utcnow()
            min_date = now + timedelta(days=3)
            max_date = now + timedelta(days=10)
            
            for market in all_markets:
                ticker = market.get("ticker", "")
                title = market.get("title", "")
                
                # Check city
                city = self.identify_city(ticker, title)
                if not city:
                    continue
                
                # Check event date (3-10 days out)
                close_time_str = market.get("close_time") or market.get("expiration_time")
                if close_time_str:
                    try:
                        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                        if not (min_date <= close_time <= max_date):
                            continue
                    except:
                        continue
                
                # Check volume (>= $20,000)
                volume = market.get("volume", 0) or 0
                if volume < 20000:
                    logging.debug(f"[TRACKER] Skipping {ticker}: Volume ${volume} < $20,000")
                    continue
                
                # Add city to market data
                market["city"] = city
                eligible.append(market)
                
            logging.info(f"[TRACKER] Found {len(eligible)} eligible temperature markets")
            
        except Exception as e:
            logging.error(f"[TRACKER] Error fetching markets: {e}")
        
        return eligible
    
    def poll_and_store_prices(self) -> List[Dict]:
        """
        Main polling function - runs every 15 minutes.
        Fetches prices for all eligible markets and stores them.
        Returns list of markets with their current data.
        """
        markets = self.get_eligible_markets()
        stored = []
        
        for market in markets:
            ticker = market.get("ticker")
            city = market.get("city")
            
            # Calculate midpoint, bid, ask
            yes_bid = market.get("yes_bid", 0) or 0
            yes_ask = market.get("yes_ask", 0) or 0
            
            if yes_bid == 0 and yes_ask == 0:
                continue
                
            midpoint = (yes_bid + yes_ask) / 2
            spread = yes_ask - yes_bid
            volume = market.get("volume", 0) or 0
            
            # Store the price snapshot
            self.storage.store_price(
                ticker=ticker,
                city=city,
                midpoint=midpoint,
                bid=yes_bid,
                ask=yes_ask,
                volume=volume
            )
            
            stored.append({
                "ticker": ticker,
                "city": city,
                "midpoint": midpoint,
                "bid": yes_bid,
                "ask": yes_ask,
                "spread": spread,
                "volume": volume,
                "close_time": market.get("close_time") or market.get("expiration_time")
            })
            
            logging.debug(f"[TRACKER] Stored {ticker} ({city}): mid={midpoint:.0f}¢, spread={spread:.0f}¢")
        
        # Purge old data
        self.storage.purge_old_prices(hours=72)
        
        logging.info(f"[TRACKER] Stored prices for {len(stored)} markets")
        return stored
    
    def check_eligibility_criteria(self, ticker: str, city: str, current_midpoint: float, spread: float) -> Tuple[bool, str]:
        """
        Check if a market meets all eligibility criteria for entry:
        1. Had >= 65% price at some point in last 48 hours
        2. Spread <= 3¢
        3. Not on cooldown
        
        Returns (is_eligible, reason)
        """
        # Check cooldown
        if self.storage.is_on_cooldown(city):
            return False, "City is on cooldown"
        
        # Check spread
        if spread > 3:
            return False, f"Spread {spread:.0f}¢ > 3¢"
        
        # Check 48-hour high
        max_48h = self.storage.get_max_price_in_window(ticker, hours=48)
        if max_48h is None:
            return False, "No price history available"
        
        if max_48h < 65:
            return False, f"48h high ({max_48h:.0f}¢) < 65¢"
        
        return True, "Eligible"
    
    def detect_overreaction(self, ticker: str, current_midpoint: float) -> Tuple[bool, float]:
        """
        Detect if there's an overreaction:
        - Current price in 35-45% range
        - Drop of at least 20 points from 12-hour high
        
        Returns (is_overreaction, drop_amount)
        """
        # Check if in target range
        if not (35 <= current_midpoint <= 45):
            return False, 0
        
        # Get 12-hour max
        max_12h = self.storage.get_max_price_in_window(ticker, hours=12)
        if max_12h is None:
            return False, 0
        
        drop = max_12h - current_midpoint
        
        if drop >= 20:
            logging.info(f"[TRACKER] Overreaction detected for {ticker}: {max_12h:.0f}¢ -> {current_midpoint:.0f}¢ (drop: {drop:.0f})")
            return True, drop
        
        return False, drop
