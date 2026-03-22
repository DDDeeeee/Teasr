import QtQuick
import "../Theme.js" as Theme

Rectangle {
    id: root

    property alias text: label.text
    property bool primary: true
    property bool enabled: true
    signal clicked()

    implicitHeight: Theme.controlHeight
    implicitWidth: Math.max(96, label.implicitWidth + 32)
    radius: Theme.buttonRadius
    color: !enabled
        ? (primary ? "#85858a" : "#f4eee6")
        : primary
            ? (mouseArea.pressed ? "#15161b" : mouseArea.containsMouse ? "#2b2c33" : Theme.accentDark)
            : (mouseArea.pressed ? "#f1ebe3" : mouseArea.containsMouse ? "#f9f4ed" : "#fffaf6")
    border.width: primary ? 0 : 1
    border.color: primary ? "transparent" : (mouseArea.containsMouse ? Theme.borderStrong : Theme.border)
    opacity: enabled ? 1.0 : 0.58

    Text {
        id: label
        anchors.centerIn: parent
        color: root.primary ? "#ffffff" : Theme.textPrimary
        font.pixelSize: 14
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}