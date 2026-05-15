import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from azure.data.tables import TableServiceClient, TableClient

class StorageClient:
    """
    Azure Table Storage client for persisting:
    - Price history (72-hour rolling window)
    - Open positions and tranches
    - City cooldowns
    """
    
    def __init__(self):
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not self.connection_string:
            logging.warning("[STORAGE] No connection string found. Using in-memory fallback.")
            self._use_memory = True
            self._memory_store = {"prices": [], "positions": {}, "cooldowns": {}}
        else:
            self._use_memory = False
            self.service = TableServiceClient.from_connection_string(self.connection_string)
            self._ensure_tables()
    
    def _ensure_tables(self):
        """Create tables if they don't exist."""
        table_names = ["PriceHistory", "Positions", "Cooldowns", "TradeLog", "StrategyNotes", "ParameterChanges"]
        for name in table_names:
            try:
                self.service.create_table_if_not_exists(name)
            except Exception as e:
                logging.error(f"[STORAGE] Failed to create table {name}: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # PRICE HISTORY
    # ═══════════════════════════════════════════════════════════════
    
    def store_price(self, ticker: str, city: str, midpoint: float, bid: float, ask: float, volume: float):
        """Store a price snapshot."""
        timestamp = datetime.utcnow()
        
        if self._use_memory:
            self._memory_store["prices"].append({
                "ticker": ticker, "city": city, "midpoint": midpoint,
                "bid": bid, "ask": ask, "volume": volume, "timestamp": timestamp
            })
            # Purge old data (keep 72 hours)
            cutoff = timestamp - timedelta(hours=72)
            self._memory_store["prices"] = [p for p in self._memory_store["prices"] if p["timestamp"] > cutoff]
        else:
            table = self.service.get_table_client("PriceHistory")
            entity = {
                "PartitionKey": ticker,
                "RowKey": timestamp.isoformat(),
                "City": city,
                "Midpoint": midpoint,
                "Bid": bid,
                "Ask": ask,
                "Volume": volume,
                "Timestamp": timestamp.isoformat()
            }
            table.upsert_entity(entity)
    
    def get_price_history(self, ticker: str, hours: int = 48) -> List[Dict]:
        """Get price history for a ticker."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        if self._use_memory:
            return [p for p in self._memory_store["prices"] 
                    if p["ticker"] == ticker and p["timestamp"] > cutoff]
        else:
            table = self.service.get_table_client("PriceHistory")
            # Use RowKey (which is the ISO timestamp string) for comparison
            cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%S')
            query = f"PartitionKey eq '{ticker}' and RowKey ge '{cutoff_str}'"
            try:
                entities = table.query_entities(query)
                return [dict(e) for e in entities]
            except Exception as e:
                logging.warning(f"[STORAGE] Query failed, fetching all: {e}")
                # Fallback: get all entities for this ticker and filter in Python
                entities = table.query_entities(f"PartitionKey eq '{ticker}'")
                return [dict(e) for e in entities]
    
    def get_max_price_in_window(self, ticker: str, hours: int) -> Optional[float]:
        """Get the maximum midpoint price in a time window."""
        history = self.get_price_history(ticker, hours)
        if not history:
            return None
        return max(h.get("Midpoint", h.get("midpoint", 0)) for h in history)
    
    def purge_old_prices(self, hours: int = 72):
        """Remove price data older than specified hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%S')
        
        if self._use_memory:
            self._memory_store["prices"] = [p for p in self._memory_store["prices"] if p["timestamp"] > cutoff]
        else:
            table = self.service.get_table_client("PriceHistory")
            try:
                # Query for old entries using RowKey comparison
                query = f"RowKey lt '{cutoff_str}'"
                for entity in table.query_entities(query):
                    table.delete_entity(entity["PartitionKey"], entity["RowKey"])
            except Exception as e:
                logging.warning(f"[STORAGE] Purge failed: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # POSITIONS
    # ═══════════════════════════════════════════════════════════════
    
    def get_position(self, city: str) -> Optional[Dict]:
        """Get open position for a city."""
        if self._use_memory:
            return self._memory_store["positions"].get(city)
        else:
            table = self.service.get_table_client("Positions")
            try:
                entity = table.get_entity("weather", city)
                return dict(entity)
            except:
                return None
    
    def save_position(self, city: str, ticker: str, tranches_filled: List[int], 
                      entry_prices: List[float], total_shares: int, total_cost: float):
        """Save or update a position."""
        data = {
            "ticker": ticker,
            "tranches_filled": tranches_filled,
            "entry_prices": entry_prices,
            "total_shares": total_shares,
            "total_cost": total_cost,
            "opened_at": datetime.utcnow().isoformat()
        }
        
        if self._use_memory:
            self._memory_store["positions"][city] = data
        else:
            table = self.service.get_table_client("Positions")
            entity = {
                "PartitionKey": "weather",
                "RowKey": city,
                "Ticker": ticker,
                "TranchesFilled": str(tranches_filled),
                "EntryPrices": str(entry_prices),
                "TotalShares": total_shares,
                "TotalCost": total_cost,
                "OpenedAt": data["opened_at"]
            }
            table.upsert_entity(entity)
    
    def close_position(self, city: str):
        """Close a position and set cooldown."""
        if self._use_memory:
            if city in self._memory_store["positions"]:
                del self._memory_store["positions"][city]
        else:
            table = self.service.get_table_client("Positions")
            try:
                table.delete_entity("weather", city)
            except:
                pass
        
        # Set cooldown
        self.set_cooldown(city)
    
    def get_all_positions(self) -> Dict[str, Dict]:
        """Get all open positions."""
        if self._use_memory:
            return self._memory_store["positions"]
        else:
            table = self.service.get_table_client("Positions")
            positions = {}
            for entity in table.query_entities("PartitionKey eq 'weather'"):
                positions[entity["RowKey"]] = dict(entity)
            return positions
    
    # ═══════════════════════════════════════════════════════════════
    # COOLDOWNS
    # ═══════════════════════════════════════════════════════════════
    
    def set_cooldown(self, city: str, hours: int = 12):
        """Set a cooldown for a city."""
        expiry = datetime.utcnow() + timedelta(hours=hours)
        
        if self._use_memory:
            self._memory_store["cooldowns"][city] = expiry
        else:
            table = self.service.get_table_client("Cooldowns")
            entity = {
                "PartitionKey": "weather",
                "RowKey": city,
                "ExpiresAt": expiry.isoformat(),
                "SetAt": datetime.utcnow().isoformat()
            }
            table.upsert_entity(entity)
    
    def is_on_cooldown(self, city: str) -> bool:
        """Check if a city is on cooldown."""
        now = datetime.utcnow()
        
        if self._use_memory:
            expiry = self._memory_store["cooldowns"].get(city)
            return expiry is not None and expiry > now
        else:
            table = self.service.get_table_client("Cooldowns")
            try:
                entity = table.get_entity("weather", city)
                expiry = datetime.fromisoformat(entity["ExpiresAt"])
                return expiry > now
            except:
                return False
    
    def clear_expired_cooldowns(self):
        """Remove expired cooldowns."""
        now = datetime.utcnow()
        
        if self._use_memory:
            self._memory_store["cooldowns"] = {
                k: v for k, v in self._memory_store["cooldowns"].items() if v > now
            }
        else:
            table = self.service.get_table_client("Cooldowns")
            for entity in table.query_entities("PartitionKey eq 'weather'"):
                expiry = datetime.fromisoformat(entity["ExpiresAt"])
                if expiry < now:
                    table.delete_entity(entity["PartitionKey"], entity["RowKey"])

    # ═══════════════════════════════════════════════════════════════
    # TRADE LOG (P&L Tracking)
    # ═══════════════════════════════════════════════════════════════

    def log_trade(self, strategy: str, ticker: str, action: str, count: int, price: float, is_dry_run: bool):
        """Log a trade (buy/sell) for P&L tracking."""
        timestamp = datetime.utcnow()
        total_value = count * (price / 100)
        
        # Buy = Negative Cashflow (Cost), Sell = Positive Cashflow (Revenue)
        cashflow = -total_value if action.lower() == "buy" else total_value
        
        if self._use_memory:
            if "trades" not in self._memory_store:
                self._memory_store["trades"] = []
            self._memory_store["trades"].append({
                "strategy": strategy, "ticker": ticker, "action": action,
                "count": count, "price": price, "cashflow": cashflow,
                "is_dry_run": is_dry_run, "timestamp": timestamp
            })
        else:
            table = self.service.get_table_client("TradeLog")
            entity = {
                "PartitionKey": strategy,  # e.g., "CLIMATE", "WEATHER"
                "RowKey": f"{timestamp.isoformat()}-{ticker}",
                "Ticker": ticker,
                "Action": action,
                "Count": count,
                "Price": price,
                "Cashflow": cashflow,
                "IsDryRun": is_dry_run,
                "Timestamp": timestamp.isoformat()
            }
            table.upsert_entity(entity)
            
    def get_trade_log(self, strategy: str = None) -> List[Dict]:
        """Get trade history for P&L calculation."""
        if self._use_memory:
            trades = self._memory_store.get("trades", [])
            if strategy:
                return [t for t in trades if t["strategy"] == strategy]
            return trades
        else:
            table = self.service.get_table_client("TradeLog")
            try:
                if strategy:
                    query = f"PartitionKey eq '{strategy}'"
                    entities = table.query_entities(query)
                else:
                    entities = table.list_entities()
                return [dict(e) for e in entities]
            except Exception as e:
                logging.error(f"[STORAGE] Failed to fetch trade log: {e}")
                return []

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY NOTES
    # ═══════════════════════════════════════════════════════════════

    def save_strategy_note(self, bot_name: str, note: str):
        """Save a strategy note for a bot."""
        timestamp = datetime.utcnow()
        
        if self._use_memory:
            if "notes" not in self._memory_store:
                self._memory_store["notes"] = {}
            if bot_name not in self._memory_store["notes"]:
                self._memory_store["notes"][bot_name] = []
            self._memory_store["notes"][bot_name].append({
                "note": note, "timestamp": timestamp.isoformat()
            })
        else:
            table = self.service.get_table_client("StrategyNotes")
            entity = {
                "PartitionKey": bot_name.upper(),
                "RowKey": timestamp.isoformat(),
                "Note": note,
                "Timestamp": timestamp.isoformat()
            }
            table.upsert_entity(entity)
    
    def get_strategy_notes(self, bot_name: str = None) -> List[Dict]:
        """Get strategy notes for a bot or all bots."""
        if self._use_memory:
            notes = self._memory_store.get("notes", {})
            if bot_name:
                return notes.get(bot_name, [])
            all_notes = []
            for bn, note_list in notes.items():
                for n in note_list:
                    all_notes.append({"bot": bn, **n})
            return all_notes
        else:
            table = self.service.get_table_client("StrategyNotes")
            try:
                if bot_name:
                    query = f"PartitionKey eq '{bot_name.upper()}'"
                    entities = table.query_entities(query)
                else:
                    entities = table.list_entities()
                return sorted([dict(e) for e in entities], 
                             key=lambda x: x.get("Timestamp", ""), reverse=True)
            except Exception as e:
                logging.error(f"[STORAGE] Failed to fetch strategy notes: {e}")
                return []

    # ═══════════════════════════════════════════════════════════════
    # PARAMETER CHANGELOG (Auto-logged)
    # ═══════════════════════════════════════════════════════════════

    def log_parameter_change(self, bot_name: str, param_name: str, 
                             old_value: str, new_value: str):
        """Log a parameter change for a bot."""
        timestamp = datetime.utcnow()
        
        if self._use_memory:
            if "changelog" not in self._memory_store:
                self._memory_store["changelog"] = []
            self._memory_store["changelog"].append({
                "bot": bot_name, "param": param_name,
                "old": old_value, "new": new_value,
                "timestamp": timestamp.isoformat()
            })
        else:
            table = self.service.get_table_client("ParameterChanges")
            entity = {
                "PartitionKey": bot_name.upper(),
                "RowKey": f"{timestamp.isoformat()}-{param_name}",
                "ParamName": param_name,
                "OldValue": str(old_value),
                "NewValue": str(new_value),
                "Timestamp": timestamp.isoformat()
            }
            table.upsert_entity(entity)
    
    def get_parameter_changelog(self, bot_name: str = None) -> List[Dict]:
        """Get parameter change history for a bot or all bots."""
        if self._use_memory:
            changes = self._memory_store.get("changelog", [])
            if bot_name:
                return [c for c in changes if c["bot"] == bot_name]
            return changes
        else:
            table = self.service.get_table_client("ParameterChanges")
            try:
                if bot_name:
                    query = f"PartitionKey eq '{bot_name.upper()}'"
                    entities = table.query_entities(query)
                else:
                    entities = table.list_entities()
                return sorted([dict(e) for e in entities],
                             key=lambda x: x.get("Timestamp", ""), reverse=True)
            except Exception as e:
                logging.error(f"[STORAGE] Failed to fetch parameter changelog: {e}")
                return []
