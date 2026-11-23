
#!/opt/bin/sh
set -eu

PLUGIN_DIR="${OC_PLUGIN_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"

echo "[API Server] Running install.sh..."
sh "$PLUGIN_DIR/install.sh"