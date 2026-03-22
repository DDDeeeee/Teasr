import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

Rectangle {
    id: root

    property string status: "idle"
    property string label: ""

    function backgroundColor() {
        if (status === "recording" || status === "realtime_streaming") return "#e8f3ec"
        if (status === "transcribing" || status === "polishing" || status === "injecting") return "#f9efd9"
        if (status === "failed") return "#f7e2df"
        if (status === "completed") return "#edf4e6"
        return "#efe8df"
    }

    function textColor() {
        if (status === "recording" || status === "realtime_streaming") return Theme.success
        if (status === "transcribing" || status === "polishing" || status === "injecting") return Theme.warning
        if (status === "failed") return Theme.danger
        if (status === "completed") return Theme.success
        return Theme.idle
    }

    implicitHeight: 32
    implicitWidth: labelMetrics.width + 28
    radius: 16
    color: backgroundColor()
    border.width: 1
    border.color: Qt.darker(color, 1.06)

    Text {
        id: labelMetrics
        anchors.centerIn: parent
        text: root.label
        color: root.textColor()
        font.pixelSize: 13
        font.weight: Font.DemiBold
    }
}
