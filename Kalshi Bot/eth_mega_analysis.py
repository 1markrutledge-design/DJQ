#!/usr/bin/env python3
"""
ETH MEGA ANALYSIS v2
=====================
Uses 33 markets with full 5-sec price timelines + 491 settled outcomes.

Strategy: Find entry rules based on price patterns in the 33 complete markets,
then validate the overall YES/NO base rate using all 491 outcomes.
"""

import csv
import math
from collections import defaultdict
from datetime import datetime, timezone

DATA_FILE = "market_history.csv"

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
print("=" * 70)
print(" ETH MEGA STRATEGY ANALYSIS")
print("=" * 70)
print("\nLoading data...")

all_outcomes = {}   # ticker -> YES/NO  (all 491)
markets      = defaultdict(list)  # ticker -> [price rows]

with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ticker = (row.get("ticker") or "").strip()
        if "KXETH" not in ticker:
            continue
        result = (row.get("result") or "").strip()
        if result in ("YES", "NO"):
            all_outcomes[ticker] = result
            continue
        # Price row
        bid_s  = (row.get("yes_bid")    or "").strip()
        ask_s  = (row.get("yes_ask")    or "").strip()
        last_s = (row.get("last_price") or "").strip()
        ts_s   = (row.get("timestamp")  or "").strip()
        cl_s   = (row.get("close_time") or "").strip()
        if not (bid_s or ask_s or last_s):
            continue
        try:
            bid  = int(bid_s)  if bid_s  else 0
            ask  = int(ask_s)  if ask_s  else 0
            last = int(last_s) if last_s else 0
        except ValueError:
            continue
        if bid == 0 and ask == 0 and last == 0:
            continue
        try:
            ts = datetime.fromisoformat(ts_s)
        except ValueError:
            continue
        markets[ticker].append({
            "ts": ts, "bid": bid, "ask": ask, "last": last, "close_s": cl_s
        })

complete = {t: markets[t] for t in markets if t in all_outcomes}

print(f"  Total ETH outcomes (all week) : {len(all_outcomes)}")
print(f"    → YES: {sum(1 for v in all_outcomes.values() if v=='YES')}  "
      f"NO: {sum(1 for v in all_outcomes.values() if v=='NO')}")
yes_all = sum(1 for v in all_outcomes.values() if v=='YES')
no_all  = len(all_outcomes) - yes_all
print(f"    → Base YES rate             : {yes_all/len(all_outcomes)*100:.1f}%")
print(f"  Markets with 5-sec price data : {len(complete)}")
print()

# ─────────────────────────────────────────────
# BUILD TIMELINES  (minutes_remaining as key)
# ─────────────────────────────────────────────
def parse_close(ticker, rows):
    """Get close time from stored close_time field."""
    for r in rows:
        cs = r.get("close_s", "").strip()
        if cs:
            try:
                return datetime.fromisoformat(cs.replace("Z", "+00:00"))
            except ValueError:
                pass
    return None

timelines = {}
for ticker, rows in complete.items():
    close_dt = parse_close(ticker, rows)
    if close_dt is None:
        continue
    tl = []
    for r in sorted(rows, key=lambda x: x["ts"]):
        mr = (close_dt - r["ts"]).total_seconds() / 60.0
        if -1 <= mr <= 16:
            mid = (r["bid"] + r["ask"]) / 2.0
            tl.append({"mr": mr, "bid": r["bid"], "ask": r["ask"],
                        "last": r["last"], "mid": mid})
    if len(tl) >= 10:
        timelines[ticker] = tl

outcomes = {t: all_outcomes[t] for t in timelines}
print(f"  Timelines ready               : {len(timelines)}")
print(f"  (Outcomes for those markets:  YES={sum(1 for v in outcomes.values() if v=='YES')}, "
      f"NO={sum(1 for v in outcomes.values() if v=='NO')})")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def snap_at(tl, min_mr, max_mr):
    """First snapshot (highest mr = earliest time) in window."""
    cands = [s for s in tl if min_mr <= s["mr"] <= max_mr]
    return max(cands, key=lambda s: s["mr"]) if cands else None

def pnl(side, snap, outcome):
    if side == "YES":
        cost = snap["ask"]
        won  = (outcome == "YES")
    else:
        cost = 100 - snap["bid"]   # NO ask
        won  = (outcome == "NO")
    return (100 - cost) if won else -cost, cost, won

# ─────────────────────────────────────────────
# STRATEGY GRID SEARCH
# ─────────────────────────────────────────────
print("\nRunning strategy grid search...")

windows = [
    (13, 15),  # First 2 min
    (11, 15),  # First 4 min
    (10, 14),
    (8,  13),
    (6,  11),
    (5,  10),
    (4,   9),
    (3,   8),
    (2,   7),
    (1,   5),
    (0.5, 3),
    (0,   2),
    (11, 15),  # alias for early
    (0,  5),   # last 5 min
    (5,  15),  # first half
    (0,  8),   # second half
]
thresholds = list(range(15, 86, 5))
conditions = ["last_above","last_below","bid_above","bid_below",
              "ask_above","ask_below","mid_above","mid_below"]
sides = ["YES", "NO"]

def check(snap, cond, thr):
    return {
        "last_above": snap["last"] >= thr,
        "last_below": snap["last"] <= thr,
        "bid_above":  snap["bid"]  >= thr,
        "bid_below":  snap["bid"]  <= thr,
        "ask_above":  snap["ask"]  >= thr,
        "ask_below":  snap["ask"]  <= thr,
        "mid_above":  snap["mid"]  >= thr,
        "mid_below":  snap["mid"]  <= thr,
    }.get(cond, False)

results = []
for (lo, hi) in windows:
    for thr in thresholds:
        for cond in conditions:
            for side in sides:
                wins=0; losses=0; tot_cost=0; tot_pnl=0
                for ticker, tl in timelines.items():
                    s = snap_at(tl, lo, hi)
                    if s is None: continue
                    if not check(s, cond, thr): continue
                    o = outcomes[ticker]
                    p, cost, won = pnl(side, s, o)
                    tot_pnl += p; tot_cost += cost
                    if won: wins += 1
                    else:   losses += 1
                n = wins + losses
                if n < 5: continue
                wr = wins / n
                avg_cost = tot_cost / n
                avg_pnl  = tot_pnl / n
                ev = wr * (100 - avg_cost) - (1-wr) * avg_cost
                results.append({
                    "window": f"{lo:.1f}-{hi:.1f}",
                    "lo": lo, "hi": hi,
                    "thr": thr, "cond": cond, "side": side,
                    "n": n, "wins": wins, "losses": losses,
                    "wr": wr, "avg_cost": avg_cost,
                    "avg_pnl": avg_pnl, "ev": ev,
                })

print(f"  Tested: {len(windows)*len(thresholds)*len(conditions)*len(sides)} combos")
print(f"  Valid (n≥5): {len(results)}")

# Also unconditional always-on
print("\n--- UNCONDITIONAL 'ALWAYS BUY' RESULTS ---")
for side in ["YES","NO"]:
    for (lo,hi) in [(13,15),(10,14),(8,13),(5,10),(2,7),(0,5),(0,15)]:
        wins=0; losses=0; tot_c=0; tot_p=0
        for ticker,tl in timelines.items():
            s = snap_at(tl,lo,hi)
            if s is None: continue
            o = outcomes[ticker]
            p,cost,won = pnl(side,s,o)
            tot_p+=p; tot_c+=cost
            if won: wins+=1
            else: losses+=1
        n=wins+losses
        if n==0: continue
        wr=wins/n; avg_c=tot_c/n; avg_p=tot_p/n
        print(f"  [{side}] {lo:.0f}-{hi:.0f}min  n={n:>3}  WR={wr*100:.1f}%  "
              f"AvgEntry={avg_c:.1f}¢  AvgPnL={avg_p:+.2f}¢/share")

# ─────────────────────────────────────────────
# RANK RESULTS
# ─────────────────────────────────────────────
pos_ev = [r for r in results if r["ev"] > 0]
print(f"\n  Positive EV strategies: {len(pos_ev)}")

# Score = EV * sqrt(n) * frequency_weight
for r in pos_ev:
    freq_weight = r["n"] / len(timelines)  # what fraction of markets this fires on
    r["score"] = r["ev"] * math.sqrt(r["n"]) * (1 + freq_weight)

pos_ev.sort(key=lambda r: r["score"], reverse=True)

# ─────────────────────────────────────────────
# PRINT TABLES
# ─────────────────────────────────────────────
SEP = "─" * 95

def hdr():
    print(f"{'#':>3}  {'Window':>10}  {'Condition':>14}  {'Thr':>4}  {'Side':>4}  "
          f"{'N':>4}  {'WR%':>6}  {'Entry':>6}  {'EV/sh':>7}  "
          f"{'Win$':>6}  {'Loss$':>6}  {'Score':>7}")
    print(SEP)

def row_str(i, r):
    win_prof  =  100 - r["avg_cost"]
    loss_prof = -r["avg_cost"]
    return (f"{i:>3}  {r['window']:>10}  {r['cond']:>14}  {r['thr']:>4}  "
            f"{r['side']:>4}  {r['n']:>4}  {r['wr']*100:>5.1f}%  "
            f"{r['avg_cost']:>5.1f}c  {r['ev']:>+6.2f}c  "
            f"{win_prof:>5.1f}c  {loss_prof:>5.1f}c  {r['score']:>7.3f}")

print(f"\n{'='*95}")
print("  TOP 40 STRATEGIES — RANKED BY COMPOSITE SCORE (EV × √N × Frequency)")
print(f"{'='*95}")
hdr()
for i, r in enumerate(pos_ev[:40], 1):
    print(row_str(i, r))

# High frequency (fires on 60%+ of markets)
hi_freq = [r for r in pos_ev if r["n"]/len(timelines) >= 0.5]
hi_freq.sort(key=lambda r: r["ev"], reverse=True)
print(f"\n{'='*95}")
print(f"  HIGH-FREQUENCY STRATEGIES (fires on ≥50% of {len(timelines)} sample markets)")
print(f"{'='*95}")
hdr()
for i, r in enumerate(hi_freq[:25], 1):
    print(row_str(i, r))

# Best pure EV
best_ev = sorted(pos_ev, key=lambda r: r["ev"], reverse=True)
print(f"\n{'='*95}")
print("  HIGHEST RAW EV/SHARE (regardless of frequency)")
print(f"{'='*95}")
hdr()
for i, r in enumerate(best_ev[:20], 1):
    print(row_str(i, r))

# ─────────────────────────────────────────────
# PRICE DISTRIBUTION BY OUTCOME
# ─────────────────────────────────────────────
print(f"\n{'='*70}")
print("  PRICE DISTRIBUTION BY OUTCOME (5-10 min remaining window)")
print(f"{'='*70}")
by_out = {"YES":[], "NO":[]}
for ticker, tl in timelines.items():
    s = snap_at(tl, 5, 10)
    if s:
        by_out[outcomes[ticker]].append(s)

for out, snaps in by_out.items():
    if not snaps: continue
    lasts = [s["last"] for s in snaps]
    bids  = [s["bid"]  for s in snaps]
    asks  = [s["ask"]  for s in snaps]
    n = len(lasts)
    print(f"\n  OUTCOME={out}  (n={n})")
    print(f"    avg last={sum(lasts)/n:.1f}¢  avg bid={sum(bids)/n:.1f}¢  avg ask={sum(asks)/n:.1f}¢")
    buckets = [(0,20),(20,30),(30,40),(40,50),(50,60),(60,70),(70,80),(80,101)]
    for lo,hi in buckets:
        cnt = sum(1 for v in lasts if lo<=v<hi)
        bar = "█" * int(cnt/n*30)
        print(f"    [{lo:>2}-{hi-1:>2}¢] {cnt:>3} ({cnt/n*100:>5.1f}%) {bar}")

# ─────────────────────────────────────────────
# DETAILED TOP 7 STRATEGY PLANS
# ─────────────────────────────────────────────
print(f"\n{'='*70}")
print("  TOP 7 STRATEGIES — FULL DETAIL + IMPLEMENTATION PLAN")
print(f"{'='*70}")

top7 = pos_ev[:7]
for rank, r in enumerate(top7, 1):
    win_pnl  = 100 - r["avg_cost"]
    loss_pnl = r["avg_cost"]
    fire_rate = r["n"] / len(timelines) * 100
    est_daily = 96 * (r["n"]/len(timelines))  # 96 ETH markets per day
    daily_ev = r["ev"] * est_daily
    print(f"""
  ━━━ STRATEGY #{rank} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RULE   : When {r['cond'].replace('_',' ')} {"≥" if "above" in r['cond'] else "≤"} {r['thr']}¢
           during the {r['window']} minutes-remaining window → buy {r['side']}
  RESULTS: {r['n']} trades  |  {r['wr']*100:.1f}% win rate
           Avg entry: {r['avg_cost']:.1f}¢  |  Win profit: +{win_pnl:.1f}¢  |  Loss: -{loss_pnl:.1f}¢
           EV/share : {r['ev']:+.2f}¢
  SCALE  : Fires on {fire_rate:.0f}% of markets → ~{est_daily:.0f} trades/day (of 96)
           Est. daily EV @ 1 share: {daily_ev:+.1f}¢ = ${daily_ev/100:+.4f}
  BOT    : entry_trigger="{r['cond']}", threshold={r['thr']}, side="{r['side']}",
           window_min={r['lo']}, window_max={r['hi']}, hold="to_expiry\"""")

print(f"\n{'='*70}")
print("ANALYSIS COMPLETE")
print(f"{'='*70}")
