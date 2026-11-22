(() => {
    if (window.openCreatorDashboardLoaded) return;
    window.openCreatorDashboardLoaded = true;

    const API = new URL("/api/dashboard", document.currentScript.src).href;
    const PLUGINS_API = new URL("/api/plugins", document.currentScript.src).href;
    const SYNC_API = new URL("/api/synchronization", document.currentScript.src).href;
    let panel;
    let refreshTimer;

    const el = (tag, cls, value) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (value !== undefined) node.textContent = value;
        return node;
    };

    const section = (parent, title) => {
        const block = el("section", "oc-section");
        const sectionIds = {
            "Printer": "oc-printer",
            "Data Synchronization": "oc-synchronization",
            "Temperatures": "oc-temperatures",
            "MCU boards": "oc-mcus",
            "Community Projects": "oc-plugins"
        };
        if (sectionIds[title]) block.id = sectionIds[title];
        block.appendChild(el("h3", "", title));
        parent.appendChild(block);
        return block;
    };

    const row = (parent, label, value, state, extraClass) => {
        const line = el("div", "oc-row");
        if (extraClass) line.classList.add(extraClass);
        line.appendChild(el("span", "oc-label", label));
        const result = el("span", "oc-value", value);
        if (state) result.classList.add("oc-" + state);
        line.appendChild(result);
        parent.appendChild(line);
    };

    const temperature = value =>
        value && Number.isFinite(value.temperature)
            ? `${value.temperature.toFixed(1)} °C`
            : "Unavailable";

    function createPanel() {
        const panel = el("main", "oc-panel");
        const content = el("div", "oc-content");

        content.id = "oc-dashboard-content";
        content.appendChild(el("p", "oc-loading", "Loading dashboard…"));

        panel.appendChild(content);
        document.body.appendChild(panel);
    }



    function renderPlugins(parent, data) {
        const previous = document.getElementById("oc-plugins");
        if (previous) previous.remove();

        const block = section(parent, "Community Projects");
        block.id = "oc-plugins";

        const message = el("p", "oc-project-empty", "");
        block.appendChild(message);

        if (data?.error) {
            message.textContent = data.error;
            return;
        }

        const plugins = data?.plugins || [];
        const available = data?.available || [];

        if (!plugins.length && !available.length) {
            message.textContent = "No plugins detected.";
            return;
        }

        message.textContent =
            `${plugins.length} installed plugin(s) · ${available.length} available.`;

        for (const plugin of plugins) {
            const card = el("article", "oc-project-card");
            const heading = el("div", "oc-project-heading");

            heading.appendChild(el("strong", "oc-project-name", plugin.name || plugin.id));

            const status = el(
                "span",
                "oc-project-status",
                plugin.trackable ? "Not checked" : "Not trackable"
            );
            heading.appendChild(status);
            card.appendChild(heading);

            if (plugin.description) {
                card.appendChild(el("p", "oc-project-description", plugin.description));
            }

            const details = [];
            if (plugin.author) details.push(`By ${plugin.author}`);
            if (plugin.official) details.push("Official");
            if (plugin.repository) details.push(plugin.repository);
            if (details.length) {
                card.appendChild(el("div", "oc-project-meta", details.join(" · ")));
            }

            if (plugin.note) {
                card.appendChild(el("p", "oc-project-warning", plugin.note));
            }

            if (plugin.trackable) {
                const check = el("button", "oc-project-check", "Check updates");
                check.type = "button";

                check.addEventListener("click", async () => {
                    check.disabled = true;
                    check.textContent = "Checking…";
                    status.textContent = "Checking…";

                    try {
                        const response = await fetch(
                            `${PLUGINS_API}/${encodeURIComponent(plugin.id)}/check-updates`,
                            { method: "POST", cache: "no-store" }
                        );

                        const result = await response.json();
                        if (!response.ok) {
                            throw new Error(result.error || `HTTP ${response.status}`);
                        }

                        const labels = {
                            update_available: ["Update available", "oc-warning"],
                            up_to_date: ["Up to date", "oc-good"],
                            not_trackable: ["Not trackable", "oc-warning"],
                            unable_to_check: ["Check failed", "oc-bad"]
                        };

                        const display = labels[result.status] ||
                            ["Unknown status", "oc-warning"];

                        status.textContent = display[0];
                        status.className = `oc-project-status ${display[1]}`;

                        const oldCommits = card.querySelector(".oc-project-commits");
                        if (oldCommits) oldCommits.remove();

                        if (result.local_commit || result.remote_commit) {
                            card.appendChild(el(
                                "div",
                                "oc-project-commits",
                                `Local: ${(result.local_commit || "Unknown").slice(0, 7)}`
                                + ` · Remote: ${(result.remote_commit || "Unavailable").slice(0, 7)}`
                            ));
                        }

                        if (result.dirty) {
                            card.appendChild(el(
                                "p", "oc-project-warning",
                                "The local repository contains uncommitted changes."
                            ));
                        }

                        if (result.error) {
                            card.appendChild(el("p", "oc-project-warning", result.error));
                        }
                    } catch (error) {
                        status.textContent = "Check failed";
                        status.className = "oc-project-status oc-bad";
                        card.appendChild(el("p", "oc-project-warning", error.message));
                    } finally {
                        check.disabled = false;
                        check.textContent = "Check again";
                    }
                });

                const toolbar = el("div", "oc-project-toolbar");
                toolbar.appendChild(check);
                card.appendChild(toolbar);
            }

            block.appendChild(card);
        }

        for (const plugin of available) {
            const card = el("article", "oc-project-card");
            const heading = el("div", "oc-project-heading");

            heading.appendChild(el("strong", "oc-project-name", plugin.name || plugin.id));
            const status = el("span", "oc-project-status", "Available");
            heading.appendChild(status);
            card.appendChild(heading);

            if (plugin.description)
                card.appendChild(el("p", "oc-project-description", plugin.description));

            const details = [];
            if (plugin.author) details.push(`By ${plugin.author}`);
            if (plugin.official) details.push("Official");
            if (plugin.repository) details.push(plugin.repository);
            if (details.length)
                card.appendChild(el("div", "oc-project-meta", details.join(" · ")));

            if (plugin.note)
                card.appendChild(el("p", "oc-project-warning", plugin.note));

            const toolbar = el("div", "oc-project-toolbar");
            const install = el("button", "oc-project-check", "Install");
            install.type = "button";

            install.addEventListener("click", async () => {
                const startedAt = Date.now();
                install.disabled = true;
                install.textContent = "Installing…";
                status.textContent = "Installing…";

                let installError = null;
                let connectionInterrupted = false;

                try {
                    const response = await fetch(
                        `${PLUGINS_API}/${encodeURIComponent(plugin.id)}/install`,
                        { method: "POST", cache: "no-store" }
                    );
                    let result = {};
                    try { result = await response.json(); } catch (_) {}

                    if (!response.ok || !result.success)
                        installError = new Error(result.error || `HTTP ${response.status}`);
                } catch (error) {
                    connectionInterrupted = true;
                    installError = error;
                }

                const remaining = 10000 - (Date.now() - startedAt);
                if (remaining > 0)
                    await new Promise(resolve => setTimeout(resolve, remaining));

                if (connectionInterrupted) {
                    status.textContent = "Verifying installation…";
                    status.className = "oc-project-status oc-warning";

                    const deadline = Date.now() + 180000;
                    let installed = false;

                    while (Date.now() < deadline) {
                        try {
                            const verify = await fetch(PLUGINS_API, { cache: "no-store" });
                            if (verify.ok) {
                                const data = await verify.json();
                                installed = (data.plugins || []).some(item => item.id === plugin.id);
                                if (installed) break;
                            }
                        } catch (_) {}
                        await new Promise(resolve => setTimeout(resolve, 3000));
                    }

                    if (installed) {
                        await refresh();
                        return;
                    }

                    status.textContent = "Installation status unknown";
                    status.className = "oc-project-status oc-warning";
                    install.textContent = "Check dashboard";
                    install.disabled = true;
                    card.appendChild(el("p", "oc-project-warning",
                        "Connection interrupted during installation. Reload the dashboard to check the final status."));
                    return;
                }

                if (installError) {
                    status.textContent = "Install failed";
                    status.className = "oc-project-status oc-bad";
                    install.disabled = false;
                    install.textContent = "Retry";
                    card.appendChild(el("p", "oc-project-warning", installError.message));
                    return;
                }

                await refresh();
            });

            toolbar.appendChild(install);
            card.appendChild(toolbar);
            block.appendChild(card);
        }

    }

    function renderControls(parent, data) {
        const controls = section(parent, "Controls");
        const actions = el("div", "oc-control-actions");

        if (data.soc.mode === "tunneled") {
            const goSoc = el("button", "oc-control-button", "Go SoC");
            goSoc.type = "button";
            goSoc.addEventListener("click", () => {
                if (window.confirm("Switch the Creator 5 to SoC mode?")) {
                    window.open("/api/go-soc", "_blank", "noopener");
                }
            });
            actions.appendChild(goSoc);
        }

        const currentScreen = String(data.creator.screen || "").toLowerCase();

        for (const screen of ["grumpy", "helix"]) {
            const label = screen === "grumpy"
                ? "Switch to Grumpy"
                : "Switch to Helix";

            const button = el("button", "oc-control-button", label);
            button.type = "button";
            button.disabled = currentScreen === screen;

            button.addEventListener("click", async () => {
                if (!window.confirm(`Switch the screen to ${screen}?`)) {
                    return;
                }

                button.disabled = true;
                try {
                    const response = await fetch(`/api/screen/${screen}`, {
                        method: "POST",
                        cache: "no-store"
                    });
                    const result = await response.json();

                    if (!response.ok || !result.success) {
                        throw new Error(result.error || `HTTP ${response.status}`);
                    }

                    await refresh();
                } catch (error) {
                    window.alert(`Screen switch failed: ${error.message}`);
                    button.disabled = false;
                }
            });

            actions.appendChild(button);
        }

        const tunneled = el("button", "oc-control-button", "Switch to Tunneled");
        tunneled.type = "button";
        tunneled.disabled =
            data.external_host?.reachable !== true ||
            data.soc.mode === "tunneled";

        tunneled.addEventListener("click", () => {
            if (tunneled.disabled) return;

            if (!window.confirm("Switch the Creator 5 to Tunneled mode?")) {
                return;
            }

            window.top.location.href = `${window.location.protocol}//${window.location.hostname}:8765/go_tunneled`;
        });

        actions.appendChild(tunneled);
        controls.appendChild(actions);
    }


    function parseToolchanges(value) {
        if (typeof value !== "string") return null;
        const result = {};
        for (const line of value.split(/\r?\n/)) {
            const match = line.match(/^\s*(Total|T[0-3])\s*:\s*(\d+)\s*$/i);
            if (match) result[match[1].toUpperCase()] = Number(match[2]);
        }
        return Object.keys(result).length ? result : null;
    }

    function decodeFile(info) {
        if (!info || info.exists !== true || typeof info.data !== "string") return null;
        try {
            const binary = atob(info.data);
            return Uint8Array.from(binary, char => char.charCodeAt(0));
        } catch {
            return null;
        }
    }

    function fileDate(info) {
        if (!Number.isFinite(info?.mtime_ns)) return "Unknown";
        return new Date(info.mtime_ns / 1e6).toLocaleString();
    }

    function calibrationDetails(filename, info) {
        const bytes = decodeFile(info);
        if (!bytes) return "File unavailable";

        const size = `${bytes.length.toLocaleString()} bytes`;

        try {
            let raw = new TextDecoder().decode(bytes);
            raw = raw.replace(/\/\*[\s\S]*?\*\//g, "");
            const data = JSON.parse(raw);

            if (filename === "extruder.json") {
                const number = value =>
                    Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "not set";

                const tools = ["t0", "t1", "t2", "t3"].map(key =>
                    `${key.toUpperCase()}: X ${number(data[key + "_offset_x"])}, Y ${number(data[key + "_offset_y"])}, Z ${number(data[key + "_offset_z"])}`
                );

                return [
                    size,
                    `Focal offset: ${data.focal_offset ?? "not set"}`,
                    `Pixel distance: ${data.pixel_distance ?? "not set"}`,
                    `Current extruder: ${data.now_extruder ?? "not set"}`,
                    ...tools
                ].join(" · ");
            }

            return [
                size,
                ...Object.entries(data).map(([key, value]) => `${key}: ${value}`)
            ].join(" · ");
        } catch {
            return size + " · Unreadable calibration data";
        }
    }


    function renderSynchronization(parent, data) {
        const block = section(parent, "Data Synchronization");

        if (!data || data.success === false) {
            row(block, "Synchronization data", data?.error || "Unavailable", "bad");
            return;
        }

        const creator = data.creator || data;
        const external = data.external_host || {};
        const hostAvailable = external.available === true;
        const mode = data.mode;
        const filesA = creator.firmware_res?.files || {};
        const filesB = external.firmware_res?.files || {};

        const card = title => {
            const node = el("div", "oc-sync-card");
            node.appendChild(el("h4", "", title));
            block.appendChild(node);
            return node;
        };

        const status = (node, valid, equal) => {
            const value = !hostAvailable || !valid
                ? ["Unavailable", "bad"]
                : equal ? ["Synced", "good"] : ["Out of sync", "bad"];
            row(node, "Sync status", value[0], value[1]);
        };

        const toolchanges = value => {
            const parsed = parseToolchanges(value || "");
            return parsed
                ? ["TOTAL", "T0", "T1", "T2", "T3"]
                    .map(key => `${key}: ${parsed[key] ?? "—"}`).join(" · ")
                : "Unavailable";
        };

        const aTools = parseToolchanges(creator.toolchanges || "");
        const bTools = parseToolchanges(external.toolchanges || "");

        const toolsCard = card("Toolchanges");
        row(toolsCard, "External Host", hostAvailable ? toolchanges(external.toolchanges) : "Unavailable",
            hostAvailable && bTools ? "good" : "bad");
        row(toolsCard, "Creator 5", toolchanges(creator.toolchanges),
            aTools ? "good" : "bad");
        status(toolsCard, !!aTools && !!bTools,
            JSON.stringify(aTools) === JSON.stringify(bTools));

        const hoursCard = card("Nozzle Hours");
        const aHours = creator.nozzle_hours || {};
        const bHours = external.nozzle_hours || {};
        const hourKeys = Array.from({length: 4}, (_, i) => `nozzle_seconds_t${i}`);
        let hoursValid = true;
        let hoursEqual = true;

        for (let i = 0; i < 4; i++) {
            const key = `nozzle_seconds_t${i}`;
            const a = aHours[key];
            const b = bHours[key];
            const valid = Number.isFinite(a) && Number.isFinite(b);
            hoursValid = hoursValid && valid;
            hoursEqual = hoursEqual && valid && a === b;

            row(hoursCard, `T${i} · External Host`,
                hostAvailable && Number.isFinite(b) ? `${(b / 3600).toFixed(2)} h` : "Unavailable",
                hostAvailable && Number.isFinite(b) ? "good" : "bad", "oc-nozzle-hours-row");
            row(hoursCard, `T${i} · Creator 5`,
                Number.isFinite(a) ? `${(a / 3600).toFixed(2)} h` : "Unavailable",
                Number.isFinite(a) ? "good" : "bad", "oc-nozzle-hours-row");
        }
        status(hoursCard, hoursValid, hoursEqual);

        const calibrationSummary = (filename, info) => {
            const bytes = decodeFile(info);
            if (!info?.exists || !bytes) return "Unavailable";

            const size = `${bytes.length.toLocaleString()} bytes`;
            try {
                let raw = new TextDecoder().decode(bytes);
                raw = raw.replace(/\/\*[\s\S]*?\*\//g, "");
                const values = JSON.parse(raw);

                if (filename === "extruder.json") {
                    return [
                        size,
                        `Focal offset: ${values.focal_offset ?? "not set"}`,
                        `Pixel distance: ${values.pixel_distance ?? "not set"}`,
                        "T0: unavailable",
                        "T1: unavailable",
                        "T2: unavailable",
                        "T3: unavailable"
                    ].join(" · ");
                }

                return [
                    size,
                    ...Object.entries(values).map(([key, value]) => `${key}: ${value}`)
                ].join(" · ");
            } catch {
                return `${size} · Unreadable calibration data`;
            }
        };

        const renderCalibrationCard = (title, filename) => {
            const node = card(title);
            const a = filesA[filename];
            const b = filesB[filename];
            const aExists = a?.exists === true;
            const bExists = b?.exists === true;

            row(node, "External Host",
                hostAvailable && bExists ? `Present · ${fileDate(b)}` : "Unavailable",
                hostAvailable && bExists ? "good" : "bad");
            row(node, "External Host data",
                hostAvailable ? calibrationSummary(filename, b) : "Unavailable",
                hostAvailable && bExists ? "good" : "bad");

            row(node, "Creator 5",
                aExists ? `Present · ${fileDate(a)}` : "Unavailable",
                aExists ? "good" : "bad");
            row(node, "Creator 5 data",
                calibrationSummary(filename, a),
                aExists ? "good" : "bad");

            const valid = !!a && !!b &&
                typeof a.exists === "boolean" &&
                typeof b.exists === "boolean" &&
                (!a.exists || typeof a.data === "string") &&
                (!b.exists || typeof b.data === "string");
            const equal = valid && a.exists === b.exists &&
                (!a.exists || a.data === b.data);

            status(node, valid, equal);
        };

        renderCalibrationCard("Extruder Calibration", "extruder.json");
        renderCalibrationCard("Z Offset Calibration", "zoffset.json");

        row(block, "Automatic sync", "On mode change");
        row(block, "Current direction", data.sync_direction || "Unavailable");

        const actions = el("div", "oc-sync-actions");
        const canSync = hostAvailable && (mode === "soc" || mode === "tunneled");

        for (const [item, label] of [
            ["toolchanges", "Sync Toolchanges"],
            ["nozzle_hours", "Sync Nozzle Hours"],
            ["extruder", "Sync Extruder"],
            ["zoffset", "Sync Z Offset"]
        ]) {
            const button = el("button", "oc-sync-button", label);
            button.type = "button";
            button.disabled = !canSync;

            button.addEventListener("click", async () => {
                button.disabled = true;
                button.textContent = "Syncing…";

                try {
                    const response = await fetch(`${SYNC_API}/${item}`, {
                        method: "POST"
                    });
                    const result = await response.json();

                    if (!response.ok || result.success !== true)
                        throw new Error(result.error || `HTTP ${response.status}`);

                    await refresh();
                } catch (error) {
                    window.alert(`Synchronization failed: ${error.message}`);
                    button.disabled = !canSync;
                    button.textContent = label;
                }
            });

            actions.appendChild(button);
        }

        block.appendChild(actions);

        if (!hostAvailable) {
            block.appendChild(el("p", "oc-sync-note",
                "Manual synchronization is unavailable while the External Host is offline."
            ));
        }
    }

    function render(data, pluginData, syncData) {
        const content = document.getElementById("oc-dashboard-content");
        content.replaceChildren();

        const printer = section(content, "Printer");
        row(printer, "Klipper", data.printer.connected
            ? data.printer.state : "Disconnected",
            data.printer.connected ? "good" : "bad");
        row(printer, "Print state",
            data.printer.print?.state || "Unknown");
        row(printer, "Creator 5 API",
            data.creator.reachable ? "Online" : "Offline",
            data.creator.reachable ? "good" : "bad");
        row(printer, "SoC mode",
            data.soc.mode || "Unavailable",
            data.soc.mode ? "good" : "bad");
        row(printer, "Screen",
            data.creator.screen || "Unknown");

        renderControls(printer, data);
        const external = data.external_host || {};
        row(
            printer,
            "External Host",
            external.configured
                ? (external.reachable ? "Online" : "Offline")
                : "Not configured",
            external.reachable ? "good" : (external.configured ? "bad" : "")
        );
        renderSynchronization(content, syncData);

        const temps = section(content, "Temperatures");
        if (data.temperatures.external_host) {
            row(temps, "External Host", temperature(data.temperatures.external_host));
        }
        row(temps, "Mainboard", temperature(data.temperatures.mainboard));
        row(temps, "Toolhead", temperature(data.temperatures.toolhead));
        row(temps, "Nozzle", temperature(data.temperatures.nozzle));
        row(temps, "Bed", temperature(data.temperatures.bed));

        const mcus = section(content, "MCU boards");
        for (const [name, info] of Object.entries(data.mcus)) {
            row(mcus, name.replace("mcu ", "").toUpperCase(),
                info.connected ? (info.chip || "Connected") : "Unavailable",
                info.connected ? "good" : "bad");
        }

        renderPlugins(content, pluginData);

        content.appendChild(el(
            "div", "oc-footer",
            "Local dashboard"
        ));
    }

    async function refresh() {
        const content = document.getElementById("oc-dashboard-content");
        try {
            const [response, pluginsResponse, syncResponse] = await Promise.all([
                fetch(API, { cache: "no-store" }),
                fetch(PLUGINS_API, { cache: "no-store" }),
                fetch(SYNC_API, { cache: "no-store" })
            ]);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            let plugins = { plugins: [], error: null };

            if (pluginsResponse.ok) {
                plugins = await pluginsResponse.json();
            } else {
                plugins.error = `Plugins API HTTP ${pluginsResponse.status}`;
            }

            let syncData = {};
            if (syncResponse.ok) {
                syncData = await syncResponse.json();
            } else {
                syncData = {
                    success: false,
                    error: `Local data API HTTP ${syncResponse.status}`
                };
            }

            render(data, plugins, syncData);
        } catch (error) {
            content.replaceChildren(
                el("p", "oc-error", `Dashboard connection error: ${error.message}`)
            );
        }
    }

    createPanel();
    refresh();

})();
