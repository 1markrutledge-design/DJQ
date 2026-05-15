#!/usr/bin/env python3
"""
Kalshi BTC Bot — Live Dashboard (Rich TUI)
==========================================
Reads bot_status.json written by bot.py and renders a live terminal UI.

Usage:
    python dashboard.py          # auto-refreshes every 2 seconds
    python dashboard.py --once   # print once and exit
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

STATUS_FILE   = "bot_status.json"
REFRESH_SECS  = 2
ONCE_MODE     = "--once" in sys.argv

console = Console()

# ── Color helpers ─────────────────────────────────────────────────────────────

STATUS_COLORS = {
    "WATCHING": "dim white",
    "ENTERED":  "yellow",
    "FILLED":   "bright_cyan",
    "EXITED":   "dim green",
    "LOCKED":   "dim red",
}

def _status_badge(status: str) -> Text:
    icons = {
        "WATCHING": "👁 ",
        "ENTERED":  "⏳",
        "FILLED":   "🟢",
        "EXITED":   "✅",
        "LOCKED":   "🔒",
    }
    color = STATUS_COLORS.get(status, "white")
    icon  = icons.get(status, "  ")
    return Text(f"{icon} {status}", style=color)

def _pl_text(cents: int | None) -> Text:
    if cents is None:
        return Text("—", style="dim")
    dollars = cents / 100
    style   = "bright_green" if cents >= 0 else "bright_red"
    sign    = "+" if cents >= 0 else ""
    return Text(f"{sign}{cents}¢  ({sign}${dollars:.2f})", style=style)

def _mins_text(mins: float) -> Text:
    if mins < 0:
        return Text("EXPIRED", style="dim red")
    elif mins <= 3:
        return Text(f"{mins:.1f} min", style="bright_red bold")
    elif mins <= 12:
        return Text(f"{mins:.1f} min", style="yellow")
    else:
        return Text(f"{mins:.1f} min", style="dim")

# ── Load status ───────────────────────────────────────────────────────────────

def load_status() -> dict:
    if not os.path.exists(STATUS_FILE):
        return {}
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

# ── Build UI panels ───────────────────────────────────────────────────────────

def build_header(data: dict) -> Panel:
    dry_run  = data.get("dry_run", False)
    updated  = data.get("last_updated", "—")
    mode_tag = "[bold red blink]● LIVE[/]" if not dry_run else "[bold yellow]◌ DRY-RUN[/]"

    try:
        dt  = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        ts  = dt.strftime("%H:%M:%S UTC")
        staleness = f"[dim]({age:.0f}s ago)[/]" if age < 60 else f"[red]({age:.0f}s ago — bot may be down)[/]"
    except Exception:
        ts         = updated
        staleness  = ""

    txt = Text.assemble(
        "  🤖  Kalshi BTC 15M Front-Runner    ",
        (mode_tag, ""),
        f"    Last update: {ts} {staleness}",
    )
    return Panel(Align.center(txt), style="bold blue", padding=(0, 1))


def build_stats(data: dict) -> Panel:
    balance_c = data.get("balance_cents", 0)
    pl_c      = data.get("total_pl_cents", 0)
    strategies = data.get("strategy", {})

    # Strategy Table
    strat_table = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold dim blue")
    strat_table.add_column("Series", style="cyan")
    strat_table.add_column("Trigger", justify="right")
    strat_table.add_column("Bid", justify="right")
    strat_table.add_column("Stop-Loss", justify="right", style="bright_red")
    strat_table.add_column("Size", justify="right")
    strat_table.add_column("Type", justify="center")

    for ticker, s in strategies.items():
        if ticker == "DEFAULT": continue
        strat_table.add_row(
            ticker,
            f"{s.get('trigger')}¢",
            f"{s.get('bid')}¢",
            f"{s.get('stop_loss')}¢",
            f"x{s.get('trade_count')}",
            "Taker" if not s.get('post_only', True) else "Maker"
        )

    return Panel(strat_table, title="[bold]📊  Active Strategies (Triggers & Stop-Losses)[/]", border_style="blue", padding=(0, 1))


def build_markets_table(data: dict) -> Panel:
    markets = data.get("markets", {})

    tbl = Table(
        box=box.SIMPLE_HEAVY,
        expand=True,
        show_header=True,
        header_style="bold dim white",
        row_styles=["", "dim"],
    )
    tbl.add_column("Ticker",        style="cyan",  no_wrap=True, min_width=30)
    tbl.add_column("Status",        justify="left", min_width=14)
    tbl.add_column("Bid",           justify="right", min_width=6)
    tbl.add_column("Ask",           justify="right", min_width=6)
    tbl.add_column("Entry",         justify="right", min_width=7)
    tbl.add_column("Exit",          justify="right", min_width=7)
    tbl.add_column("P&L",           justify="right", min_width=18)
    tbl.add_column("Closes In",     justify="right", min_width=10)

    if not markets:
        tbl.add_row(
            "—", "No active markets yet…", "—", "—", "—", "—", "—", "—",
        )
    else:
        # Sort: active states first, then by time to close
        sorted_markets = sorted(
            markets.values(),
            key=lambda m: (
                ["ENTERED","FILLED","WATCHING","EXITED","LOCKED"].index(m.get("status","LOCKED")),
                m.get("mins_to_close", 999),
            ),
        )
        for m in sorted_markets:
            status     = m.get("status", "—")
            entry      = m.get("entry_price")
            exit_p     = m.get("exit_price")
            pl         = m.get("realized_pl_c")
            mins       = m.get("mins_to_close", -1)

            tbl.add_row(
                m.get("ticker", "—"),
                _status_badge(status),
                Text(f"{m.get('bid','—')}¢", style="bright_white") if m.get("bid") else Text("—", style="dim"),
                Text(f"{m.get('ask','—')}¢", style="bright_white") if m.get("ask") else Text("—", style="dim"),
                Text(f"{entry}¢",  style="yellow")  if entry  else Text("—", style="dim"),
                Text(f"{exit_p}¢", style="dim")     if exit_p else Text("—", style="dim"),
                _pl_text(pl),
                _mins_text(mins),
            )

    return Panel(tbl, title="[bold]📈  Active Markets[/]", border_style="blue")


def build_trade_log(data: dict) -> Panel:
    log_entries = data.get("trade_log", [])

    tbl = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold dim white")
    tbl.add_column("Time",  style="dim",       no_wrap=True, width=10)
    tbl.add_column("Event", style="bold white", width=18)
    tbl.add_column("Ticker",style="cyan",       no_wrap=True)
    tbl.add_column("Price", justify="right",    width=8)
    tbl.add_column("Note",  style="dim",        ratio=1)

    event_styles = {
        "BUY_PLACED":        "yellow",
        "BUY_FILLED":        "bright_cyan",
        "STOP_LOSS":         "bright_red",
        "CANCELLED_UNFILLED":"dim red",
    }

    for entry in reversed(log_entries[-12:]):
        raw_ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            ts = dt.strftime("%H:%M:%S")
        except Exception:
            ts = raw_ts[:8]

        event  = entry.get("event", "—")
        ticker = entry.get("ticker", "—")
        price  = entry.get("price")
        note   = entry.get("note", "")
        pl_c   = entry.get("pl_cents")

        style  = event_styles.get(event, "white")
        pl_str = f" {'+' if (pl_c or 0)>=0 else ''}{pl_c}¢" if pl_c is not None else ""

        tbl.add_row(
            ts,
            Text(event, style=style),
            ticker,
            f"{price}¢" if price is not None else "—",
            f"{note}{pl_str}",
        )

    if not log_entries:
        tbl.add_row("—", "No trades yet", "—", "—", "Waiting for signals…")

    return Panel(tbl, title="[bold]📜  Trade Log[/]", border_style="blue")


def build_footer() -> Panel:
    txt = Text(
        "  q / Ctrl-C to quit    |    Refreshes every 2s    |    Data source: bot_status.json  ",
        style="dim",
        justify="center",
    )
    return Panel(txt, style="dim blue", padding=(0, 0))


# ── Layout ────────────────────────────────────────────────────────────────────

def build_layout(data: dict) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(build_header(data),        name="header",  size=3),
        Layout(name="body",               ratio=1),
        Layout(build_footer(),            name="footer",  size=3),
    )
    layout["body"].split_column(
        Layout(build_stats(data),         name="stats",   size=10),
        Layout(build_markets_table(data), name="markets", ratio=2),
        Layout(build_trade_log(data),     name="log",     ratio=1),
    )
    return layout


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if ONCE_MODE:
        data = load_status()
        console.print(build_layout(data))
        return

    console.clear()
    try:
        with Live(
            build_layout(load_status()),
            console=console,
            refresh_per_second=1 / REFRESH_SECS,
            screen=True,
        ) as live:
            while True:
                time.sleep(REFRESH_SECS)
                data = load_status()
                live.update(build_layout(data))
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard closed.[/dim]")


if __name__ == "__main__":
    main()
