import os
import json
from datetime import datetime, timezone, timedelta
from azure.data.tables import TableServiceClient

TABLE_NAME = "StrikeoutBotTracker"
ET_OFFSET = -4

def get_config():
    path = '/Users/markrutledge/Documents/DjQueue/Kalshi Bot/strikeout_bot/local.settings.json'
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data.get('Values', {})
    except:
        return {}

def _table_client():
    config = get_config()
    conn = config.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        print("Missing AZURE_STORAGE_CONNECTION_STRING in local.settings.json")
        return None
    svc  = TableServiceClient.from_connection_string(conn)
    return svc.get_table_client(TABLE_NAME)

def main():
    today_et = (datetime.now(timezone.utc) + timedelta(hours=ET_OFFSET)).strftime("%Y-%m-%d")
    print(f"--- DIAGNOSING RUN FOR {today_et} ---")
    
    tc = _table_client()
    if not tc: return

    # 1. Check Sweep Record
    try:
        sweep = tc.get_entity(partition_key="SWEEP", row_key=today_et)
        print(f"Sweep Found: Yes")
        print(f"Swept At: {sweep.get('swept_at')}")
        records_json = sweep.get('game_records')
        print(f"Records JSON exists: {bool(records_json)}")
        if records_json:
            records = json.loads(records_json)
            print(f"Starters Processed: {len(records)}")
            for r in records:
                print(f"  - {r.get('pitcher')} ({r.get('team')}): Status={r.get('status')}, Max Prob={r.get('max_prob')}")
    except Exception as e:
        print(f"Sweep Found: No record for {today_et} ({str(e)})")

    # 2. Check Orders placed today
    print("\nOrders Summary (Today ET):")
    try:
        orders = tc.query_entities("PartitionKey eq 'ORDER'")
        count = 0
        # Today in ET starts at UTC-4. Let's just look at everything since yesterday UTC to be safe.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        for o in orders:
            placed_at = o.get('placed_at', '')
            if placed_at >= cutoff:
                print(f"  - {o.get('RowKey')}: Ticker={o.get('ticker')}, Status={o.get('status')}, Placed={placed_at}")
                count += 1
        if count == 0:
            print("  - No orders found in last 24h")
    except Exception as e:
        print(f"Error querying orders: {e}")

if __name__ == "__main__":
    main()
