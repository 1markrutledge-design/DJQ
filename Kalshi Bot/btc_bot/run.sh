#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Kalshi BTC 15-Minute Front-Runner Bot — Local Mac Launcher
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   ./run.sh            → live trading (real orders)
#   ./run.sh --dry-run  → simulation mode (no real orders)
#   ./run.sh --debug    → verbose logging
#
# First-time setup:
#   1. cp .env.example .env
#   2. Edit .env with your KALSHI_API_KEY_ID and key file path
#   3. Place kalshi_private.pem in this directory
#   4. pip install -r requirements.txt
#   5. ./run.sh --dry-run   (test connection, no real money)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  🤖  Kalshi BTC 15M Front-Runner Bot — Local Launcher${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Load .env if present ──────────────────────────────────────────────────────
if [[ -f ".env" ]]; then
    echo -e "${GREEN}✔ Loading .env${NC}"
    # shellcheck disable=SC1091
    set -a; source .env; set +a
else
    echo -e "${YELLOW}⚠  No .env file found. Falling back to shell environment.${NC}"
    echo -e "   Run: cp .env.example .env  and fill in your credentials."
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────────

# 1. Python 3.11+
PYTHON=$(command -v python3 || true)
if [[ -z "$PYTHON" ]]; then
    echo -e "${RED}✖ python3 not found. Install via: brew install python${NC}"; exit 1
fi
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✔ Python ${PY_VER}${NC}"

# 2. API Key ID
if [[ -z "${KALSHI_API_KEY_ID:-}" ]]; then
    echo -e "${RED}✖ KALSHI_API_KEY_ID is not set.${NC}"; exit 1
fi
echo -e "${GREEN}✔ API Key ID set (${KALSHI_API_KEY_ID:0:8}…)${NC}"

# 3. Private key
KEY_PATH="${KALSHI_PRIVATE_KEY_PATH:-kalshi_private.pem}"
if [[ -z "${KALSHI_PRIVATE_KEY_PEM:-}" ]]; then
    if [[ ! -f "$KEY_PATH" ]]; then
        echo -e "${RED}✖ Private key not found at: $KEY_PATH${NC}"
        echo -e "   Place your RSA private key there, or set KALSHI_PRIVATE_KEY_PEM."
        exit 1
    fi
    echo -e "${GREEN}✔ Private key found: $KEY_PATH${NC}"
else
    echo -e "${GREEN}✔ Private key loaded from KALSHI_PRIVATE_KEY_PEM env var${NC}"
fi

# 4. Dependencies
echo -e "${CYAN}▸ Checking dependencies…${NC}"
if ! "$PYTHON" -c "import websockets, requests, cryptography, rich" 2>/dev/null; then
    echo -e "${YELLOW}Installing missing packages…${NC}"
    "$PYTHON" -m pip install -q -r requirements.txt
fi
echo -e "${GREEN}✔ All dependencies present${NC}"

# ── Dry-run detection ─────────────────────────────────────────────────────────
EXTRA_FLAGS=(${@+"$@"})
if [[ "${DRY_RUN:-false}" == "true" ]] || [[ " ${EXTRA_FLAGS[*]:-} " == *" --dry-run "* ]]; then
    echo -e "${YELLOW}⚠  DRY-RUN MODE — no real orders will be placed${NC}"
else
    echo -e "${RED}🔴 LIVE MODE — real orders will be placed on Kalshi${NC}"
    echo -e "   (Run with --dry-run to test without spending money)"
    echo ""
    read -r -p "   Type 'yes' to confirm live trading: " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# ── Dashboard tip ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}💡 Tip: Open a second terminal and run:${NC}"
echo -e "   cd '${SCRIPT_DIR}' && python dashboard.py"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}▸ Starting bot…  (Ctrl-C to stop)${NC}"
echo ""

# ── Launch ────────────────────────────────────────────────────────────────────
exec caffeinate -i "$PYTHON" bot.py ${EXTRA_FLAGS[@]+"${EXTRA_FLAGS[@]}"}
