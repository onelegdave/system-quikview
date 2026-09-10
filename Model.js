// Shared, deterministic GPU selection. Device IDs use PCI addresses, not card order.
function effectiveGpus(devices, roles) {
    return (devices || []).map(function(gpu) {
        var copy = Object.assign({}, gpu);
        var role = (roles || {})[gpu.id];
        if (role === "integrated" || role === "dedicated") copy.kind = role;
        return copy;
    });
}
function hasValue(value) { return typeof value === "number" && isFinite(value); }
function selectGpu(devices, source, field) {
    var list = devices || [];
    if (source === "hottest") {
        return list.filter(function(g) { return hasValue(g.temp); })
            .sort(function(a, b) { return b.temp - a.temp; })[0] || null;
    }
    if (source === "dedicated" || source === "integrated") {
        return list.filter(function(g) { return g.kind === source; })[0] || null;
    }
    if (source && source !== "auto") {
        return list.filter(function(g) { return g.id === source; })[0] || null;
    }
    // Auto may fall back when a metric is missing. Explicit choices never do.
    var available = list.filter(function(g) { return hasValue(g[field]); });
    return available.filter(function(g) { return g.kind === "dedicated"; })[0]
        || available[0] || list.filter(function(g) { return g.kind === "dedicated"; })[0] || list[0] || null;
}
function sourceLabel(source, devices) {
    var presets = {auto: "Auto · prefer dedicated", dedicated: "Dedicated", integrated: "Integrated", hottest: "Hottest GPU"};
    if (presets[source]) return presets[source];
    var gpu = (devices || []).filter(function(g) { return g.id === source; })[0];
    return gpu ? gpu.name : "Disconnected GPU · " + source;
}

function temperatureGroups(sensors, gpus) {
    var groups = [];
    var titles = {k10temp: "Processor", coretemp: "Processor", zenpower: "Processor", cpu_thermal: "Processor",
        nvme: "NVMe storage", spd5118: "Memory module", amdgpu: "AMD graphics", acpitz: "System board"};
    (sensors || []).forEach(function(sensor) {
        var key = sensor.chip + ":" + (sensor.device || sensor.chip);
        var group = groups.filter(function(g) { return g.id === key; })[0];
        if (!group) {
            var title = titles[sensor.chip] || (/phy|wifi|iwlwifi/.test(sensor.chip) ? "Wireless" : sensor.chip);
            group = {id: key, title: title, subtitle: sensor.device || sensor.chip, sensors: []};
            groups.push(group);
        }
        group.sensors.push(sensor);
    });
    (gpus || []).forEach(function(gpu) {
        if (!hasValue(gpu.temp) || (sensors || []).some(function(s) { return s.device === gpu.id; })) return;
        groups.push({id: "gpu:" + gpu.id, title: "Graphics", subtitle: gpu.name,
            sensors: [{id: "gpu:" + gpu.id, label: "GPU", name: gpu.name, value: gpu.temp, maximum: null, critical: null}]});
    });
    var order = {"Processor": 0, "AMD graphics": 1, "Graphics": 1, "NVMe storage": 2, "Memory module": 3, "Wireless": 4, "System board": 5};
    return groups.sort(function(a, b) {
        var first = order[a.title] === undefined ? 6 : order[a.title];
        var second = order[b.title] === undefined ? 6 : order[b.title];
        return first - second || a.id.localeCompare(b.id);
    });
}
function temperatureState(sensor) {
    if (hasValue(sensor.critical) && sensor.critical > 0 && sensor.value >= sensor.critical) return "Critical";
    if (hasValue(sensor.maximum) && sensor.maximum > 0 && sensor.value >= sensor.maximum) return "High";
    return "";
}

function parsePalette(raw) {
    var result = {};
    String(raw || "").split("\n").forEach(function(line) {
        var match = line.match(/^\s*(color\d+|cyan|blue|yellow)\s*=\s*["'](#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?)["']\s*(?:#.*)?$/);
        if (match) result[match[1]] = match[2];
    });
    return result;
}
function savedSectionKeys(saved) {
    // Settings restored by QML can be QVariant sequences rather than JS Arrays.
    var result = [];
    if (!saved || typeof saved === "string" || typeof saved.length !== "number") return result;
    for (var i = 0; i < saved.length; i++) if (typeof saved[i] === "string") result.push(saved[i]);
    return result;
}
function orderedSections(saved, available) {
    var result = [], seen = {};
    savedSectionKeys(saved).forEach(function(key) {
        var entry = available.filter(function(e) { return e.key === key; })[0];
        if (entry && !seen[key]) { result.push(entry); seen[key] = true; }
    });
    available.forEach(function(entry) {
        if (!seen[entry.key]) { result.push(entry); seen[entry.key] = true; }
    });
    return result;
}
function moveSection(saved, available, key, direction) {
    var current = orderedSections(saved, available).map(function(e) { return e.key; });
    var index = current.indexOf(key), target = index + direction;
    if (index < 0 || target < 0 || target >= current.length || (direction !== -1 && direction !== 1)) return null;
    // Keep disconnected devices in saved preferences, ready for reconnection.
    var complete = [], seen = {};
    savedSectionKeys(saved).concat(current).forEach(function(value) {
        if (typeof value === "string" && !seen[value]) { complete.push(value); seen[value] = true; }
    });
    var a = complete.indexOf(key), b = complete.indexOf(current[target]);
    complete[a] = current[target]; complete[b] = key;
    return complete;
}
