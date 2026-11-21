# OpenCreator API Server

API Server is the Creator 5 component of the Creator 5 / Radxa ZERO 3W Klipper mode switching integration.

It provides the HTTP API used to switch between Creator 5 SoC mode and Tunneled mode, synchronize printer data, and redirect the browser to the active Klipper interface.

## Architecture

The integration consists of two components:

- **OpenCreator API Server** runs on the FlashForge Creator 5.
- **klipper_mode_monitor** runs on the Radxa ZERO 3W.

Both services use TCP port 8765, but run on different devices. There is no port conflict.

Example network configuration:

| Device | Example IP | Service |
|---|---|---|
| Creator 5 | 192.168.1.194 | API Server, port 8765 |
| Radxa ZERO 3W | 192.168.1.197 | klipper_mode_monitor, port 8765 |

Use the actual static IP addresses configured on your network.

## Requirements

- FlashForge Creator 5 running OpenCreator.
- Script Runner installed and working on the Creator 5.
- Radxa ZERO 3W running klipper_mode_monitor.
- Both devices reachable over the local network.
- Python available at /usr/data/python-hf/bin/python3 on the Creator 5.
- Moonraker available locally on port 7125.

Install and configure the Radxa component before testing the complete integration.

## Installation

Install the API Server plugin on the Creator 5 using the OpenCreator plugin installation mechanism.

The installer:

1. Checks that Script Runner is installed.
2. Checks that the API Server source script is present.
3. Requests the Radxa IPv4 address.
4. Determines the Creator 5 IPv4 address using the route to the Radxa.
5. Saves the Radxa address in /usr/data/opencreator/api-server.json.
6. Copies api_server.py to /usr/data/opencreator/scripts/.
7. Integrates the TUNNELED_MODE macro into the existing klipper/config/oc-macros.cfg.
8. Integrates the Tunneled Mode entry into klipper/config/.theme/navi.json.
9. Restarts Script Runner and Klipper, then checks that Klipper becomes ready.

The installer preserves existing configuration entries, macros, and navigation links. It creates timestamped backups before modifying existing configuration files.

## Script Runner

Script Runner is required because it executes the API Server script in the Creator 5 runtime.

The API Server script is installed at:

/usr/data/opencreator/scripts/api_server.py

The installer and updater restart Script Runner after copying the script.

## Klipper macro

The installer adds two sections to oc-macros.cfg:

- gcode_shell_command oc_tunneled_mode
- gcode_macro TUNNELED_MODE

The shell command calls the local Creator 5 API endpoint:

http://127.0.0.1:8765/go_tunneled

Invoke the macro from the Klipper console using:

    TUNNELED_MODE

The installer does not modify printer.my.macro.cfg or other personal Klipper macro files.

The existing oc-macros.cfg include in printer.base.cfg is preserved. The installer does not add a second include.

## Navigation integration

The installer adds or updates the Tunneled Mode entry in:

/usr/data/opencreator/klipper/config/.theme/navi.json

The link points to the Creator 5 API Server:

http://CREATOR_IP:8765/go_tunneled

Existing navigation entries are preserved. Re-running the installer updates the existing entry instead of creating duplicates.

The navigation file is intended for compatible Mainsail-style navigation integrations. Visibility depends on the frontend in use.

## Mode switching

The API Server exposes two browser endpoints:

- /go_tunneled
- /go_soc

These endpoints initiate the requested mode transition and return a waiting page that redirects the browser when the destination interface is available.

### Switch to SoC mode

The Radxa component initiates the switch to SoC mode through the Creator 5 API Server.

Before changing mode, the Creator 5 synchronizes:

- Toolchange counters from Radxa to Creator 5.
- Nozzle usage seconds from Radxa to Creator 5.

The Creator 5 then updates its mode state and schedules a reboot.

After reboot, the browser is redirected to the Creator 5 interface.

### Switch to Tunneled mode

The Creator 5 API Server initiates the switch to Tunneled mode.

Before changing mode, the Creator 5 synchronizes:

- Toolchange counters from Creator 5 to Radxa.
- Nozzle usage seconds from Creator 5 to Radxa.

The Creator 5 then updates its mode state and schedules a reboot.

After reboot, the browser is redirected to the Radxa interface.

## Data synchronization

The two components exchange cumulative printer data.

| Data | Switch to SoC | Switch to Tunneled |
|---|---|---|
| Toolchange counters | Radxa to Creator 5 | Creator 5 to Radxa |
| Nozzle usage seconds | Radxa to Creator 5 | Creator 5 to Radxa |
| Radxa SoC temperature | Radxa to Creator 5 | Radxa to Creator 5 |

Toolchange counters are stored on the Creator 5 in:

/usr/data/opencreator/klipper/config/toolchanges.txt

Nozzle lifetime counters are stored in:

/usr/data/opencreator/klipper/config/c5_misc_variables.cfg

The nozzle variables are:

- nozzle_seconds_t0
- nozzle_seconds_t1
- nozzle_seconds_t2
- nozzle_seconds_t3

The Radxa component provides the corresponding synchronization endpoints.

## Configuration

The Creator 5 API configuration is stored in:

/usr/data/opencreator/api-server.json

Example configuration:

    {
        "radxa_host": "192.168.1.197"
    }

The installer writes the Radxa address supplied during installation.

If the Radxa IP address changes, run the installer again and provide the new address. Keep both devices on stable IP addresses.

The API Server listens on:

0.0.0.0:8765

## API endpoints

The principal mode-switching endpoints are:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /go_tunneled | Switch to Tunneled mode and redirect |
| GET | /go_soc | Switch to SoC mode and redirect |
| GET | /status | Report the current mode |

The API also provides printer information and synchronization endpoints, including toolchange counters, nozzle lifetime data, and the endpoint used to receive Radxa SoC temperature.

The Radxa monitor provides its own HTTP API on its separate device, also using port 8765.

## Update

The update script:

1. Checks that Script Runner is installed.
2. Copies the updated api_server.py into the Script Runner scripts folder.
3. Restarts Script Runner.

The update does not overwrite the Creator 5 configuration, Klipper macros, or navigation file.

## Uninstallation

The uninstaller:

- Removes /usr/data/opencreator/scripts/api_server.py.
- Removes only the plugin-managed block from oc-macros.cfg.
- Removes only the plugin's Tunneled Mode navigation entry.
- Restarts Script Runner and Klipper.
- Preserves /usr/data/opencreator/api-server.json.
- Preserves all other macros and navigation entries.

The Script Runner plugin itself is not removed.

## Troubleshooting

### API Server is not responding

Check that Script Runner is installed and running.

Confirm that the API Server script exists at:

/usr/data/opencreator/scripts/api_server.py

Check that TCP port 8765 is reachable on the Creator 5.

### Mode switching fails

Check connectivity between the Creator 5 and Radxa.

Verify the radxa_host value in api-server.json and confirm that the Radxa monitor is running on port 8765.

A synchronization or validation error prevents the mode transition from continuing.

### Klipper macro is unavailable

Confirm that oc-macros.cfg is included by printer.base.cfg and that the oc_tunneled_mode shell command and TUNNELED_MODE macro are present.

Check the Klipper log for configuration errors.

### Navigation entry is not visible

Confirm that .theme/navi.json contains the Tunneled Mode entry and that the active frontend supports custom navigation entries.

## License

See the repository license.
