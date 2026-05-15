#!/usr/bin/env python3
"""
BTC MEGA ANALYSIS — Full dataset from market_history.csv
Analyzes ALL BTC 15-minute markets collected since Apr 21.
Finds the highest-EV, most reliable entry strategy.
"""

import csv
import json
from datetime import datetime, timezone
from collections import defaultdict

DATA_FILE = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/market_history.csv"

# ─── Load ALL BTC rows ──────────────────────────────────────────────────────
print("📂 Loading market_history.csv...")
markets = defaultdict(list)   # ticker -> list of price rows
results = {}                  # ticker -> "YES" | "NO"

with open(DATA_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ticker = row.get("ticker", "")
        if "KXBTC15M" not in ticker:
            continue

        result = row.get("result", "").strip().upper()
        if result in ("YES", "NO"):
            results[ticker] = result
            continue

        try:
            yes_bid   = int(row["yes_bid"]) if row.get("yes_bid")   else None
            yes_ask   = int(row["yes_ask"]) if row.get("yes_ask")   else None
            last      = int(row["last_price"]) if row.get("last_price") else None
            close_str = row.get("close_time", "")
            ts_str    = row.get("timestamp", "")

            if not ts_str or not close_str:
                continue

            ts    = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            close = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            secs_remaining = (close - ts).total_seconds()

            markets[ticker].append({
                "ts": ts,
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "last": last,
                "secs_remaining": secs_remaining,
            })
        except Exception:
            continue

# Only keep markets we have a definitive result for
settled = {t: rows for t, rows in markets.items() if t in results}
print(f"✅ Loaded {len(settled)} settled BTC markets with price data")
print(f"   YES outcomes: {sum(1 for r in results.values() if r == 'YES')}")
print(f"   NO  outcomes: {sum(1 for r in results.values() if r == 'NO')}")
print()

# ─── Helper: mid-price ──────────────────────────────────────────────────────
def mid(row):
    if row["yes_bid"] and row["yes_ask"]:
        return (row["yes_bid"] + row["yes_ask"]) / 2
    return row["last"]

# ─── Strategy Backtester ────────────────────────────────────────────────────
def backtest(condition_fn, buy_price_fn, label=""):
    """
    condition_fn(row)  -> bool  (should we enter?)
    buy_price_fn(row)  -> int   (what price do we pay, in cents)
    Returns: (trades, wins, total_pnl, avg_pnl_per_trade)
    """
    trades = 0
    wins   = 0
    total_pnl = 0
    entry_prices = []

    for ticker, rows in settled.items():
        outcome = results[ticker]
        entered = False
        for row in sorted(rows, key=lambda r: r["ts"]):
            if entered:
                break
            if condition_fn(row):
                buy = buy_price_fn(row)
                if buy is None or buy <= 0:
                    continue
                pnl = (100 - buy) if outcome == "YES" else -buy
                trades += 1
                wins   += 1 if outcome == "YES" else 0
                total_pnl += pnl
                entry_prices.append(buy)
                entered = True

    if trades == 0:
        return trades, 0, 0, 0, 0
    win_rate  = wins / trades * 100
    avg_pnl   = total_pnl / trades
    avg_entry = sum(entry_prices) / len(entry_prices)
    return trades, win_rate, total_pnl, avg_pnl, avg_entry

# ─── TIME WINDOW ANALYSIS ───────────────────────────────────────────────────
print("=" * 65)
print("§1  BASELINE — Time window + price band scan (buy YES)")
print("=" * 65)
print(f"{'Window':>20}  {'Price':>8}  {'Trades':>7}  {'WinRate':>8}  {'AvgPnL':>8}  {'TotalPnL':>9}")
print("-" * 65)

best_strategies = []

windows = [
    ("12–9 min left",  lambda r: 720 <= r["secs_remaining"] <= 900 - 1),
    ("9–6 min left",   lambda r: 540 <= r["secs_remaining"] <  720),
    ("6–3 min left",   lambda r: 360 <= r["secs_remaining"] <  540),
    ("3–1 min left",   lambda r: 60  <= r["secs_remaining"] <  360),
    ("1–0 min left",   lambda r: 0   <= r["secs_remaining"] <   60),
]

price_bands = [
    ("ANY",      lambda r: True),
    ("≤30¢",     lambda r: mid(r) is not None and mid(r) <= 30),
    ("≤40¢",     lambda r: mid(r) is not None and mid(r) <= 40),
    ("≤50¢",     lambda r: mid(r) is not None and mid(r) <= 50),
    ("≤55¢",     lambda r: mid(r) is not None and mid(r) <= 55),
    ("≤60¢",     lambda r: mid(r) is not None and mid(r) <= 60),
    ("≤65¢",     lambda r: mid(r) is not None and mid(r) <= 65),
    ("≤70¢",     lambda r: mid(r) is not None and mid(r) <= 70),
    ("60–70¢",   lambda r: mid(r) is not None and 60 <= mid(r) <= 70),
    ("≥70¢",     lambda r: mid(r) is not None and mid(r) >= 70),
    ("≥80¢",     lambda r: mid(r) is not None and mid(r) >= 80),
    ("≥90¢",     lambda r: mid(r) is not None and mid(r) >= 90),
]

for win_label, win_fn in windows:
    for price_label, price_fn in price_bands:
        def cond(row, wf=win_fn, pf=price_fn):
            return wf(row) and pf(row) and mid(row) is not None

        def buy_price(row):
            return row["yes_ask"] if row["yes_ask"] else int(mid(row) + 1)

        trades, wr, total, avg, avg_entry = backtest(cond, buy_price)
        if trades >= 8:
            row_str = f"{win_label:>20}  {price_label:>8}  {trades:>7}  {wr:>7.1f}%  {avg_entry:>6.1f}¢  {avg:>+7.2f}¢  {total:>+8}¢"
            if avg > 0 and wr >= 50:
                best_strategies.append({
                    "window": win_label, "price": price_label,
                    "trades": trades, "win_rate": wr,
                    "avg_pnl": avg, "total_pnl": total, "avg_entry": avg_entry,
                    "label": f"YES | {win_label} | {price_label}"
                })
            if trades >= 15:
                print(row_str)

# ─── BUY NO SCAN ────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("§2  BUY NO — time window + price band (pay (100 - ask) for NO)")
print("=" * 65)
print(f"{'Window':>20}  {'Price':>8}  {'Trades':>7}  {'WinRate':>8}  {'AvgBuy':>7}  {'AvgPnL':>8}  {'TotalPnL':>9}")
print("-" * 65)

for win_label, win_fn in windows:
    for price_label, price_fn in price_bands:
        def cond_no(row, wf=win_fn, pf=price_fn):
            return wf(row) and pf(row) and mid(row) is not None

        def buy_no_price(row):
            # Cost of NO = 100 - yes_bid
            yes_bid = row["yes_bid"]
            if yes_bid:
                return 100 - yes_bid
            m = mid(row)
            return int(100 - m) if m else None

        def backtest_no_wrapper(c, bp, wl=win_label, pl=price_label):
            trades = wins = total_pnl = 0
            ep = []
            for ticker, rows in settled.items():
                outcome = results[ticker]
                entered = False
                for row in sorted(rows, key=lambda r: r["ts"]):
                    if entered: break
                    if c(row):
                        buy = bp(row)
                        if buy is None or buy <= 0: continue
                        pnl = (100 - buy) if outcome == "NO" else -buy
                        trades += 1; wins += 1 if outcome == "NO" else 0
                        total_pnl += pnl; ep.append(buy); entered = True
            if trades == 0: return 0,0,0,0,0
            return trades, wins/trades*100, total_pnl, total_pnl/trades, sum(ep)/len(ep)

        trades, wr, total, avg, avg_entry = backtest_no_wrapper(cond_no, buy_no_price)
        if trades >= 15:
            row_str = f"{win_label:>20}  {price_label:>8}  {trades:>7}  {wr:>7.1f}%  {avg_entry:>6.1f}¢  {avg:>+7.2f}¢  {total:>+8}¢"
            print(row_str)
            if avg > 0 and wr >= 50:
                best_strategies.append({
                    "window": win_label, "price": price_label,
                    "trades": trades, "win_rate": wr,
                    "avg_pnl": avg, "total_pnl": total, "avg_entry": avg_entry,
                    "label": f"NO | {win_label} | {price_label}"
                })

# ─── MOMENTUM SCAN: First price jump in window ──────────────────────────────
print()
print("=" * 65)
print("§3  MOMENTUM — Buy YES after first upward price jump in window")
print("=" * 65)

def momentum_backtest(window_start, window_end, jump_thresh):
    """Buy YES the first time price jumps +jump_thresh¢ within the window."""
    trades = wins = total = 0
    ep = []
    for ticker, rows in settled.items():
        outcome = results[ticker]
        sorted_rows = sorted(rows, key=lambda r: r["ts"])
        in_window = [r for r in sorted_rows if window_end <= r["secs_remaining"] < window_start]
        if len(in_window) < 2:
            continue
        prev_mid = None
        for row in in_window:
            m = mid(row)
            if m is None:
                continue
            if prev_mid is not None and (m - prev_mid) >= jump_thresh:
                buy = row["yes_ask"] if row["yes_ask"] else int(m + 1)
                pnl = (100 - buy) if outcome == "YES" else -buy
                trades += 1; wins += 1 if outcome == "YES" else 0
                total += pnl; ep.append(buy); break
            prev_mid = m
    if trades == 0:
        return
    wr = wins/trades*100
    avg = total/trades
    avg_e = sum(ep)/len(ep)
    print(f"  Win:{window_start//60}-{window_end//60}min  Jump≥{jump_thresh}¢  → {trades:>4} trades  {wr:.1f}% win  Entry≈{avg_e:.1f}¢  AvgPnL {avg:+.2f}¢  Total {total:+}¢")

for ws, we in [(900,720), (720,540), (540,360), (360,180), (180,60), (60,0)]:
    for jump in [3, 5, 8, 10, 15]:
        momentum_backtest(ws, we, jump)

# ─── PRICE REVERSAL: Buy dip in last 5 min ──────────────────────────────────
print()
print("=" * 65)
print("§4  CRASH RECOVERY — Buy after big drop mid-market")
print("=" * 65)

def crash_backtest(window_start, window_end, drop_thresh, target_price_max):
    trades = wins = total = 0
    ep = []
    for ticker, rows in settled.items():
        outcome = results[ticker]
        sorted_rows = sorted(rows, key=lambda r: r["ts"])
        in_window = [r for r in sorted_rows if window_end <= r["secs_remaining"] < window_start]
        if len(in_window) < 3:
            continue
        mids = [(r, mid(r)) for r in in_window if mid(r) is not None]
        for i in range(1, len(mids)):
            prev_row, prev_m = mids[i-1]
            curr_row, curr_m = mids[i]
            if curr_m is None or prev_m is None:
                continue
            drop = prev_m - curr_m
            if drop >= drop_thresh and curr_m <= target_price_max:
                buy = curr_row["yes_ask"] if curr_row["yes_ask"] else int(curr_m + 1)
                pnl = (100 - buy) if outcome == "YES" else -buy
                trades += 1; wins += 1 if outcome == "YES" else 0
                total += pnl; ep.append(buy); break

    if trades < 5:
        return
    wr = wins/trades*100
    avg = total/trades
    avg_e = sum(ep)/len(ep)
    print(f"  Win:{window_start//60}-{window_end//60}m  Drop≥{drop_thresh}¢  MaxPrice{target_price_max}¢  → {trades:>3} trades  {wr:.1f}% win  Entry≈{avg_e:.1f}¢  AvgPnL {avg:+.2f}¢  Total {total:+}¢")

for ws, we in [(900,540), (540,180), (180,60), (60,0)]:
    for drop in [5, 8, 10, 15]:
        for target in [40, 50, 60, 70]:
            crash_backtest(ws, we, drop, target)

# ─── ASK PRICE EDGE: maker vs taker ─────────────────────────────────────────
print()
print("=" * 65)
print("§5  SPREAD ANALYSIS — Bid/Ask spread by time window")
print("=" * 65)
spreads_by_window = defaultdict(list)
for ticker, rows in settled.items():
    for row in rows:
        if row["yes_bid"] and row["yes_ask"] and row["yes_ask"] > row["yes_bid"]:
            spread = row["yes_ask"] - row["yes_bid"]
            sr = row["secs_remaining"]
            if sr >= 720:   spreads_by_window["12-15min"].append(spread)
            elif sr >= 540: spreads_by_window["9-12min"].append(spread)
            elif sr >= 360: spreads_by_window["6-9min"].append(spread)
            elif sr >= 180: spreads_by_window["3-6min"].append(spread)
            elif sr >= 60:  spreads_by_window["1-3min"].append(spread)
            else:           spreads_by_window["0-1min"].append(spread)

for win, spreads in sorted(spreads_by_window.items()):
    avg_s = sum(spreads)/len(spreads)
    print(f"  {win:>10}: avg spread = {avg_s:.2f}¢  (n={len(spreads)})")

# ─── SUMMARY ────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("§6  TOP PROFITABLE STRATEGIES (EV > 0, WinRate ≥ 50%)")
print("=" * 65)
best_strategies.sort(key=lambda x: x["avg_pnl"], reverse=True)
for s in best_strategies[:15]:
    print(f"  {s['label']}")
    print(f"    Trades={s['trades']}  WinRate={s['win_rate']:.1f}%  AvgEntry={s['avg_entry']:.1f}¢  AvgPnL={s['avg_pnl']:+.2f}¢  TotalPnL={s['total_pnl']:+}¢")

print()
print("✅ Analysis complete.")
