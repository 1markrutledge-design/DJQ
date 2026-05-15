#!/bin/bash
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"


RESOURCE_GROUP="Temperature90bot_group"
FUNCTION_APP="Temperature90bot"
BOT_DIR="/Users/markrutledge/Documents/DjQueue/Kalshi Bot/weather_bot"
ZIP_PATH="/Users/markrutledge/Documents/DjQueue/Kalshi Bot/weather_bot_deploy.zip"
PACKAGES_DIR="$BOT_DIR/.python_packages/lib/site-packages"

echo "=== Step 1: Install packages (bundled for Flex Consumption) ==="
rm -rf "$BOT_DIR/.python_packages"
mkdir -p "$PACKAGES_DIR"
pip3 install \
  --target "$PACKAGES_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.13 \
  --only-binary=:all: \
  --upgrade \
  requests cryptography azure-functions azure-storage-blob

echo "=== Step 2: Build zip with code + bundled packages ==="
rm -f "$ZIP_PATH"
cd "$BOT_DIR"
zip -r "$ZIP_PATH" \
  __init__.py \
  function_app.py \
  kalshi_client.py \
  series_config.py \
  state.py \
  strategy.py \
  host.json \
  requirements.txt \
  .python_packages/

echo "ZIP size: $(du -sh "$ZIP_PATH" | cut -f1)"

echo "=== Step 3: Deploy (local zip, no remote build) ==="
az functionapp deployment source config-zip \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNCTION_APP" \
  --src "$ZIP_PATH" \
  --build-remote false

echo ""
echo "✅ Done! Check Azure Portal → Temperature90bot → Monitor for logs."
