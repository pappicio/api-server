#!/opt/bin/sh
set -eu

DEST="/usr/data/opencreator/scripts/api_server.py"

rm -f "$DEST"

if [ -f /usr/data/opencreator/plugins/script-runner/opencreator-plugin.json ]; then
    echo "[API Server] Restarting Script Runner..."
    oc-plugin restart script-runner
fi

echo "[API Server] Removed."
echo "[API Server] Configuration preserved: /usr/data/opencreator/api-server.json"
