#!/opt/bin/sh
set -eu

PLUGIN_DIR="${OC_PLUGIN_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
RUNNER_MANIFEST="/usr/data/opencreator/plugins/script-runner/opencreator-plugin.json"
SCRIPTS_DIR="/usr/data/opencreator/scripts"
SOURCE="$PLUGIN_DIR/scripts/api_server.py"
DEST="$SCRIPTS_DIR/api_server.py"
CONFIG="/usr/data/opencreator/api-server.json"
MACROS="/usr/data/opencreator/klipper/config/oc-macros.cfg"
NAVI="/usr/data/opencreator/klipper/config/.theme/navi.json"
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

if [ ! -f "$MACROS" ]; then
    echo "[API Server] ERROR: oc-macros.cfg not found."
    exit 1
fi

printf "[API Server] Remote Host IPv4 address: " > /dev/tty
if ! read -r REMOTE_HOST < /dev/tty; then
    echo "[API Server] ERROR: Unable to read IP from terminal."
    exit 1
fi

if [ -z "$REMOTE_HOST" ]; then
    echo "[API Server] ERROR: IP address is required."
    exit 1
fi

CREATOR_HOST="$(ip -4 route get "$REMOTE_HOST" |
    sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1)"

if [ -z "$CREATOR_HOST" ]; then
    echo "[API Server] ERROR: Unable to determine Creator 5 IPv4 address."
    exit 1
fi

echo "[API Server] Creator 5 IP: $CREATOR_HOST"
echo "[API Server] Remote Host IP: $REMOTE_HOST"

# Validate addresses and update configuration, macros and navigation.
REMOTE_HOST="$REMOTE_HOST" \
CREATOR_HOST="$CREATOR_HOST" \
CONFIG="$CONFIG" \
MACROS="$MACROS" \
NAVI="$NAVI" \
"$PYTHON" <<'PY'
import os
import json
import ipaddress
import re
import shutil
from datetime import datetime

remote = str(ipaddress.IPv4Address(os.environ["REMOTE_HOST"]))
creator = str(ipaddress.IPv4Address(os.environ["CREATOR_HOST"]))

config_path = os.environ["CONFIG"]
macros_path = os.environ["MACROS"]
navi_path = os.environ["NAVI"]

def backup(path):
    if os.path.isfile(path):
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = path + ".bak." + suffix
        shutil.copy2(path, target)
        print("[API Server] Backup:", target)

# Preserve existing API configuration.
try:
    with open(config_path, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

config["remote_host"] = remote
os.makedirs(os.path.dirname(config_path), exist_ok=True)
backup(config_path)
with open(config_path, "w") as f:
    json.dump(config, f, indent=4)
    f.write("\n")

print("[API Server] Saved Remote Host IP:", remote)

# Add only missing Klipper sections.
with open(macros_path, "r") as f:
    macros = f.read()

sections = [
    (
        "gcode_shell_command oc_tunneled_mode",
        """[gcode_shell_command oc_tunneled_mode]
command: curl -fsS --max-time 10 "http://127.0.0.1:8765/go_tunneled" >/dev/null
timeout: 15.
verbose: False"""
    ),
    (
        "gcode_macro TUNNELED_MODE",
        """[gcode_macro TUNNELED_MODE]
description: Switch Creator 5 to Tunneled mode
gcode:
    RUN_SHELL_COMMAND CMD=oc_tunneled_mode"""
    ),
]

missing = []
for section, content in sections:
    pattern = r"(?m)^\[" + re.escape(section) + r"\]\s*$"
    if not re.search(pattern, macros):
        missing.append(content)

if missing:
    backup(macros_path)
    addition = "\n\n# BEGIN api-server\n"
    addition += "\n\n".join(missing)
    addition += "\n# END api-server\n"
    with open(macros_path, "a") as f:
        f.write(addition)
    print("[API Server] TUNNELED_MODE macro integration updated.")
else:
    print("[API Server] TUNNELED_MODE macro already present.")

# Preserve existing Mainsail navigation entries.
try:
    with open(navi_path, "r") as f:
        navigation = json.load(f)
except FileNotFoundError:
    navigation = []

if not isinstance(navigation, list):
    raise ValueError("Navigation JSON must contain a list.")

entry = {
    "title": "Tunneled Mode",
    "href": "http://%s:8765/go_tunneled" % creator,
    "target": "_self",
    "icon": "M21,9L17,5V8H10V10H17V13M7,11L3,15L7,19V16H14V14H7V11Z",
    "position": 90
}

matches = [
    i for i, item in enumerate(navigation)
    if isinstance(item, dict) and item.get("title") == "Tunneled Mode"
]

if matches:
    first = matches[0]
    updated = dict(navigation[first])
    updated.update(entry)
    navigation[first] = updated
    for index in reversed(matches[1:]):
        del navigation[index]
else:
    navigation.append(entry)

os.makedirs(os.path.dirname(navi_path), exist_ok=True)
backup(navi_path)
with open(navi_path, "w") as f:
    json.dump(navigation, f, indent=2)
    f.write("\n")

print("[API Server] Navigation entry configured:", entry["href"])
PY

mkdir -p "$SCRIPTS_DIR"
cp "$SOURCE" "$DEST"

echo "[API Server] Restarting Script Runner..."
oc-plugin restart script-runner

echo "[API Server] Requesting Klipper restart..."
"$PYTHON" <<'PY'
import json
import time
import urllib.request
import urllib.error

base = "http://127.0.0.1:7125"

request = urllib.request.Request(
    base + "/printer/restart",
    data=b"",
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
except Exception as exc:
    raise SystemExit("[API Server] Klipper restart request failed: %s" % exc)

for attempt in range(60):
    try:
        with urllib.request.urlopen(base + "/printer/info", timeout=5) as response:
            info = json.loads(response.read().decode("utf-8"))
        state = info.get("result", {}).get("state")
        if state == "ready":
            print("[API Server] Klipper restarted and is ready.")
            break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("[API Server] ERROR: Klipper did not become ready within 120 seconds.")
PY

echo "[API Server] Installation completed successfully."
