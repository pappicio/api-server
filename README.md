# OpenCreator API Server

OpenCreator API Server is a modular API and dashboard component for the FlashForge Creator 5 running OpenCreator.

It provides local printer APIs, a web dashboard, configuration and calibration access, screen management, and SoC / Tunneled mode switching.

It can operate independently on the Creator 5. A remote Linux host is optional and is only required for features that depend on remote monitoring and synchronization.

## Features

- Web dashboard served directly by the API Server.
- Local printer status and information.
- Printer configuration access.
- Firmware calibration file access and synchronization.
- SoC / Tunneled mode switching.
- GrumpyScreen and HelixScreen switching.
- External Host connectivity and status monitoring.
- Toolchange counter and nozzle usage synchronization.
- Optional firmware calibration synchronization.
- Installed plugin discovery and update information.
- Local operation when the External Host is unavailable.

## Architecture

The integration consists of two independent components.

| Component | Device | Responsibility |
|---|---|---|
| OpenCreator API Server | FlashForge Creator 5 | Local APIs, dashboard, printer management and mode switching |
| Mode Monitor | Raspberry Pi, Radxa ZERO 3W or compatible Linux host | Remote monitoring, synchronization endpoints and External Host integration |

Repository for the companion component:

https://github.com/pappicio/Raspberry-C5-klipper_mode_monitor

Both components are needed for the complete Creator 5 / remote host integration. However, the API Server does not require the remote component to provide its local functionality.

### Standalone operation

The API Server continues operating when the External Host is:

- Not configured.
- Offline or unreachable.
- Temporarily unavailable.

Local dashboard data, printer APIs, configuration access, calibration access and local controls remain available.

Only features requiring the remote host are unavailable or skipped. Remote connectivity problems must not prevent the Creator 5 from operating in SoC mode.

## Requirements

- FlashForge Creator 5 running OpenCreator.
- Script Runner installed and working on the Creator 5.
- Python available at `/usr/data/python-hf/bin/python3`.
- Moonraker available locally on port `7125`.

For remote integration:

- Raspberry Pi, Radxa ZERO 3W or compatible Linux host.
- Mode Monitor installed and running on the remote host.
- Network connectivity between the Creator 5 and the remote host.

## Installation

Install the API Server plugin on the Creator 5 using the OpenCreator plugin installation mechanism.

The plugin includes:

- `install.sh`
- `update.sh`
- `uninstall.sh`
- `scripts/api_server.py`
- `frontend/`

The installer checks the required Creator 5 dependencies, installs the API Server files and configures the optional remote host integration.

Script Runner is required to execute the API Server in the Creator 5 runtime.

A remote host is not mandatory for installation or local operation.

### External Host configuration

The API Server configuration is stored in:

```text
/usr/data/opencreator/api-server.json
```

Example:

```json
{
    "remote_host": "192.168.1.197",
    "sync_firmware_res": true
}
```

- `remote_host`: IP address of the remote Linux host. Remote integration is unavailable when no host is configured or reachable.
- `sync_firmware_res`: enables or disables firmware calibration synchronization.

The remote host is optional. Its absence does not disable the local API Server.

## Dashboard

The API Server includes a web dashboard served by its existing HTTP server.

Open:

```text
http://CREATOR_IP:8765/
```

The dashboard uses the same API Server process and port. It does not start a separate web server.

The dashboard provides access to local printer information, configuration, calibration, mode controls, screen controls, External Host status and synchronization information.

### External Host status

The dashboard reports whether the remote host is configured and reachable.

Remote-dependent information and actions are handled independently from local printer functionality.

When the External Host is unavailable, the dashboard remains usable and local controls remain available.

### Mode controls

The dashboard provides controls for switching between:

- SoC mode.
- Tunneled mode.

The Tunneled mode action requires a reachable External Host. When the host is unavailable, the control remains visible but disabled.

The SoC mode control is available when the current mode permits the transition.

### Screen controls

The dashboard provides controls for switching between:

- GrumpyScreen.
- HelixScreen.

### Plugin information

The dashboard can discover installed plugins by reading their manifests under:

```text
/usr/data/opencreator/plugins/
```

Plugin manifests use the `opencreator-plugin.json` format.

The dashboard can present installed plugin information and available version/update information.

Plugin installation, updating and removal remain the responsibility of the official OpenCreator Plugin Manager. The API Server does not replace or modify the plugin manager.

## Script Runner

Script Runner executes the API Server script in the Creator 5 runtime.

The runtime script is installed at:

```text
/usr/data/opencreator/scripts/api_server.py
```

The API Server uses the existing HTTP server on port `8765`.

The dashboard and API endpoints share the same server and process.

## Mode switching

The API Server exposes mode-switching endpoints:

- `GET /go_tunneled`
- `GET /go_soc`
- `POST /api/mode/tunneled`
- `POST /api/mode/soc`

The browser endpoints initiate the requested transition and provide the corresponding waiting and redirection behavior.

The POST endpoints are used by the dashboard controls.

### Switch to Tunneled mode

The Creator 5 initiates the transition to Tunneled mode.

When the remote host is available, the API Server coordinates the required synchronization before scheduling the transition.

After the transition, the browser can be redirected to the remote Klipper interface.

### Switch to SoC mode

The remote integration can request a transition back to SoC mode through the Creator 5 API Server.

When the remote host is available, synchronization is performed before the transition.

The Creator 5 then schedules the required reboot and returns to its local interface.

### Legacy mode endpoints

The following endpoints remain available for compatibility:

- `/on`
- `/off`

## Data synchronization

The API Server coordinates synchronization between the Creator 5 and the remote Mode Monitor.

Supported data includes:

| Data | Description |
|---|---|
| Toolchange counters | Synchronization of toolchange counts |
| Nozzle usage | Synchronization of cumulative nozzle usage hours |
| Firmware calibration | Optional synchronization of supported calibration files |
| External Host temperature | Remote system temperature information |

Remote synchronization is skipped when the External Host is unavailable.

### Toolchange counters

Creator 5 toolchange data is stored in:

```text
/usr/data/opencreator/klipper/config/toolchanges.txt
```

The remote Mode Monitor provides the corresponding synchronization API.

### Nozzle usage

Nozzle lifetime counters are stored in:

```text
/usr/data/opencreator/klipper/config/c5_misc_variables.cfg
```

The supported variables are:

- `nozzle_seconds_t0`
- `nozzle_seconds_t1`
- `nozzle_seconds_t2`
- `nozzle_seconds_t3`

The remote Mode Monitor provides the corresponding nozzle usage API.

### Firmware calibration synchronization

Firmware calibration synchronization is optional and controlled by:

```json
"sync_firmware_res": true
```

The Creator 5 calibration directory is:

```text
/usr/data/firmwareRes/config/
```

Supported files:

- `extruder.json`
- `zoffset.json`

`test.json` is intentionally excluded.

Synchronization compares file modification timestamps and transfers the newest version. Original timestamps are preserved, file replacement is atomic, and conflicts are reported rather than silently overwriting files.

When synchronization is disabled, no firmware calibration transfer is performed.

The remote Mode Monitor must support the following endpoints:

```text
GET  /api/firmware_res
POST /api/firmware_res
```

## API endpoints

The API Server listens on:

```text
0.0.0.0:8765
```

The following endpoints are provided by the Creator 5 API Server.

### Status and information

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/status` | Current mode status |
| GET | `/api/status` | API status information |
| GET | `/api/external-host` | External Host configuration and availability |
| GET | `/api/printer/info` | Printer information |
| GET | `/api/config` | Printer configuration |
| GET | `/api/config/` | Configuration access |
| GET | `/api/synchronization` | Synchronization status |

### Calibration

The API provides calibration access through:

```text
/api/calibration/
```

Supported calibration resources include:

- `bed_mesh`
- `extruder`
- `zoffset`

### Mode and screen controls

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/go_tunneled` | Initiate Tunneled mode transition |
| GET | `/go_soc` | Initiate SoC mode transition |
| POST | `/api/mode/tunneled` | Request Tunneled mode |
| POST | `/api/mode/soc` | Request SoC mode |
| POST | `/api/screen/grumpy` | Switch to GrumpyScreen |
| POST | `/api/screen/helix` | Switch to HelixScreen |

### Synchronization and commands

The API also provides:

- `/api/synchronization`
- `/api/commands`
- `/api/pitemp`

`POST /api/pitemp` receives remote host temperature information.

The companion Mode Monitor provides its own synchronization endpoints, including:

```text
/api/toolchanges
/api/nozzle_hours
/api/firmware_res
```

Both components use port `8765` on their respective devices. There is no port conflict.

## Update

Use the OpenCreator Plugin Manager to update the API Server.

The updater:

- Updates the API Server source files.
- Preserves the existing runtime configuration.
- Restarts Script Runner as required.

The updater does not manage personal Klipper configuration, navigation files or user-defined macros.

## Uninstallation

Use the OpenCreator Plugin Manager to remove the API Server.

The uninstaller removes the plugin-managed API Server files and runtime integration.

It does not remove Script Runner or modify unrelated user configuration.

The following configuration is preserved:

```text
/usr/data/opencreator/api-server.json
```

Personal Klipper configuration, macros and navigation entries are not managed by the API Server installer or uninstaller.

## Troubleshooting

### Dashboard is not responding

Check that Script Runner is installed and running.

Confirm that the runtime script exists:

```text
/usr/data/opencreator/scripts/api_server.py
```

Check that port `8765` is listening on the Creator 5.

### External Host is unavailable

Check the `remote_host` value in:

```text
/usr/data/opencreator/api-server.json
```

Verify network connectivity and confirm that Mode Monitor is running on the remote host.

Local API Server functionality does not depend on remote connectivity.

### Mode switching to Tunneled fails

Confirm that the External Host is configured and reachable.

Verify that the remote Mode Monitor service is running and that the required synchronization endpoints are available.

### Screen switching fails

Check that the requested screen is installed and that its corresponding runtime service is available.

### Calibration synchronization fails

Check that `sync_firmware_res` is enabled and that the remote Mode Monitor supports:

```text
GET  /api/firmware_res
POST /api/firmware_res
```

## License

See the repository license.