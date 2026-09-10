pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons
import "Model.js" as Model

Panel {
    id: root
    moduleName: "onelegdave.system-quikview"
    ipcTarget: "onelegdave.system-quikview"
    manageIpc: false
    IpcHandler {
        target: "onelegdave.system-quikview"
        function open(): void { root.customizing = false; root.open() }
        function close(): void { root.close() }
        function toggle(): void { root.toggle() }
        function metric(value: string): string {
            if (root.choices.indexOf(value) < 0) return "unknown metric"
            root.save("metric", value)
            return "ok"
        }
        function source(value: string): string {
            if (root.sourceOptions.map(o => o.value).indexOf(value) < 0) return "unknown source"
            root.save("gpuSource", value)
            return "ok"
        }
        function fold(section: string): void { root.fold(section) }
        function scrollBy(pixels: string): void { root.scrollBy(Number(pixels)) }
        function customize(): void { root.customizing = true; root.open() }
        function move(key: string, direction: string): void { root.moveSection(key, Number(direction)) }
        function status(): string {
            return JSON.stringify({customizing: root.customizing, order: root.sectionLayout.map(e => e.key), renderedOrder: dashboard.children.filter(item => "entry" in item).sort((a, b) => a.y - b.y).map(item => item.entry.key), colors: {cpu: root.cpuColor.toString(), memory: root.memoryColor.toString(), gpu: root.gpuColor.toString(), temperature: root.temperatureColor.toString()}, metric: root.metric, collapsed: root.collapsed, stale: root.stale, cpu: root.snapshot.cpu, gpus: root.gpuList, gpuSource: root.gpuSource, temperatureGpu: root.temperatureGpu, barText: root.barValue(), geometry: {barWidth: button.width, popupX: panel.cardOrigin.x, popupY: panel.cardOrigin.y, popupWidth: panel.contentWidth, popupHeight: panel.contentHeight}, viewport: {height: scroll.height, contentHeight: body.implicitHeight, y: root.flickable ? root.flickable.contentY : 0}})
        }
    }
    property var snapshot: ({})
    property double received: 0
    property bool stale: true
    // Omarchy exposes these runtime objects as generic QtObject properties.
    readonly property var themeFont: Style.font
    readonly property var popupColors: Color.popups
    readonly property var shellHost: bar
    readonly property var barWindow: button.QsWindow.window
    readonly property Flickable flickable: scroll.contentItem as Flickable
    readonly property color ink: popupColors.text
    readonly property color cpuColor: Color.accent
    ThemePalette { id: themePalette }
    readonly property color memoryColor: themePalette.memory
    readonly property color gpuColor: themePalette.gpu
    readonly property color temperatureColor: themePalette.temperature
    property bool customizing: false
    onCustomizingChanged: Qt.callLater(function() { if (root.flickable) root.flickable.contentY = 0 })
    readonly property var availableSections: [
        {key: "overview", label: "Overview cards"}, {key: "cpu", label: "Processor"}, {key: "memory", label: "Memory"}
    ].concat(gpuList.map(g => ({key: "gpu-" + g.id, label: (g.kind === "dedicated" ? "Dedicated GPU" : g.kind === "integrated" ? "Integrated GPU" : "GPU") + " · " + g.name}))).concat([
        {key: "disks", label: "Storage"}, {key: "network", label: "Network"},
        {key: "temperatures", label: "Temperatures"}, {key: "processes", label: "Top processes"}
    ])
    readonly property var sectionLayout: Model.orderedSections(setting("sectionOrder", []), availableSections)
    function moveSection(key, direction) {
        let order = Model.moveSection(setting("sectionOrder", []), availableSections, key, direction)
        if (order) save("sectionOrder", order)
    }
    function sectionComponent(key) {
        if (key && key.indexOf("gpu-") === 0) return gpuComponent
        return {overview: overviewComponent, cpu: cpuComponent, memory: memoryComponent, disks: disksComponent,
            network: networkComponent, temperatures: temperaturesComponent, processes: processesComponent}[key] || null
    }
    readonly property var networks: snapshot.networks || []
    readonly property int inactiveNetworkCount: networks.filter(n => n.state === "down").length
    readonly property var visibleNetworks: setting("showInactiveNetworks", false) ? networks : networks.filter(n => n.state !== "down")
    readonly property var thermalGroups: Model.temperatureGroups(snapshot.temperatures, gpuList)
    readonly property var thermalSensors: thermalGroups.reduce((items, group) => items.concat(group.sensors), [])
    readonly property real downloadRate: networks.reduce((total, n) => total + (n.down || 0), 0)
    readonly property real uploadRate: networks.reduce((total, n) => total + (n.up || 0), 0)
    readonly property var hottestSensor: thermalSensors.slice().sort((a, b) => b.value - a.value)[0] || ({})
    readonly property var processes: snapshot.processes || []
    readonly property real processCpuMaximum: Math.max(1, ...processes.map(p => p.cpu || 0))
    readonly property real processMemoryMaximum: Math.max(1, ...processes.map(p => p.memory || 0))
    property var history: ({})
    readonly property string gpuSource: setting("gpuSource", "auto")
    readonly property var gpuRoles: setting("gpuRoles", ({}))
    readonly property var sourceOptions: [
        {value: "auto", label: "Auto · prefer dedicated"},
        {value: "dedicated", label: "Dedicated"},
        {value: "integrated", label: "Integrated"},
        {value: "hottest", label: "Hottest GPU"}
    ].concat(gpuList.map(g => ({value: g.id, label: g.name + " · " + g.id})))
    readonly property var temperatureGpu: Model.selectGpu(gpuList, gpuSource, "temp") || ({})
    readonly property var primaryGpu: Model.selectGpu(gpuList, gpuSource, "usage") || ({})
    readonly property var memoryGpu: Model.selectGpu(gpuList, gpuSource, "used") || ({})
    readonly property string metric: setting("metric", "CPU")
    readonly property var choices: ["CPU", "Memory", "GPU", "Integrated GPU", "Dedicated GPU", "CPU temperature", "GPU temperature", "VRAM", "Network", "Disk", "Icon only"]
    readonly property var collapsed: setting("collapsed", ["indicator", "cpu", "disks", "network", "temperatures", "processes"])
    readonly property var gpuList: Model.effectiveGpus(snapshot.gpus, gpuRoles)
    readonly property var dedicated: gpuList.filter(g => g.kind === "dedicated")[0] || ({})
    readonly property var integrated: gpuList.filter(g => g.kind === "integrated")[0] || ({})
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function scrollBy(delta) {
        if (!isFinite(delta)) return
        let flick = root.flickable
        if (flick && flick.contentY !== undefined) flick.contentY = Math.max(0, Math.min(body.implicitHeight - scroll.height, flick.contentY + delta))
    }
    function fade(color, opacity) { return Qt.rgba(color.r, color.g, color.b, opacity) }
    function pct(value) { return value === null || value === undefined ? "—" : Math.round(value) + "%" }
    function temp(value) { return value === null || value === undefined ? "—" : Math.round(value) + "°C" }
    function bytes(value) {
        if (value === null || value === undefined) return "—"
        let units = ["B", "KiB", "MiB", "GiB", "TiB"], i = 0
        while (value >= 1024 && i < 4) { value /= 1024; i++ }
        return value.toFixed(i > 1 ? 1 : 0) + " " + units[i]
    }
    function save(key, value) {
        let next = Object.assign({}, settings)
        next[key] = value
        if (root.shellHost && root.shellHost.shell) root.shellHost.shell.updateEntryInline(moduleName, next)
    }
    function fold(key) {
        let next = collapsed.slice(), i = next.indexOf(key)
        if (i >= 0) next.splice(i, 1); else next.push(key)
        save("collapsed", next)
    }
    function isCollapsed(key, legacy) {
        if (key === "gpu-roles") return !setting("showGpuRoles", false)
        if (key === "layout-settings") return setting("hideLayoutSettings", false)
        return collapsed.indexOf(key) >= 0 || (legacy && collapsed.indexOf(legacy) >= 0)
    }
    function foldGpu(key, legacy) {
        if (key === "layout-settings") { save("hideLayoutSettings", !setting("hideLayoutSettings", false)); return }
        if (key === "gpu-roles") { save("showGpuRoles", !setting("showGpuRoles", false)); return }
        if (collapsed.indexOf(legacy) >= 0) save("collapsed", collapsed.filter(k => k !== legacy && k !== key))
        else fold(key)
    }
    function record(data) {
        let next = Object.assign({}, history)
        function push(key, value) { next[key] = (next[key] || []).concat([value]).slice(-60) }
        push("cpu", data.cpu); push("memory", (data.memory || {}).percent)
        for (let gpu of (data.gpus || [])) push(gpu.id, gpu.usage)
        const nets = data.networks || []
        push("download", nets.some(n => n.down !== null) ? nets.reduce((sum, n) => sum + (n.down || 0), 0) : null)
        push("upload", nets.some(n => n.up !== null) ? nets.reduce((sum, n) => sum + (n.up || 0), 0) : null)
        history = next
    }
    function setRole(id, role) {
        let next = Object.assign({}, gpuRoles)
        if (role === "auto") delete next[id]; else next[id] = role
        save("gpuRoles", next)
    }
    function barValue() {
        if (metric === "Icon only") return "󰓅"
        if (stale) return "󰓅 —"
        switch (metric) {
        case "Memory": return "RAM " + pct((snapshot.memory || {}).percent)
        case "GPU": return "GPU " + pct(primaryGpu.usage)
        case "Integrated GPU": return "iGPU " + pct(integrated.usage)
        case "Dedicated GPU": return "dGPU " + pct(dedicated.usage)
        case "CPU temperature": return "CPU " + temp(snapshot.cpuTemp)
        case "GPU temperature": return "GPU " + temp(temperatureGpu.temp)
        case "VRAM": return "VRAM " + bytes(memoryGpu.used)
        case "Disk": return "DISK " + pct((snapshot.disks || [])[0]?.percent)
        case "Network":
            let nets = snapshot.networks || []
            return "↓ " + bytes(nets.reduce((sum, n) => sum + (n.down || 0), 0)) + "/s"
        default: return "󰻠 " + pct(snapshot.cpu)
        }
    }
    Process {
        id: collector
        command: ["python3", "-u", decodeURIComponent(Qt.resolvedUrl("monitor.py").toString().replace("file://", "")), "--interval", String(Math.max(1, root.setting("interval", 2)))]
        running: true
        onCommandChanged: if (running) running = false
        stdout: SplitParser {
            onRead: data => {
                try { root.snapshot = JSON.parse(data); root.record(root.snapshot); root.received = Date.now(); root.stale = false }
                catch (e) { console.warn("System QuikView: invalid telemetry", e) }
            }
        }
    }
    Timer {
        interval: 3000; repeat: true; running: true
        onTriggered: {
            root.stale = Date.now() - root.received > Math.max(10000, root.setting("interval", 2) * 3000)
            if (!collector.running) collector.running = true
        }
    }
    WidgetButton {
        id: button
        bar: root.bar
        text: root.barValue()
        fontSize: root.themeFont.body
        tooltipText: "System QuikView · " + root.metric + (root.metric === "GPU temperature" ? " · " + (root.temperatureGpu.name || "Unavailable") : "") + "\nClick for details · right-click to customize"
        onPressed: b => { if (b === Qt.RightButton) { root.customizing = true; root.open() } else { if (!root.opened) root.customizing = false; root.toggle() } }
    }
    // Keep the real bar button content-sized. The popup follows this separate
    // zero-size anchor, whose screen-space center is captured once per opening.
    // Compensating for the button's transform prevents bar reflow from moving it.
    TransformWatcher {
        id: buttonTransform
        a: root.barWindow ? root.barWindow.contentItem : null
        b: button
    }
    Item {
        id: popupAnchor
        parent: button
        width: 0
        height: 0
        property point heldCenter: Qt.point(0, 0)
        property bool captured: false
        function capture() {
            const window = root.barWindow
            if (!window) return
            heldCenter = button.mapToItem(window.contentItem, button.width / 2, button.height / 2)
            captured = true
        }
        readonly property point currentOrigin: {
            buttonTransform.transform
            const window = root.barWindow
            return window ? button.mapToItem(window.contentItem, 0, 0) : Qt.point(0, 0)
        }
        x: captured ? heldCenter.x - currentOrigin.x : button.width / 2
        y: captured ? heldCenter.y - currentOrigin.y : button.height / 2
    }
    // Leave the anchor captured during the closing fade; recapture next time.
    onOpenedChanged: if (opened) popupAnchor.capture()
    KeyboardPanel {
        id: panel
        anchorItem: popupAnchor
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: keys
        contentWidth: panel.fittedContentWidth(Style.space(480))
        contentHeight: panel.fittedContentHeight(body.implicitHeight, Style.space(820))
        Item {
            id: keys
            anchors.fill: parent
            Keys.onEscapePressed: root.close()
            Keys.onDownPressed: root.scrollBy(40)
            Keys.onUpPressed: root.scrollBy(-40)
            Keys.onPressed: event => {
                if (event.key === Qt.Key_PageDown) { root.scrollBy(scroll.height * 0.8); event.accepted = true }
                if (event.key === Qt.Key_PageUp) { root.scrollBy(-scroll.height * 0.8); event.accepted = true }
            }
            Controls.ScrollView {
                id: scroll
                anchors.fill: parent
                clip: true
                contentWidth: availableWidth
                contentHeight: body.implicitHeight
                Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
                Controls.ScrollBar.vertical: Controls.ScrollBar {
                    policy: body.implicitHeight > scroll.height ? Controls.ScrollBar.AlwaysOn : Controls.ScrollBar.AlwaysOff
                    contentItem: Rectangle { implicitWidth: Style.space(3); radius: width / 2; color: root.ink; opacity: 0.3 }
                }
                Column {
                    id: body
                    width: scroll.availableWidth
                    spacing: Style.space(10)
                    RowLayout {
                        width: parent.width
                        spacing: Style.space(12)
                        Rectangle {
                            Layout.preferredWidth: Style.space(42); Layout.preferredHeight: width
                            radius: Style.space(12); color: root.fade(root.cpuColor, 0.16)
                            Text { anchors.centerIn: parent; text: "ϟ"; font.pixelSize: Style.space(32); color: root.cpuColor; font.bold: true }
                        }
                        Column {
                            Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Style.space(3)
                            Text { width: parent.width; elide: Text.ElideRight; text: root.customizing ? "Customize" : "System QuikView"; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Math.max(20, root.themeFont.title); font.bold: true }
                            Text { width: parent.width; elide: Text.ElideRight; text: root.customizing ? "MAKE IT YOURS" : "YOUR SYSTEM, AT A GLANCE"; color: root.ink; opacity: 0.5; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.letterSpacing: 1.3 }
                        }
                        Button { text: root.customizing ? "Done" : "Customize"; foreground: root.ink; bordered: true; focusable: true; onClicked: root.customizing = !root.customizing }
                    }
                    RowLayout {
                        width: parent.width; spacing: Style.space(6)
                        Rectangle { implicitWidth: Style.space(6); implicitHeight: implicitWidth; radius: width/2; color: root.stale ? Color.urgent : root.memoryColor }
                        Label { Layout.fillWidth: true; text: root.stale ? "Readings unavailable · retrying" : "Live  ·  every " + root.setting("interval", 2) + "s"; font.pixelSize: Style.space(12); opacity: 0.7 }
                        Text { text: Math.floor((root.snapshot.uptime || 0) / 3600) + "h uptime"; color: root.ink; opacity: 0.5; font.family: root.themeFont.family; font.pixelSize: Style.space(12) }
                    }
                    Column {
                        width: parent.width; spacing: Style.space(14); visible: root.customizing
                        Label { text: "Choose a bar reading and arrange your dashboard."; opacity: 0.6; font.pixelSize: Style.space(12); wrapMode: Text.WordWrap; elide: Text.ElideNone }
                        Section {
                            sectionKey: "layout-settings"; title: "Section order"; summary: "↑ / ↓ to move"; icon: "☷"
                            Repeater {
                                model: root.sectionLayout.length
                                Rectangle {
                                    id: orderRow
                                    required property int index
                                    readonly property var entry: root.sectionLayout[index] || ({})
                                    width: parent.width; implicitHeight: Style.space(43)
                                    radius: Style.space(6); color: root.fade(root.ink, 0.035)
                                    RowLayout {
                                        anchors.fill: parent; anchors.margins: Style.space(5); spacing: Style.space(8)
                                        Text { text: orderRow.index + 1; color: root.cpuColor; font.family: root.themeFont.family; font.pixelSize: Style.space(12); leftPadding: Style.space(7) }
                                        Text { Layout.fillWidth: true; text: orderRow.entry.label || ""; elide: Text.ElideRight; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(12) }
                                        Button { text: "↑"; enabled: orderRow.index > 0; opacity: enabled ? 1 : 0.3; foreground: root.ink; bordered: true; focusable: true; tooltipText: "Move " + orderRow.entry.label + " up"; onClicked: root.moveSection(orderRow.entry.key, -1) }
                                        Button { text: "↓"; enabled: orderRow.index < root.sectionLayout.length - 1; opacity: enabled ? 1 : 0.3; foreground: root.ink; bordered: true; focusable: true; tooltipText: "Move " + orderRow.entry.label + " down"; onClicked: root.moveSection(orderRow.entry.key, 1) }
                                    }
                                }
                            }
                            Button { text: "Default order"; foreground: root.ink; bordered: true; focusable: true; onClicked: root.save("sectionOrder", []) }
                        }
                    Column {
                        width: parent.width; spacing: Style.space(10)
                        Label { text: "Top bar reading"; font.bold: true }
                        Flow {
                            width: parent.width; spacing: Style.space(5)
                            Repeater {
                                model: root.choices
                                Button {
                                    required property string modelData
                                    text: modelData; foreground: root.ink; fontSize: root.themeFont.caption
                                    bordered: true; active: root.metric === modelData; focusable: true
                                    onClicked: root.save("metric", modelData)
                                }
                            }
                        }
                        Label { text: "GPU source"; font.bold: true }
                        Label { text: "For GPU usage, temperature and VRAM. Auto prefers a dedicated GPU with a reading."; wrapMode: Text.WordWrap; elide: Text.ElideNone; opacity: 0.65; font.pixelSize: Style.space(12) }
                        Repeater {
                            model: root.sourceOptions.length
                            Choice {
                                required property int index
                                readonly property var modelData: root.sourceOptions[index] || ({label: "", value: ""})
                                text: modelData.label; selected: root.gpuSource === modelData.value
                                onClicked: root.save("gpuSource", modelData.value)
                            }
                        }
                        Label { text: "Temperature now: " + (root.temperatureGpu.name || "Unavailable") + "  ·  " + root.temp(root.temperatureGpu.temp); wrapMode: Text.WordWrap; elide: Text.ElideNone; color: root.gpuColor; font.pixelSize: Style.space(12) }
                        Section {
                            sectionKey: "gpu-roles"; title: "GPU role overrides"; summary: "Advanced"; icon: "󰢮"
                            Label { text: "If auto-detection cannot identify a device, choose its role here. Selecting a device by name always works independently of its role."; wrapMode: Text.WordWrap; elide: Text.ElideNone; opacity: 0.65; font.pixelSize: Style.space(12) }
                            Repeater {
                                model: root.gpuList.length
                                Column {
                                    id: roleDevice
                                    required property int index
                                    readonly property var gpu: root.gpuList[index] || ({})
                                    width: parent.width; spacing: Style.space(5)
                                    Label { text: roleDevice.gpu.name; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: Style.space(12) }
                                    Flow {
                                        width: parent.width; spacing: Style.space(5)
                                        Repeater {
                                            model: ["auto", "integrated", "dedicated"]
                                            Button {
                                                required property string modelData
                                                text: modelData === "auto" ? "Auto-detect" : modelData === "integrated" ? "Integrated" : "Dedicated"
                                                active: (root.gpuRoles[roleDevice.gpu.id] || "auto") === modelData
                                                foreground: root.ink; bordered: true; focusable: true; fontSize: Style.space(11)
                                                onClicked: root.setRole(roleDevice.gpu.id, modelData)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    }
                    Column {
                        id: dashboard
                        width: parent.width; spacing: Style.space(10); visible: !root.customizing
                        Repeater {
                            model: root.sectionLayout.length
                            Loader {
                                required property int index
                                readonly property var entry: root.sectionLayout[index] || ({})
                                readonly property var gpu: root.gpuList.filter(g => "gpu-" + g.id === entry.key)[0] || ({})
                                width: parent.width
                                sourceComponent: root.sectionComponent(entry.key)
                            }
                        }
                    }

                }
            }
        }
    }

    Component {
        id: cpuComponent
                    Section {
                        sectionKey: "cpu"; title: "Processor"; tint: root.cpuColor; icon: "󰻠"; summary: root.pct(root.snapshot.cpu) + "  ·  " + root.temp(root.snapshot.cpuTemp)
                        Meter { value: root.snapshot.cpu }
                        Label { text: "Load  " + (root.snapshot.load || []).map(v => v.toFixed(2)).join("  /  "); opacity: 0.65 }
                        Grid {
                            id: coreGrid
                            width: parent.width; columns: 8; spacing: Style.space(4)
                            Repeater {
                                model: root.snapshot.cores || []
                                Rectangle {
                                    required property var modelData
                                    required property int index
                                    width: (coreGrid.width - coreGrid.spacing * 7) / 8; height: Style.space(28); radius: Style.space(3)
                                    color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.05 + (modelData || 0) / 250)
                                    Text { anchors.centerIn: parent; text: root.pct(parent.modelData); color: root.ink; font.family: root.themeFont.family; font.pixelSize: root.themeFont.caption }
                                }
                            }
                        }
                    }
    }

    Component {
        id: memoryComponent
                    Section {
                        sectionKey: "memory"; title: "Memory"; tint: root.memoryColor; icon: "󰍛"; summary: root.pct((root.snapshot.memory || {}).percent)
                        Meter { value: (root.snapshot.memory || {}).percent; tint: root.memoryColor }
                        Label { text: root.bytes((root.snapshot.memory || {}).used) + " / " + root.bytes((root.snapshot.memory || {}).total) + " used" }
                        Label { text: "Swap  " + root.bytes((root.snapshot.memory || {}).swapUsed) + " / " + root.bytes((root.snapshot.memory || {}).swapTotal); opacity: 0.65 }
                    }
    }

    Component {
        id: disksComponent
                    Section {
                        sectionKey: "disks"; title: "Storage"; icon: "󰋊"; summary: (root.snapshot.disks || []).length + " mounted"
                        Repeater {
                            model: root.snapshot.disks || []
                            Column {
                                id: diskRow
                                required property var modelData
                                width: parent.width; spacing: Style.space(5)
                                Label { text: diskRow.modelData.name + "  ·  " + root.bytes(diskRow.modelData.used) + " / " + root.bytes(diskRow.modelData.total) }
                                Meter { value: diskRow.modelData.percent }
                            }
                        }
                    }
    }

    Component {
        id: networkComponent
                    Section {
                        sectionKey: "network"; title: "Network"; icon: "󰛳"; tint: root.memoryColor
                        summary: "↓ " + root.bytes(root.downloadRate) + "/s"
                        Row {
                            width: parent.width; spacing: Style.space(8)
                            RateCard { width: (parent.width - parent.spacing) / 2; heading: "↓  DOWNLOAD"; value: root.downloadRate; tint: root.memoryColor; samples: root.history.download || [] }
                            RateCard { width: (parent.width - parent.spacing) / 2; heading: "↑  UPLOAD"; value: root.uploadRate; tint: root.gpuColor; samples: root.history.upload || [] }
                        }
                        Label { text: "All interfaces · graphs scale to recent traffic"; opacity: 0.5; font.pixelSize: Style.space(11) }
                        Label { visible: !root.networks.length; text: "No network interfaces detected"; opacity: 0.65 }
                        Button {
                            visible: root.inactiveNetworkCount > 0
                            text: (root.setting("showInactiveNetworks", false) ? "Hide" : "Show") + " " + root.inactiveNetworkCount + " inactive interfaces"
                            foreground: root.ink; fontSize: Style.space(11); bordered: true; focusable: true
                            onClicked: root.save("showInactiveNetworks", !root.setting("showInactiveNetworks", false))
                        }
                        Repeater {
                            model: root.visibleNetworks.length
                            Rectangle {
                                id: interfaceCard
                                required property int index
                                readonly property var net: root.visibleNetworks[index] || ({})
                                readonly property bool linked: net.state === "up" || (net.down || 0) > 0 || (net.up || 0) > 0
                                width: parent.width; implicitHeight: interfaceBody.implicitHeight + Style.space(20)
                                radius: Style.space(7); color: root.fade(root.memoryColor, linked ? 0.06 : 0.02)
                                border.width: 1; border.color: root.fade(root.memoryColor, linked ? 0.18 : 0.07)
                                opacity: net.state === "down" ? 0.5 : 1
                                Column {
                                    id: interfaceBody
                                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                    anchors.margins: Style.space(10); spacing: Style.space(7)
                                    RowLayout {
                                        width: parent.width; spacing: Style.space(7)
                                        Rectangle { implicitWidth: Style.space(5); implicitHeight: implicitWidth; radius: width / 2; color: interfaceCard.linked ? root.memoryColor : root.fade(root.ink, 0.4) }
                                        Text { Layout.fillWidth: true; text: interfaceCard.net.name || ""; elide: Text.ElideRight; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(13); font.bold: true }
                                        Text { text: (interfaceCard.net.kind || "Interface") + " · " + (interfaceCard.net.state || "unknown"); color: root.ink; opacity: 0.5; font.family: root.themeFont.family; font.pixelSize: Style.space(10) }
                                    }
                                    Row {
                                        width: parent.width
                                        Label { width: parent.width / 2; text: "↓ " + root.bytes(interfaceCard.net.down) + "/s"; color: root.memoryColor; font.pixelSize: Style.space(13) }
                                        Label { width: parent.width / 2; text: "↑ " + root.bytes(interfaceCard.net.up) + "/s"; color: root.gpuColor; horizontalAlignment: Text.AlignRight; font.pixelSize: Style.space(13) }
                                    }
                                    Label { text: "Received " + root.bytes(interfaceCard.net.received) + "  ·  Sent " + root.bytes(interfaceCard.net.sent); font.pixelSize: Style.space(10); opacity: 0.45 }
                                }
                            }
                        }
                    }
    }

    Component {
        id: temperaturesComponent
                    Section {
                        sectionKey: "temperatures"; title: "Temperatures"; icon: "󰔏"; tint: root.temperatureColor
                        summary: root.thermalSensors.length + " sensors  ·  " + root.temp(root.hottestSensor.value) + " max"
                        Row {
                            width: parent.width; spacing: Style.space(8)
                            ThermalHero { width: (parent.width - parent.spacing) / 2; heading: "PROCESSOR"; value: root.snapshot.cpuTemp; note: "CPU sensor maximum" }
                            ThermalHero { width: (parent.width - parent.spacing) / 2; heading: "HOTTEST SENSOR"; value: root.hottestSensor.value; note: root.hottestSensor.name || "No sensors detected" }
                        }
                        Label { visible: !root.thermalGroups.length; text: "No temperature sensors available"; opacity: 0.65 }
                        Repeater {
                            model: root.thermalGroups.length
                            Rectangle {
                                id: thermalCard
                                required property int index
                                readonly property var group: root.thermalGroups[index] || ({sensors: []})
                                width: parent.width; implicitHeight: thermalBody.implicitHeight + Style.space(24)
                                radius: Style.space(7); color: root.fade(root.temperatureColor, 0.035)
                                border.width: 1; border.color: root.fade(root.temperatureColor, 0.13)
                                Column {
                                    id: thermalBody
                                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                                    anchors.margins: Style.space(12); spacing: Style.space(10)
                                    Column {
                                        width: parent.width; spacing: Style.space(3)
                                        Label { text: thermalCard.group.title; font.bold: true; font.pixelSize: Style.space(13) }
                                        Label { text: thermalCard.group.subtitle; opacity: 0.45; font.pixelSize: Style.space(10) }
                                    }
                                    Repeater {
                                        model: thermalCard.group.sensors.length
                                        Column {
                                            id: sensorRow
                                            required property int index
                                            readonly property var sensor: thermalCard.group.sensors[index] || ({})
                                            readonly property string condition: Model.temperatureState(sensor)
                                            readonly property real limit: sensor.critical > 0 ? sensor.critical : sensor.maximum > 0 ? sensor.maximum : 100
                                            width: thermalBody.width; spacing: Style.space(4)
                                            RowLayout {
                                                width: parent.width
                                                Text { Layout.fillWidth: true; text: (sensorRow.sensor.label || sensorRow.sensor.name || "").replace(/^temp([0-9]+)$/, "Sensor $1"); elide: Text.ElideRight; color: root.ink; opacity: 0.75; font.family: root.themeFont.family; font.pixelSize: Style.space(12) }
                                                Text { text: sensorRow.condition; visible: text !== ""; color: Color.urgent; font.family: root.themeFont.family; font.pixelSize: Style.space(10) }
                                                Text { text: root.temp(sensorRow.sensor.value); color: sensorRow.condition ? Color.urgent : root.temperatureColor; font.family: root.themeFont.family; font.pixelSize: Style.space(18); font.bold: true }
                                            }
                                            Rectangle {
                                                width: parent.width; height: Style.space(4); radius: height/2; color: root.fade(root.temperatureColor, 0.12)
                                                Rectangle { width: parent.width * Math.max(0, Math.min(1, (sensorRow.sensor.value || 0) / sensorRow.limit)); height: parent.height; radius: height/2; color: sensorRow.condition ? Color.urgent : root.temperatureColor; Behavior on width { NumberAnimation { duration: 250 } } }
                                            }
                                            Label { text: sensorRow.sensor.critical > 0 ? "Critical limit " + root.temp(sensorRow.sensor.critical) : sensorRow.sensor.maximum > 0 ? "High limit " + root.temp(sensorRow.sensor.maximum) : "Scale 0–100°C · no hardware limit reported"; opacity: 0.4; font.pixelSize: Style.space(10) }
                                        }
                                    }
                                }
                            }
                        }
                    }
    }

    Component {
        id: processesComponent
                    Section {
                        sectionKey: "processes"; title: "Top processes"; icon: "󰓅"; tint: root.cpuColor
                        summary: root.processes.length + " shown"
                        RowLayout {
                            width: parent.width; spacing: Style.space(10)
                            Text { Layout.fillWidth: true; text: "RANKED BY CPU"; color: root.ink; opacity: 0.5; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.letterSpacing: 1 }
                            Text { Layout.preferredWidth: Style.space(64); text: "CPU"; horizontalAlignment: Text.AlignRight; color: root.cpuColor; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.bold: true; font.letterSpacing: 1 }
                            Text { Layout.preferredWidth: Style.space(88); text: "MEMORY"; horizontalAlignment: Text.AlignRight; color: root.memoryColor; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.bold: true; font.letterSpacing: 1; rightPadding: Style.space(10) }
                        }
                        Label { visible: !root.processes.length; text: "Waiting for process readings…"; opacity: 0.65 }
                        Repeater {
                            model: root.processes.length
                            Rectangle {
                                id: processCard
                                required property int index
                                readonly property var process: root.processes[index] || ({})
                                readonly property bool leading: index === 0 && process.cpu > 0
                                width: parent.width; implicitHeight: Style.space(63)
                                radius: Style.space(7)
                                color: root.fade(leading ? root.cpuColor : root.ink, leading ? 0.075 : 0.025)
                                border.width: 1; border.color: root.fade(leading ? root.cpuColor : root.ink, leading ? 0.24 : 0.07)
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: Style.space(10); spacing: Style.space(10)
                                    Rectangle {
                                        Layout.preferredWidth: Style.space(26); Layout.preferredHeight: width; radius: Style.space(7)
                                        color: root.fade(root.cpuColor, processCard.leading ? 0.18 : 0.07)
                                        Text { anchors.centerIn: parent; text: String(processCard.index + 1).padStart(2, "0"); color: root.cpuColor; opacity: processCard.leading ? 1 : 0.55; font.family: root.themeFont.family; font.pixelSize: Style.space(11); font.bold: true }
                                    }
                                    Column {
                                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Style.space(6)
                                        Text { width: parent.width; text: processCard.process.name || "—"; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(13); font.bold: true }
                                        Text { text: "PID " + (processCard.process.pid || "—"); color: root.ink; opacity: 0.4; font.family: root.themeFont.family; font.pixelSize: Style.space(10) }
                                    }
                                    Column {
                                        Layout.preferredWidth: Style.space(64); spacing: Style.space(9)
                                        Text { width: parent.width; text: root.stale ? "—" : (processCard.process.cpu || 0).toFixed(1) + "%"; horizontalAlignment: Text.AlignRight; color: root.cpuColor; font.family: root.themeFont.family; font.pixelSize: Style.space(14); font.bold: true; fontSizeMode: Text.Fit; minimumPixelSize: Style.space(10) }
                                        Rectangle {
                                            width: parent.width; height: Style.space(3); radius: height / 2; color: root.fade(root.cpuColor, 0.12)
                                            Rectangle { width: parent.width * (processCard.process.cpu || 0) / root.processCpuMaximum; height: parent.height; radius: height / 2; color: root.cpuColor }
                                        }
                                    }
                                    Column {
                                        Layout.preferredWidth: Style.space(88); spacing: Style.space(9)
                                        Text { width: parent.width; text: root.stale ? "—" : root.bytes(processCard.process.memory); horizontalAlignment: Text.AlignRight; color: root.memoryColor; font.family: root.themeFont.family; font.pixelSize: Style.space(13); font.bold: true; fontSizeMode: Text.Fit; minimumPixelSize: Style.space(10) }
                                        Rectangle {
                                            width: parent.width; height: Style.space(3); radius: height / 2; color: root.fade(root.memoryColor, 0.12)
                                            Rectangle { width: parent.width * (processCard.process.memory || 0) / root.processMemoryMaximum; height: parent.height; radius: height / 2; color: root.memoryColor }
                                        }
                                    }
                                }
                            }
                        }
                        Label { text: "CPU: 100% = one fully occupied thread"; opacity: 0.5; font.pixelSize: Style.space(10) }
                        Label { text: "Bars compare each column’s highest reading in this list"; opacity: 0.4; font.pixelSize: Style.space(10); wrapMode: Text.WordWrap; elide: Text.ElideNone }
                    }
    }

    Component {
        id: gpuComponent
                        Section {
                            id: gpuSection
                            readonly property var gpuHost: parent
                            readonly property var modelData: gpuHost && gpuHost.gpu ? gpuHost.gpu : ({})
                            sectionKey: "gpu-" + gpuSection.modelData.id
                            legacyKey: "gpu-" + gpuSection.modelData.card
                            tint: root.gpuColor; icon: "󰢮"
                            title: gpuSection.modelData.kind === "dedicated" ? "Dedicated GPU" : gpuSection.modelData.kind === "integrated" ? "Integrated GPU" : "Graphics processor"
                            summary: root.pct(gpuSection.modelData.usage) + "  ·  " + root.temp(gpuSection.modelData.temp)
                            Label { text: gpuSection.modelData.name; opacity: 0.75; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                            Meter { value: gpuSection.modelData.usage; tint: root.gpuColor }
                            Label { text: gpuSection.modelData.usage === null ? "Utilization unavailable from this driver" : "Utilization  " + root.pct(gpuSection.modelData.usage) }
                            Label { text: "VRAM  " + root.bytes(gpuSection.modelData.used) + " / " + root.bytes(gpuSection.modelData.total) }
                            Flow {
                                width: parent.width; spacing: Style.space(5)
                                Button { text: "Pin temperature ↗"; foreground: root.gpuColor; bordered: true; focusable: true; fontSize: Style.space(11); onClicked: { let next = Object.assign({}, root.settings, {metric: "GPU temperature", gpuSource: gpuSection.modelData.id}); root.shellHost.shell.updateEntryInline(root.moduleName, next) } }
                            }

                        }
    }

    Component {
        id: overviewComponent
                    Row {
                        width: parent.width; spacing: Style.space(8)
                        SummaryTile { width: (parent.width - parent.spacing * 2) / 3; title: "CPU"; reading: root.pct(root.snapshot.cpu); note: root.temp(root.snapshot.cpuTemp); tint: root.cpuColor; values: root.history.cpu || []; metricName: "CPU" }
                        SummaryTile { width: (parent.width - parent.spacing * 2) / 3; title: "MEMORY"; reading: root.pct((root.snapshot.memory || {}).percent); note: root.bytes((root.snapshot.memory || {}).used); tint: root.memoryColor; values: root.history.memory || []; metricName: "Memory" }
                        SummaryTile { width: (parent.width - parent.spacing * 2) / 3; title: "GPU"; reading: root.pct(root.primaryGpu.usage); note: root.temp(root.primaryGpu.temp); tint: root.gpuColor; values: root.history[root.primaryGpu.id] || []; metricName: "GPU" }
                    }
    }
    component Label: Text {
        width: parent.width
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: root.ink
        font.family: root.themeFont.family
        font.pixelSize: Math.max(14, root.themeFont.body)
    }
    component Meter: Rectangle {
        property var value
        property color tint: root.cpuColor
        width: parent.width; height: Style.space(6); radius: height / 2
        color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.12)
        Rectangle {
            width: parent.width * Math.max(0, Math.min(100, parent.value || 0)) / 100
            height: parent.height; radius: height / 2
            color: parent.value >= 90 ? Color.urgent : parent.tint
            Behavior on width { NumberAnimation { duration: 250 } }
        }
    }
    component RateCard: Rectangle {
        id: rate
        required property string heading
        required property real value
        required property color tint
        property var samples: []
        readonly property real graphMaximum: Math.max(1024, ...samples.filter(v => v !== null))
        implicitHeight: Style.space(125); radius: Style.space(8)
        color: root.fade(tint, 0.065); border.width: 1; border.color: root.fade(tint, 0.18)
        Column {
            anchors.fill: parent; anchors.margins: Style.space(11); spacing: Style.space(6)
            Text { text: rate.heading; color: rate.tint; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.bold: true; font.letterSpacing: 1 }
            Text { width: parent.width; fontSizeMode: Text.Fit; minimumPixelSize: Style.space(13); text: root.stale ? "—" : root.bytes(rate.value) + "/s"; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(22); font.bold: true }
            Sparkline { width: parent.width; height: Style.space(35); values: rate.samples; maximum: rate.graphMaximum; tint: rate.tint }
            Text { text: "Peak " + root.bytes(rate.graphMaximum === 1024 ? Math.max(0, ...rate.samples.filter(v => v !== null)) : rate.graphMaximum) + "/s"; color: rate.tint; opacity: 0.6; font.family: root.themeFont.family; font.pixelSize: Style.space(10) }
        }
    }
    component ThermalHero: Rectangle {
        id: hero
        required property string heading
        property var value
        property string note: ""
        implicitHeight: Style.space(100); radius: Style.space(8)
        color: root.fade(root.temperatureColor, 0.065); border.width: 1; border.color: root.fade(root.temperatureColor, 0.18)
        Column {
            anchors.fill: parent; anchors.margins: Style.space(11); spacing: Style.space(6)
            Text { text: hero.heading; color: root.temperatureColor; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.bold: true; font.letterSpacing: 1 }
            Text { text: root.stale ? "—" : root.temp(hero.value); color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(28); font.bold: true }
            Text { width: parent.width; text: hero.note; elide: Text.ElideRight; color: root.ink; opacity: 0.5; font.family: root.themeFont.family; font.pixelSize: Style.space(10) }
        }
    }
    component SummaryTile: Controls.AbstractButton {
        id: tile
        required property string title
        required property string reading
        required property string note
        required property color tint
        required property string metricName
        property var values: []
        implicitHeight: Style.space(133)
        hoverEnabled: true
        Accessible.name: title + " " + reading + ". Pin to top bar"
        onClicked: root.save("metric", metricName)
        background: Rectangle {
            radius: Style.space(10)
            color: root.fade(tile.tint, tile.hovered ? 0.14 : 0.075)
            border.width: 1
            border.color: root.fade(tile.tint, tile.activeFocus || root.metric === tile.metricName ? 0.75 : 0.2)
            Behavior on color { ColorAnimation { duration: 120 } }
        }
        contentItem: Item {
            Column {
                anchors.fill: parent; anchors.margins: Style.space(12); spacing: Style.space(4)
                Text { text: tile.title; color: tile.tint; font.family: root.themeFont.family; font.pixelSize: Style.space(10); font.bold: true; font.letterSpacing: 1.2 }
                Text { width: parent.width; fontSizeMode: Text.Fit; minimumPixelSize: Style.space(16); text: root.stale ? "—" : tile.reading; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(29); font.bold: true }
                Text { width: parent.width; elide: Text.ElideRight; text: tile.note; color: root.ink; opacity: 0.65; font.family: root.themeFont.family; font.pixelSize: Style.space(11) }
                Sparkline { width: parent.width; height: Style.space(25); values: tile.values; tint: tile.tint }
            }
        }
    }
    component Choice: Controls.AbstractButton {
        id: choice
        property bool selected: false
        width: parent.width; implicitHeight: Style.space(34)
        hoverEnabled: true
        Accessible.name: text
        background: Rectangle {
            radius: Style.space(6)
            color: root.fade(root.gpuColor, choice.selected ? 0.16 : choice.hovered ? 0.09 : 0.025)
            border.width: 1; border.color: root.fade(root.gpuColor, choice.selected || choice.activeFocus ? 0.65 : 0.12)
        }
        contentItem: RowLayout {
            spacing: Style.space(8)
            Text { text: choice.selected ? "●" : "○"; color: root.gpuColor; leftPadding: Style.space(10) }
            Text { Layout.fillWidth: true; text: choice.text; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(12); rightPadding: Style.space(10) }
        }
    }
    component Section: Rectangle {
        id: section
        required property string sectionKey
        required property string title
        property string summary: ""
        property string icon: ""
        property string legacyKey: ""
        property color tint: root.ink
        readonly property bool expanded: !root.isCollapsed(sectionKey, legacyKey)
        default property alias detail: details.data
        width: parent.width
        implicitHeight: heading.height + (expanded ? details.implicitHeight + Style.space(14) : 0)
        radius: Style.space(9)
        color: root.fade(root.ink, 0.035)
        border.width: 1; border.color: root.fade(root.ink, 0.09)
        Controls.AbstractButton {
            id: heading
            width: parent.width; height: Style.space(43)
            hoverEnabled: true
            Accessible.name: section.title + " " + section.summary + (section.expanded ? ". Collapse" : ". Expand")
            onClicked: root.foldGpu(section.sectionKey, section.legacyKey)
            background: Rectangle {
                radius: Style.space(9)
                color: root.fade(section.tint, heading.hovered || heading.activeFocus ? 0.1 : 0)
                border.width: heading.activeFocus ? 1 : 0; border.color: section.tint
            }
            contentItem: RowLayout {
                spacing: Style.space(10)
                Text { text: section.icon; color: section.tint; font.family: root.themeFont.family; font.pixelSize: Style.space(17); leftPadding: Style.space(12) }
                Text { text: section.title; Layout.fillWidth: true; color: root.ink; font.family: root.themeFont.family; font.pixelSize: Style.space(13); font.bold: true; elide: Text.ElideRight }
                Text { Layout.maximumWidth: parent.width * 0.48; elide: Text.ElideRight; text: section.summary; color: section.tint; opacity: 0.85; font.family: root.themeFont.family; font.pixelSize: Style.space(12) }
                Text { text: section.expanded ? "⌄" : "›"; color: root.ink; opacity: 0.5; font.pixelSize: Style.space(17); rightPadding: Style.space(12) }
            }
        }
        Column {
            id: details
            anchors.top: heading.bottom
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: Style.space(14); anchors.rightMargin: Style.space(14)
            spacing: Style.space(8)
            visible: section.expanded
        }
    }
}
