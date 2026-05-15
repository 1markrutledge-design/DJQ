#!/usr/bin/env python3
import http.server
import socketserver
import json
import os
import csv
import time
from datetime import datetime, timedelta
from collections import defaultdict

PORT = 8000
CSV_FILE = "market_history.csv"

# Coin Groups based on the Research Audit
MOMENTUM_COINS = ["KXBTC15M", "KXETH15M"]
REVERSION_COINS = ["KXSOL15M", "KXXRP15M", "KXBNB15M", "KXDOGE15M", "KXHYPE15M"]

class StrategyBible:
    @staticmethod
    def analyze_10m_mark(ticker_data):
        """
        Analyzes the price at the 10-minute mark to see if it predicted the winner.
        Returns stats for the 'Squeeze' and 'Reversion' strategies.
        """
        history = ticker_data["history_timed"]
        result = ticker_data["result"]
        series = ticker_data["series"]
        
        if not history or not result: return None
        
        # Determine the 'start' of the 15m window
        # We assume the window ends at close_time or the last timestamp
        # Most 15m cycles start at :00, :15, :30, :45
        # We'll use the 'close_time' as the anchor if available
        first_ts = history[0][0]
        
        # Strategy: The 10-Minute Squeeze (BTC/ETH style)
        squeeze_win = None
        # Strategy: The 10-Minute Reversion (Choppy style)
        reversion_win = None
        
        for ts, p in history:
            elapsed = (ts - first_ts).total_seconds()
            
            # Look for the snapshot closest to 10 minutes (600s)
            if 590 <= elapsed <= 620:
                # YES Side Squeeze
                if p >= 80:
                    squeeze_win = (result == "YES")
                elif p <= 20:
                    squeeze_win = (result == "NO")
                    
                # YES Side Reversion
                if p <= 20:
                    reversion_win = (result == "YES")
                elif p >= 80:
                    reversion_win = (result == "NO")
                
                break # We only need the 10m mark
                
        return {"squeeze": squeeze_win, "reversion": reversion_win}

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(self.get_market_summary()).encode())
        else:
            if self.path == '/' or self.path == '': self.path = '/dashboard/index.html'
            else: self.path = '/dashboard' + self.path
            return super().do_GET()

    def get_market_summary(self):
        if not os.path.exists(CSV_FILE): return {"error": "No history.", "markets": {}}
        
        ticker_data = defaultdict(lambda: {"history_timed": [], "result": None, "series": ""})
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row['ticker']
                if not ticker or ticker == 'ticker': continue
                series = ticker.split("-")[0]
                ticker_data[ticker]["series"] = series
                if row.get('result'): ticker_data[ticker]["result"] = row['result'].upper()
                
                if row.get('last_price') or row.get('yes_bid'):
                    p = float(row['last_price']) if row['last_price'] else float(row['yes_bid'] or 0)
                    ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                    if p > 0: ticker_data[ticker]["history_timed"].append((ts, p))

        series_stats = {}
        for ticker, data in ticker_data.items():
            series = data["series"]
            if series not in series_stats:
                series_stats[series] = {
                    "name": series, "current": {"bid": 0, "ask": 0},
                    "group": "Momentum" if series in MOMENTUM_COINS else "Choppy",
                    "bible": {"win": 0, "loss": 0},
                    "history": []
                }
            
            # Update current
            if data["history_timed"]:
                latest = data["history_timed"][-1]
                series_stats[series]["current"]["price"] = latest[1]
                series_stats[series]["history"] = [h[1] for h in data["history_timed"]][-60:]

            # Bible Strategy Analysis
            stats = StrategyBible.analyze_10m_mark(data)
            if stats:
                target_strat = "squeeze" if series_stats[series]["group"] == "Momentum" else "reversion"
                outcome = stats.get(target_strat)
                if outcome is True: series_stats[series]["bible"]["win"] += 1
                elif outcome is False: series_stats[series]["bible"]["loss"] += 1

        return {"markets": series_stats, "updated": datetime.now().isoformat()}

if __name__ == "__main__":
    if not os.path.exists('dashboard'): os.makedirs('dashboard')
    print(f"🚀 Bible-Integrated Dashboard running at http://localhost:8000")
    with socketserver.TCPServer(("", 8000), DashboardHandler) as httpd:
        httpd.serve_forever()
