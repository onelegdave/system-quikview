import QtQuick
import Quickshell.Io
import qs.Commons
import "Model.js" as Model

QtObject {
    id: root
    property string path: Color.currentThemePath + "/colors.toml"
    property var values: ({})
    readonly property color memory: values.color6 || values.cyan || Color.accent
    readonly property color gpu: values.color4 || values.blue || Color.accent
    readonly property color temperature: values.color3 || values.yellow || Color.accent
    property FileView paletteFile: FileView {
        path: root.path
        watchChanges: true
        printErrors: false
        onLoaded: root.values = Model.parsePalette(text())
        onFileChanged: reload()
        onLoadFailed: root.values = ({})
    }
    // Theme switching replaces the current theme files. Shell color updates
    // provide a second reload trigger even when a file watcher follows old files.
    property Connections themeChanges: Connections {
        target: Color
        function onShellValuesChanged() { root.paletteFile.reload() }
        function onAccentChanged() { root.paletteFile.reload() }
        function onForegroundChanged() { root.paletteFile.reload() }
    }
}
