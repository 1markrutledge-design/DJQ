import sys, os, json
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from azure.storage.blob import BlobServiceClient

def download_state():
    settings_path = "/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json"
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    
    conn = vals["AZURE_STORAGE_CONNECTION_STRING"]
    service = BlobServiceClient.from_connection_string(conn)
    blob = service.get_blob_client(container="tennis-bot-state", blob="validated_targets.json")
    
    try:
        data = blob.download_blob().readall()
        state = json.loads(data.decode("utf-8"))
        print(f"Loaded state with {len(state)} tickers.")
        
        # Check for Uchiyama
        found = False
        for ticker in state.keys():
            if "UCH" in ticker or "MAT" in ticker:
                print(f"FOUND IN STATE: {ticker}")
                found = True
        if not found:
            print("No 'Uchiyama' or 'Matsuoka' tickers found in state.")
            
    except Exception as e:
        print(f"Error downloading state: {e}")

if __name__ == "__main__":
    download_state()
