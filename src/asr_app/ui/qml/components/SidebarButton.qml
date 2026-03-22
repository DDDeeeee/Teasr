import QtQuick
import "../Theme.js" as Theme

Rectangle {
    id: root

    property alias text: label.text
    property bool current: false
    property bool enabled: true
    signal clicked()

    implicitHeight: Theme.controlHeight
    implicitWidth: 120
    radius: Theme.buttonRadius
    color: current
        ? Theme.accentDark
        : (mouseArea.pressed ? "#f2ece4" : mouseArea.containsMouse ? "#faf5ee" : "transparent")
    border.width: current ? 0 : 1
    border.color: current ? "transparent" : (mouseArea.containsMouse ? Theme.borderStrong : "transparent")
    opacity: enabled ? 1.0 : 0.56

    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        color: current ? "#ffffff" : Theme.textPrimary
        font.pixelSize: 14
        font.weight: Font.DemiBold
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