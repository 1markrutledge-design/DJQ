"""
force_sweep.py — Trigger the Azure Function directly to force a sweep NOW.
Resets the sweep flag in Table Storage, then invokes the function.
"""

import json
import time
import requests
from azure.data.tables import TableServiceClient, UpdateMode

# ── Load settings ────────────────────────────────────────────────────────────
with open("local.settings.json") as f:
    settings = json.load(f).get("Values", {})

CONN_STR = settings["AZURE_STORAGE_CONNECTION_STRING"]
TABLE    = "StrikeoutBotTracker"

# ── Step 1: Reset today's sweep ──────────────────────────────────────────────
import datetime
today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
print(f"1️⃣  Resetting sweep flag for {today}...")
tc = TableServiceClient.from_connection_string(CONN_STR).get_table_client(TABLE)
try:
    tc.delete_entity("SWEEP", today)
    print("   ✅ Sweep flag deleted")
except Exception:
    print("   ✅ No sweep flag to delete (already clean)")

# ── Step 2: Get Azure Function admin key ─────────────────────────────────────
print("\n2️⃣  Getting Azure Function admin key...")
import subprocess
result = subprocess.run(
    ["az", "functionapp", "keys", "list",
     "--name", "Strikeoutbot",
     "--resource-group", "Strikeoutbot_group",
     "--query", "masterKey", "-o", "tsv"],
    capture_output=True, text=True
)
master_key = result.stdout.strip()
if not master_key:
    print("   ❌ Could not get master key. Run 'az login' first.")
    exit(1)
print(f"   ✅ Got master key: {master_key[:8]}...")

# ── Step 3: Trigger the function ─────────────────────────────────────────────
print("\n3️⃣  Triggering mlb_k_ladder function...")
url = "https://strikeoutbot-hjghdnewfhdaeegw.eastus-01.azurewebsites.net/admin/functions/mlb_k_ladder"
headers = {
    "x-functions-key": master_key,
    "Content-Type": "application/json",
}
resp = requests.post(url, headers=headers, json={}, timeout=30)
print(f"   HTTP {resp.status_code}")
if resp.status_code == 202:
    print("   ✅ Function triggered! Check Azure Monitor logs in ~30 seconds.")
    print("\n   📋 Go to Azure Portal → Strikeoutbot → Functions → mlb_k_ladder → Monitor")
    print("   You should see the Daily_Bid_Sweep running with real Kalshi API calls.")
else:
    print(f"   ❌ Unexpected response: {resp.text[:200]}")

print("\n4️⃣  Waiting 10s then checking if sweep was marked done...")
time.sleep(10)
try:
    ent = tc.get_entity("SWEEP", today)
    done = ent.get("sweep_done", False)
    records = json.loads(ent.get("game_records", "[]"))
    print(f"   sweep_done = {done}")
    print(f"   game_records = {len(records)} games")
    if records:
        for r in records:
            print(f"     pitcher_id={r.get('pitcher_id')}  game={r.get('game_time_utc')}")
    else:
        print("   ⚠ No games in records — either still running or no contracts matched.")
except Exception:
    print("   ⏳ Sweep not done yet — function may still be running. Check Azure logs.")

print("\nDone! Check Azure Monitor for full logs.")
