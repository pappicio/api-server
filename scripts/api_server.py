
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

API_CONFIG = {}
try:
    if os.path.isfile(API_CONFIG_FILE):
        with open(API_CONFIG_FILE, "r") as f:
            loaded_config = json.load(f)
        if isinstance(loaded_config, dict):
            API_CONFIG = loaded_config
except Exception as e:
    print("[API] Optional configuration unavailable: %s" % e, flush=True)

REMOTE_CANDIDATE = API_CONFIG.get("remote_host")

if RUNNER_MODE == "tunneled":
    runner_host = os.environ.get("OC_MOONRAKER_IP", "").strip()
    if runner_host:
        REMOTE_CANDIDATE = runner_host

RADXA_HOST = None
if REMOTE_CANDIDATE:
    try:
        RADXA_HOST = str(ipaddress.IPv4Address(REMOTE_CANDIDATE))
    except (ValueError, ipaddress.AddressValueError):
        RADXA_HOST = None

SYNC_FIRMWARE_RES = API_CONFIG.get("sync_firmware_res", False) is True

def get_creator_ip():
    targets = []
    if RADXA_HOST:
        targets.append((RADXA_HOST, 8765))
    targets.append(("1.1.1.1", 80))

    for target in targets:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            return sock.getsockname()[0]
        except OSError:
            pass
        finally:
            sock.close()

    return "127.0.0.1"

CREATOR_HOST = get_creator_ip()

def remote_host_available(timeout=2):
    if not RADXA_HOST:
        return False
    try:
        conn = socket.create_connection((RADXA_HOST, 8765), timeout=timeout)
        conn.close()
        return True
    except OSError:
        return False

REMOTE_HOST_ONLINE = remote_host_available()

BASE_DIR = "/usr/data/opencreator"
CONFIG_DIR = "/usr/data/firmwareRes/config"

SCREEN_FILE = os.path.join(BASE_DIR, "screen")
SCREEN_SCRIPT = os.path.join(BASE_DIR, "startup/scripts/40-screen.sh")

MARKER = os.path.join(BASE_DIR, "startup/tunneled")
BACKUP = os.path.join(BASE_DIR, "startup/tunneled_")

MESH_FILE = os.path.join(CONFIG_DIR, "levelData")

# Toolchange lifetime counter synchronization
TOOLCHANGES_FILE = "/usr/data/opencreator/klipper/config/toolchanges.txt"
RADXA_TOOLCHANGES_URL = ("http://%s:8765/api/toolchanges" % RADXA_HOST) if RADXA_HOST else None
TOOLCHANGES_TIMEOUT = 10
MAX_TOOLCHANGES_SIZE = 4096

# Nozzle lifetime synchronization
NOZZLE_HOURS_FILE = "/usr/data/opencreator/klipper/config/c5_misc_variables.cfg"
RADXA_NOZZLE_HOURS_URL = ("http://%s:8765/api/nozzle_hours" % RADXA_HOST) if RADXA_HOST else None
RADXA_FIRMWARE_RES_URL = ("http://%s:8765/api/firmware_res" % RADXA_HOST) if RADXA_HOST else None
FIRMWARE_RES_FILES = ("extruder.json", "zoffset.json")
FIRMWARE_RES_TIMEOUT = 15
MAX_FIRMWARE_RES_SIZE = 1024 * 1024
NOZZLE_HOURS_TIMEOUT = 10
NOZZLE_HOURS_KEYS = tuple("nozzle_seconds_t%d" % i for i in range(4))


# Radxa SoC temperature
RADXA_TEMP_FILE = "/tmp/radxa_soc_temp"


# Authorized clients

ALLOWED_IPS = {"127.0.0.1"}

if RADXA_HOST:
    ALLOWED_IPS.add(RADXA_HOST)

if CREATOR_HOST and CREATOR_HOST != "127.0.0.1":
    ALLOWED_IPS.add(CREATOR_HOST)

ALLOWED_NETWORKS_LIST = []

try:
    if CREATOR_HOST and CREATOR_HOST != "127.0.0.1":
        import subprocess

        interfaces = subprocess.check_output(
            ["ip", "-o", "-f", "inet", "addr", "show"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )

        for line in interfaces.splitlines():
            fields = line.split()
            if "inet" not in fields:
                continue

            address = fields[fields.index("inet") + 1]
            interface = ipaddress.ip_interface(address)

            if interface.ip == ipaddress.ip_address(CREATOR_HOST):
                network = str(interface.network)
                if network not in ALLOWED_NETWORKS_LIST:
                    ALLOWED_NETWORKS_LIST.append(network)

except Exception as e:
    print("[API] Unable to detect local LAN subnet: %s" % e, flush=True)

ALLOWED_NETWORKS = tuple(ALLOWED_NETWORKS_LIST)


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
        "url": "http://%s/" % (RADXA_HOST or CREATOR_HOST),
        "probe": "http://%s/" % (RADXA_HOST or CREATOR_HOST),
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
    if not remote_host_available():
        raise RuntimeError("Remote Host is not configured or reachable")

    if target == "tunneled":
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

    if target == "soc":
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
    if not remote_host_available():
        raise RuntimeError("Remote Host is not configured or reachable")

    if target == "tunneled":
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

    if target == "soc":
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


def sync_firmware_res(target, filenames=None):

    if not SYNC_FIRMWARE_RES:
        return

    if target not in ("soc", "tunneled"):
        raise ValueError("Invalid firmwareRes sync target")

    if not remote_host_available():
        raise RuntimeError("External Host is not configured or reachable")

    import base64

    request = urllib.request.Request(
        RADXA_FIRMWARE_RES_URL,
        headers={"Cache-Control": "no-cache"}
    )

    with urllib.request.urlopen(request, timeout=FIRMWARE_RES_TIMEOUT) as response:
        remote_result = json.loads(response.read().decode("utf-8"))

    if not remote_result.get("success"):
        raise RuntimeError("External Host did not return firmwareRes files")

    remote_files = remote_result.get("files")
    if not isinstance(remote_files, dict):
        raise ValueError("Invalid firmwareRes response from External Host")

    for filename in (filenames or FIRMWARE_RES_FILES):
        local_path = os.path.join(CONFIG_DIR, filename)
        local_exists = os.path.isfile(local_path)
        remote_info = remote_files.get(filename)

        if not isinstance(remote_info, dict):
            raise ValueError("Missing External Host metadata for " + filename)

        remote_exists = remote_info.get("exists") is True

        # SOC mode: Creator 5 is authoritative; upload to External Host.
        if target == "soc":
            if not local_exists:
                print("[API] firmwareRes: local source missing, skipped: " + filename, flush=True)
                continue

            local_stat = os.stat(local_path)
            with open(local_path, "rb") as file:
                local_content = file.read(MAX_FIRMWARE_RES_SIZE + 1)

            if len(local_content) > MAX_FIRMWARE_RES_SIZE:
                raise ValueError("Local firmwareRes file too large: " + filename)

            if remote_exists:
                remote_content = base64.b64decode(
                    remote_info.get("data", ""),
                    validate=True
                )
                if len(remote_content) > MAX_FIRMWARE_RES_SIZE:
                    raise ValueError("External Host firmwareRes file too large: " + filename)

                if remote_content == local_content:
                    print("[API] firmwareRes already identical: " + filename, flush=True)
                    continue

            payload = json.dumps({
                "filename": filename,
                "mtime_ns": local_stat.st_mtime_ns,
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
                raise RuntimeError("External Host did not confirm " + filename)

            print("[API] firmwareRes synced Creator 5 -> External Host: " + filename, flush=True)
            continue

        # Tunneled mode: External Host is authoritative; download locally.
        if not remote_exists:
            print("[API] firmwareRes: External Host source missing, skipped: " + filename, flush=True)
            continue

        remote_mtime_ns = remote_info.get("mtime_ns")
        if type(remote_mtime_ns) is not int or remote_mtime_ns < 0:
            raise ValueError("Invalid External Host timestamp: " + filename)

        remote_content = base64.b64decode(
            remote_info.get("data", ""),
            validate=True
        )
        if len(remote_content) > MAX_FIRMWARE_RES_SIZE:
            raise ValueError("External Host firmwareRes file too large: " + filename)

        if local_exists:
            with open(local_path, "rb") as file:
                local_content = file.read(MAX_FIRMWARE_RES_SIZE + 1)
            if len(local_content) > MAX_FIRMWARE_RES_SIZE:
                raise ValueError("Local firmwareRes file too large: " + filename)

            if local_content == remote_content:
                print("[API] firmwareRes already identical: " + filename, flush=True)
                continue

        atomic_write_firmware_res(
            local_path,
            remote_content,
            remote_mtime_ns
        )

        print("[API] firmwareRes synced External Host -> Creator 5: " + filename, flush=True)



def collect_synchronization():

    import base64

    mode = get_mode()

    with open(TOOLCHANGES_FILE, "rb") as f:
        toolchanges = f.read(MAX_TOOLCHANGES_SIZE + 1)

    validate_toolchanges(toolchanges)

    with open(NOZZLE_HOURS_FILE, "r") as f:
        lines = f.readlines()

    nozzle_values = {}

    for line in lines:
        match = re.match(
            r"^\s*(nozzle_seconds_t[0-3])\s*=\s*(\d+)\s*$",
            line
        )
        if match:
            key = match.group(1)
            if key in nozzle_values:
                raise ValueError("Duplicate nozzle hours variable: " + key)
            nozzle_values[key] = int(match.group(2))

    nozzle_values = validate_nozzle_hours(nozzle_values)

    firmware_files = {}

    for filename in FIRMWARE_RES_FILES:
        local_path = os.path.join(CONFIG_DIR, filename)

        if not os.path.isfile(local_path):
            firmware_files[filename] = {
                "exists": False,
                "mtime_ns": None,
                "data": None
            }
            continue

        file_stat = os.stat(local_path)

        with open(local_path, "rb") as f:
            content = f.read(MAX_FIRMWARE_RES_SIZE + 1)

        if len(content) > MAX_FIRMWARE_RES_SIZE:
            raise ValueError("Firmware calibration file too large: " + filename)

        firmware_files[filename] = {
            "exists": True,
            "mtime_ns": file_stat.st_mtime_ns,
            "data": base64.b64encode(content).decode("ascii")
        }

    creator_data = {
        "success": True,
        "mode": mode,
        "toolchanges": toolchanges.decode("utf-8"),
        "nozzle_hours": nozzle_values,
        "firmware_res": {
            "success": True,
            "files": firmware_files
        }
    }

    external = {
        "configured": bool(RADXA_HOST),
        "available": False,
        "toolchanges": None,
        "nozzle_hours": None,
        "firmware_res": None
    }

    if RADXA_HOST:
        external["available"] = remote_host_available(timeout=1)

    if external["available"]:
        endpoints = (
            ("toolchanges", RADXA_TOOLCHANGES_URL, "text"),
            ("nozzle_hours", RADXA_NOZZLE_HOURS_URL, "json"),
            ("firmware_res", RADXA_FIRMWARE_RES_URL, "json")
        )

        for name, url, response_type in endpoints:
            try:
                request = urllib.request.Request(
                    url,
                    headers={"Cache-Control": "no-cache"}
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    content = response.read()

                if response_type == "text":
                    external[name] = content.decode("utf-8")
                else:
                    external[name] = json.loads(content.decode("utf-8"))

            except Exception as exc:
                external[name] = {"_error": str(exc)}

    return {
        "success": True,
        "mode": mode,
        "sync_direction": (
            "Creator 5 -> External Host" if mode == "soc"
            else "External Host -> Creator 5" if mode == "tunneled"
            else None
        ),
        "creator": creator_data,
        "external_host": external,

        # Preserve the existing local-data fields for compatibility.
        "toolchanges": creator_data["toolchanges"],
        "nozzle_hours": creator_data["nozzle_hours"],
        "firmware_res": creator_data["firmware_res"]
    }


def change_mode(target):

    if target not in ("tunneled", "soc"):
        raise ValueError("Invalid mode")

    current = get_mode()

    if current == "unknown":
        raise RuntimeError("Invalid mode marker state")

    if target == current:
        return False

    # Synchronize data before changing mode when the External Host is available.
    if remote_host_available(timeout=1):
        print("[API] External Host online: synchronizing printer data", flush=True)
        sync_toolchanges(target)
        sync_nozzle_hours(target)
        if SYNC_FIRMWARE_RES:
            sync_firmware_res(target)
    else:
        print(
            "[API] External Host unavailable: continuing with local data",
            flush=True
        )

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
# LOCAL DASHBOARD AND PLUGIN INVENTORY
# ============================================================

DASHBOARD_DIR = "/usr/data/opencreator/plugins/api-server/frontend"
PLUGIN_DIR = "/usr/data/opencreator/plugins"
PLUGIN_CATALOG_FILE = "/usr/data/opencreator/plugin-manager/catalog.json"
PLUGIN_MANAGER_EXECUTABLE = "/usr/data/opencreator/plugin-manager/oc-plugin"
PLUGIN_INSTALL_LOCK = threading.Lock()
MOONRAKER_URL = "http://127.0.0.1:7125"
GIT_EXECUTABLE = "/opt/bin/git"


def dashboard_moonraker_data():
    objects = (
        "webhooks", "print_stats", "extruder", "heater_bed", "toolhead",
        "mcu", "mcu eboard", "mcu eheaterboard", "mcu levelboard",
        "temperature_sensor mainboard_mcu",
        "temperature_sensor toolhead_mcu"
    )
    from urllib.parse import quote
    query = "&".join(quote(name, safe="") for name in objects)
    request = urllib.request.Request(
        MOONRAKER_URL + "/printer/objects/query?" + query,
        headers={"Cache-Control": "no-cache"}
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("result", {}).get("status", {})


def dashboard_temperature(status, candidates):
    for name in candidates:
        value = status.get(name)
        if isinstance(value, dict) and isinstance(value.get("temperature"), (int, float)):
            return {"temperature": value["temperature"]}

    for name, value in status.items():
        lowered = name.lower()
        if any(candidate in lowered for candidate in candidates):
            if isinstance(value, dict) and isinstance(value.get("temperature"), (int, float)):
                return {"temperature": value["temperature"]}

    return None


def dashboard_external_host_temperature():
    try:
        with open(RADXA_TEMP_FILE, "r") as f:
            value = float(f.read().strip())
        return {"temperature": value / 1000.0}
    except (OSError, ValueError):
        return None


def collect_dashboard():
    status = {}
    moonraker_error = None

    try:
        status = dashboard_moonraker_data()
    except Exception as error:
        moonraker_error = str(error)

    webhooks = status.get("webhooks", {})
    print_stats = status.get("print_stats", {})
    printer_connected = (
        isinstance(webhooks, dict)
        and str(webhooks.get("state", "")).lower() == "ready"
    )

    mcus = {}
    for name in ("mcu", "mcu eboard", "mcu eheaterboard", "mcu levelboard"):
        info = status.get(name)
        connected = isinstance(info, dict) and bool(info)
        mcus[name] = {
            "connected": connected,
            "chip": (
                (info.get("mcu_constants") or {}).get("MCU")
                if connected else None
            )
        }

    try:
        mode = get_mode()
    except Exception:
        mode = "unknown"

    try:
        screen = open(SCREEN_FILE, "r").read().strip()
    except Exception:
        screen = "unknown"

    temperatures = {
        "external_host": dashboard_external_host_temperature(),
        "mainboard": dashboard_temperature(status, (
            "temperature_sensor mainboard_mcu",
        )),
        "toolhead": dashboard_temperature(status, (
            "temperature_sensor toolhead_mcu",
        )),
        "nozzle": dashboard_temperature(status, ("extruder",)),
        "bed": dashboard_temperature(status, ("heater_bed",))
    }

    return {
        "printer": {
            "connected": printer_connected,
            "state": webhooks.get("state", "Disconnected"),
            "print": {"state": print_stats.get("state", "Unknown")}
        },
        "creator": {
            "reachable": True,
            "screen": screen
        },
        "soc": {"mode": mode},
        "external_host": {
            "configured": bool(RADXA_HOST),
            "reachable": (
                remote_host_available(timeout=1) if RADXA_HOST else False
            )
        },
        "temperatures": temperatures,
        "mcus": mcus,
        "errors": {"moonraker": moonraker_error}
    }


def load_plugin_catalog():
    try:
        with open(PLUGIN_CATALOG_FILE, "r") as f:
            data = json.load(f)
        entries = data.get("plugins", [])
        return {
            item["id"]: item
            for item in entries
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
        }
    except Exception as error:
        print("[API] Plugin catalog unavailable: %s" % error, flush=True)
        return {}


def collect_plugins():
    catalog = load_plugin_catalog()
    plugins = []

    try:
        entries = sorted(os.listdir(PLUGIN_DIR))
    except OSError:
        entries = []

    for plugin_id in entries:
        if plugin_id.startswith("."):
            continue

        directory = os.path.join(PLUGIN_DIR, plugin_id)
        if not os.path.isdir(directory):
            continue

        metadata = catalog.get(plugin_id, {})
        has_git = os.path.isdir(os.path.join(directory, ".git")) or os.path.isfile(
            os.path.join(directory, ".git")
        )

        plugins.append({
            "id": plugin_id,
            "name": metadata.get("name", plugin_id.replace("-", " ").replace("_", " ").title()),
            "description": metadata.get("description", ""),
            "author": metadata.get("author", ""),
            "official": metadata.get("official", False),
            "repository": metadata.get("url", ""),
            "note": metadata.get("note", ""),
            "installed": True,
            "trackable": bool(has_git and metadata.get("url")),
            "update_status": "not_checked"
        })

    available = [
        {"id": k, "name": v.get("name", k),
         "description": v.get("description", ""),
         "author": v.get("author", ""),
         "official": v.get("official", False),
         "repository": v.get("url", ""), "note": v.get("note", "")}
        for k, v in sorted(catalog.items())
        if v.get("url") and not os.path.isdir(os.path.join(PLUGIN_DIR, k))
    ]
    return {"success": True, "plugins": plugins, "available": available}


def normalize_repository_url(value):
    return str(value or "").strip().rstrip("/").removesuffix(".git").lower()


def check_plugin_updates(plugin_id):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", plugin_id):
        return 400, {"success": False, "status": "not_trackable", "error": "Invalid plugin ID"}

    catalog = load_plugin_catalog()
    metadata = catalog.get(plugin_id)
    directory = os.path.join(PLUGIN_DIR, plugin_id)

    if not metadata or not os.path.isdir(directory):
        return 404, {"success": False, "status": "not_trackable", "error": "Plugin is not catalogued or installed"}

    if not os.path.exists(os.path.join(directory, ".git")):
        return 200, {"success": True, "status": "not_trackable", "error": "No Git repository"}

    if not os.path.isfile(GIT_EXECUTABLE):
        return 200, {"success": False, "status": "unable_to_check", "error": "Git executable unavailable"}

    repository = metadata.get("url", "")
    try:
        def git(*args):
            return subprocess.check_output(
                [GIT_EXECUTABLE, "-C", directory] + list(args),
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                timeout=5
            ).strip()

        local_commit = git("rev-parse", "HEAD")
        branch = git("branch", "--show-current")
        origin = git("remote", "get-url", "origin")
        dirty = bool(git("status", "--porcelain"))

        if not branch:
            return 200, {
                "success": True, "status": "not_trackable",
                "error": "Detached HEAD", "local_commit": local_commit,
                "dirty": dirty
            }

        if normalize_repository_url(origin) != normalize_repository_url(repository):
            return 200, {
                "success": True, "status": "not_trackable",
                "error": "Git origin does not match the plugin catalog",
                "local_commit": local_commit, "branch": branch, "dirty": dirty
            }

        remote_output = subprocess.check_output(
            [GIT_EXECUTABLE, "ls-remote", repository, "refs/heads/" + branch],
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            timeout=10
        ).strip()

        remote_commit = remote_output.split()[0] if remote_output else None
        if not remote_commit:
            return 200, {
                "success": False, "status": "unable_to_check",
                "error": "Remote branch not found",
                "local_commit": local_commit, "branch": branch, "dirty": dirty
            }

        return 200, {
            "success": True,
            "status": "update_available" if remote_commit != local_commit else "up_to_date",
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "branch": branch,
            "dirty": dirty
        }

    except subprocess.TimeoutExpired:
        return 200, {"success": False, "status": "unable_to_check", "error": "Git operation timed out"}
    except Exception as error:
        return 200, {"success": False, "status": "unable_to_check", "error": str(error)}


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

        # Dashboard frontend assets.
        dashboard_assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
            "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8")
        }
        if path in dashboard_assets:
            filename, content_type = dashboard_assets[path]
            asset_path = os.path.join(DASHBOARD_DIR, filename)
            try:
                with open(asset_path, "rb") as asset:
                    body = asset.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_json(404, {"error": "Dashboard asset not found"})
            return

        if path == "/api/dashboard":
            try:
                self.send_json(200, collect_dashboard())
            except Exception as error:
                self.send_json(500, {"success": False, "error": str(error)})
            return

        if path == "/api/plugins":
            self.send_json(200, collect_plugins())
            return

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

        # External Host status for the web interface
        if path == "/api/external-host":

            available = remote_host_available(timeout=1)

            self.send_json(200, {
                "configured": bool(RADXA_HOST),
                "available": bool(available),
                "url": (
                    "http://%s:8765/" % RADXA_HOST
                    if RADXA_HOST else None
                )
            })

            return

        # Synchronization state
        if path == "/api/synchronization":

            try:
                self.send_json(200, collect_synchronization())
            except Exception as e:
                self.send_json(500, {
                    "success": False,
                    "error": str(e)
                })

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

        install_match = re.fullmatch(
            r"/api/plugins/([a-zA-Z0-9_.-]+)/install", path
        )
        if install_match:
            pid = install_match.group(1)
            item = load_plugin_catalog().get(pid)
            if not item or not item.get("url"):
                self.send_json(404, {"success": False, "error": "Unknown plugin"})
                return
            if os.path.isdir(os.path.join(PLUGIN_DIR, pid)):
                self.send_json(409, {"success": False, "error": "Already installed"})
                return
            if not PLUGIN_INSTALL_LOCK.acquire(False):
                self.send_json(409, {"success": False, "error": "Installation already running"})
                return
            try:
                result = subprocess.run(
                    [PLUGIN_MANAGER_EXECUTABLE, "install", item["url"]],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True, timeout=1800
                )
                output = (result.stdout or "")[-8000:]
                self.send_json(200 if result.returncode == 0 else 500, {
                    "success": result.returncode == 0, "plugin_id": pid,
                    "output": output, "error": "" if result.returncode == 0 else output
                })
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
            finally:
                PLUGIN_INSTALL_LOCK.release()
            return

        plugin_match = re.fullmatch(
            r"/api/plugins/([a-zA-Z0-9_.-]+)/check-updates", path
        )
        if plugin_match:
            code, result = check_plugin_updates(plugin_match.group(1))
            self.send_json(code, result)
            return

        # Manual synchronization
        if path.startswith("/api/synchronization/"):

            item = path.rsplit("/", 1)[-1]

            if item not in (
                "toolchanges",
                "nozzle_hours",
                "extruder",
                "zoffset"
            ):
                self.send_json(404, {
                    "success": False,
                    "error": "Unknown synchronization item"
                })
                return

            try:
                mode = get_mode()

                if mode not in ("soc", "tunneled"):
                    raise RuntimeError("Printer mode is unknown")

                if item == "toolchanges":
                    sync_toolchanges(mode)

                elif item == "nozzle_hours":
                    sync_nozzle_hours(mode)

                else:
                    if not SYNC_FIRMWARE_RES:
                        raise RuntimeError(
                            "Firmware calibration synchronization is disabled"
                        )

                    filename = item + ".json"
                    sync_firmware_res(mode, (filename,))

                self.send_json(200, {
                    "success": True,
                    "item": item,
                    "mode": mode
                })

            except Exception as e:
                message = str(e)
                status = 409 if "Conflitto" in message or "Conflict" in message else 500

                self.send_json(status, {
                    "success": False,
                    "item": item,
                    "error": message
                })

            return

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
