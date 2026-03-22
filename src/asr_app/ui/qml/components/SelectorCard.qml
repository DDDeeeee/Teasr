import QtQuick
import QtQuick.Layouts
import "../Theme.js" as Theme

CardSurface {
    id: root

    property string eyebrow: ""
    property string title: ""
    property string detail: ""
    property var optionsModel: []
    property string selectedValue: ""
    signal valueSelected(string value)

    implicitHeight: contentColumn.implicitHeight + Theme.cardPadding * 2

    Column {
        id: contentColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.cardPadding
        spacing: Theme.sectionGap

        Text {
            width: parent.width
            text: root.eyebrow
            color: Theme.textMuted
            font.pixelSize: 11
            font.capitalization: Font.AllUppercase
        }

        Text {
            width: parent.width
            text: root.title
            color: Theme.textPrimary
            font.pixelSize: 18
            font.weight: Font.Bold
            elide: Text.ElideRight
        }

        Text {
            visible: text.length > 0
            width: parent.width
            text: root.detail
            color: Theme.textSecondary
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }

        ValueComboBox {
            width: parent.width
            optionsModel: root.optionsModel
            selectedValue: root.selectedValue
            onValueSelected: function(value) { root.valueSelected(value) }
        }
    }
}