import sys, os, json
sys.path.append("/Users/markrutledge/Desktop/bot_code")
from azure.storage.blob import BlobServiceClient

def upload_cache():
    settings_path = "/Users/markrutledge/Documents/DjQueue/bot_investigate/local.settings.json"
    with open(settings_path, "r") as f:
        vals = json.load(f).get("Values", {})
    
    conn = vals["AZURE_STORAGE_CONNECTION_STRING"]
    service = BlobServiceClient.from_connection_string(conn)
    container = service.get_container_client("tennis-bot-state")
    blob = container.get_blob_client("match_cache.json")
    
    cache_path = "/Users/markrutledge/Documents/DjQueue/Kalshi Bot/match_cache.json"
    with open(cache_path, "rb") as data:
        blob.upload_blob(data, overwrite=True)
    print("Successfully uploaded match_cache.json to Azure.")

if __name__ == "__main__":
    upload_cache()
