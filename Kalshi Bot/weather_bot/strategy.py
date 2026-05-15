"""
strategy.py
Core trading logic for the weather maker bot.

Optimizations:
  - State blob loaded ONCE per run, not per market
  - 200ms delay between Kalshi API calls to avoid 429 rate limits
  - Price read directly from already-fetched market data (no extra API call)
"""

import time
import logging
from typing import Optional

from kalshi_client import KalshiClient
from state import PositionState
from series_config import (
    WEATHER_SERIES,
    ENTRY_PRICE_CENTS,
    TRIGGER_PRICE_CENTS,
    STOP_LOSS_PRICE_CENTS,
    CONTRACTS_PER_MARKET,
)

logger = logging.getLogger(__name__)

API_CALL_DELAY = 0.2  # seconds between Kalshi API calls to avoid 429s


def to_int(val) -> int:
    """Safely convert decimal strings ('1.00'), floats, or None to int."""
    try:
        if val is None:
            return 0
        return int(float(str(val)))
    except (ValueError, TypeError):
        return 0


def extract_yes_bid(market: dict) -> Optional[int]:
    """Extract the best YES bid in cents from a market dict (already fetched)."""
    # Try all known Kalshi field names for YES bid price.
    # V2 API often uses _dollars suffixes with decimal strings (e.g. "0.9000").
    price_fields = (
        "yes_bid",
        "yes_bid_dollars",
        "last_price",
        "last_price_dollars",
        "last_yes_price",
        "yes_price"
    )

    for field in price_fields:
        val = market.get(field)
        if val is not None:
            try:
                # Handle string dollar values like "0.9000"
                if isinstance(val, str):
                    return int(round(float(val) * 100))
                # Handle direct integers or floats
                return int(val)
            except (ValueError, TypeError):
                pass
    return None



def get_current_yes_bid(client: KalshiClient, ticker: str) -> Optional[int]:
    """Fetch fresh price for a ticker via API (used for stop-loss checks)."""
    try:
        market = client.get_market(ticker)
        return extract_yes_bid(market)
    except Exception as e:
        logger.warning(f"Could not get price for {ticker}: {e}")
    return None


def check_if_order_filled(client: KalshiClient, order_id: str) -> bool:
    """Return True if the given order_id is in the 'filled' state."""
    try:
        orders = client.get_orders(status="filled")
        for o in orders:
            if o.get("order_id") == order_id:
                return True
    except Exception as e:
        logger.warning(f"Could not check order fill status for {order_id}: {e}")
    return False


def has_kalshi_position(client: KalshiClient, ticker: str) -> bool:
    """Return True if Kalshi shows a live position for this ticker."""
    try:
        pos = client.get_position_for_ticker(ticker)
        # Use robust to_int to handle position_fp, market_position, etc.
        pos_count = to_int(pos.get("position") or pos.get("position_fp") or pos.get("market_position"))
        if pos and pos_count > 0:
            return True
    except Exception as e:
        logger.warning(f"Could not check Kalshi position for {ticker}: {e}")
    return False


def run_strategy(client: KalshiClient, state: PositionState):
    """Main per-run strategy loop."""
    logger.info("=== Weather Bot run started ===")

    # -------------------------------------------------------
    # Step 1: Discover all open markets — with delay between calls
    # -------------------------------------------------------
    all_markets: list[dict] = []
    for series in WEATHER_SERIES:
        try:
            markets = client.get_markets_for_series(series, status="open")
            for m in markets:
                m["_series"] = series
            all_markets.extend(markets)
        except Exception as e:
            logger.warning(f"Could not fetch markets for series {series}: {e}")
        time.sleep(API_CALL_DELAY)  # avoid 429 rate limiting

    logger.info(f"Discovered {len(all_markets)} open weather markets across {len(WEATHER_SERIES)} series")

    if not all_markets:
        logger.info("No markets found — exiting early")
        return

    # Deduplicate markets by ticker to avoid redundant processing
    seen_tickers = set()
    unique_markets = []
    for m in all_markets:
        t = m.get("ticker")
        if t and t not in seen_tickers:
            seen_tickers.add(t)
            unique_markets.append(m)
    all_markets = unique_markets

    # Log first market raw fields so we can see what price fields Kalshi returns
    if all_markets:
        sample = {k: v for k, v in all_markets[0].items() if k not in ("_series",)}
        logger.info(f"[DEBUG] Sample market fields: {sample}")

    # -------------------------------------------------------
    # Step 2: Load state and SYNC with Kalshi reality
    # -------------------------------------------------------
    positions = state.load()
    sync_state_with_kalshi(client, positions)
    positions_changed = False

    # -------------------------------------------------------
    # Step 3: Process each market using the synchronized state
    # -------------------------------------------------------
    for market in all_markets:
        ticker: str = market.get("ticker", "")
        series: str = market.get("_series", "")
        if not ticker:
            continue

        changed = _process_market(client, ticker, series, market, positions)
        if changed:
            positions_changed = True
        time.sleep(API_CALL_DELAY)

    # -------------------------------------------------------
    # Step 4: Save state once if anything changed (including SYNC changes)
    # -------------------------------------------------------
    if positions_changed:
        state.save(positions)
        logger.info(f"[STATE] Saved updated positions ({len(positions)} active markets)")

    logger.info("=== Weather Bot run complete ===")


def sync_state_with_kalshi(client: KalshiClient, positions: dict):
    """
    Fetch ALL actual positions and resting orders from Kalshi to reconcile reality.
    This prevents double-betting if the local state blob is behind or if a 
    parallel run just acted.
    """
    try:
        logger.info("[SYNC] Reconciling state with Kalshi reality...")
        
        # 1. Fetch all positions
        kalshi_positions = client.get_positions()
        for p in kalshi_positions:
            ticker = p.get("ticker")
            # Kalshi API fields can vary: check position, position_fp, etc.
            pos_count = to_int(p.get("position") or p.get("position_fp") or p.get("market_position") or p.get("count"))
            
            if not ticker or pos_count <= 0:
                continue
            
            # If we didn't know about this position or it was marked 'resting',
            # update it to 'filled' and arm the stop.
            if ticker not in positions or positions[ticker].get("status") != "filled":
                logger.info(f"[SYNC] Found existing market position for {ticker}")
                # We don't overwrite the whole dict if it's already there (to preserve entered_at/series)
                if ticker not in positions:
                    positions[ticker] = {}
                
                positions[ticker].update({
                    "status": "filled",
                    "stop_armed": True,
                    "contracts": pos_count,
                })

        # 2. Fetch all resting orders
        kalshi_orders = client.get_orders(status="resting")
        for o in kalshi_orders:
            ticker = o.get("ticker")
            # Only care about resting BUY orders (maker entries)
            if not ticker or o.get("action") != "buy":
                continue
            
            # If we have a resting order on Kalshi but state says nothing or says 'filled' (incorrectly),
            # reconcile it to 'resting'.
            if ticker not in positions or positions[ticker].get("status") != "resting":
                logger.info(f"[SYNC] Found existing resting BUY order for {ticker} (order_id={o.get('order_id')})")
                if ticker not in positions:
                    positions[ticker] = {}
                
                positions[ticker].update({
                    "status": "resting",
                    "order_id": o.get("order_id"),
                    "entry_price": o.get("yes_price"),
                    "contracts": o.get("count"),
                    "stop_armed": False,
                })
    except Exception as e:
        logger.warning(f"[SYNC] Failed to reconcile state with Kalshi: {e}")


def _process_market(
    client: KalshiClient,
    ticker: str,
    series: str,
    market_data: dict,  # already-fetched market dict with price info
    positions: dict,    # shared in-memory state — mutated in place
) -> bool:
    """
    Process a single market. Mutates 'positions' dict in place.
    Returns True if state changed (so caller knows to save).
    """
    pos = positions.get(ticker)

    # ------------------------------------------------------------------
    # CASE A: Resting order — check if filled
    # ------------------------------------------------------------------
    if pos and pos.get("status") == "resting":
        order_id = pos.get("order_id")
        logger.info(f"[{ticker}] Resting order {order_id} — checking fill status")

        filled = check_if_order_filled(client, order_id) or has_kalshi_position(client, ticker)
        if filled:
            positions[ticker]["status"] = "filled"
            positions[ticker]["stop_armed"] = True
            logger.info(f"[{ticker}] ✅ Order FILLED — stop-loss armed at {STOP_LOSS_PRICE_CENTS}¢")
            return True
        else:
            logger.info(f"[{ticker}] ⏳ Still resting — no action")
        return False

    # ------------------------------------------------------------------
    # CASE B: Filled position — monitor stop-loss
    # ------------------------------------------------------------------
    if pos and pos.get("status") == "filled" and pos.get("stop_armed"):
        current_bid = get_current_yes_bid(client, ticker)  # fresh price for stop-loss
        logger.info(f"[{ticker}] Filled — bid: {current_bid}¢ | stop: {STOP_LOSS_PRICE_CENTS}¢")

        if current_bid is None:
            logger.warning(f"[{ticker}] No price — skipping stop check")
            return False

        if current_bid <= STOP_LOSS_PRICE_CENTS:
            logger.info(f"[{ticker}] 🛑 STOP-LOSS triggered ({current_bid}¢) — taker SELL")
            try:
                result = client.place_market_order(ticker=ticker, side="yes", count=CONTRACTS_PER_MARKET, action="sell")
                logger.info(f"[{ticker}] Stop-loss sell submitted: {result}")
                del positions[ticker]
                return True
            except Exception as e:
                logger.error(f"[{ticker}] ❌ Stop-loss sell FAILED: {e}")
        else:
            logger.info(f"[{ticker}] 💼 Holding ({current_bid}¢ > {STOP_LOSS_PRICE_CENTS}¢)")
        return False

    # ------------------------------------------------------------------
    # CASE C: No position — evaluate entry (use already-fetched price)
    # ------------------------------------------------------------------
    current_bid = extract_yes_bid(market_data)
    if current_bid is None:
        logger.info(f"[{ticker}] No price in market data — skipping (fields: {list(market_data.keys())})")
        return False

    logger.info(f"[{ticker}] No position — bid: {current_bid}¢ | trigger: {TRIGGER_PRICE_CENTS}¢")

    if current_bid >= TRIGGER_PRICE_CENTS:
        logger.info(f"[{ticker}] 🎯 TRIGGER HIT ({current_bid}¢) — placing resting maker BUY at {ENTRY_PRICE_CENTS}¢")
        try:
            from datetime import datetime, timezone
            order = client.place_limit_order(
                ticker=ticker,
                side="yes",
                count=CONTRACTS_PER_MARKET,
                limit_price=ENTRY_PRICE_CENTS,
            )


            order_id = order.get("order_id") or order.get("id", "unknown")
            positions[ticker] = {
                "status": "resting",
                "order_id": order_id,
                "entry_price": ENTRY_PRICE_CENTS,
                "contracts": CONTRACTS_PER_MARKET,
                "stop_armed": False,
                "entered_at": datetime.now(timezone.utc).isoformat(),
                "series": series,
            }
            logger.info(f"[{ticker}] ✅ Resting order placed (order_id={order_id})")
            return True
        except Exception as e:
            logger.error(f"[{ticker}] ❌ Entry order failed: {e}")

    return False
