import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from shared.kalshi_client import KalshiClient
from shared.storage_client import StorageClient

class ClimateTracker:
    """
    Tracks prices for climate markets (temperature + rainfall) in target cities.
    Polls every 15 minutes and stores 72-hour rolling history.
    """
    
    # Temperature cities and their ticker patterns
    TEMP_CITIES = {
        "Phoenix": ["PHX", "PHOENIX"],
        "Las Vegas": ["LAS", "VEGAS", "LV"],
        "Austin": ["AUS", "AUSTIN"],
        "Miami": ["MIA", "MIAMI"],
        "Chicago": ["CHI", "CHICAGO", "ORD"],
        "New York": ["NYC", "NY", "NEWYORK", "JFK"],
    }
    
    # Rainfall cities and their ticker patterns
    RAIN_CITIES = {
        "Miami": ["MIA", "MIAMI"],
        "Tampa": ["TPA", "TAMPA"],
        "Houston": ["HOU", "HOUSTON", "IAH"],
        "New Orleans": ["NO", "NOLA", "NEWORLEANS", "MSY"],
        "Seattle": ["SEA", "SEATTLE"],
    }
    
    # Series tickers to search for temperature
    TEMP_SERIES = [
        "KXHIGHPHX",   # Phoenix
        "KXHIGHLV",    # Las Vegas
        "KXHIGHAUS",   # Austin
        "KXHIGHMIA",   # Miami
        "KXHIGHCHI",   # Chicago
        "KXHIGHNYC",   # NYC
        "KXHIGHNY",    # NYC alternate
        "HIGHTEMP",    # Generic
        "KXTEMP",      # Generic
    ]
    
    # Series tickers to search for rainfall
    RAIN_SERIES = [
        "KXRAINMIA",   # Miami
        "KXRAINTPA",   # Tampa
        "KXRAINHOU",   # Houston
        "KXRAINNO",    # New Orleans
        "KXRAINSEA",   # Seattle
        "KXRAIN",      # Generic
        "RAIN",        # Generic
        "PRECIP",      # Precipitation
    ]
    
    def __init__(self, kalshi_client: KalshiClient, storage_client: StorageClient):
        self.kalshi = kalshi_client
        self.storage = storage_client
    
    def identify_city(self, ticker: str, title: str, city_map: Dict) -> Optional[str]:
        """Identify which target city a market belongs to."""
        search_text = (ticker + " " + title).upper()
        
        for city, patterns in city_map.items():
            for pattern in patterns:
                if pattern in search_text:
                    return city
        return None
    
    def fetch_markets_for_series(self, series_list: List[str]) -> List[Dict]:
        """Fetch markets from multiple series tickers."""
        all_markets = []
        
        for series in series_list:
            try:
                markets = self.kalshi.get_markets(series_ticker=series, status="active")
                if markets:
                    logging.info(f"[CLIMATE] Found {len(markets)} markets for series {series}")
                    all_markets.extend(markets)
            except Exception as e:
                logging.debug(f"[CLIMATE] No markets for series {series}")
        
        return all_markets
    
    def get_eligible_temp_markets(self) -> List[Dict]:
        """Fetch eligible temperature markets."""
        eligible = []
        
        try:
            all_markets = self.fetch_markets_for_series(self.TEMP_SERIES)
            
            now = datetime.utcnow()
            min_date = now + timedelta(days=3)
            max_date = now + timedelta(days=10)
            
            for market in all_markets:
                ticker = market.get("ticker", "")
                title = market.get("title", "")
                
                city = self.identify_city(ticker, title, self.TEMP_CITIES)
                if not city:
                    continue
                
                # Check event date
                close_time_str = market.get("close_time") or market.get("expiration_time")
                if close_time_str:
                    try:
                        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                        if not (min_date <= close_time <= max_date):
                            continue
                    except:
                        continue
                
                # Check volume
                volume = market.get("volume", 0) or 0
                if volume < 20000:
                    continue
                
                market["city"] = city
                market["market_type"] = "temperature"
                eligible.append(market)
            
            logging.info(f"[CLIMATE] Found {len(eligible)} eligible temperature markets")
            
        except Exception as e:
            logging.error(f"[CLIMATE] Error fetching temp markets: {e}")
        
        return eligible
    
    def get_eligible_rain_markets(self) -> List[Dict]:
        """Fetch eligible rainfall markets."""
        eligible = []
        
        try:
            all_markets = self.fetch_markets_for_series(self.RAIN_SERIES)
            
            now = datetime.utcnow()
            min_date = now + timedelta(days=3)
            max_date = now + timedelta(days=10)
            
            for market in all_markets:
                ticker = market.get("ticker", "")
                title = market.get("title", "")
                
                city = self.identify_city(ticker, title, self.RAIN_CITIES)
                if not city:
                    continue
                
                # Check event date
                close_time_str = market.get("close_time") or market.get("expiration_time")
                if close_time_str:
                    try:
                        close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                        if not (min_date <= close_time <= max_date):
                            continue
                    except:
                        continue
                
                # Check volume
                volume = market.get("volume", 0) or 0
                if volume < 20000:
                    continue
                
                market["city"] = city
                market["market_type"] = "rainfall"
                eligible.append(market)
            
            logging.info(f"[CLIMATE] Found {len(eligible)} eligible rainfall markets")
            
        except Exception as e:
            logging.error(f"[CLIMATE] Error fetching rain markets: {e}")
        
        return eligible
    
    def poll_and_store_prices(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Main polling function - runs every 15 minutes.
        Returns (temp_markets, rain_markets)
        """
        temp_markets = self.get_eligible_temp_markets()
        rain_markets = self.get_eligible_rain_markets()
        
        all_markets = temp_markets + rain_markets
        stored_count = 0
        
        for market in all_markets:
            ticker = market.get("ticker")
            city = market.get("city")
            market_type = market.get("market_type", "temp")
            
            yes_bid = market.get("yes_bid", 0) or 0
            yes_ask = market.get("yes_ask", 0) or 0
            
            if yes_bid == 0 and yes_ask == 0:
                continue
            
            midpoint = (yes_bid + yes_ask) / 2
            volume = market.get("volume", 0) or 0
            
            self.storage.store_price(
                ticker=ticker,
                city=f"{city}_{market_type}",
                midpoint=midpoint,
                bid=yes_bid,
                ask=yes_ask,
                volume=volume
            )
            stored_count += 1
        
        self.storage.purge_old_prices(hours=72)
        logging.info(f"[CLIMATE] Stored prices for {stored_count} markets")
        
        return temp_markets, rain_markets
    
    def check_eligibility(self, ticker: str, city: str, market_type: str, 
                          midpoint: float, spread: float) -> Tuple[bool, str]:
        """Check if market meets entry criteria."""
        storage_key = f"{city}_{market_type}"
        
        if self.storage.is_on_cooldown(storage_key):
            return False, "City is on cooldown"
        
        if spread > 3:
            return False, f"Spread {spread:.0f}¢ > 3¢"
        
        max_48h = self.storage.get_max_price_in_window(ticker, hours=48)
        if max_48h is None:
            return False, "No price history"
        
        if max_48h < 65:
            return False, f"48h high ({max_48h:.0f}¢) < 65¢"
        
        return True, "Eligible"
    
    def detect_overreaction(self, ticker: str, current_midpoint: float) -> Tuple[bool, float]:
        """Detect if there's an overreaction (20+ point drop from 12h high)."""
        if not (35 <= current_midpoint <= 45):
            return False, 0
        
        max_12h = self.storage.get_max_price_in_window(ticker, hours=12)
        if max_12h is None:
            return False, 0
        
        drop = max_12h - current_midpoint
        
        if drop >= 20:
            logging.info(f"[CLIMATE] Overreaction: {ticker} dropped {drop:.0f} points ({max_12h:.0f}→{current_midpoint:.0f})")
            return True, drop
        
        return False, drop
