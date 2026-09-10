import QtQuick

Canvas {
    id: root
    property var values: []
    property real maximum: 100
    onMaximumChanged: requestPaint()
    required property color tint
    onValuesChanged: requestPaint()
    onTintChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        if (!values || values.length < 2) return
        ctx.strokeStyle = tint
        ctx.lineWidth = 1.8
        ctx.lineJoin = "round"
        let started = false
        ctx.beginPath()
        for (let i = 0; i < values.length; i++) {
            if (values[i] === null || values[i] === undefined) { started = false; continue }
            const x = i * width / (values.length - 1)
            const y = height - 3 - Math.max(0, Math.min(maximum, values[i])) * (height - 6) / Math.max(1, maximum)
            if (started) ctx.lineTo(x, y); else { ctx.moveTo(x, y); started = true }
        }
        ctx.stroke()
    }
}
