"""
Auditor Bot — Daily Performance Report
Runs at 9 AM (Big Report) and 12 PM, 3 PM, 9 PM (Status Updates) ET.
Fetches Kalshi settlement data, aggregates P&L by sport,
and sends a formatted email via Azure Logic Apps (Gmail Connector).

Completely standalone — no shared code with any other bot.
"""

from __future__ import annotations

import os
import base64
import logging
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import azure.functions as func
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KALSHI_BASE = "https://api.elections.kalshi.com"


# How many days back to look for "All-Time" stats
ALL_TIME_DAYS = 30

# Max settlements per API page (Kalshi max is 200)
PAGE_LIMIT = 200

# Bot classification — maps prefixes and heuristics to specific bot names
BOT_RULES: list[tuple[str, str]] = [
    # Women's CBB
    ("KXNCAAWBGAME",        "Women's CBB Bot"),
    ("KXNCAAWB",            "Women's CBB Bot"),
    # Men's CBB
    ("KXNCAAMBGAME",        "College Basketball Bot"),
    ("KXNCAAMB",            "College Basketball Bot"),
    # MLB
    ("KXMLBSO",             "Strikeout Bot"),
    ("KXMLBTOTAL",          "MLB Run Scattershot"),
    ("KXMLBTEAMTOTAL",      "MLB Run Scattershot"),
    ("KXMLBGAME",           "MLB Moneyline Bot"),
    ("KXMLB",               "MLB Bot"),
    # NBA
    ("KXNBAGAME",           "NBA Scattershot"),
    ("KXNBA",               "NBA Scattershot"),
    # Soccer
    ("KXEPL",               "Soccer Scattershot"),
    ("KXUCL",               "Soccer Scattershot"),
    ("KXMLS",               "Soccer Scattershot"),
    ("KXLALIGA",            "Soccer Scattershot"),
    ("KXSERIEA",            "Soccer Scattershot"),
    ("KXCHNSL",             "Soccer Scattershot"),
    ("KXJLEAGUE",           "Soccer Scattershot"),
    ("KXCANPL",             "Soccer Scattershot"),
    ("KXBUNDES",            "Soccer Scattershot"),
    ("KXLIGUE",             "Soccer Scattershot"),
    ("KXERED",              "Soccer Scattershot"),
    ("KXPROL",              "Soccer Scattershot"),
    ("KXELITE",             "Soccer Scattershot"),
    ("KXALLS",              "Soccer Scattershot"),
    ("KXSCOT",              "Soccer Scattershot"),
    ("KXSUPERLIG",          "Soccer Scattershot"),
    ("KXNWSL",              "Soccer Scattershot"),
    ("KXBALLER",            "Soccer Scattershot"),
    ("KXCOPA",              "Soccer Scattershot"),
    ("KXPL",                "Soccer Scattershot"),
    ("KXCHAMP",             "Soccer Scattershot"),
    ("KXEUR",               "Soccer Scattershot"),
    ("KXSOCCER",            "Soccer Scattershot"),
    # MMA / UFC
    ("KXUFC",               "UFC Bot"),
    # NFL
    ("KXPROFOOT",           "NFL Bot"),
    ("KXSB",                "NFL Bot"),
    ("KXNFLGAME",           "NFL Bot"),
    ("KXNFL",               "NFL Bot"),
    # College Baseball
    ("KXCAABASE",           "College Baseball Bot"),
    # Climate / Weather
    ("KXHIGH",              "Climate Bot"),
    ("KXHIGHT",             "Climate Bot"),
    ("KXLOW",               "Climate Bot"),
    ("KXLOWT",              "Climate Bot"),
    ("KXRAIN",              "Climate Bot"),
    ("KXPRECIP",            "Climate Bot"),
    ("KXSNOW",              "Climate Bot"),
    ("KXHURR",              "Climate Bot"),
    ("KXGLB",               "Climate Bot"),
    # Economics
    ("CPID",                "Economics Bot"),
    ("FED",                 "Economics Bot"),
    ("GDP",                 "Economics Bot"),
    ("JOBS",                "Economics Bot"),
    ("RETAIL",              "Economics Bot"),
    # Culture & Music
    ("KXSPOT",              "Music Bot"),
    ("KXARTIST",            "Music Bot"),
    ("KXMUSIC",             "Music Bot"),
    # Commodities
    ("KXGOLD",              "Commodities Bot"),
    ("KXWTI",               "Commodities Bot"),
    ("KXBRENT",             "Commodities Bot"),
    ("KXNATGAS",            "Commodities Bot"),
    ("KXSILVER",            "Commodities Bot"),
    ("KXCOPPER",            "Commodities Bot"),
    ("KXAAAGAS",            "Commodities Bot"),
    # Crypto
    ("KXBTCD",              "Bitcoin Bot"),
    ("KXBTC",               "Bitcoin Bot"),
    ("KXETHD",              "Ethereum Bot"),
    ("KXETH",               "Ethereum Bot"),
    ("KXSOLD",              "Solana Bot"),
    ("KXSOL",               "Solana Bot"),
    ("KXXRP",               "XRP Bot"),
    ("KXDOGE",              "Dogecoin Bot"),
    ("KXBNB",               "BNB Bot"),
    ("KXHYPE",              "Hyperliquid Bot"),
    ("KXCRYPTO",            "Crypto Bot"),
]


app = func.FunctionApp()

# ---------------------------------------------------------------------------
# RSA-PSS Auth (same pattern as all other bots)
# ---------------------------------------------------------------------------

def _load_private_key():
    """Load RSA private key from env var, handling collapsed PEM strings."""
    pem_data = os.environ["KALSHI_PRIVATE_KEY_PEM"]
    pem_data = pem_data.replace("\\n", "\n").replace('"', "").strip()

    header = "-----BEGIN RSA PRIVATE KEY-----"
    footer = "-----END RSA PRIVATE KEY-----"

    if header in pem_data and "\n" not in pem_data[len(header):len(header) + 10]:
        content = pem_data.replace(header, "").replace(footer, "").strip()
        pem_data = f"{header}\n{content}\n{footer}"
    elif header not in pem_data and "MIIE" in pem_data:
        pem_data = f"{header}\n{pem_data}\n{footer}"

    return serialization.load_pem_private_key(pem_data.encode(), password=None)


def _sign_request(method: str, path: str) -> dict:
    """Build Kalshi v2 auth headers (RSA-PSS / SHA-256)."""
    clean_path = path.split("?")[0]
    timestamp_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    message = (timestamp_ms + method.upper() + clean_path).encode()

    private_key = _load_private_key()
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )

    key_id = os.environ["KALSHI_API_KEY_ID"].replace('"', "").strip()
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }


# Use a session for connection reuse across the single daily run
_session = requests.Session()


def _kalshi_get(path: str, params: dict | None = None) -> dict:
    """Authenticated GET to Kalshi v2 API."""
    url = KALSHI_BASE + path
    headers = _sign_request("GET", path)
    time.sleep(0.3)  # gentle rate-limit respect
    resp = _session.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

def fetch_balance() -> int:
    """Return the portfolio cash balance in cents."""
    data = _kalshi_get("/trade-api/v2/portfolio/balance")
    # Kalshi returns balance in cents as an integer
    return data.get("balance", 0)


def fetch_settlements(min_ts: datetime, max_ts: datetime) -> list[dict]:
    """
    Paginate through all settlements between min_ts and max_ts (inclusive).
    Kalshi's settlements endpoint accepts min_ts/max_ts as Unix timestamps (seconds).
    Returns a flat list of settlement dicts.
    Memory-efficient: processes one page at a time, never holds more than
    PAGE_LIMIT items in memory simultaneously before appending to the result list.
    """
    results: list[dict] = []
    cursor: str | None = None
    min_unix = int(min_ts.timestamp())
    max_unix = int(max_ts.timestamp())

    while True:
        params: dict = {
            "limit": PAGE_LIMIT,
            "min_ts": min_unix,
            "max_ts": max_unix,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            data = _kalshi_get("/trade-api/v2/portfolio/settlements", params=params)
        except requests.HTTPError as exc:
            logging.error("Settlement fetch failed: %s", exc)
            break

        page: list[dict] = data.get("settlements", [])
        results.extend(page)

        cursor = data.get("cursor")
        if not cursor or not page:
            break

    logging.info("Fetched %d total settlements between %s and %s", len(results), min_ts.date(), max_ts.date())
    return results


# ---------------------------------------------------------------------------
# Bot Classification Logic
# ---------------------------------------------------------------------------

def classify_bot(s: dict) -> str:
    """
    Map a Kalshi settlement record to a specific bot name.
    Uses ticker prefixes, share counts, and entry prices to distinguish variants.
    """
    ticker = s.get("ticker", s.get("market_ticker", "UNKNOWN")).upper()
    
    # 1. Special Case: Tennis Bot Variants
    # Champion vs Scattershot vs Late Momentum
    if any(ticker.startswith(p) for p in ["KXATP", "KXWTA", "KXITF"]):
        yes_shares = float(s.get("yes_count_fp", "0") or "0")
        no_shares  = float(s.get("no_count_fp",  "0") or "0")
        shares = yes_shares if yes_shares > 0 else no_shares
        
        # Calculate approximate entry price in cents
        cost_cents = round(float(s.get("yes_total_cost_dollars", "0") or "0") * 100)
        if cost_cents == 0:
            cost_cents = round(float(s.get("no_total_cost_dollars", "0") or "0") * 100)
            
        avg_price = (cost_cents / shares) if shares > 0 else 0
        
        if shares in [2.0, 4.0]:
            return "Tennis Champion Bot"
        elif shares == 1.0:
            # Scattershot uses entries at 50, 52, 54
            if 48 <= avg_price <= 56:
                return "Tennis Scattershot Bot"
            # Late Momentum uses entries 65-84
            if 60 <= avg_price <= 88:
                return "Tennis Late Momentum Bot"
            return "Tennis Bot (Other)"
        else:
            return "Tennis Bot (Mixed/Manual)"

    # 2. Standard Prefix Matching
    for prefix, bot_name in BOT_RULES:
        if ticker.startswith(prefix):
            return bot_name
            
    return "Other/Misc"


# ---------------------------------------------------------------------------
# P&L Aggregation
# ---------------------------------------------------------------------------

def _make_category_stats() -> dict:
    return {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "gross_pnl_cents": 0,
        "fees_cents": 0,
        "net_pnl_cents": 0,
    }


def aggregate_settlements(settlements: list[dict]) -> dict:
    """
    Aggregate settlements into overall + per-bot stats.
    """
    overall = _make_category_stats()
    by_bot: dict[str, dict] = {}

    for s in settlements:
        ticker = s.get("ticker", s.get("market_ticker", "UNKNOWN"))

        # -- Parse share counts (strings like '3.00') --
        yes_shares = float(s.get("yes_count_fp", "0") or "0")
        no_shares  = float(s.get("no_count_fp",  "0") or "0")

        # Skip records where the user had NO shares at settlement.
        if yes_shares == 0.0 and no_shares == 0.0:
            continue

        # -- Settlement value per YES share (cents): 100 if YES wins, 0 if NO wins --
        # NO shares are worth (100 - value) cents each at settlement.
        value_cents = int(s.get("value", 0))

        # -- Compute payouts --
        yes_payout = round(yes_shares * value_cents)
        no_payout  = round(no_shares  * (100 - value_cents))
        total_payout = yes_payout + no_payout

        # -- Cost: what was originally paid for these shares (dollars → cents) --
        yes_cost_cents = round(float(s.get("yes_total_cost_dollars", "0") or "0") * 100)
        no_cost_cents  = round(float(s.get("no_total_cost_dollars",  "0") or "0") * 100)
        cost_cents = yes_cost_cents + no_cost_cents

        # -- Fee: Kalshi's settlement fee (dollars → cents) --
        fee_cents = round(float(s.get("fee_cost", "0") or "0") * 100)

        # -- P&L --
        gross_pnl_cents = total_payout - cost_cents
        net_pnl_cents   = gross_pnl_cents - fee_cents

        is_win = net_pnl_cents > 0

        bot_name = classify_bot(s)
        if bot_name not in by_bot:
            by_bot[bot_name] = _make_category_stats()

        for bucket in (overall, by_bot[bot_name]):
            bucket["count"] += 1
            bucket["wins"]   += 1 if is_win else 0
            bucket["losses"] += 0 if is_win else 1
            bucket["gross_pnl_cents"] += gross_pnl_cents
            bucket["fees_cents"]      += fee_cents
            bucket["net_pnl_cents"]   += net_pnl_cents

    return {"overall": overall, "by_bot": by_bot}


# ---------------------------------------------------------------------------
# Email Formatting
# ---------------------------------------------------------------------------

def _fmt_dollars(cents: int) -> str:
    """Format cents as a signed dollar string, e.g. +$1.26 or -$0.42."""
    dollars = cents / 100.0
    sign = "+" if dollars >= 0 else "-"
    return f"{sign}${abs(dollars):.2f}"




def _win_pct(wins: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(wins / total * 100):.1f}%"


def build_email_body(
    balance_cents: int,
    yesterday_date: str,
    today_date: str,
    today_time_et: str,
    yesterday: dict | None,
    today: dict,
    alltime: dict | None,
    last3days: dict | None = None,
    is_light: bool = False,
) -> str:
    """
    Build the plaintext email.
    `yesterday`, `today`, and `alltime` are dicts with keys: overall, by_bot.
    If `is_light` is True, omit Yesterday and All-Time sections.
    """
    report_stats = {
        "yesterday": yesterday,
        "today": today,
        "alltime": alltime,
        "last3days": last3days
    }
    # DEBUG
    logging.info(f"DEBUG: last3days keys: {list(last3days.keys()) if last3days else 'None'}")
    t = today["overall"]

    lines = []

    # --- CURRENT STATUS ---
    lines.append("CURRENT STATUS:")
    lines.append(f"  Cash Balance: ${balance_cents / 100:.2f}")
    if is_light:
        lines.append(f"  Update Time: {today_time_et} ET")
    lines.append("")

    # --- TODAY SO FAR ---
    lines.append("-" * 40)
    lines.append(f"TODAY SO FAR ({today_date} as of {today_time_et} ET):")
    lines.append("-" * 40)

    t_total = t["count"]
    if t_total == 0:
        lines.append("  No settlements yet today.")
    else:
        lines.append(
            f"  Positions Settled: {t_total} ({t['wins']}W / {t['losses']}L)"
        )
        lines.append(
            f"  Gross P&L: {_fmt_dollars(t['gross_pnl_cents'])} | "
            f"Fees: {_fmt_dollars(t['fees_cents'])}"
        )
        lines.append(
            f"  >>> NET P&L: {_fmt_dollars(t['net_pnl_cents'])} <<<"
        )
        lines.append("")
        lines.append("  By Bot:")
        t_bots = sorted(
            today["by_bot"].items(),
            key=lambda kv: kv[1]["net_pnl_cents"],
            reverse=True,
        )
        for bot_name, stats in t_bots:
            lines.append(
                f"    {bot_name} {stats['count']} ({stats['wins']}W / {stats['losses']}L): "
                f"{_fmt_dollars(stats['net_pnl_cents'])}"
            )

    if not is_light and yesterday:
        # --- YESTERDAY ---
        lines.append("")
        lines.append("-" * 40)
        lines.append(f"YESTERDAY ({yesterday_date}):")
        lines.append("-" * 40)

        y = yesterday["overall"]
        y_total = y["count"]
        lines.append(
            f"  Positions Settled: {y_total} ({y['wins']}W / {y['losses']}L)"
        )
        lines.append(
            f"  Gross P&L: {_fmt_dollars(y['gross_pnl_cents'])} | "
            f"Fees: {_fmt_dollars(y['fees_cents'])}"
        )
        lines.append(
            f"  >>> NET P&L: {_fmt_dollars(y['net_pnl_cents'])} <<<"
        )
        lines.append("")
        lines.append("  By Bot:")

        y_bots = sorted(
            yesterday["by_bot"].items(),
            key=lambda kv: kv[1]["net_pnl_cents"],
            reverse=True,
        )
        if y_bots:
            for bot_name, stats in y_bots:
                lines.append(
                    f"    {bot_name} {stats['count']} ({stats['wins']}W / {stats['losses']}L): "
                    f"{_fmt_dollars(stats['net_pnl_cents'])}"
                )
        else:
            lines.append("    No settlements yesterday.")

    if not is_light and report_stats.get("last3days"):
        l3 = report_stats["last3days"]
        l3_total = l3["overall"]["count"]
        lines.append("")
        lines.append("-" * 40)
        lines.append("LAST 3 DAYS SUMMARY:")
        lines.append("-" * 40)
        lines.append(f"  Positions Settled: {l3_total} ({l3['overall']['wins']}W / {l3['overall']['losses']}L)")
        lines.append(f"  Gross P&L: {_fmt_dollars(l3['overall']['gross_pnl_cents'])} | Fees: {_fmt_dollars(l3['overall']['fees_cents'])}")
        lines.append(f"  >>> NET P&L: {_fmt_dollars(l3['overall']['net_pnl_cents'])} <<<")
        lines.append("")
        lines.append("  By Bot (Last 3 Days):")
        l3_bots = sorted(l3["by_bot"].items(), key=lambda kv: kv[1]["net_pnl_cents"], reverse=True)
        for bot_name, s_stats in l3_bots:
            lines.append(f"    {bot_name} {s_stats['count']} ({s_stats['wins']}W / {s_stats['losses']}L): {_fmt_dollars(s_stats['net_pnl_cents'])}")

    if not is_light and alltime:
        # --- ALL-TIME ---
        lines.append("")
        lines.append("-" * 40)
        lines.append(f"ALL-TIME (Last {ALL_TIME_DAYS} Days):")
        lines.append("-" * 40)

        a = alltime["overall"]
        a_total = a["count"]
        lines.append(
            f"  Total Settled: {a_total} ({a['wins']}W / {a['losses']}L"
            f" = {_win_pct(a['wins'], a_total)})"
        )
        lines.append(
            f"  Gross P&L: {_fmt_dollars(a['gross_pnl_cents'])} | "
            f"Fees: {_fmt_dollars(a['fees_cents'])}"
        )
        lines.append(
            f"  >>> NET P&L: {_fmt_dollars(a['net_pnl_cents'])} <<<"
        )
        lines.append("")
        lines.append("  By Bot:")

        a_bots = sorted(
            alltime["by_bot"].items(),
            key=lambda kv: kv[1]["net_pnl_cents"],
            reverse=True,
        )
        if a_bots:
            for bot_name, stats in a_bots:
                lines.append(
                    f"    {bot_name} {stats['count']} ({stats['wins']}W / {stats['losses']}L): "
                    f"{_fmt_dollars(stats['net_pnl_cents'])}"
                )
        else:
            lines.append("    No settlements in the last 180 days.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email Delivery via Azure Logic Apps
# ---------------------------------------------------------------------------

def send_via_logic_app(subject: str, body: str) -> None:
    """POST the email to the Azure Logic App HTTP trigger.
    Gmail connector renders body as HTML, so we wrap in <pre> to preserve
    all line breaks and monospace formatting.
    """
    trigger_url = os.environ["LOGIC_APP_TRIGGER_URL"]
    # Wrap in <pre> so Gmail preserves newlines — without this everything
    # collapses into one line of text.
    html_body = f'<pre style="font-family:monospace;font-size:13px;line-height:1.5">{body}</pre>'
    payload = {"subject": subject, "body": html_body}

    resp = _session.post(trigger_url, json=payload, timeout=30)
    resp.raise_for_status()
    logging.info("Logic App triggered successfully — status %d", resp.status_code)


# Timer Trigger — Selective (9 AM, 12 PM, 3 PM, 9 PM ET)
# Full Report: 9:00 AM ET
# Status Updates: 12:00 PM, 3:00 PM, 9:00 PM ET

@app.timer_trigger(
    # Fires every hour at :00. Internal logic filters to the 9 AM - 11 PM ET window.
    schedule="0 0 * * * *",
    arg_name="timer",
    run_on_startup=False,
)
def auditor_bot(timer: func.TimerRequest) -> None:
    """Main entry point — runs every hour during the day."""
    run_start = datetime.now(timezone.utc)
    logging.info("=" * 60)
    logging.info("AUDITOR BOT STARTED at %s", run_start.isoformat())
    logging.info("=" * 60)

    if timer.past_due:
        logging.warning("Timer is past due — running anyway")

    try:
        # --- Date Setup ---
        # Use proper America/New_York timezone — handles EST/EDT automatically.
        ET = ZoneInfo("America/New_York")
        now_et = run_start.astimezone(ET)
        
        # 9:00 AM ET is our designated "Full Report" run.
        force_full = os.environ.get("FORCE_FULL_REPORT", "").lower() == "true"
        is_full_report = (now_et.hour == 9 or force_full)

        # Filter out any runs that aren't our intended targets.
        is_status_update = (now_et.hour in [12, 15, 21])
        
        force_run = os.environ.get("FORCE_AUDIT", "").lower() == "true"

        if not (is_full_report or is_status_update or force_run):
            logging.info("Skipping unscheduled run at %02d:%02d ET", now_et.hour, now_et.minute)
            return

        report_type = "FULL" if is_full_report else "LIGHT"
        logging.info("Current Time (ET): %s | Report Type: %s", now_et.isoformat(), report_type)

        yesterday_et = now_et.date() - timedelta(days=1)
        yesterday_date_str = yesterday_et.strftime("%B %d, %Y")

        # Convert ET midnight boundaries to UTC for API params
        yesterday_start_utc = datetime(
            yesterday_et.year, yesterday_et.month, yesterday_et.day,
            0, 0, 0, tzinfo=ET
        ).astimezone(timezone.utc)
        yesterday_end_utc = yesterday_start_utc + timedelta(days=1)

        # --- 1. Fetch Balance ---
        logging.info("Fetching portfolio balance...")
        balance_cents = fetch_balance()
        logging.info("Balance: %d cents ($%.2f)", balance_cents, balance_cents / 100)

        # Today-so-far window: midnight ET today → now
        today_start_utc = yesterday_end_utc  # same boundary
        today_date_str = now_et.strftime("%B %d, %Y")
        today_time_str = now_et.strftime("%I:%M %p").lstrip("0")  # e.g. "11:05 AM"

        # --- 2. Fetch Today So Far (Always) ---
        logging.info("Fetching today's settlements so far...")
        today_settlements = fetch_settlements(today_start_utc, run_start)
        today_stats = aggregate_settlements(today_settlements)
        t = today_stats["overall"]

        # --- 3. Fetch Yesterday & All-Time (Only for Full Report) ---
        yesterday_stats = None
        alltime_stats   = None
        
        if is_full_report:
            logging.info("Fetching yesterday's settlements...")
            yesterday_settlements = fetch_settlements(yesterday_start_utc, yesterday_end_utc)
            yesterday_stats = aggregate_settlements(yesterday_settlements)

            logging.info("Fetching all-time settlements (180 days)...")
            today_midnight_et = datetime(now_et.year, now_et.month, now_et.day, 0, 0, 0, tzinfo=ET)
            alltime_start_utc = (today_midnight_et - timedelta(days=ALL_TIME_DAYS)).astimezone(timezone.utc)
            alltime_settlements = fetch_settlements(alltime_start_utc, run_start)
            alltime_stats = aggregate_settlements(alltime_settlements)

            logging.info("Fetching last 3 days settlements...")
            last3days_start_utc = (today_midnight_et - timedelta(days=3)).astimezone(timezone.utc)
            last3days_settlements = fetch_settlements(last3days_start_utc, run_start)
            last3days_stats = aggregate_settlements(last3days_settlements)
            
            y = yesterday_stats["overall"]
            stats_bundle = {
                "today": today_stats,
                "yesterday": yesterday_stats,
                "last3days": last3days_stats,
                "alltime": alltime_stats
            }
            subject = (
                f"DJQ Daily Report — {yesterday_date_str} | "
                f"Net: {'+' if y['net_pnl_cents'] >= 0 else ''}"
                f"${y['net_pnl_cents'] / 100:.2f}"
            )
        else:
            subject = (
                f"DJQ Status Update — {today_time_str} ET | "
                f"Today: {'+' if t['net_pnl_cents'] >= 0 else ''}"
                f"${t['net_pnl_cents'] / 100:.2f}"
            )

        # --- 4. Build Email ---
        body = build_email_body(
            balance_cents=balance_cents,
            yesterday_date=yesterday_date_str,
            today_date=today_date_str,
            today_time_et=today_time_str,
            yesterday=yesterday_stats,
            today=today_stats,
            alltime=alltime_stats,
            last3days=last3days_stats if is_full_report else None,
            is_light=(not is_full_report)
        )

        logging.info("Email subject: %s", subject)
        
        # --- 5. Send ---
        send_via_logic_app(subject, body)

        logging.info("AUDITOR BOT COMPLETED in %.1fs", (datetime.now(timezone.utc) - run_start).total_seconds())

    except Exception:
        logging.exception("AUDITOR BOT FAILED")
        raise
