
#!/usr/prog/Python-3.8.2/bin/python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import ipaddress
import platform
import subprocess
import threading
import shutil
import tempfile
import stat
import urllib.request
import socket

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "0.0.0.0"
PORT = 8765

API_CONFIG_FILE = "/usr/data/opencreator/api-server.json"
RUNNER_MODE = os.environ.get("OC_RUNNER_MODE", "").strip().lower()

try:
    if RUNNER_MODE == "tunneled":
        RUNNER_RADXA_HOST = os.environ.get("OC_MOONRAKER_IP", "").strip()
        RADXA_HOST = str(ipaddress.IPv4Address(RUNNER_RADXA_HOST))

        API_CONFIG = {}
        if os.path.isfile(API_CONFIG_FILE):
            with open(API_CONFIG_FILE, "r") as f:
                API_CONFIG = json.load(f)

        API_CONFIG["remote_host"] = RADXA_HOST
        with open(API_CONFIG_FILE, "w") as f:
            json.dump(API_CONFIG, f, indent=4)
            f.write("\n")

    elif RUNNER_MODE == "soc":
        with open(API_CONFIG_FILE, "r") as f:
            API_CONFIG = json.load(f)
        RADXA_HOST = str(ipaddress.IPv4Address(API_CONFIG["remote_host"]))

    else:
        raise ValueError("OC_RUNNER_MODE assente o non valido: %s" % RUNNER_MODE)

except Exception as e:
    raise RuntimeError("Configurazione API Server non valida (modalità %s): %s" % (RUNNER_MODE, e))

SYNC_FIRMWARE_RES = API_CONFIG.get("sync_firmware_res", False) is True


def get_creator_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((RADXA_HOST, 8765))
        return sock.getsockname()[0]
    finally:
        sock.close()


CREATOR_HOST = get_creator_ip()

BASE_DIR = "/usr/data/opencreator"
CONFIG_DIR = "/usr/data/firmwareRes/config"

SCREEN_FILE = os.path.join(BASE_DIR, "screen")
SCREEN_SCRIPT = os.path.join(BASE_DIR, "startup/scripts/40-screen.sh")

MARKER = os.path.join(BASE_DIR, "startup/tunneled")
BACKUP = os.path.join(BASE_DIR, "startup/tunneled_")

MESH_FILE = os.path.join(CONFIG_DIR, "levelData")

# Toolchange lifetime counter synchronization
TOOLCHANGES_FILE = "/usr/data/opencreator/klipper/config/toolchanges.txt"
RADXA_TOOLCHANGES_URL = "http://%s:8765/api/toolchanges" % RADXA_HOST
TOOLCHANGES_TIMEOUT = 10
MAX_TOOLCHANGES_SIZE = 4096

# Nozzle lifetime synchronization
NOZZLE_HOURS_FILE = "/usr/data/opencreator/klipper/config/c5_misc_variables.cfg"
RADXA_NOZZLE_HOURS_URL = "http://%s:8765/api/nozzle_hours" % RADXA_HOST
RADXA_FIRMWARE_RES_URL = "http://%s:8765/api/firmware_res" % RADXA_HOST
FIRMWARE_RES_FILES = ("extruder.json", "zoffset.json")
FIRMWARE_RES_TIMEOUT = 15
MAX_FIRMWARE_RES_SIZE = 1024 * 1024
NOZZLE_HOURS_TIMEOUT = 10
NOZZLE_HOURS_KEYS = tuple("nozzle_seconds_t%d" % i for i in range(4))


# Radxa SoC temperature
RADXA_TEMP_FILE = "/tmp/radxa_soc_temp"


# Authorized clients

ALLOWED_IPS = {
    RADXA_HOST,
    "127.0.0.1",
}

ALLOWED_NETWORKS = (
    str(ipaddress.ip_network(RADXA_HOST + "/24", strict=False)),
)


# JSON files exposed by the API

CONFIG_FILES = {
    "general": "general.json",
    "total": "total.json",
    "print": "print.json",
    "time": "time.json",
    "extruder": "extruder.json",
    "filament": "filament.json",
    "zoffset": "zoffset.json",
    "test": "test.json",
    "recovery": "recovery.json",
    "recovery_flag": "recovery_flag.json",
}


# ============================================================
# MODE REDIRECT CONFIGURATION
# ============================================================

GO = {
    "go_tunneled": {
        "mode": "tunneled",
        "title": "Tunneled",
        "url": "http://%s/" % RADXA_HOST,
        "probe": "http://%s/" % RADXA_HOST,
    },
    "go_soc": {
        "mode": "soc",
        "title": "SoC",
        "url": "http://%s/" % CREATOR_HOST,
        "probe": "http://%s:7125/server/info" % CREATOR_HOST,
    },
}


WAIT_PAGE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cambio modalita</title>

<style>
body {
    font-family: Arial, sans-serif;
    background: #111;
    color: #eee;
    text-align: center;
    padding-top: 20vh;
}
h2 {
    font-size: 25px;
}
p {
    color: #aaa;
    font-size: 16px;
}
.spinner {
    margin: 30px auto;
    width: 42px;
    height: 42px;
    border: 4px solid #444;
    border-top-color: #2196f3;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}
@keyframes spin {
    to { transform: rotate(360deg); }
}
</style>
</head>

<body>

<h2>Riavvio stampante in corso...</h2>
<div class="spinner"></div>

<p>Passaggio alla modalita __TITLE__.</p>

<p id="status">
Attendere, sto aspettando il riavvio della stampante...
</p>

<script>
const destination = "__URL__";
const probe = "__PROBE__";

function poll() {

    document.getElementById("status").textContent =
        "Verifica disponibilita del sistema...";

    var controller = new AbortController();

    var timeout = setTimeout(function () {
        controller.abort();
    }, 4000);

    fetch(probe, {
        mode: "no-cors",
        cache: "no-store",
        signal: controller.signal
    })
    .then(function () {

        clearTimeout(timeout);

        document.getElementById("status").textContent =
            "Sistema disponibile. Reindirizzamento...";

        setTimeout(function () {
            location.href = destination;
        }, 3000);

    })
    .catch(function () {

        clearTimeout(timeout);

        document.getElementById("status").textContent =
            "Stampante ancora in avvio. Attendere...";

        setTimeout(poll, 2000);

    });
}

// Attesa iniziale del riavvio
setTimeout(poll, 20000);
</script>
</body>
</html>
"""


# ============================================================
# ACCESS CONTROL
# ============================================================

def allowed_client(address):

    try:
        ip = ipaddress.ip_address(address)

        if str(ip) in ALLOWED_IPS:
            return True

        return any(
            ip in ipaddress.ip_network(net)
            for net in ALLOWED_NETWORKS
        )

    except ValueError:
        return False


# ============================================================
# TOOLCHANGES SYNCHRONIZATION
# ============================================================

def validate_toolchanges(content):

    if isinstance(content, bytes):
        content = content.decode("utf-8")

    if len(content.encode("utf-8")) > MAX_TOOLCHANGES_SIZE:
        raise ValueError("toolchanges.txt troppo grande")

    values = {}

    for line in content.splitlines():
        if not line.strip():
            continue

        match = re.fullmatch(
            r"\s*(Total|T[0-3])\s*:\s*(\d+)\s*",
            line
        )

        if not match:
            raise ValueError("Formato toolchanges.txt non valido")

        key = match.group(1)

        if key in values:
            raise ValueError("Valore duplicato in toolchanges.txt: " + key)

        values[key] = int(match.group(2))

    required = ("Total", "T0", "T1", "T2", "T3")

    if any(key not in values for key in required):
        raise ValueError("toolchanges.txt incompleto")

    if values["Total"] != sum(values[key] for key in ("T0", "T1", "T2", "T3")):
        raise ValueError("Total non corrisponde alla somma di T0-T3")

    return values


def atomic_write_toolchanges(path, content):

    data = content.encode("utf-8") if isinstance(content, str) else content
    validate_toolchanges(data)

    if not os.path.isfile(path):
        raise RuntimeError("File toolchanges.txt non trovato: " + path)

    with open(path, "rb") as f:
        previous = f.read(MAX_TOOLCHANGES_SIZE + 1)

    if previous == data:
        return False

    file_stat = os.stat(path)
    backup_path = path + ".bak"
    shutil.copy2(path, backup_path)

    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(
        prefix=".toolchanges-",
        suffix=".tmp",
        dir=directory
    )

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Preserve the original owner, group and permissions.
        os.chown(temporary_path, file_stat.st_uid, file_stat.st_gid)
        os.chmod(temporary_path, stat.S_IMODE(file_stat.st_mode))
        os.replace(temporary_path, path)

    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

    return True


def sync_toolchanges(target):

    if target == "soc":
        request = urllib.request.Request(
            RADXA_TOOLCHANGES_URL,
            headers={"Cache-Control": "no-cache"}
        )

        with urllib.request.urlopen(request, timeout=TOOLCHANGES_TIMEOUT) as response:
            content = response.read(MAX_TOOLCHANGES_SIZE + 1)

        validate_toolchanges(content)
        changed = atomic_write_toolchanges(TOOLCHANGES_FILE, content)

        print(
            "[API] toolchanges sincronizzato Radxa -> Creator (changed=%s)" % changed,
            flush=True
        )
        return

    if target == "tunneled":
        with open(TOOLCHANGES_FILE, "rb") as f:
            content = f.read(MAX_TOOLCHANGES_SIZE + 1)

        validate_toolchanges(content)

        request = urllib.request.Request(
            RADXA_TOOLCHANGES_URL,
            data=content,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=TOOLCHANGES_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))

        if not result.get("success"):
            raise RuntimeError("Il Radxa non ha confermato il salvataggio di toolchanges.txt")

        print(
            "[API] toolchanges sincronizzato Creator -> Radxa (changed=%s)"
            % result.get("changed"),
            flush=True
        )
        return

    raise ValueError("Invalid toolchanges sync target")



def validate_nozzle_hours(data):

    if isinstance(data, bytes):
        data = data.decode("utf-8")

    values = json.loads(data) if isinstance(data, str) else data

    if not isinstance(values, dict):
        raise ValueError("Formato nozzle_hours non valido")

    result = {}

    for key in NOZZLE_HOURS_KEYS:
        value = values.get(key)

        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Valore non valido per " + key)

        result[key] = value

    return result


def atomic_write_nozzle_hours(path, values):

    values = validate_nozzle_hours(values)

    if not os.path.isfile(path):
        raise RuntimeError("File variabili non trovato: " + path)

    with open(path, "r") as f:
        lines = f.readlines()

    found = dict((key, 0) for key in NOZZLE_HOURS_KEYS)
    updated = []

    for line in lines:
        replaced = False

        for key in NOZZLE_HOURS_KEYS:
            match = re.match(
                r"^(\s*" + re.escape(key) + r"\s*=\s*)\d+(\s*(?:#.*)?)(\r?\n)?$",
                line
            )

            if match:
                found[key] += 1
                newline = match.group(3) or ""
                updated.append(
                    match.group(1) + str(values[key]) +
                    match.group(2) + newline
                )
                replaced = True
                break

        if not replaced:
            updated.append(line)

    for key, count in found.items():
        if count != 1:
            raise ValueError(
                "La variabile %s deve comparire una sola volta (trovata %d)"
                % (key, count)
            )

    content = "".join(updated).encode("utf-8")

    with open(path, "rb") as f:
        previous = f.read()

    if previous == content:
        return False

    file_stat = os.stat(path)
    shutil.copy2(path, path + ".bak")

    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(
        prefix=".nozzle-hours-",
        suffix=".tmp",
        dir=directory
    )

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.chown(temporary_path, file_stat.st_uid, file_stat.st_gid)
        os.chmod(temporary_path, stat.S_IMODE(file_stat.st_mode))
        os.replace(temporary_path, path)

    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

    return True


def sync_nozzle_hours(target):

    if target == "soc":
        request = urllib.request.Request(
            RADXA_NOZZLE_HOURS_URL,
            headers={"Cache-Control": "no-cache"}
        )

        with urllib.request.urlopen(request, timeout=NOZZLE_HOURS_TIMEOUT) as response:
            data = response.read(4096)

        values = validate_nozzle_hours(data)
        changed = atomic_write_nozzle_hours(NOZZLE_HOURS_FILE, values)

        print(
            "[API] nozzle hours sincronizzati Radxa -> Creator (changed=%s)"
            % changed,
            flush=True
        )
        return

    if target == "tunneled":
        with open(NOZZLE_HOURS_FILE, "r") as f:
            lines = f.readlines()

        values = {}
        for line in lines:
            match = re.match(
                r"^\s*(nozzle_seconds_t[0-3])\s*=\s*(\d+)\s*$",
                line
            )
            if match:
                key = match.group(1)
                if key in values:
                    raise ValueError("Variabile duplicata: " + key)
                values[key] = int(match.group(2))

        if any(key not in values for key in NOZZLE_HOURS_KEYS):
            raise ValueError("Variabili nozzle hours incomplete")

        payload = json.dumps(values).encode("utf-8")
        request = urllib.request.Request(
            RADXA_NOZZLE_HOURS_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=NOZZLE_HOURS_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))

        if not result.get("success"):
            raise RuntimeError("Il Radxa non ha confermato il salvataggio nozzle hours")

        print(
            "[API] nozzle hours sincronizzati Creator -> Radxa (changed=%s)"
            % result.get("changed"),
            flush=True
        )
        return

    raise ValueError("Invalid nozzle hours sync target")


# ============================================================
# CONFIGURATION READER
# ============================================================

def read_config(name):

    if name not in CONFIG_FILES:
        raise ValueError("Configuration not allowed")

    path = os.path.join(CONFIG_DIR, CONFIG_FILES[name])

    with open(path, "r") as f:
        content = f.read()

    content = re.sub(
        r"/\*.*?\*/",
        "",
        content,
        flags=re.S
    )

    return json.loads(content)


# ============================================================
# PRINTER MODE
# ============================================================

def get_mode():

    tunnel_script = "/usr/data/opencreator/tunneled/tunneled.sh"

    # The executable bit is the single source of truth.
    executable = bool(os.stat(tunnel_script).st_mode & 0o111)
    mode = "tunneled" if executable else "soc"

    correct = MARKER if mode == "tunneled" else BACKUP
    wrong = BACKUP if mode == "tunneled" else MARKER

    correct_exists = os.path.exists(correct)
    wrong_exists = os.path.exists(wrong)

    if correct_exists and wrong_exists:
        os.unlink(wrong)

    elif wrong_exists and not correct_exists:
        os.replace(wrong, correct)

    elif not correct_exists and not wrong_exists:
        fd = os.open(correct, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(fd)

    return mode



def atomic_write_firmware_res(path, content, mtime_ns):

    if len(content) > MAX_FIRMWARE_RES_SIZE:
        raise ValueError("File calibrazione troppo grande: " + path)

    directory = os.path.dirname(path)
    old_info = os.stat(path) if os.path.isfile(path) else None

    fd, temporary_path = tempfile.mkstemp(
        prefix=".firmware-res-",
        suffix=".tmp",
        dir=directory
    )

    try:
        mode = stat.S_IMODE(old_info.st_mode) if old_info else 0o644
        os.fchmod(fd, mode)

        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

        if old_info:
            os.chown(temporary_path, old_info.st_uid, old_info.st_gid)
            atime_ns = old_info.st_atime_ns
            shutil.copy2(path, path + ".bak")
        else:
            atime_ns = mtime_ns

        os.utime(temporary_path, ns=(atime_ns, mtime_ns))
        os.replace(temporary_path, path)
        temporary_path = None

        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def sync_firmware_res(target):

    if not SYNC_FIRMWARE_RES:
        return

    import base64

    request = urllib.request.Request(
        RADXA_FIRMWARE_RES_URL,
        headers={"Cache-Control": "no-cache"}
    )

    with urllib.request.urlopen(request, timeout=FIRMWARE_RES_TIMEOUT) as response:
        remote_result = json.loads(response.read().decode("utf-8"))

    if not remote_result.get("success"):
        raise RuntimeError("Il Radxa non ha restituito i file firmwareRes")

    remote_files = remote_result.get("files")
    if not isinstance(remote_files, dict):
        raise ValueError("Risposta firmwareRes del Radxa non valida")

    for filename in FIRMWARE_RES_FILES:
        local_path = os.path.join(CONFIG_DIR, filename)
        local_exists = os.path.isfile(local_path)
        remote_info = remote_files.get(filename)

        if not isinstance(remote_info, dict):
            raise ValueError("Metadati remoti mancanti per " + filename)

        remote_exists = remote_info.get("exists") is True
        local_content = None
        local_mtime_ns = None
        remote_content = None
        remote_mtime_ns = None

        if local_exists:
            local_stat = os.stat(local_path)
            local_mtime_ns = local_stat.st_mtime_ns
            with open(local_path, "rb") as file:
                local_content = file.read(MAX_FIRMWARE_RES_SIZE + 1)
            if len(local_content) > MAX_FIRMWARE_RES_SIZE:
                raise ValueError("File locale troppo grande: " + filename)

        if remote_exists:
            remote_mtime_ns = remote_info.get("mtime_ns")
            if type(remote_mtime_ns) is not int or remote_mtime_ns < 0:
                raise ValueError("Timestamp remoto non valido: " + filename)

            remote_content = base64.b64decode(
                remote_info.get("data", ""),
                validate=True
            )
            if len(remote_content) > MAX_FIRMWARE_RES_SIZE:
                raise ValueError("File remoto troppo grande: " + filename)

        if not local_exists and not remote_exists:
            print("[API] firmwareRes: %s assente su entrambi, ignorato" % filename, flush=True)
            continue

        if local_exists and remote_exists:
            if local_content == remote_content:
                print("[API] firmwareRes: %s già identico" % filename, flush=True)
                continue

            if local_mtime_ns == remote_mtime_ns:
                raise RuntimeError(
                    "Conflitto firmwareRes: %s ha contenuti diversi e timestamp uguali" % filename
                )

            local_is_newer = local_mtime_ns > remote_mtime_ns
        else:
            local_is_newer = local_exists

        if local_is_newer:
            payload = json.dumps({
                "filename": filename,
                "mtime_ns": local_mtime_ns,
                "data": base64.b64encode(local_content).decode("ascii")
            }).encode("utf-8")

            upload = urllib.request.Request(
                RADXA_FIRMWARE_RES_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(upload, timeout=FIRMWARE_RES_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))

            if not result.get("success"):
                raise RuntimeError("Il Radxa non ha confermato " + filename)

            direction = "Creator -> Radxa"

        else:
            atomic_write_firmware_res(
                local_path,
                remote_content,
                remote_mtime_ns
            )
            direction = "Radxa -> Creator"

        print(
            "[API] firmwareRes sincronizzato: %s (%s)" % (filename, direction),
            flush=True
        )



def change_mode(target):

    if target not in ("tunneled", "soc"):
        raise ValueError("Invalid mode")

    current = get_mode()

    if current == "unknown":
        raise RuntimeError("Invalid mode marker state")

    if target == current:
        return False

    # Synchronize lifetime toolchange counters before changing mode markers.
    # Any transfer or validation error aborts the mode switch and reboot.
    sync_toolchanges(target)
    sync_nozzle_hours(target)
    sync_firmware_res(target)

    # Set permissions first, then reconcile mode markers.
    os.chmod(
        "/usr/data/opencreator/tunneled/tunneled.sh",
        0o755 if target == "tunneled" else 0o644
    )

    actual_mode = get_mode()

    if actual_mode != target:
        raise RuntimeError("Mode reconciliation failed: expected %s, got %s"
                           % (target, actual_mode))

    def reboot():

        time.sleep(5)

        subprocess.Popen(
            ["/sbin/reboot"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

    threading.Thread(
        target=reboot,
        daemon=True
    ).start()

    return True


# ============================================================
# SCREEN CONTROL
# ============================================================

def change_screen(screen):

    if screen not in ("grumpy", "helix"):
        raise ValueError("Invalid screen")

    with open(SCREEN_FILE, "w") as f:
        f.write(screen + "\n")

    return True


# ============================================================
# HTTP SERVER
# ============================================================

class APIHandler(BaseHTTPRequestHandler):

    server_version = "Creator5API/1.0"

    def log_message(self, fmt, *args):

        print(
            "[API] %s - %s" % (
                self.client_address[0],
                fmt % args
            ),
            flush=True
        )

    # --------------------------------------------------------
    # RESPONSE HELPERS
    # --------------------------------------------------------

    def send_json(self, code, data):

        body = json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ).encode("utf-8")

        self.send_response(code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, code, text):

        body = text.encode("utf-8")

        self.send_response(code)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, code, html):

        body = html.encode("utf-8")

        self.send_response(code)
        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def check_access(self):

        address = self.client_address[0]

        if not allowed_client(address):

            self.send_json(403, {
                "error": "Access denied",
                "client": address
            })

            return False

        return True

    def read_body(self):

        length = int(
            self.headers.get("Content-Length", "0")
        )

        if length > 4096:
            raise ValueError("Request too large")

        if length == 0:
            return {}

        data = self.rfile.read(length)

        if not data:
            return {}

        return json.loads(data.decode("utf-8"))

    # --------------------------------------------------------
    # MODE REDIRECT
    # --------------------------------------------------------

    def handle_go(self, action):

        config = GO[action]

        try:

            changed = change_mode(config["mode"])

            print(
                "[API] Mode switch: %s (changed=%s)"
                % (config["mode"], changed),
                flush=True
            )

            html = WAIT_PAGE

            html = html.replace(
                "__TITLE__",
                config["title"]
            )

            html = html.replace(
                "__URL__",
                config["url"]
            )

            html = html.replace(
                "__PROBE__",
                config["probe"]
            )

            self.send_html(200, html)

        except Exception as e:

            self.send_json(500, {
                "success": False,
                "error": str(e)
            })

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self):

        if not self.check_access():
            return

        path = urlparse(self.path).path.rstrip("/") or "/"

        # One-click mode switch + wait page + redirect
        action = path.strip("/")

        if action in GO:
            self.handle_go(action)
            return

        # Moonraker compatibility
        if path == "/status":

            mode = get_mode()

            if mode == "unknown":
                self.send_text(409, "unknown")
            else:
                self.send_text(
                    200,
                    "on" if mode == "tunneled" else "off"
                )

            return

        # Legacy mode activation (JSON)
        if path == "/on":
            self.handle_mode("tunneled")
            return

        if path == "/off":
            self.handle_mode("soc")
            return

        # API status
        if path == "/api/status":

            self.send_json(200, {
                "mode": get_mode(),
                "screen": self.get_screen()
            })

            return

        # Printer information
        if path == "/api/printer/info":

            self.send_json(200, {
                "hostname": platform.node(),
                "platform": platform.platform(),
                "python": platform.python_version(),
                "mode": get_mode()
            })

            return

        # Available configurations
        if path == "/api/config":

            self.send_json(200, {
                "available": list(CONFIG_FILES.keys())
            })

            return

        # Configuration files
        if path.startswith("/api/config/"):

            name = path.split("/")[-1]

            try:

                data = read_config(name)
                self.send_json(200, data)

            except ValueError as e:

                self.send_json(404, {
                    "error": str(e)
                })

            except Exception as e:

                self.send_json(500, {
                    "error": str(e)
                })

            return

        # Bed mesh
        if path == "/api/calibration/bed_mesh":

            try:

                with open(MESH_FILE, "r") as f:
                    self.send_text(200, f.read())

            except Exception as e:

                self.send_json(500, {
                    "error": str(e)
                })

            return

        # Calibration data
        if path == "/api/calibration/extruder":

            try:
                self.send_json(200, read_config("extruder"))

            except Exception as e:
                self.send_json(500, {"error": str(e)})

            return

        if path == "/api/calibration/zoffset":

            try:
                self.send_json(200, read_config("zoffset"))

            except Exception as e:
                self.send_json(500, {"error": str(e)})

            return

        # Available commands
        if path == "/api/commands":

            self.send_json(200, {
                "screens": ["grumpy", "helix"],
                "modes": ["tunneled", "soc"]
            })

            return

        self.send_json(404, {
            "error": "Endpoint not found"
        })

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(self):

        if not self.check_access():
            return

        path = urlparse(self.path).path.rstrip("/")

        if path == "/api/mode/tunneled":
            self.handle_mode("tunneled")
            return

        if path == "/api/mode/soc":
            self.handle_mode("soc")
            return

        if path == "/api/screen/grumpy":
            self.handle_screen("grumpy")
            return

        if path == "/api/screen/helix":
            self.handle_screen("helix")
            return


        if path == "/api/pitemp":

            try:
                length = int(self.headers.get("Content-Length", "0"))

                if length <= 0 or length > 32:
                    raise ValueError("Dimensione temperatura non valida")

                temperature = self.rfile.read(length).decode("utf-8").strip()

                if not temperature.isdigit():
                    raise ValueError("Valore temperatura non valido")

                value = int(temperature)

                if value <= 0 or value > 150000:
                    raise ValueError("Temperatura fuori intervallo")

                temporary_file = RADXA_TEMP_FILE + ".tmp"

                with open(temporary_file, "w") as f:
                    f.write(str(value) + "\n")
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(temporary_file, RADXA_TEMP_FILE)

                self.send_json(200, {
                    "success": True,
                    "temperature": value
                })

            except Exception as e:
                self.send_json(400, {
                    "success": False,
                    "error": str(e)
                })

            return




        self.send_json(404, {
            "error": "Endpoint not found"
        })

    # --------------------------------------------------------
    # ACTION HANDLERS
    # --------------------------------------------------------

    def handle_mode(self, target):

        try:

            changed = change_mode(target)

            self.send_json(200, {
                "success": True,
                "mode": target,
                "changed": changed,
                "reboot_scheduled": changed
            })

        except Exception as e:

            self.send_json(500, {
                "success": False,
                "error": str(e)
            })

    def handle_screen(self, screen):

        try:

            change_screen(screen)

            self.send_json(200, {
                "success": True,
                "screen": screen
            })

        except Exception as e:

            self.send_json(500, {
                "success": False,
                "error": str(e)
            })

    # --------------------------------------------------------
    # UTILITIES
    # --------------------------------------------------------

    def get_screen(self):

        try:

            with open(SCREEN_FILE, "r") as f:
                return f.read().strip()

        except Exception:
            return "unknown"


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    print("===================================")
    print(" FlashForge Creator 5 API Server")
    print("===================================")
    print("Listening on %s:%s" % (HOST, PORT))
    print("Authorized IPs:", ALLOWED_IPS)
    print("Mode:", get_mode())



    server = ThreadingHTTPServer(
        (HOST, PORT),
        APIHandler
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        pass

    finally:
        server.server_close()
