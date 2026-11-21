#!/opt/bin/sh
set -eu

DEST="/usr/data/opencreator/scripts/api_server.py"
MACROS="/usr/data/opencreator/klipper/config/oc-macros.cfg"
NAVI="/usr/data/opencreator/klipper/config/.theme/navi.json"
PYTHON="/usr/data/python-hf/bin/python3"

echo "[API Server] Removing plugin integrations..."

"$PYTHON" <<'PY'
import os
import re
import json
import shutil
from datetime import datetime

macros_path = "/usr/data/opencreator/klipper/config/oc-macros.cfg"
navi_path = "/usr/data/opencreator/klipper/config/.theme/navi.json"

def backup(path):
    if os.path.isfile(path):
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = path + ".bak." + suffix
        shutil.copy2(path, target)
        print("[API Server] Backup:", target)

# Remove only the block managed by this plugin.
if os.path.isfile(macros_path):
    with open(macros_path, "r") as f:
        content = f.read()

    updated, count = re.subn(
        r"(?ms)\n?# BEGIN api-server\n.*?^# END api-server\n?",
        "\n",
        content
    )

    if count:
        backup(macros_path)
        with open(macros_path, "w") as f:
            f.write(updated)
        print("[API Server] Removed managed Klipper macro block.")
    else:
        print("[API Server] No managed macro block found.")

# Remove only this plugin's Tunneled Mode navigation entry.
if os.path.isfile(navi_path):
    with open(navi_path, "r") as f:
        navigation = json.load(f)

    if not isinstance(navigation, list):
        raise ValueError("Navigation JSON must contain a list.")

    updated = [
        item for item in navigation
        if not (
            isinstance(item, dict)
            and item.get("title") == "Tunneled Mode"
            and str(item.get("href", "")).endswith(":8765/go_tunneled")
        )
    ]

    if len(updated) != len(navigation):
        backup(navi_path)
        with open(navi_path, "w") as f:
            json.dump(updated, f, indent=2)
            f.write("\n")
        print("[API Server] Removed Tunneled Mode navigation entry.")
    else:
        print("[API Server] No managed navigation entry found.")
PY

rm -f "$DEST"

if [ -f /usr/data/opencreator/plugins/script-runner/opencreator-plugin.json ]; then
    echo "[API Server] Restarting Script Runner..."
    oc-plugin restart script-runner
fi

echo "[API Server] Restarting Klipper..."
"$PYTHON" <<'PY'
import json
import time
import urllib.request

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

for _ in range(60):
    try:
        with urllib.request.urlopen(base + "/printer/info", timeout=5) as response:
            info = json.loads(response.read().decode("utf-8"))
        if info.get("result", {}).get("state") == "ready":
            print("[API Server] Klipper restarted and is ready.")
            break
    except Exception:
        pass
    time.sleep(2)
else:
    raise SystemExit("[API Server] ERROR: Klipper did not become ready within 120 seconds.")
PY

echo "[API Server] Removed."
echo "[API Server] Configuration preserved: /usr/data/opencreator/api-server.json"
