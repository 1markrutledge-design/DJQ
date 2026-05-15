import azure.functions as func
import logging
import json
import os
from datetime import datetime, timedelta
from shared.kalshi_client import KalshiClient
from shared.strategies.ufc_favorite import UFCFavoriteStrategy

app = func.FunctionApp()

# ============================================
# DASHBOARD HTML PAGE
# ============================================

@app.route(route="dashboard", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard_page(req: func.HttpRequest) -> func.HttpResponse:
    """Serve the trading dashboard HTML page."""
    try:
        # Get the path to the static HTML file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "static", "index.html")
        
        with open(html_path, "r") as f:
            html_content = f.read()
        
        return func.HttpResponse(
            html_content,
            mimetype="text/html",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error serving dashboard: {e}")
        return func.HttpResponse(
            f"<h1>Dashboard Error</h1><p>{e}</p>",
            mimetype="text/html",
            status_code=500
        )

@app.timer_trigger(schedule="0 0 9-16 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def buyer_timer(myTimer: func.TimerRequest) -> None:
    logging.info('UFC Buyer Timer trigger function started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        strategy = UFCFavoriteStrategy(client)
        strategy.execute_buyer()
        
        logging.info('UFC Buyer Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in buyer_timer: {e}")

@app.timer_trigger(schedule="0 */3 17-23,0,1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True) 
def seller_timer(myTimer: func.TimerRequest) -> None:
    logging.info('UFC Seller Timer trigger function started.')
    
    try:
        client = KalshiClient()
        client.login()
        
        strategy = UFCFavoriteStrategy(client)
        strategy.execute_seller()
        
        logging.info('UFC Seller Strategy execution completed.')
    except Exception as e:
        logging.error(f"Error in seller_timer: {e}")


# ============================================
# DAILY EMAIL SUMMARY
# ============================================

@app.timer_trigger(schedule="0 0 21 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=True)
def daily_email_summary(myTimer: func.TimerRequest) -> None:
    """Send daily email summary of all bot activity at 9 PM ET."""
    logging.info('Daily email summary triggered.')
    
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content
        
        # Get SendGrid API key
        sendgrid_key = os.getenv("SENDGRID_API_KEY")
        if not sendgrid_key:
            logging.warning("SENDGRID_API_KEY not set - skipping email")
            return
        
        # Get Kalshi data
        client = KalshiClient()
        client.login()
        
        fills = client.get_fills(limit=500) or []
        positions = client.get_positions() or {}
        balance = client.get_balance() or {}
        
        # Calculate stats
        eastern_now = datetime.utcnow() - timedelta(hours=5)
        today = eastern_now.strftime("%Y-%m-%d")
        
        # Filter today's trades
        today_fills = [f for f in fills if str(f.get("created_time", ""))[:10] == today]
        
        # Categorize trades
        def categorize(fill):
            ticker = fill.get("ticker", "").upper()
            order_id = fill.get("client_order_id", "")
            if order_id.startswith("88-") or "UFC" in ticker:
                return "UFC"
            elif order_id.startswith("WX-") or order_id.startswith("77-"):
                return "Weather"
            elif order_id.startswith("CL-") or order_id.startswith("66-"):
                return "Climate"
            elif any(x in ticker for x in ["KXNBA", "KXNCAA", "KXNFL", "KXNHL", "LALIGA"]):
                return "Sports"
            return "Other"
        
        def calc_pnl(fill):
            action = fill.get("action", "")
            price = fill.get("yes_price", 0) / 100
            count = fill.get("count", 0)
            return -price * count if action == "buy" else price * count
        
        # Today's stats by category
        categories = {}
        for f in today_fills:
            cat = categorize(f)
            if cat not in categories:
                categories[cat] = {"trades": 0, "pnl": 0}
            categories[cat]["trades"] += 1
            categories[cat]["pnl"] += calc_pnl(f)
        
        # All-time stats
        all_pnl = sum(calc_pnl(f) for f in fills)
        
        # Build email HTML
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #333;">📊 Daily Trading Summary</h1>
            <p style="color: #666;">{eastern_now.strftime("%A, %B %d, %Y")}</p>
            
            <div style="background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h2 style="margin-top: 0;">💰 Portfolio</h2>
                <p><strong>Cash Balance:</strong> ${balance.get('balance', 0) / 100:.2f}</p>
                <p><strong>All-Time P&L:</strong> <span style="color: {'green' if all_pnl >= 0 else 'red'};">${all_pnl:.2f}</span></p>
            </div>
            
            <h2>📅 Today's Activity</h2>
            {'<p style="color: #999;">No trades today.</p>' if not today_fills else ''}
        """
        
        for cat, stats in categories.items():
            color = 'green' if stats['pnl'] >= 0 else 'red'
            email_html += f"""
            <div style="background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px; margin: 10px 0;">
                <h3 style="margin: 0 0 10px 0;">{cat}</h3>
                <p style="margin: 5px 0;">Trades: {stats['trades']}</p>
                <p style="margin: 5px 0;">P&L: <span style="color: {color}; font-weight: bold;">${stats['pnl']:.2f}</span></p>
            </div>
            """
        
        email_html += f"""
            <h2>📈 Bot Status</h2>
            <ul>
                <li>🥊 UFC Bot: {'Running' if os.getenv('DRY_RUN', 'false').lower() != 'true' else 'DRY RUN'}</li>
                <li>🌦️ Weather Bot: DRY RUN (Separate App)</li>
                <li>🌡️ Climate Bot: DRY RUN (Separate App)</li>
            </ul>
            
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 12px;">This is an automated email from your Kalshi Trading Bots.</p>
        </body>
        </html>
        """
        
        # Send email
        message = Mail(
            from_email=Email("noreply@kalshibots.com", "Kalshi Bots"),
            to_emails=To("1markrutledge@gmail.com"),
            subject=f"📊 Daily Trading Summary - {eastern_now.strftime('%b %d')}",
            html_content=Content("text/html", email_html)
        )
        
        sg = SendGridAPIClient(sendgrid_key)
        response = sg.send(message)
        
        logging.info(f"Daily email sent! Status: {response.status_code}")
        
    except Exception as e:
        logging.error(f"Error sending daily email: {e}")


# ============================================
# DASHBOARD API ENDPOINT
# ============================================

@app.route(route="dashboard/stats", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard_stats(req: func.HttpRequest) -> func.HttpResponse:
    """API endpoint for the trading dashboard."""
    logging.info("Dashboard stats API called.")
    
    try:
        client = KalshiClient()
        client.login()
        
        # Get all data from Kalshi
        fills = client.get_fills() or []
        
        # RESET TENNIS DASHBOARD: Filter out old tennis trades before the new strategy launch
        cutoff = "2026-02-24T16:45:00Z"
        fills = [f for f in fills if not (("KXATP" in str(f.get("ticker", "")).upper() or "KXWTA" in str(f.get("ticker", "")).upper()) and str(f.get("created_time", "")) < cutoff)]
        
        positions = client.get_positions()
        orders = client.get_resting_orders()
        balance = client.get_balance()
        
        # DEBUG: Log unique tickers to help fix categorization
        unique_tickers = list(set(f.get("ticker", "") for f in fills))
        logging.info(f"Unique tickers in fills: {unique_tickers[:20]}")  # Log first 20
        
        # FIXED CATEGORIZATION
        ufc_fills = []
        weather_fills = []
        climate_fills = []
        sports_fills = []
        other_fills = []
        
        for f in fills:
            ticker = str(f.get("ticker", "")).upper()
            cid = str(f.get("client_order_id", ""))
            
            # 1. Check by client_order_id prefix first (bot trades)
            if cid.startswith("88-") or cid.startswith("88"):
                ufc_fills.append(f)
            elif cid.startswith("WX-") or cid.startswith("77"):
                weather_fills.append(f)
            elif cid.startswith("CL-") or cid.startswith("66"):
                climate_fills.append(f)
            # 2. Check by ticker pattern
            elif "UFC" in ticker:
                ufc_fills.append(f)
            # 3. TENNIS & SPORTS: NBA, NCAA, NFL, etc (must check BEFORE weather patterns)
            elif any(x in ticker for x in ["KXATP", "KXWTA", "KXNBA", "KXNCAA", "KXNFL", "KXNHL", "KXMLB", "LALIGA", "KXEPL", "KXSOCCER"]):
                sports_fills.append(f)
            # 4. Weather: Temperature indices (INXD = temp index)
            elif any(x in ticker for x in ["INXD", "HIGHTEMP", "LOWTEMP", "KXTEMP"]):
                weather_fills.append(f)
            # 5. Climate
            elif any(x in ticker for x in ["CLIMATE", "CO2", "CARBON", "RAINFALL"]):
                climate_fills.append(f)
            else:
                other_fills.append(f)
        
        # Calculate total portfolio value (cash + position value)
        cash_balance = balance.get("balance", 0) / 100
        position_value = sum(p.get("market_value", 0) / 100 for p in positions)
        total_portfolio = cash_balance + position_value
        
        # Build daily P&L calendar
        daily_calendar = calculate_daily_calendar(fills)
        
        # Calculate stats
        stats = {
            "generated_at": datetime.utcnow().isoformat(),
            "balance": {
                "available": round(cash_balance, 2),
                "position_value": round(position_value, 2),
                "total_portfolio": round(total_portfolio, 2)
            },
            "overview": calculate_overview(fills, positions, orders),
            
            # Separate Real vs Simulated P&L
            "real_pnl": {
                "all_time": round(sum(calculate_fill_pnl(f) for f in ufc_fills + sports_fills + other_fills), 2),
                "today": round(sum(calculate_fill_pnl(f) for f in ufc_fills + sports_fills + other_fills 
                              if str(f.get("created_time", ""))[:10] == (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d")), 2),
                "trades": len(ufc_fills + sports_fills + other_fills)
            },
            "simulated_pnl": {
                "all_time": round(sum(calculate_fill_pnl(f) for f in weather_fills + climate_fills), 2),
                "today": round(sum(calculate_fill_pnl(f) for f in weather_fills + climate_fills 
                              if str(f.get("created_time", ""))[:10] == (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d")), 2),
                "trades": len(weather_fills + climate_fills)
            },
            
            "strategies": {
                "ufc": calculate_strategy_stats(ufc_fills, "UFC Favorite", is_simulated=False),
                "weather": calculate_strategy_stats(weather_fills, "Weather", is_simulated=True),
                "climate": calculate_strategy_stats(climate_fills, "Climate", is_simulated=True),
                "sports": calculate_strategy_stats(sports_fills, "Tennis / Sports", is_simulated=False),
                "other": calculate_strategy_stats(other_fills, "Other", is_simulated=False)
            },
            
            # Bot Leaderboard (sorted by P&L)
            "leaderboard": calculate_bot_leaderboard({
                "UFC Favorite": ufc_fills,
                "Sports": sports_fills,
                "Weather (Sim)": weather_fills,
                "Climate (Sim)": climate_fills
            }),
            
            # Alerts for daily losses
            "alerts": calculate_alerts(daily_calendar, {
                "ufc": ufc_fills,
                "weather": weather_fills,
                "climate": climate_fills,
                "sports": sports_fills
            }),
            
            "leaderboards": {
                "cities": calculate_city_leaderboard(weather_fills + climate_fills),
                "fighters": calculate_fighter_leaderboard(ufc_fills)
            },
            "recent_trades": get_recent_trades(fills, 20),
            "daily_calendar": daily_calendar,
            "chart_data": {
                "cumulative_pnl": calculate_cumulative_pnl(fills),
                "cumulative_real_pnl": calculate_cumulative_pnl(ufc_fills + sports_fills + other_fills),
                "cumulative_simulated_pnl": calculate_cumulative_pnl(weather_fills + climate_fills),
                "strategy_distribution": [
                    {"name": "UFC Favorite", "value": round(sum(calculate_fill_pnl(f) for f in ufc_fills), 2)},
                    {"name": "Weather (Sim)", "value": round(sum(calculate_fill_pnl(f) for f in weather_fills), 2)},
                    {"name": "Climate (Sim)", "value": round(sum(calculate_fill_pnl(f) for f in climate_fills), 2)},
                    {"name": "Tennis / Sports", "value": round(sum(calculate_fill_pnl(f) for f in sports_fills), 2)},
                    {"name": "Other", "value": round(sum(calculate_fill_pnl(f) for f in other_fills), 2)}
                ]
            },
            # DEBUG INFO - remove after fixing
            "debug": {
                "sample_tickers": unique_tickers[:10],
                "fill_count": len(fills),
                "ufc_count": len(ufc_fills),
                "weather_count": len(weather_fills),
                "climate_count": len(climate_fills),
                "sports_count": len(sports_fills),
                "other_count": len(other_fills)
            }
        }
        
        return func.HttpResponse(
            json.dumps(stats, default=str),
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )
        
    except Exception as e:
        logging.error(f"Dashboard API error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )


# ============================================
# SIMULATED TRADES ENDPOINT (Dry Run Bots)
# ============================================

@app.route(route="dashboard/simulated", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def simulated_trades(req: func.HttpRequest) -> func.HttpResponse:
    """API endpoint for viewing dry-run simulated trades (separate from real P&L)."""
    logging.info("Simulated trades API called.")
    
    try:
        # Try to import storage client (may not have storage connection)
        try:
            from shared.storage_client import StorageClient
            storage = StorageClient()
        except Exception as e:
            logging.warning(f"Could not connect to storage: {e}")
            return func.HttpResponse(
                json.dumps({
                    "error": "Storage not configured",
                    "message": "Set AZURE_STORAGE_CONNECTION_STRING in environment variables to enable dry run tracking.",
                    "simulated_trades": []
                }),
                mimetype="application/json",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        # Get all simulated (dry run) trades
        all_trades = storage.get_trade_log()
        dry_run_trades = [t for t in all_trades if t.get("IsDryRun", t.get("is_dry_run", False))]
        
        # Separate by strategy
        weather_sim = [t for t in dry_run_trades if t.get("PartitionKey", t.get("strategy", "")).upper() == "WEATHER"]
        climate_sim = [t for t in dry_run_trades if t.get("PartitionKey", t.get("strategy", "")).upper() == "CLIMATE"]
        
        # Calculate simulated P&L
        def calc_sim_pnl(trades):
            return sum(t.get("Cashflow", t.get("cashflow", 0)) for t in trades)
        
        # Format trades for display
        def format_trades(trades):
            return [{
                "ticker": t.get("Ticker", t.get("ticker", "")),
                "action": t.get("Action", t.get("action", "")),
                "count": t.get("Count", t.get("count", 0)),
                "price": t.get("Price", t.get("price", 0)),
                "cashflow": round(t.get("Cashflow", t.get("cashflow", 0)), 2),
                "timestamp": t.get("Timestamp", t.get("timestamp", ""))
            } for t in sorted(trades, key=lambda x: x.get("Timestamp", x.get("timestamp", "")), reverse=True)[:50]]
        
        stats = {
            "generated_at": datetime.utcnow().isoformat(),
            "is_simulation": True,
            "warning": "This is simulated data from dry-run mode. NOT REAL MONEY.",
            "weather": {
                "name": "Weather (Simulated)",
                "total_trades": len(weather_sim),
                "simulated_pnl": round(calc_sim_pnl(weather_sim), 2),
                "recent_trades": format_trades(weather_sim)
            },
            "climate": {
                "name": "Climate (Simulated)",
                "total_trades": len(climate_sim),
                "simulated_pnl": round(calc_sim_pnl(climate_sim), 2),
                "recent_trades": format_trades(climate_sim)
            },
            "total_simulated_pnl": round(calc_sim_pnl(dry_run_trades), 2),
            "total_simulated_trades": len(dry_run_trades)
        }
        
        return func.HttpResponse(
            json.dumps(stats, default=str),
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )
        
    except Exception as e:
        logging.error(f"Simulated trades API error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e), "simulated_trades": []}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )


def calculate_overview(fills, positions, orders):
    """Calculate overall portfolio stats with REAL win rate."""
    # Calculate net P&L by ticker (matches buys with sells)
    ticker_pnl = calculate_pnl_by_ticker(fills)
    
    # Only count settled/completed trades (where we have both buy and sell)
    settled_tickers = {t: pnl for t, pnl in ticker_pnl.items() if pnl != 0}
    winning_tickers = sum(1 for pnl in settled_tickers.values() if pnl > 0)
    total_settled = len(settled_tickers)
    
    # Real win rate: % of tickers that were profitable
    real_win_rate = (winning_tickers / total_settled * 100) if total_settled > 0 else 0
    
    # Today's stats - use Eastern timezone (UTC-5 in winter, UTC-4 in summer)
    # For simplicity, we'll use UTC-5 (EST)
    eastern_now = datetime.utcnow() - timedelta(hours=5)
    today_eastern = eastern_now.strftime("%Y-%m-%d")
    
    today_fills = []
    for f in fills:
        fill_time = str(f.get("created_time", ""))[:10]  # Get YYYY-MM-DD
        if fill_time == today_eastern:
            today_fills.append(f)
    
    today_pnl = sum(calculate_fill_pnl(f) for f in today_fills)
    
    return {
        "total_pnl": round(sum(ticker_pnl.values()), 2),
        "today_pnl": round(today_pnl, 2),
        "total_trades": len(fills),
        "today_trades": len(today_fills),
        "win_rate": round(real_win_rate, 1),
        "settled_bets": total_settled,
        "active_positions": len(positions),
        "pending_orders": len(orders)
    }


def calculate_strategy_stats(fills, strategy_name, is_simulated=False):
    """Calculate detailed stats for a specific strategy with actionable metrics."""
    if not fills:
        return {
            "name": strategy_name, 
            "is_simulated": is_simulated,
            "total_trades": 0, 
            "total_pnl": 0, 
            "today_pnl": 0,
            "win_rate": 0,
            "wins": 0,
            "losses": 0,
            "avg_return_pct": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "avg_buy_price": 0,
            "avg_sell_price": 0,
            "best_entry": 0,
            "worst_entry": 0
        }
    
    # Separate buys and sells
    buys = [f for f in fills if f.get("action") == "buy"]
    sells = [f for f in fills if f.get("action") == "sell"]
    
    # Calculate P&L by ticker for real win rate
    ticker_pnl = calculate_pnl_by_ticker(fills)
    settled_tickers = {t: pnl for t, pnl in ticker_pnl.items() if pnl != 0}
    winning_tickers = sum(1 for pnl in settled_tickers.values() if pnl > 0)
    losing_tickers = sum(1 for pnl in settled_tickers.values() if pnl < 0)
    total_settled = len(settled_tickers)
    real_win_rate = (winning_tickers / total_settled * 100) if total_settled > 0 else 0
    
    # Best and worst trade P&L
    trade_pnls = list(settled_tickers.values())
    best_trade = max(trade_pnls) if trade_pnls else 0
    worst_trade = min(trade_pnls) if trade_pnls else 0
    
    # Average return per trade (as %)
    total_pnl = sum(ticker_pnl.values())
    total_cost = sum(f.get("yes_price", 0) / 100 * f.get("count", 0) for f in buys)
    avg_return_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    
    # Today's P&L (Eastern timezone)
    eastern_now = datetime.utcnow() - timedelta(hours=5)
    today_eastern = eastern_now.strftime("%Y-%m-%d")
    today_fills = [f for f in fills if str(f.get("created_time", ""))[:10] == today_eastern]
    today_pnl = sum(calculate_fill_pnl(f) for f in today_fills)
    
    # Entry/exit analysis
    buy_prices = [f.get("yes_price", 0) for f in buys if f.get("yes_price")]
    sell_prices = [f.get("yes_price", 0) for f in sells if f.get("yes_price")]
    
    avg_buy = sum(buy_prices) / len(buy_prices) if buy_prices else 0
    avg_sell = sum(sell_prices) / len(sell_prices) if sell_prices else 0
    
    # Find best and worst entries (for buys, lower is better)
    best_entry = min(buy_prices) if buy_prices else 0
    worst_entry = max(buy_prices) if buy_prices else 0
    
    return {
        "name": strategy_name,
        "is_simulated": is_simulated,
        "total_trades": len(fills),
        "total_pnl": round(total_pnl, 2),
        "today_pnl": round(today_pnl, 2),
        "win_rate": round(real_win_rate, 1),
        "wins": winning_tickers,
        "losses": losing_tickers,
        "settled_bets": total_settled,
        "avg_return_pct": round(avg_return_pct, 1),
        "avg_profit_per_bet": round(total_pnl / total_settled if total_settled > 0 else 0, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "buys": len(buys),
        "sells": len(sells),
        "avg_buy_price": round(avg_buy, 1),
        "avg_sell_price": round(avg_sell, 1),
        "best_entry": round(best_entry, 1),
        "worst_entry": round(worst_entry, 1),
        "price_spread": round(avg_sell - avg_buy, 1)
    }


def calculate_pnl_by_ticker(fills):
    """Calculate net P&L for each ticker (matches buys with sells)."""
    ticker_data = {}
    
    for fill in fills:
        ticker = fill.get("ticker", "unknown")
        if ticker not in ticker_data:
            ticker_data[ticker] = {"cost": 0, "revenue": 0}
        
        action = fill.get("action", "")
        price = fill.get("yes_price", 0) / 100  # cents to dollars
        count = fill.get("count", 0)
        
        if action == "buy":
            ticker_data[ticker]["cost"] += price * count
        else:  # sell
            ticker_data[ticker]["revenue"] += price * count
    
    # Net P&L = revenue - cost
    return {t: data["revenue"] - data["cost"] for t, data in ticker_data.items()}


def calculate_city_leaderboard(fills):
    """Calculate profit by city."""
    city_stats = {}
    for fill in fills:
        ticker = str(fill.get("ticker", ""))
        city = ticker.split("-")[0].replace("HIGH", "").replace("LOW", "") if ticker else "Unknown"
        if city not in city_stats:
            city_stats[city] = {"city": city, "trades": 0, "pnl": 0}
        city_stats[city]["trades"] += 1
        city_stats[city]["pnl"] += calculate_fill_pnl(fill)
    return sorted(city_stats.values(), key=lambda x: x["pnl"], reverse=True)[:10]


def calculate_fighter_leaderboard(fills):
    """Calculate profit by fighter."""
    fighter_stats = {}
    for fill in fills:
        ticker = str(fill.get("ticker", ""))
        parts = ticker.split("-")
        fighter = parts[2].title() if len(parts) >= 3 else "Unknown"
        if fighter not in fighter_stats:
            fighter_stats[fighter] = {"fighter": fighter, "trades": 0, "pnl": 0}
        fighter_stats[fighter]["trades"] += 1
        fighter_stats[fighter]["pnl"] += calculate_fill_pnl(fill)
    return sorted(fighter_stats.values(), key=lambda x: x["pnl"], reverse=True)[:10]


def get_recent_trades(fills, limit=20):
    """Get the most recent trades."""
    sorted_fills = sorted(fills, key=lambda x: x.get("created_time", ""), reverse=True)
    return [{
        "date": f.get("created_time", ""),
        "ticker": f.get("ticker", ""),
        "action": f.get("action", ""),
        "side": f.get("side", ""),
        "count": f.get("count", 0),
        "price": f.get("yes_price", 0),
        "pnl": round(calculate_fill_pnl(f), 2)
    } for f in sorted_fills[:limit]]


def calculate_cumulative_pnl(fills):
    """Calculate cumulative P&L over time."""
    sorted_fills = sorted(fills, key=lambda x: x.get("created_time", ""))
    cumulative = 0
    data_points = []
    for fill in sorted_fills:
        cumulative += calculate_fill_pnl(fill)
        data_points.append({
            "date": str(fill.get("created_time", ""))[:10],
            "value": round(cumulative, 2)
        })
    return data_points


def calculate_fill_pnl(fill):
    """Calculate P&L for a single fill."""
    action = fill.get("action", "")
    price = fill.get("yes_price", 0) / 100
    count = fill.get("count", 0)
    return -price * count if action == "buy" else price * count


def calculate_daily_calendar(fills):
    """Calculate P&L for each day to display in calendar view."""
    daily_pnl = {}
    
    for fill in fills:
        date_str = str(fill.get("created_time", ""))[:10]  # Get just the date part
        if not date_str:
            continue
            
        if date_str not in daily_pnl:
            daily_pnl[date_str] = {"date": date_str, "pnl": 0, "trades": 0}
        
        daily_pnl[date_str]["pnl"] += calculate_fill_pnl(fill)
        daily_pnl[date_str]["trades"] += 1
    
    # Round P&L values
    for day in daily_pnl.values():
        day["pnl"] = round(day["pnl"], 2)
    
    # Sort by date and return as list
    return sorted(daily_pnl.values(), key=lambda x: x["date"], reverse=True)


def calculate_bot_leaderboard(bot_fills_dict):
    """Calculate bot performance leaderboard sorted by P&L."""
    leaderboard = []
    
    for bot_name, fills in bot_fills_dict.items():
        if not fills:
            pnl = 0
            win_rate = 0
            trades = 0
        else:
            ticker_pnl = calculate_pnl_by_ticker(fills)
            settled = {t: p for t, p in ticker_pnl.items() if p != 0}
            wins = sum(1 for p in settled.values() if p > 0)
            total = len(settled)
            
            pnl = sum(ticker_pnl.values())
            win_rate = (wins / total * 100) if total > 0 else 0
            trades = len(fills)
        
        leaderboard.append({
            "bot": bot_name,
            "pnl": round(pnl, 2),
            "win_rate": round(win_rate, 1),
            "trades": trades,
            "is_simulated": "(Sim)" in bot_name
        })
    
    # Sort by P&L descending
    leaderboard.sort(key=lambda x: x["pnl"], reverse=True)
    
    # Add rank
    for i, item in enumerate(leaderboard, 1):
        item["rank"] = i
    
    return leaderboard


def calculate_alerts(daily_calendar, bot_fills_dict, threshold=-10):
    """Calculate alerts for daily losses exceeding threshold."""
    alerts = []
    eastern_now = datetime.utcnow() - timedelta(hours=5)
    today = eastern_now.strftime("%Y-%m-%d")
    
    # Check each bot's daily P&L
    for bot_name, fills in bot_fills_dict.items():
        if not fills:
            continue
            
        # Group by date
        daily = {}
        for f in fills:
            date_str = str(f.get("created_time", ""))[:10]
            if date_str not in daily:
                daily[date_str] = 0
            daily[date_str] += calculate_fill_pnl(f)
        
        # Check for losses exceeding threshold
        for date, pnl in daily.items():
            if pnl < threshold:
                alerts.append({
                    "type": "daily_loss",
                    "bot": bot_name,
                    "date": date,
                    "amount": round(pnl, 2),
                    "threshold": threshold,
                    "is_today": date == today
                })
    
    # Sort by date descending (most recent first)
    alerts.sort(key=lambda x: x["date"], reverse=True)
    
    return alerts[:10]  # Return only last 10 alerts


# ============================================
# STRATEGY NOTES ENDPOINTS
# ============================================

@app.route(route="strategy/notes", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def save_notes(req: func.HttpRequest) -> func.HttpResponse:
    """Save a strategy note."""
    try:
        from shared.storage_client import StorageClient
        storage = StorageClient()
        
        body = req.get_json()
        bot_name = body.get("bot", "")
        note = body.get("note", "")
        
        if not bot_name or not note:
            return func.HttpResponse(
                json.dumps({"error": "bot and note are required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        storage.save_strategy_note(bot_name, note)
        
        return func.HttpResponse(
            json.dumps({"success": True, "message": "Note saved"}),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )


@app.route(route="strategy/notes", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_notes(req: func.HttpRequest) -> func.HttpResponse:
    """Get strategy notes."""
    try:
        from shared.storage_client import StorageClient
        storage = StorageClient()
        
        bot_name = req.params.get("bot")
        notes = storage.get_strategy_notes(bot_name)
        
        return func.HttpResponse(
            json.dumps({"notes": notes}, default=str),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"notes": [], "error": str(e)}),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )


@app.route(route="strategy/changelog", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_changelog(req: func.HttpRequest) -> func.HttpResponse:
    """Get parameter change log."""
    try:
        from shared.storage_client import StorageClient
        storage = StorageClient()
        
        bot_name = req.params.get("bot")
        changelog = storage.get_parameter_changelog(bot_name)
        
        return func.HttpResponse(
            json.dumps({"changelog": changelog}, default=str),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"changelog": [], "error": str(e)}),
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"}
        )
