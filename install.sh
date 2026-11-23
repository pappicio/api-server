
#!/opt/bin/sh
set -eu

PLUGIN_DIR="${OC_PLUGIN_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
SCRIPTS_DIR="/usr/data/opencreator/scripts"
CONFIG="/usr/data/opencreator/api-server.json"
MACROS="/usr/data/opencreator/klipper/config/oc-macros.cfg"
NAVI="/usr/data/opencreator/klipper/config/.theme/navi.json"
PYTHON="/usr/data/python-hf/bin/python3"

UPDATE_MODE=0
[ "${1:-}" = "--update" ] && UPDATE_MODE=1

echo "[API Server] Installing native plugin..."

[ -f "$PLUGIN_DIR/scripts/api_server.py" ] || {
    echo "[API Server] ERROR: api_server.py not found."
    exit 1
}

[ -f "$PLUGIN_DIR/scripts/api-server.sh" ] || {
    echo "[API Server] ERROR: api-server.sh not found."
    exit 1
}

[ -f "$MACROS" ] || {
    echo "[API Server] ERROR: oc-macros.cfg not found."
    exit 1
}

# Remove the previous Script Runner-managed copy.
if [ -f "$SCRIPTS_DIR/api_server.py" ]; then
    rm -f "$SCRIPTS_DIR/api_server.py"
    echo "[API Server] Removed legacy shared script."
fi

# Read existing configuration without changing it.
REMOTE_HOST="$("$PYTHON" -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        print(json.load(f).get("remote_host", ""))
except Exception:
    print("")
' "$CONFIG")"

SYNC_VALUE="$("$PYTHON" -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        value = json.load(f).get("sync_firmware_res", None)
        print("" if value is None else str(value).lower())
except Exception:
    print("")
' "$CONFIG")"

# Ask for initial settings only during a fresh interactive installation.
if [ "$UPDATE_MODE" -eq 0 ] && [ -z "$REMOTE_HOST" ]; then
    if ( : </dev/tty ) 2>/dev/null; then
        printf "[API Server] Remote Host IPv4 address (leave empty for local-only mode): " > /dev/tty
        read -r REMOTE_HOST < /dev/tty || REMOTE_HOST=""
    else
        echo "[API Server] No terminal available. Continuing in local-only mode."
    fi
fi

if [ "$UPDATE_MODE" -eq 0 ] && [ -z "$SYNC_VALUE" ]; then
    if ( : </dev/tty ) 2>/dev/null; then
        printf "[API Server] Synchronize calibrations on SoC/Tunneled switches? (y/N): " > /dev/tty
        read -r SYNC_CHOICE < /dev/tty || SYNC_CHOICE=""

        case "$SYNC_CHOICE" in
            y|Y|yes|YES|Yes) SYNC_VALUE=true ;;
            *) SYNC_VALUE=false ;;
        esac
    else
        SYNC_VALUE=false
    fi
fi

# Determine the Creator 5 address using the selected network route.
CREATOR_HOST=""

if [ -n "$REMOTE_HOST" ]; then
    CREATOR_HOST="$(ip -4 route get "$REMOTE_HOST" 2>/dev/null |
        sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1)"
fi

if [ -z "$CREATOR_HOST" ]; then
    CREATOR_HOST="$(ip -4 route get 1.1.1.1 2>/dev/null |
        sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1)"
fi

REMOTE_HOST="$REMOTE_HOST" \
CREATOR_HOST="$CREATOR_HOST" \
SYNC_VALUE="$SYNC_VALUE" \
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

config_path = os.environ["CONFIG"]
macros_path = os.environ["MACROS"]
navi_path = os.environ["NAVI"]

remote = os.environ.get("REMOTE_HOST", "").strip()
creator = os.environ.get("CREATOR_HOST", "").strip()
sync_value = os.environ.get("SYNC_VALUE", "").strip().lower()

def backup(path):
    if os.path.isfile(path):
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = path + ".bak." + suffix
        shutil.copy2(path, target)
        print("[API Server] Backup:", target)

try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

if not isinstance(config, dict):
    raise SystemExit("[API Server] ERROR: API config must be a JSON object.")

changed = False

if remote:
    try:
        remote = str(ipaddress.IPv4Address(remote))
    except ValueError:
        raise SystemExit("[API Server] ERROR: Invalid Remote Host IPv4 address.")

    if config.get("remote_host") != remote:
        config["remote_host"] = remote
        changed = True

if sync_value in ("true", "false") and "sync_firmware_res" not in config:
    config["sync_firmware_res"] = sync_value == "true"
    changed = True

if changed or not os.path.exists(config_path):
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    backup(config_path)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
        f.write("\n")

print("[API Server] Configuration preserved and updated.")

# Add only missing Klipper sections.
with open(macros_path) as f:
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
    )
]

missing = []
for section, content in sections:
    pattern = r"(?m)^\[" + re.escape(section) + r"\]\s*$"
    if not re.search(pattern, macros):
        missing.append(content)

if missing:
    backup(macros_path)
    with open(macros_path, "a") as f:
        f.write("\n\n# BEGIN api-server\n")
        f.write("\n\n".join(missing))
        f.write("\n# END api-server\n")
    print("[API Server] Klipper macro integration updated.")
else:
    print("[API Server] Klipper macros already present.")

# Configure Mainsail navigation when the Creator IP is available.
if creator:
    try:
        creator = str(ipaddress.IPv4Address(creator))
    except ValueError:
        raise SystemExit("[API Server] ERROR: Invalid Creator IPv4 address.")

    try:
        with open(navi_path) as f:
            navigation = json.load(f)
    except FileNotFoundError:
        navigation = []

    if not isinstance(navigation, list):
        raise SystemExit("[API Server] ERROR: Navigation JSON must contain a list.")

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

    print("[API Server] Mainsail navigation configured.")
else:
    print("[API Server] Creator IP unavailable. Navigation was not changed.")
PY

echo "[API Server] Installation completed successfully."
