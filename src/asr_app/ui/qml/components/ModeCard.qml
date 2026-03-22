import QtQuick
import QtQuick.Layouts
import "../Theme.js" as Theme

Rectangle {
    id: root

    property string title: ""
    property string description: ""
    property bool current: false
    signal clicked()

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    implicitHeight: contentColumn.implicitHeight + Theme.cardPadding * 2
    radius: Theme.cardRadius
    color: current ? "#f3ebe1" : (mouseArea.pressed ? "#f8f2ea" : mouseArea.containsMouse ? "#fcf8f2" : "#ffffff")
    border.width: 1
    border.color: current ? Theme.borderStrong : (mouseArea.containsMouse ? Theme.borderStrong : Theme.border)
    clip: true

    Column {
        id: contentColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.cardPadding
        spacing: Theme.sectionGap

        Text {
            width: parent.width
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: 16
            font.weight: Font.Bold
            wrapMode: Text.WordWrap
        }

        Text {
            width: parent.width
            text: root.description
            color: Theme.textSecondary
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }

        Rectangle {
            width: stateLabel.implicitWidth + 18
            height: 28
            radius: 14
            color: root.current ? Theme.accentDark : Theme.accentSoft

            Text {
                id: stateLabel
                anchors.centerIn: parent
                text: root.current ? root.tr("comp_mode_current", "Current Mode") : root.tr("comp_mode_switch", "Click to Switch")
                color: root.current ? "#ffffff" : Theme.accentWarm
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
