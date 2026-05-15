"""
mlb_k_ladder_azure.py  →  function_app.py
Kalshi MLB Strikeout K-Ladder Bot — Azure Function (Python v2)
Function App: StrikeoutBot

Strategy
────────
  9:00 AM ET  → Daily_Bid_Sweep
                Discover confirmed starters, compute 70 % confidence ladder
                via Poisson model (K/9 + Whiff%), place resting 1-share
                Maker Limit Buy orders for every tier 3+ up to Anchor.

  Every 3 min → Monitor_and_Flip
                Scan portfolio fills.  Any filled buy → immediately place
                1-share Limit Sell @ $0.99.  Any filled sell → close record.

  At game time → Cleanup_Unfilled_Bids
                Cancel every open buy order whose game has started.

Override        If it is past 9 AM but today's sweep was never run,
                run Daily_Bid_Sweep immediately regardless of the clock.

Env vars required
─────────────────
  KALSHI_API_KEY_ID               RSA key identifier
  KALSHI_PRIVATE_KEY_PEM          RSA private key (PEM, may use \\n escapes)
  KALSHI_MEMBER_ID                Kalshi member UUID
  AZURE_STORAGE_CONNECTION_STRING Azure Storage for state table
"""

from __future__ import annotations

import io
import os
import csv
import json
import math
import time
import base64
import logging
from datetime import datetime, timezone, timedelta

import requests
import azure.functions as func
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from azure.data.tables import TableServiceClient, UpdateMode

# ─────────────────────────────────────────────────────────────────────────────
# Constants & Configuration
# ─────────────────────────────────────────────────────────────────────────────

KALSHI_BASE     = "https://api.elections.kalshi.com"
MLB_API_BASE    = "https://statsapi.mlb.com/api/v1"
SAVANT_BASE     = "https://baseballsavant.mlb.com"

CONFIDENCE_FLOOR  = 0.80    # Elevated from 0.77 to further improve win rate
MAX_ASK_CENTS     = 85      # Don't pay more than 85c for any share
MIN_ASK_CENTS     = 10
DAILY_SHARE_LIMIT = 25      # Safety cap on total new shares per day
EXPECTED_INNINGS  = 5.5
LEAGUE_AVG_WHIFF  = 0.25
LEAGUE_AVG_TEAM_K = 0.225   # Roughly 22.5% K-rate average for batters
ET_OFFSET         = -4      # Eastern Time vs UTC
CURRENT_SEASON    = 2026
PRIOR_SEASON      = 2025
MIN_TIER          = 3      # Never bid below 3 K tier
MAX_TIER          = 6      # "Moonshot Filter": Don't bid above 6 Ks

TABLE_NAME = "StrikeoutBotTracker"

app = func.FunctionApp()


# ─────────────────────────────────────────────────────────────────────────────
# RSA-PSS Auth  (Kalshi API V2)
# ─────────────────────────────────────────────────────────────────────────────

def _load_private_key():
    """Load RSA private key from env var, using proven logic from investigate_positions.py."""
    pem_data = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    if not pem_data:
        raise Exception("Missing KALSHI_PRIVATE_KEY_PEM in environment")

    # Clean up escaping and spaces
    pem_data = pem_data.replace("\\n", "\n").replace("\\\\n", "\n").replace('"', "").strip()
    
    # If it's a one-liner without headers, wrap it. 
    # But if it has headers, just use it.
    if "-----BEGIN" not in pem_data:
        pem_data = f"-----BEGIN RSA PRIVATE KEY-----\n{pem_data}\n-----END RSA PRIVATE KEY-----"

    try:
        return serialization.load_pem_private_key(pem_data.encode(), password=None)
    except Exception as exc:
        logging.error("[Auth] PEM Load Failed: %s", exc)
        raise


def sign_request(method: str, path: str) -> dict:
    """Return Kalshi RSA-PSS auth headers for a request."""
    clean_path = path.split("?")[0]
    ts_ms = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    msg   = (ts_ms + method.upper() + clean_path).encode()
    key   = _load_private_key()
    sig   = key.sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    key_id = os.environ["KALSHI_API_KEY_ID"].replace('"', "").strip()
    return {
        "KALSHI-ACCESS-KEY":       key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "Content-Type":            "application/json",
    }


def kalshi_get(path: str, params: dict | None = None) -> dict:
    headers = sign_request("GET", path)
    time.sleep(0.4)
    resp = requests.get(KALSHI_BASE + path, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def kalshi_post(path: str, body: dict) -> dict:
    headers = sign_request("POST", path)
    time.sleep(0.4)
    resp = requests.post(KALSHI_BASE + path, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def kalshi_delete(path: str) -> bool:
    headers = sign_request("DELETE", path)
    time.sleep(0.4)
    resp = requests.delete(KALSHI_BASE + path, headers=headers, timeout=30)
    if resp.status_code in (200, 204):
        return True
    logging.warning("[Kalshi] DELETE %s → %s", path, resp.status_code)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Kalshi API V2 Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_kalshi_client():
    """Fallback: return a simple wrapper for existing helpers."""
    class SimpleClient:
        def get_positions(self): return kalshi_get("/trade-api/v2/portfolio/positions")
        def get_market(self, ticker): return kalshi_get(f"/trade-api/v2/markets/{ticker}")
        def create_order(self, **kwargs): return kalshi_post("/trade-api/v2/portfolio/orders", kwargs)
    return SimpleClient()


def get_market_pulse(ticker: str) -> dict:
    """Fetch the absolute latest orderbook for a specific ticker (Deep Pulse)."""
    try:
        data = kalshi_get(f"/trade-api/v2/markets/{ticker}")
        return data.get("market", {})
    except Exception as exc:
        logging.error("[Pulse] Failed for %s: %s", ticker, exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Azure Table Storage — State Manager
# ─────────────────────────────────────────────────────────────────────────────

def _table_client():
    conn = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    svc  = TableServiceClient.from_connection_string(conn)
    svc.create_table_if_not_exists(TABLE_NAME)
    return svc.get_table_client(TABLE_NAME)


def _today_et() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=ET_OFFSET)).strftime("%Y-%m-%d")


def is_sweep_done_today() -> bool:
    today = _today_et()
    try:
        tc  = _table_client()
        ent = tc.get_entity(partition_key="SWEEP", row_key=today)
        # Check for either 'sweep_done' or a very recent 'in_progress' timestamp (locked for 10 mins)
        if ent.get("sweep_done", False):
            return True
        
        in_progress_str = ent.get("in_progress_at")
        if in_progress_str:
            in_progress_dt = datetime.fromisoformat(in_progress_str)
            # If it's been less than 10 minutes since it started, consider it locked
            if (datetime.now(timezone.utc) - in_progress_dt).total_seconds() < 600:
                logging.warning("[Lock] Sweep is currently IN PROGRESS (started at %s).", in_progress_str)
                return True
        return False
    except Exception:
        return False


def start_sweep_lock() -> None:
    today = _today_et()
    tc    = _table_client()
    tc.upsert_entity(
        {
            "PartitionKey":   "SWEEP",
            "RowKey":         today,
            "sweep_done":     False,
            "in_progress_at": datetime.now(timezone.utc).isoformat(),
        },
        mode=UpdateMode.REPLACE,
    )
    logging.info("[Lock] Sweep lock initialized for %s", today)


def mark_sweep_done(game_records: list) -> None:
    today = _today_et()
    tc    = _table_client()
    tc.upsert_entity(
        {
            "PartitionKey": "SWEEP",
            "RowKey":       today,
            "sweep_done":   True,
            "game_records": json.dumps(game_records),
            "swept_at":     datetime.now(timezone.utc).isoformat(),
        },
        mode=UpdateMode.REPLACE,
    )
    logging.info("[State] Sweep marked done for %s", today)


def save_order(order_id: str, ticker: str, pitcher_id: str,
               tier: int, buy_price: int, game_time_utc: str) -> None:
    tc = _table_client()
    tc.upsert_entity(
        {
            "PartitionKey":    "ORDER",
            "RowKey":          order_id,
            "ticker":          ticker,
            "pitcher_id":      pitcher_id,
            "tier":            tier,
            "buy_price_cents": buy_price,
            "status":          "buy_pending",
            "game_time_utc":   game_time_utc,
            "placed_at":       datetime.now(timezone.utc).isoformat(),
            "sell_order_id":   "",
        },
        mode=UpdateMode.REPLACE,
    )


def update_order(order_id: str, **kwargs) -> None:
    tc = _table_client()
    tc.upsert_entity(
        {"PartitionKey": "ORDER", "RowKey": order_id, **kwargs},
        mode=UpdateMode.MERGE,
    )


def get_open_orders() -> list[dict]:
    tc = _table_client()
    return list(tc.query_entities(
        "PartitionKey eq 'ORDER' and (status eq 'buy_pending' or status eq 'sell_pending')"
    ))


def get_stale_buy_orders() -> list[dict]:
    """
    Returns buy_pending orders whose scheduled game_time_utc is now in the past.
    Uses string comparison — ISO-8601 sorts lexicographically.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tc      = _table_client()
    return list(tc.query_entities(
        f"PartitionKey eq 'ORDER' and status eq 'buy_pending' and game_time_utc le '{now_iso}'"
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Poisson Confidence Calculator  (no external deps — pure Python)
# ─────────────────────────────────────────────────────────────────────────────

def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_cdf(n: int, lam: float) -> float:
    """P(X ≤ n) for Poisson(lam)."""
    return sum(_poisson_pmf(k, lam) for k in range(n + 1))


def prob_k_or_more(n: int, k9: float, whiff_pct: float, opp_k_factor: float = 1.0) -> float:
    """
    P(strikeouts ≥ n) for a starter.

    λ  = K/9 × (expected_innings / 9)             — raw expected Ks
    λ' = λ × clamp(whiff_pct / league_avg, 0.7–1.4) — whiff-adjusted
    λ'' = λ' × opp_k_factor                      — opponent-aware scaling

    Returns P(X ≥ n) = 1 − CDF(n−1).
    """
    raw_lam      = k9 * (EXPECTED_INNINGS / 9.0)
    whiff_factor = whiff_pct / LEAGUE_AVG_WHIFF if whiff_pct > 0 else 1.0
    whiff_factor = max(0.70, min(1.40, whiff_factor))
    lam_adj      = raw_lam * whiff_factor * opp_k_factor
    return 1.0 - _poisson_cdf(n - 1, lam_adj)


# ─────────────────────────────────────────────────────────────────────────────
# MLB Stats API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_todays_starters() -> list[dict]:
    """
    Returns confirmed starters for today's MLB schedule.
    Each entry: {pitcher_name, mlb_id, team, opponent, game_time_utc, game_pk}
    Only includes games with a probablePitcher announced (2026 participation rule).
    """
    today_et = (datetime.now(timezone.utc) + timedelta(hours=ET_OFFSET)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            f"{MLB_API_BASE}/schedule",
            params={
                "sportId": 1,
                "date":    today_et,
                "hydrate": "probablePitcher,lineupConfirmed,team",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.error("[MLB] Schedule fetch failed: %s", exc)
        return []

    starters = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            # 1. Status Check
            state = game.get("status", {}).get("abstractGameState", "")
            if state == "Final":
                continue

            # 2. Date Safety Check: Only process games that start 'today' in ET.
            # Convert game UTC time to ET and compare date string.
            game_time_str = game.get("gameDate", "")
            if game_time_str:
                game_utc = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                game_et  = game_utc.astimezone(timezone(timedelta(hours=ET_OFFSET)))
                if game_et.strftime("%Y-%m-%d") != today_et:
                    logging.info("[MLB] Skipping game %s — not today (%s vs %s)", game_pk, game_et.strftime("%Y-%m-%d"), today_et)
                    continue
            game_time_utc = game.get("gameDate", "")
            game_pk       = game.get("gamePk")

            for side in ("home", "away"):
                team_data   = game.get("teams", {}).get(side, {})
                probable    = team_data.get("probablePitcher")
                if not probable:
                    continue  # No confirmed starter — skip (participation rule)

                opp_side = "away" if side == "home" else "home"
                opp_abbr = (
                    game.get("teams", {})
                    .get(opp_side, {})
                    .get("team", {})
                    .get("abbreviation", "UNK")
                )
                starters.append({
                    "pitcher_name":  probable.get("fullName", "Unknown"),
                    "mlb_id":        probable.get("id"),
                    "team":          team_data.get("team", {}).get("abbreviation", "UNK"),
                    "opponent":      opp_abbr,
                    "side":          side,   # "away" or "home"
                    "game_time_utc": game_time_utc,
                    "game_pk":       game_pk,
                })

    logging.info("[MLB] %d confirmed starters for %s", len(starters), today_et)
    return starters


def fetch_team_k_factors() -> dict:
    """
    Fetches team hitting K% stats and returns a map of {Abbreviation: Factor}.
    Factor = (Team K% / League Average K%).
    """
    factors = {}
    try:
        # Try current season first
        resp = requests.get(f"{MLB_API_BASE}/teams/stats", params={
            "stats": "season", "group": "hitting", "season": CURRENT_SEASON, "sportId": 1
        }, timeout=15)
        data = resp.json()
        stats_list = data.get("stats", [])
        splits = stats_list[0].get("splits", []) if stats_list else []
        
        # If early season, blend with prior season or just use prior
        if len(splits) < 30: # Missing teams or too early
             resp = requests.get(f"{MLB_API_BASE}/teams/stats", params={
                 "stats": "season", "group": "hitting", "season": PRIOR_SEASON, "sportId": 1
             }, timeout=15)
             data = resp.json()
             stats_list = data.get("stats", [])
             splits = stats_list[0].get("splits", []) if stats_list else []

        for s in splits:
            abbr = s.get("team", {}).get("abbreviation")
            st = s.get("stat", {})
            k = st.get("strikeOuts", 0)
            pa = st.get("plateAppearances", 0)
            if pa > 100 and abbr: # Minimum sample size
                k_rate = k / pa
                factors[abbr] = k_rate / LEAGUE_AVG_TEAM_K
                
    except Exception as exc:
        logging.error("[MLB] Team stats fetch failed: %s", exc)
    
    return factors


def fetch_pitcher_k9(mlb_id: int) -> float | None:
    """K/9 from MLB Stats API for the current season."""
    try:
        resp = requests.get(
            f"{MLB_API_BASE}/people/{mlb_id}/stats",
            params={"stats": "season", "group": "pitching",
                    "season": CURRENT_SEASON, "sportId": 1},
            timeout=15,
        )
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        if splits:
            val = splits[0].get("stat", {}).get("strikeoutsPer9Inn")
            return float(val) if val is not None else None
    except Exception as exc:
        logging.warning("[MLB] K/9 failed for mlb_id=%s: %s", mlb_id, exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Baseball Savant — Whiff Rate  (downloaded once, cached in-process)
# ─────────────────────────────────────────────────────────────────────────────

_savant_cache: dict[str, float] = {}   # mlb_id_str → whiff_pct (0–1)

# Ordered list of Savant CSV endpoints to try. We stop at first success.
_SAVANT_URLS = [
    # Primary: arsenal-stats leaderboard — aggregated per pitcher, has whiff_percent
    (
        f"https://baseballsavant.mlb.com/leaderboards/arsenal-stats"
        f"?type=pitcher&year={CURRENT_SEASON}&min=100&csv=true",
        "pitcher_id",      # mlb id column
        "whiff_percent",   # whiff column
    ),
    # Fallback: statcast leaderboard grouped by name (aggregated)
    (
        f"https://baseballsavant.mlb.com/statcast_search/csv"
        f"?hfSea={CURRENT_SEASON}%7C&player_type=pitcher"
        f"&min_pitches=100&group_by=name&hfGT=R%7C",
        "pitcher",         # pitcher mlb_id column in this format
        "whiff_percent",
    ),
]

# Full browser-like headers — required to avoid Savant's bot check
_SAVANT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://baseballsavant.mlb.com/leaderboard",
    "Connection":      "keep-alive",
}


def _parse_savant_csv(text: str, pid_col: str, whiff_col: str) -> dict[str, float]:
    """Parse a Savant CSV and return {mlb_id_str: whiff_pct}."""
    result: dict[str, float] = {}
    reader = csv.DictReader(io.StringIO(text))

    # Log actual column names once so they're visible in Azure Monitor
    logging.info("[Savant] CSV columns: %s", reader.fieldnames)

    for row in reader:
        # Try the known column first, then common aliases
        pid = (
            row.get(pid_col)
            or row.get("player_id")
            or row.get("pitcher")
            or row.get("mlb_id", "")
        )
        raw = (
            row.get(whiff_col)
            or row.get("whiff_percent")
            or row.get("whiff_pct")
            or row.get("whiff%")
            or row.get("k_percent", "")
        )
        if not pid or not raw:
            continue
        try:
            pct = float(str(raw).replace("%", "").strip())
            # Savant can return 0–100 or 0–1 depending on endpoint
            result[str(pid)] = pct / 100.0 if pct > 1.0 else pct
        except ValueError:
            pass
    return result


def fetch_savant_whiff_map() -> dict[str, float]:
    """
    Download pitcher whiff/K-rate from Baseball Savant using a browser-like
    session. Tries multiple endpoints in order; returns {} on total failure
    (caller falls back to LEAGUE_AVG_WHIFF per pitcher).
    Column names are logged to Azure Monitor on every fresh download.
    """
    global _savant_cache
    if _savant_cache:
        return _savant_cache

    session = requests.Session()
    session.headers.update(_SAVANT_HEADERS)

    for url, pid_col, whiff_col in _SAVANT_URLS:
        try:
            resp = session.get(url, timeout=35)
            resp.raise_for_status()

            # Savant returns HTML when the bot check triggers
            if resp.text.strip().startswith("<!"):
                logging.warning("[Savant] Got HTML from %s — bot check triggered. Trying next URL.", url)
                continue

            result = _parse_savant_csv(resp.text, pid_col, whiff_col)
            if result:
                logging.info("[Savant] ✅ Loaded whiff/K%% for %d pitchers via %s", len(result), url)
                _savant_cache = result
                return result
            else:
                logging.warning("[Savant] URL returned 0 rows: %s", url)

        except Exception as exc:
            logging.warning("[Savant] URL failed (%s): %s", url, exc)

    logging.warning("[Savant] All endpoints failed. Bot will use LEAGUE_AVG_WHIFF (%.3f) for all pitchers.", LEAGUE_AVG_WHIFF)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Kalshi Market Discovery
# ─────────────────────────────────────────────────────────────────────────────

def fetch_pitcher_markets(pitcher_token: str) -> list[tuple[int, dict]]:
    """
    Fetch all open KXMLBKS markets matching pitcher_token.
    Returns list of (tier_int, market_dict) sorted ascending by tier.

    Ticker format: KXMLBKS-26MAR261315PITNYM-PITPSKENES30-7
    Tier is the final dash-segment (integer).
    Only includes tiers >= MIN_TIER.
    """
    token_upper = pitcher_token.upper()
    found: list[tuple[int, dict]] = []
    cursor = None

    for _ in range(10):     # paginate up to 2 000 markets
        params: dict = {"series_ticker": SERIES_TICKER, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        try:
            data    = kalshi_get("/trade-api/v2/markets", params=params)
            markets = data.get("markets", [])
        except Exception as exc:
            logging.error("[Kalshi] Market page fetch failed: %s", exc)
            break

        for m in markets:
            ticker = m.get("ticker", "")
            if token_upper not in ticker.upper():
                continue
            # Parse tier from last segment
            try:
                tier = int(ticker.rsplit("-", 1)[-1])
            except (ValueError, IndexError):
                continue
            if tier >= MIN_TIER:
                found.append((tier, m))

        cursor = data.get("cursor")
        if not cursor or not markets:
            break

    found.sort(key=lambda x: x[0])
    return found


def build_event_ticker(starter: dict) -> str:
    """
    Build the full Kalshi event ticker for a game.
    Format: KXMLBKS-26MAR261315PITNYM
      26MAR26  = date in ET
      1315     = game start time in ET (24h)
      PITNYM   = away team + home team (uppercase)
    """
    dt_utc = datetime.fromisoformat(starter["game_time_utc"].replace("Z", "+00:00"))
    dt_et  = dt_utc + timedelta(hours=ET_OFFSET)
    month_map = {
        1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
    }
    date_str = f"{dt_et.strftime('%y')}{month_map.get(dt_et.month, 'UNK')}{dt_et.strftime('%d')}"
    time_str = dt_et.strftime("%H%M")

    team     = starter["team"].upper()
    opponent = starter["opponent"].upper()
    if starter.get("side", "away") == "away":
        teams = team + opponent       # away first
    else:
        teams = opponent + team       # opponent is the away team

    return f"KXMLBKS-{date_str}{time_str}{teams}"


def fetch_event_markets(event_ticker: str) -> list[tuple[int, dict]]:
    """
    Fetch all open YES/NO contracts under a specific KXMLBKS game event.
    Uses the event_ticker API param (more precise than series search).
    Returns list of (strikeout_threshold, market_dict) sorted ascending.

    Threshold is sourced from:
      1. floor_strike field (preferred — Kalshi sets this for threshold markets)
      2. Numeric suffix of ticker (fallback)
    """
    found: list[tuple[int, dict]] = []
    try:
        data    = kalshi_get("/trade-api/v2/markets",
                             params={"event_ticker": event_ticker,
                                     "status": "open", "limit": 100})
        markets = data.get("markets", [])
        logging.info("[Kalshi] Event %s → %d contracts", event_ticker, len(markets))

        for m in markets:
            threshold: int | None = None

            # Primary: floor_strike (e.g. 7.0 → 7)
            fs = m.get("floor_strike")
            if fs is not None:
                try:
                    threshold = int(float(fs))
                except (ValueError, TypeError):
                    pass

            # Fallback: numeric last segment of ticker
            if threshold is None:
                try:
                    threshold = int(m.get("ticker", "").rsplit("-", 1)[-1])
                except (ValueError, IndexError):
                    pass

            if threshold is not None and threshold >= MIN_TIER:
                found.append((threshold, m))
                logging.info("[Kalshi] Contract: %s tier=%d ask=%s",
                             m.get("ticker"), threshold, m.get("yes_ask"))

    except Exception as exc:
        logging.error("[Kalshi] Event fetch failed for %s: %s", event_ticker, exc)

    found.sort(key=lambda x: x[0])
    return found

def get_current_portfolio_tickers() -> set[str]:
    """
    Returns a set of all tickers currently in the portfolio as active positions
    OR in the order book as open buy orders.
    """
    all_tickers = set()
    try:
        # 1. Active Positions (Handle both direct list and dict-wrapped)
        resp = kalshi_get("/trade-api/v2/portfolio/positions")
        pos_list = resp if isinstance(resp, list) else resp.get("market_positions", [])
        for p in pos_list:
            if float(p.get("position_fp", 0)) != 0:
                all_tickers.add(p.get("ticker", ""))

        # 2. Open Buy Orders (Handle both direct list and dict-wrapped)
        resp = kalshi_get("/trade-api/v2/portfolio/orders", params={"status": "resting"})
        ord_list = resp if isinstance(resp, list) else resp.get("orders", [])
        for o in ord_list:
            if o.get("action") == "buy":
                all_tickers.add(o.get("ticker", ""))

        logging.info("[Safe] Portfolio check: %d active tickers found.", len(all_tickers))
    except Exception as exc:
        logging.error("[Safe] Portfolio check failed: %s. Proceeding with caution.", exc)
    
    return all_tickers

def place_limit_buy(ticker: str, price_cents: int) -> str | None:
    """Place 1-share resting Maker Limit Buy. Returns order_id or None."""
    body = {
        "ticker":           ticker,
        "action":           "buy",
        "side":             "yes",
        "type":             "limit",
        "count":            1,
        "yes_price":        price_cents,
        "client_order_id":  f"11-BUY-{ticker[-12:]}-{int(time.time())}",
    }
    try:
        resp = kalshi_post("/trade-api/v2/portfolio/orders", body)
        oid  = str(resp.get("order", {}).get("order_id", ""))
        if oid:
            logging.info("[Buy] %s @ %d¢ → order_id=%s", ticker, price_cents, oid)
        return oid or None
    except requests.HTTPError as exc:
        logging.error("[Buy] Failed %s @ %d¢: %s", ticker, price_cents, exc)
        return None


def place_limit_sell(ticker: str) -> str | None:
    """Place 1-share Limit Sell @ $0.99. Returns order_id or None."""
    body = {
        "ticker":           ticker,
        "action":           "sell",
        "side":             "yes",
        "type":             "limit",
        "count":            1,
        "yes_price":        SELL_PRICE_CENTS,
        "client_order_id":  f"11-SELL-{ticker[-12:]}-{int(time.time())}",
    }
    try:
        resp = kalshi_post("/trade-api/v2/portfolio/orders", body)
        oid  = str(resp.get("order", {}).get("order_id", ""))
        if oid:
            logging.info("[Sell] %s @ 99¢ → order_id=%s", ticker, oid)
        return oid or None
    except requests.HTTPError as exc:
        logging.error("[Sell] Failed %s: %s", ticker, exc)
        return None


def cancel_order(order_id: str) -> bool:
    ok = kalshi_delete(f"/trade-api/v2/portfolio/orders/{order_id}")
    if ok:
        logging.info("[Cancel] order_id=%s cancelled", order_id)
    return ok


def cancel_all_orders() -> None:
    """DEBUG: Cancels all open orders in the portfolio."""
    logging.warning("[CancelAll] Attempting to cancel all open orders.")
    open_orders = get_open_orders() # Assuming this fetches all orders, not just 'buy_pending'
    if not open_orders:
        logging.info("[CancelAll] No open orders found.")
        return

    cancelled_count = 0
    for order in open_orders:
        oid = order.get("RowKey", "")
        ticker = order.get("ticker", "N/A")
        if oid:
            if cancel_order(oid):
                cancelled_count += 1
            else:
                logging.warning("[CancelAll] Failed to cancel order %s (%s).", oid, ticker)
    logging.warning("[CancelAll] Cancelled %d of %d open orders.", cancelled_count, len(open_orders))


# ─────────────────────────────────────────────────────────────────────────────
# Strategy: Daily_Bid_Sweep  (9 AM ET)
# ─────────────────────────────────────────────────────────────────────────────

def Daily_Bid_Sweep() -> None:
    """
    1. Fetch today's confirmed MLB starters.
    2. Pull K/9 (MLB API) + Whiff% (Baseball Savant) for each.
    3. Discover KXMLBKS markets keyed by pitcher last-name token.
    4. Walk tiers from highest → lowest; find the Anchor (highest tier ≥ 70 %).
    5. Greenlight → place ONE Maker limit buy for the Anchor tier.
       - Per-tier ask filter: skip if ask > $0.90 or ask < $0.10.
       - Limit price = ask − 1¢ (resting Maker) or model price if no ask.
    6. Persist each order to Azure Table Storage.
    7. Mark sweep done.
    """
    logging.info("[Sweep] ═══ Daily_Bid_Sweep START ═══")
    
    # Pre-emptively lock to prevent race conditions
    start_sweep_lock()

    starters = fetch_todays_starters()
    if not starters:
        logging.warning("[Sweep] No confirmed starters. Marking done and exiting.")
        mark_sweep_done([])
        return

    whiff_map          = fetch_savant_whiff_map()
    team_factors       = fetch_team_k_factors()
    existing_tickers   = get_current_portfolio_tickers()
    game_records       = []
    total_shares_placed = 0

    for starter in starters:
        if total_shares_placed >= DAILY_SHARE_LIMIT:
            logging.warning("[Sweep] Daily limit of %d shares reached. Stopping sweep.", DAILY_SHARE_LIMIT)
            break
        name          = starter["pitcher_name"]
        mlb_id        = starter["mlb_id"]
        opp_abbr      = starter["opponent"]
        game_time_utc = starter["game_time_utc"]

        logging.info("[Sweep] ── %s (%s) vs %s game @ %s UTC", name, starter["team"], opp_abbr, game_time_utc)

        # ── Stats ──────────────────────────────────────────────────────────
        k9 = fetch_pitcher_k9(mlb_id)
        if k9 is None:
            logging.warning("[Sweep] No K/9 data for %s. Skipping.", name)
            continue

        whiff_pct = whiff_map.get(str(mlb_id), LEAGUE_AVG_WHIFF)
        opp_factor = team_factors.get(opp_abbr, 1.0)
        logging.info("[Sweep] %s  K/9=%.2f  Whiff%%=%.1f%%  OppFactor=%.2fx (%s)", 
                     name, k9, whiff_pct * 100, opp_factor, opp_abbr)

        # ── Market Discovery ───────────────────────────────────────────────
        event_ticker = build_event_ticker(starter)
        logging.info("[Sweep] Target Ticker: %s", event_ticker)

        # Safety: Check if we already have a position or order for this GAME/EVENT
        if any(event_ticker in t for t in existing_tickers):
            logging.info("[Safe] %s — already in portfolio (event %s). Skipping.", name, event_ticker)
            continue

        markets = fetch_event_markets(event_ticker)  # [(tier, market_dict), …] asc

        if not markets:
            logging.warning("[Sweep] No open contracts under event '%s'. Skipping.", event_ticker)
            continue

        # ── Find Anchor Tier (highest tier with P ≥ floor) ─────────────────
        anchor_tier: int | None = None
        for tier, _ in reversed(markets):
            if tier > MAX_TIER:
                logging.info("[Sweep] %s  Tier %d+  - Skipping (Moonshot Filter > %d)", name, tier, MAX_TIER)
                continue
            p = prob_k_or_more(tier, k9, whiff_pct, opp_factor)
            logging.info("[Sweep] %s  Tier %d+  P=%.1f%%", name, tier, p * 100)
            if p >= CONFIDENCE_FLOOR:
                anchor_tier = tier
                break

        if anchor_tier is None:
            logging.info(
                "[Sweep] %s — no tier reached %.0f%% confidence. No greenlight.",
                name, CONFIDENCE_FLOOR * 100,
            )
            continue

        logging.info("[Sweep] ✅ GREENLIT  %s  Anchor=%d+", name, anchor_tier)

        # ── Place ONLY the Anchor Tier ──────────────────────────────────
        anchor_market = next((m for t, m in markets if t == anchor_tier), None)
        if not anchor_market:
            logging.warning("[Sweep] %s anchor tier %d market not found in event.", name, anchor_tier)
            continue

        ticker  = anchor_market.get("ticker", "")
        yes_ask = anchor_market.get("yes_ask")

        # Compute our model-fair price for this tier
        model_prob  = prob_k_or_more(anchor_tier, k9, whiff_pct, opp_factor)
        model_price = max(MIN_ASK_CENTS, min(MAX_ASK_CENTS, int(model_prob * 100)))

        # ── Deep Pulse Check (MAKER PROTECTION) ──────────────────────────
        pulse = get_market_pulse(ticker)
        actual_ask = pulse.get("yes_ask")
        # actual_bid = pulse.get("yes_bid")

        if actual_ask is not None:
            # If the actual ask is already at or below our intended bid, 
            # placing a bid there would make us a TAKER.
            limit_price = max(MIN_ASK_CENTS, actual_ask - 1)
            
            # Additional safety: Don't bid higher than our model or the user max
            limit_price = min(limit_price, model_price, MAX_ASK_CENTS)
            
            if actual_ask <= MIN_ASK_CENTS:
                logging.warning("[Pulse] %s ask is too low (%d¢). Taker risk. Skipping.", ticker, actual_ask)
                continue
        else:
            limit_price = model_price

        limit_price = max(MIN_ASK_CENTS, min(MAX_ASK_CENTS, limit_price))
        order_id    = place_limit_buy(ticker, limit_price)
        if order_id:
            save_order(
                order_id      = order_id,
                ticker        = ticker,
                pitcher_id    = str(mlb_id),
                tier          = anchor_tier,
                buy_price     = limit_price,
                game_time_utc = game_time_utc,
            )
            total_shares_placed += 1
            existing_tickers.add(ticker) # Update local cache to prevent duplicate processing
            logging.info("[Sweep] %s ✅ Order placed (%d/%d): %s @ %d¢", 
                         name, total_shares_placed, DAILY_SHARE_LIMIT, ticker, limit_price)
        game_records.append({"pitcher_id": str(mlb_id), "game_time_utc": game_time_utc})

    mark_sweep_done(game_records)
    logging.info("[Sweep] ═══ Daily_Bid_Sweep DONE — %d pitchers processed ═══", len(game_records))


# ─────────────────────────────────────────────────────────────────────────────
# Azure Function Entry Point
# ─────────────────────────────────────────────────────────────────────────────

@app.timer_trigger(
    schedule      = "0 0 16 * * *",   # Exactly 12:00 PM ET (16:00 UTC)
    arg_name      = "myTimer",
    run_on_startup= False,
    use_monitor   = False,
)
def mlb_k_ladder(myTimer: func.TimerRequest) -> None:
    """
    Fixed Daily Sweep: Runs exactly once per day at 12 PM ET.
    Only places orders for pitchers we DO NOT already hold in our portfolio.
    """
    logging.info("[Main] Daily MLB Sweep Triggered (12:00 PM ET / 16:00 UTC).")
    
    # Double-Lock: Check if we've already marked today as done in the database
    if is_sweep_done_today():
        logging.info("[Main] Sweep already completed today via database record. Skipping.")
        return

    try:
        Daily_Bid_Sweep()
        logging.info("[Main] Daily Sweep completed.")
    except Exception as exc:
        logging.error("[Main] MLB Sweep failed: %s", exc)

@app.route(route="manual_sweep", auth_level=func.AuthLevel.FUNCTION)
def manual_sweep(req: func.HttpRequest) -> func.HttpResponse:
    """Manual trigger to run the 12 PM logic on demand."""
    logging.warning("[Manual] Request to run sweep immediately.")
    try:
        Daily_Bid_Sweep()
        return func.HttpResponse("Sweep initiated successfully.", status_code=200)
    except Exception as e:
        return func.HttpResponse(f"Manual sweep failed: {e}", status_code=500)


@app.timer_trigger(
    schedule      = "0 */15 12-23 * * *", # Every 15 mins from 12 PM to 12 AM ET
    arg_name      = "takeProfitTimer",
    run_on_startup= False,
    use_monitor   = False,
)
def mlb_take_profit(takeProfitTimer: func.TimerRequest) -> None:
    """
    Take-Profit Monitor: Deactivated based on user request.
    Previously checked open MLB positions and sold if Bid >= 92c.
    """
    logging.info("[Monitor] Take-profit check skipping (Deactivated). Waiting for natural settlement.")
    return

