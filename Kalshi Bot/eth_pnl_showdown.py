#!/usr/bin/env python3
"""
ETH DOLLAR P&L SHOWDOWN
Ranks every strategy and combination by actual estimated daily dollars.
"""
import csv, math
from collections import defaultdict
from datetime import datetime, timezone

DATA_FILE = "market_history.csv"

# ── Load data ──────────────────────────────────────────────────────────────
markets = defaultdict(list)
outcomes = {}
with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ticker = (row.get("ticker") or "").strip()
        if "KXETH" not in ticker: continue
        result = (row.get("result") or "").strip()
        if result in ("YES","NO"):
            outcomes[ticker] = result
            continue
        bid_s  = (row.get("yes_bid")    or "").strip()
        ask_s  = (row.get("yes_ask")    or "").strip()
        last_s = (row.get("last_price") or "").strip()
        ts_s   = (row.get("timestamp")  or "").strip()
        cl_s   = (row.get("close_time") or "").strip()
        if not (bid_s or ask_s or last_s): continue
        try:
            b = int(bid_s) if bid_s else 0
            a = int(ask_s) if ask_s else 0
            l = int(last_s) if last_s else 0
            ts = datetime.fromisoformat(ts_s)
        except: continue
        markets[ticker].append({"bid":b,"ask":a,"last":l,"ts":ts,"close_s":cl_s})

def parse_close(ticker, rows):
    for r in rows:
        cs = r.get("close_s","").strip()
        if cs:
            try: return datetime.fromisoformat(cs.replace("Z","+00:00"))
            except: pass
    return None

timelines = {}
for ticker, rows in markets.items():
    if ticker not in outcomes: continue
    close_dt = parse_close(ticker, rows)
    if not close_dt: continue
    tl = []
    for r in sorted(rows, key=lambda x: x["ts"]):
        mr = (close_dt - r["ts"]).total_seconds() / 60.0
        if -1 <= mr <= 16:
            tl.append({"mr":mr,"bid":r["bid"],"ask":r["ask"],"last":r["last"],
                       "mid":(r["bid"]+r["ask"])/2.0})
    if len(tl) >= 10:
        timelines[ticker] = tl

complete_outcomes = {t: outcomes[t] for t in timelines}
N = len(timelines)
DAYS = 2  # Apr 21 afternoon + Apr 27 morning ≈ 2 trading days of data

print(f"Loaded {N} complete markets across ~{DAYS} days\n")

# ── Helpers ────────────────────────────────────────────────────────────────
def snap_at(tl, lo, hi):
    cands = [s for s in tl if lo <= s["mr"] <= hi]
    return max(cands, key=lambda s: s["mr"]) if cands else None

def check(s, cond, thr):
    return {"last_above":s["last"]>=thr,"last_below":s["last"]<=thr,
            "bid_above":s["bid"]>=thr,"bid_below":s["bid"]<=thr,
            "ask_above":s["ask"]>=thr,"ask_below":s["ask"]<=thr,
            "mid_above":s["mid"]>=thr,"mid_below":s["mid"]<=thr}.get(cond,False)

def simulate(lo, hi, cond, thr, side):
    wins=0; tot_pnl=0.0; tot_cost=0.0; fires=[]
    for ticker, tl in timelines.items():
        s = snap_at(tl, lo, hi)
        if s is None or not check(s, cond, thr): continue
        o = complete_outcomes[ticker]
        if side=="YES":  cost=s["ask"]; won=(o=="YES")
        else:            cost=100-s["bid"]; won=(o=="NO")
        pnl = (100-cost) if won else -cost
        tot_pnl += pnl; tot_cost += cost
        if won: wins+=1
        fires.append(ticker)
    n = len(fires)
    if n == 0: return None
    wr = wins/n
    avg_cost = tot_cost/n
    avg_pnl  = tot_pnl/n
    ev = wr*(100-avg_cost) - (1-wr)*avg_cost
    daily_fires = n/DAYS
    daily_pnl_cents = avg_pnl * daily_fires
    return dict(n=n, wr=wr, avg_cost=avg_cost, avg_pnl=avg_pnl, ev=ev,
                daily_fires=daily_fires, daily_dollars=daily_pnl_cents/100,
                tickers=set(fires))

# ── Named candidate strategies ─────────────────────────────────────────────
STRATEGIES = [
    # (name, lo, hi, condition, threshold, side)
    ("NO Fade Wide",        8,  13, "bid_below",  60, "NO"),
    ("NO Fade Tight",       8,  13, "last_below", 65, "NO"),
    ("NO Fade Very Wide",   8,  13, "last_above", 30, "NO"),
    ("NO Early Mid",        6,  11, "mid_above",  45, "NO"),
    ("NO Early Ask",        6,  11, "ask_below",  70, "NO"),
    ("Momentum Lock 65",    8,  13, "ask_above",  65, "YES"),
    ("Momentum Lock 70",    8,  13, "mid_above",  70, "YES"),
    ("Momentum Early 70",   6,  11, "ask_above",  70, "YES"),
    ("Deep Dip YES",        8,  13, "last_below", 30, "YES"),
    ("Dip Buyer 40",        5,  10, "last_below", 40, "YES"),
    ("Late Dip YES",        4,   9, "mid_below",  50, "YES"),
    ("Late NO Mid",        10,  14, "ask_below",  60, "NO"),
    ("Late NO Wide",       10,  14, "last_below", 55, "NO"),
    ("NO Early Bid 55",     6,  11, "bid_above",  55, "NO"),
]

print("="*72)
print("  INDIVIDUAL STRATEGY P&L RANKING (1 share per trade)")
print("="*72)
print(f"{'#':>3}  {'Strategy':<22}  {'N':>4}  {'WR%':>6}  {'Entry':>6}  "
      f"{'EV/sh':>7}  {'Est/Day':>8}  {'Daily $':>9}")
print("-"*72)

results = {}
ranked = []
for name, lo, hi, cond, thr, side in STRATEGIES:
    r = simulate(lo, hi, cond, thr, side)
    if r:
        results[name] = r
        ranked.append((name, r))

ranked.sort(key=lambda x: x[1]["daily_dollars"], reverse=True)
for i, (name, r) in enumerate(ranked, 1):
    print(f"{i:>3}  {name:<22}  {r['n']:>4}  {r['wr']*100:>5.1f}%  "
          f"{r['avg_cost']:>5.1f}c  {r['ev']:>+6.2f}c  "
          f"{r['daily_fires']:>7.1f}  ${r['daily_dollars']:>8.4f}")

# ── STACKED COMBINATIONS ───────────────────────────────────────────────────
print(f"\n{'='*72}")
print("  STACKED STRATEGY COMBINATIONS (no double-entry per market)")
print(f"{'='*72}")

combos = [
    ("NO Fade Wide + Momentum Lock 65",
     ["NO Fade Wide","Momentum Lock 65"]),
    ("NO Fade Tight + Momentum Lock 65",
     ["NO Fade Tight","Momentum Lock 65"]),
    ("NO Fade Wide + NO Early Mid",
     ["NO Fade Wide","NO Early Mid"]),
    ("NO Fade Wide + Deep Dip YES",
     ["NO Fade Wide","Deep Dip YES"]),
    ("NO Fade Wide + Momentum Lock 65 + Deep Dip YES",
     ["NO Fade Wide","Momentum Lock 65","Deep Dip YES"]),
    ("Top 3: NO Fade + Early + Momentum",
     ["NO Fade Wide","NO Early Mid","Momentum Lock 65"]),
    ("Top 4 Stack",
     ["NO Fade Wide","NO Early Mid","Momentum Lock 65","Deep Dip YES"]),
    ("NO Only: Wide+Early+Late",
     ["NO Fade Wide","NO Early Mid","Late NO Mid"]),
    ("Full Stack All",
     ["NO Fade Wide","NO Early Mid","Momentum Lock 65","Deep Dip YES",
      "Late NO Mid","Dip Buyer 40"]),
]

print(f"{'#':>3}  {'Combination':<44}  {'Trades/Day':>10}  "
      f"{'Daily $':>9}  {'$/Trade':>8}")
print("-"*80)

combo_results = []
for combo_name, strat_names in combos:
    # Each market is entered at most once — first matching strategy wins
    all_pnls = {}  # ticker -> pnl cents
    all_costs = {}
    for sname in strat_names:
        if sname not in results: continue
        lo = next(s[1] for s in STRATEGIES if s[0]==sname)
        hi = next(s[2] for s in STRATEGIES if s[0]==sname)
        cond = next(s[3] for s in STRATEGIES if s[0]==sname)
        thr  = next(s[4] for s in STRATEGIES if s[0]==sname)
        side = next(s[5] for s in STRATEGIES if s[0]==sname)
        for ticker, tl in timelines.items():
            if ticker in all_pnls: continue  # already entered
            s = snap_at(tl, lo, hi)
            if s is None or not check(s, cond, thr): continue
            o = complete_outcomes[ticker]
            if side=="YES": cost=s["ask"]; won=(o=="YES")
            else: cost=100-s["bid"]; won=(o=="NO")
            pnl = (100-cost) if won else -cost
            all_pnls[ticker] = pnl
            all_costs[ticker] = cost
    n_total = len(all_pnls)
    if n_total == 0: continue
    total_pnl = sum(all_pnls.values())
    avg_pnl = total_pnl / n_total
    daily_trades = n_total / DAYS
    daily_dollars = avg_pnl * daily_trades / 100
    per_trade = avg_pnl / 100
    combo_results.append((combo_name, daily_trades, daily_dollars, per_trade))

combo_results.sort(key=lambda x: x[2], reverse=True)
for i, (name, trades, dollars, per_trade) in enumerate(combo_results, 1):
    print(f"{i:>3}  {name:<44}  {trades:>10.1f}  ${dollars:>8.4f}  ${per_trade:>7.4f}")

# ── WINNER ANNOUNCEMENT ────────────────────────────────────────────────────
print(f"\n{'='*72}")
best_combo = combo_results[0]
best_single = ranked[0]
print(f"  🏆 BEST SINGLE STRATEGY : {best_single[0]}")
print(f"     → ${best_single[1]['daily_dollars']:.4f}/day  |  "
      f"{best_single[1]['daily_fires']:.1f} trades/day  |  "
      f"{best_single[1]['wr']*100:.1f}% win rate  |  "
      f"entry avg {best_single[1]['avg_cost']:.1f}¢")
print()
print(f"  🏆 BEST COMBINATION     : {best_combo[0]}")
print(f"     → ${best_combo[2]:.4f}/day  |  {best_combo[1]:.1f} trades/day")
print()

# Scale-up table for best single
print(f"  SCALE PROJECTION — '{best_single[0]}' (1 share = $0.01)")
print(f"  {'Shares':>8}  {'Daily $':>10}  {'Weekly $':>10}  {'Monthly $':>10}")
print(f"  {'-'*42}")
base = best_single[1]['daily_dollars']
for shares in [1,5,10,25,50,100]:
    print(f"  {shares:>8}  ${base*shares:>9.2f}  ${base*shares*7:>9.2f}  ${base*shares*30:>9.2f}")
print(f"{'='*72}")
