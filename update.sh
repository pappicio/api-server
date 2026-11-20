#!/opt/bin/sh
set -eu

PLUGIN_DIR="${OC_PLUGIN_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
SOURCE="$PLUGIN_DIR/scripts/api_server.py"
DEST="/usr/data/opencreator/scripts/api_server.py"

if [ ! -f "$SOURCE" ]; then
    echo "[API Server] ERROR: api_server.py not found."
    exit 1
fi

if [ ! -f /usr/data/opencreator/plugins/script-runner/opencreator-plugin.json ]; then
    echo "[API Server] ERROR: Script Runner is not installed."
    exit 1
fi

mkdir -p /usr/data/opencreator/scripts
cp "$SOURCE" "$DEST"

echo "[API Server] Updated. Restarting Script Runner..."
oc-plugin restart script-runner

echo "[API Server] Update completed."
