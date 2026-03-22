import QtQuick
import QtQuick.Layouts
import "../Theme.js" as Theme

Rectangle {
    id: root

    property string title: ""
    property string value: ""
    property bool compact: false

    radius: Theme.cardRadius
    color: "#faf7f2"
    border.width: 1
    border.color: Theme.border
    implicitWidth: compact ? Math.max(150, Math.min(260, Math.max(titleText.implicitWidth, valueText.implicitWidth) + 32)) : 320
    implicitHeight: compact ? 74 : Math.max(92, contentColumn.implicitHeight + 28)

    Column {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: compact ? 12 : 16
        spacing: compact ? 6 : 8

        Text {
            id: titleText
            width: parent.width
            text: root.title
            color: Theme.textMuted
            font.pixelSize: compact ? 11 : 12
            wrapMode: Text.WordWrap
        }

        Text {
            id: valueText
            width: parent.width
            text: root.value
            color: Theme.textPrimary
            font.pixelSize: compact ? 13 : 14
            font.weight: Font.DemiBold
            wrapMode: compact ? Text.WordWrap : Text.WrapAnywhere
            maximumLineCount: compact ? 2 : 100
            elide: compact ? Text.ElideRight : Text.ElideNone
        }
    }
}