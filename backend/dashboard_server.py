#!/usr/bin/env python3

import json
import logging
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import quote, unquote, urlsplit, parse_qs
from custom_projects import collect_custom_projects
from urllib.request import urlopen

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
ASSETS_DIR = BASE_DIR / "assets"

HOST = "0.0.0.0"
PORT = 8765

MOONRAKER = "http://127.0.0.1:7125"
SOC_MONITOR = "http://127.0.0.1:8765"
def load_creator_api():
    config_path = BASE_DIR / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        creator_ip = str(
            __import__("ipaddress").IPv4Address(config["creator_ip"])
        )
        return f"http://{creator_ip}:8765"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Unable to load Creator API address from {config_path}: {exc}"
        ) from exc


CREATOR_API = load_creator_api()

OBJECTS = [
    "webhooks", "print_stats", "extruder", "heater_bed", "toolhead",
    "mcu", "mcu eboard", "mcu eheaterboard", "mcu levelboard",
    "temperature_host OrangePi3W_mcu",
    "temperature_sensor mainboard_mcu",
    "temperature_sensor toolhead_mcu",
    "heater_fan heat_fan", "heater_fan heat_fan1",
    "heater_fan heat_fan2", "heater_fan heat_fan3",
    "fan_generic pcb_fan", "fan_generic heat_ctl_fan",
    "fan_generic fanM106",
]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)


def fetch_json(url, timeout=4):
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, OSError, ValueError) as exc:
        return {"_error": str(exc)}


def fetch_text(url, timeout=3):
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.read().decode("utf-8").strip()
    except (URLError, HTTPError, TimeoutError, OSError) as exc:
        return None


def collect_dashboard():
    query = "&".join(quote(name, safe="") for name in OBJECTS)
    printer_data = fetch_json(
        f"{MOONRAKER}/printer/objects/query?{query}"
    )
    printer_status = printer_data.get("result", {}).get("status", {})

    server_info = fetch_json(f"{MOONRAKER}/server/info")
    update_data = fetch_json(f"{MOONRAKER}/machine/update/status", 10)

    creator = fetch_json(f"{CREATOR_API}/api/status")
    soc_mode = fetch_text(f"{SOC_MONITOR}/status")

    mcu_names = [
        "mcu", "mcu eboard", "mcu eheaterboard", "mcu levelboard"
    ]

    fan_names = [
        "heater_fan heat_fan", "heater_fan heat_fan1",
        "heater_fan heat_fan2", "heater_fan heat_fan3",
        "fan_generic pcb_fan", "fan_generic heat_ctl_fan",
        "fan_generic fanM106",
    ]

    temperatures = {
        "external_host": printer_status.get("temperature_host OrangePi3W_mcu"),
        "radxa": printer_status.get("temperature_host OrangePi3W_mcu"),
        "mainboard": printer_status.get("temperature_sensor mainboard_mcu"),
        "toolhead": printer_status.get("temperature_sensor toolhead_mcu"),
        "nozzle": printer_status.get("extruder"),
        "bed": printer_status.get("heater_bed"),
    }

    mcus = {
        name: {
            "connected": name in printer_status,
            "chip": printer_status.get(name, {}).get(
                "mcu_constants", {}
            ).get("MCU"),
        }
        for name in mcu_names
    }

    fans = {
        name: {
            "power": printer_status.get(name, {}).get("power"),
            "speed": printer_status.get(name, {}).get("speed"),
        }
        for name in fan_names
    }

    versions = update_data.get("result", {}).get("version_info", {})
    updates = []

    for name, info in versions.items():
        behind = info.get("commits_behind_count", 0)
        updates.append({
            "name": name,
            "version": info.get("version"),
            "remote_version": info.get("remote_version"),
            "commits_behind": behind,
            "dirty": info.get("is_dirty", False),
            "error": info.get("last_error", ""),
            "warnings": info.get("warnings", []),
        })

    mode = creator.get("mode")
    if mode not in ("stock", "tunneled"):
        mode = None

    soc = {
        "mode": (
            "tunneled" if soc_mode == "on"
            else "stock" if soc_mode == "off"
            else None
        ),
        "reachable": soc_mode is not None,
    }

    return {
        "printer": {
            "connected": server_info.get("result", {}).get(
                "klippy_connected", False
            ),
            "state": server_info.get("result", {}).get(
                "klippy_state", "unknown"
            ),
            "print": printer_status.get("print_stats", {}),
            "webhooks": printer_status.get("webhooks", {}),
        },
        "temperatures": temperatures,
        "external_host_name": socket.gethostname(),
        "mcus": mcus,
        "fans": fans,
        "creator": {
            "reachable": "_error" not in creator,
            "mode": mode,
            "screen": creator.get("screen"),
        },
        "soc": soc,
        "updates": updates,
        "update_manager_busy": update_data.get("result", {}).get(
            "busy", False
        ),
        "errors": {
            "printer": printer_data.get("_error"),
            "updates": update_data.get("_error"),
        },
    }


def collect_synchronization():
    """Read-only comparison between the External Host and Creator 5."""
    external = {
        "toolchanges": fetch_text(f"{SOC_MONITOR}/api/toolchanges", 5),
        "nozzle_hours": fetch_json(f"{SOC_MONITOR}/api/nozzle_hours", 5),
        "firmware_res": fetch_json(f"{SOC_MONITOR}/api/firmware_res", 10),
    }

    mode_text = fetch_text(f"{SOC_MONITOR}/status", 4)
    mode = (
        "tunneled" if mode_text == "on"
        else "soc" if mode_text == "off"
        else None
    )

    creator = fetch_json(f"{CREATOR_API}/api/synchronization", 10)

    return {
        "success": True,
        "mode": mode,
        "sync_direction": (
            "External Host → Creator 5" if mode == "soc"
            else "Creator 5 → External Host" if mode == "tunneled"
            else None
        ),
        "external_host": external,
        "creator": creator,
    }


class DashboardHandler(BaseHTTPRequestHandler):

    def send_data(self, code, content, content_type):
        body = content if isinstance(content, bytes) else content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urlsplit(self.path)
        path = unquote(parsed_url.path)

        if path == "/api/go-soc":
            self.send_response(302)
            self.send_header("Location", f"{CREATOR_API}/go_soc")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        if path == "/api/custom-projects":
            force = parse_qs(parsed_url.query).get("refresh", ["0"])[0] == "1"
            data = collect_custom_projects(force=force)
            self.send_data(
                200,
                json.dumps(data, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
            return

        if path == "/api/synchronization":
            data = collect_synchronization()
            self.send_data(
                200,
                json.dumps(data, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
            return

        if path == "/api/dashboard":
            data = collect_dashboard()
            self.send_data(
                200,
                json.dumps(data, ensure_ascii=False),
                "application/json; charset=utf-8",
            )
            return

        if path == "/":
            path = "/index.html"

        if path.startswith("/assets/"):
            file_path = ASSETS_DIR / path.removeprefix("/assets/")
        else:
            file_path = FRONTEND_DIR / path.lstrip("/")

        try:
            resolved = file_path.resolve()
            if not resolved.is_relative_to(BASE_DIR.resolve()):
                raise ValueError("Invalid path")
            if not resolved.is_file():
                raise FileNotFoundError()
            content_type = (
                "text/css; charset=utf-8" if resolved.suffix == ".css"
                else "application/javascript; charset=utf-8"
                if resolved.suffix == ".js"
                else "text/html; charset=utf-8"
                if resolved.suffix == ".html"
                else "application/octet-stream"
            )
            self.send_data(200, resolved.read_bytes(), content_type)
        except (OSError, ValueError):
            self.send_data(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = unquote(urlsplit(self.path).path)
        sync_items = {
            "toolchanges",
            "nozzle_hours",
            "extruder",
            "zoffset",
        }
        sync_prefix = "/api/synchronization/"

        if path.startswith(sync_prefix):
            item = path[len(sync_prefix):]
            if item not in sync_items:
                self.send_data(
                    404,
                    json.dumps({"success": False, "error": "Unknown sync item"}),
                    "application/json; charset=utf-8",
                )
                return

            request = __import__(
                "urllib.request", fromlist=["Request"]
            ).Request(
                f"{CREATOR_API}/api/synchronization/{item}",
                data=b"",
                headers={"Content-Length": "0"},
                method="POST",
            )

            try:
                with urlopen(request, timeout=30) as response:
                    self.send_data(
                        response.status,
                        response.read(),
                        response.headers.get(
                            "Content-Type",
                            "application/json; charset=utf-8",
                        ),
                    )
            except (URLError, HTTPError, TimeoutError, OSError) as exc:
                self.send_data(
                    502,
                    json.dumps({"success": False, "error": str(exc)}),
                    "application/json; charset=utf-8",
                )
            return

        screen_routes = {
            "/api/screen/grumpy": "grumpy",
            "/api/screen/helix": "helix",
        }

        screen = screen_routes.get(path)
        if screen is None:
            self.send_data(
                404,
                json.dumps({"success": False, "error": "Not found"}),
                "application/json; charset=utf-8",
            )
            return

        request = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{CREATOR_API}/api/screen/{screen}",
            data=b"",
            headers={"Content-Length": "0"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=10) as response:
                body = response.read()
                content_type = response.headers.get(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_data(response.status, body, content_type)
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            self.send_data(
                502,
                json.dumps({"success": False, "error": str(exc)}),
                "application/json; charset=utf-8",
            )

    def log_message(self, fmt, *args):
        logging.info("%s - %s", self.address_string(), fmt % args)


if __name__ == "__main__":
    logging.info("OpenCreator Dashboard listening on %s:%s", HOST, PORT)
    ThreadingHTTPServer((HOST, PORT), DashboardHandler).serve_forever()
