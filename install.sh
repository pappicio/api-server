#!/opt/bin/sh
set -eu

PLUGIN_DIR="${OC_PLUGIN_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
RUNNER_MANIFEST="/usr/data/opencreator/plugins/script-runner/opencreator-plugin.json"
SCRIPTS_DIR="/usr/data/opencreator/scripts"
SOURCE="$PLUGIN_DIR/scripts/api_server.py"
DEST="$SCRIPTS_DIR/api_server.py"
CONFIG="/usr/data/opencreator/api-server.json"
PYTHON="/usr/data/python-hf/bin/python3"

echo "[API Server] Checking Script Runner..."

if [ ! -f "$RUNNER_MANIFEST" ]; then
    echo "[API Server] ERROR: Script Runner is not installed."
    exit 1
fi

if [ ! -f "$SOURCE" ]; then
    echo "[API Server] ERROR: api_server.py not found."
    exit 1
fi

printf "[API Server] Raspberry/Radxa IPv4 address: " > /dev/tty
if ! read -r RADXA_HOST < /dev/tty; then
    echo "[API Server] ERROR: Unable to read IP from terminal."
    exit 1
fi

if [ -z "$RADXA_HOST" ]; then
    echo "[API Server] ERROR: IP address is required."
    exit 1
fi

RADXA_HOST="$RADXA_HOST" CONFIG="$CONFIG" "$PYTHON" <<'PY'
import os
import json
import ipaddress

host = str(ipaddress.IPv4Address(os.environ["RADXA_HOST"]))
path = os.environ["CONFIG"]

try:
    with open(path, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

config["radxa_host"] = host

os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(config, f, indent=4)
    f.write("\n")

print("[API Server] Saved Radxa IP:", host)
PY

mkdir -p "$SCRIPTS_DIR"
cp "$SOURCE" "$DEST"

echo "[API Server] Restarting Script Runner..."
oc-plugin restart script-runner

echo "[API Server] Installation completed."
