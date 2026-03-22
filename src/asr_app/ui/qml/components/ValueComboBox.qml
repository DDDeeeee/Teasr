import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

ComboBox {
    id: root

    property var optionsModel: []
    property string selectedValue: ""
    signal valueSelected(string value)

    model: optionsModel
    textRole: "label"
    implicitHeight: Theme.controlHeight
    hoverEnabled: true
    activeFocusOnTab: false
    focusPolicy: Qt.NoFocus

    function syncCurrentIndex() {
        if (!optionsModel || optionsModel.length === 0) {
            return
        }
        for (var i = 0; i < optionsModel.length; i += 1) {
            if (String(optionsModel[i].value) === String(selectedValue)) {
                currentIndex = i
                return
            }
        }
        currentIndex = 0
    }

    onOptionsModelChanged: syncCurrentIndex()
    onSelectedValueChanged: syncCurrentIndex()
    Component.onCompleted: syncCurrentIndex()
    onActivated: {
        if (currentIndex >= 0 && currentIndex < optionsModel.length) {
            valueSelected(String(optionsModel[currentIndex].value))
        }
    }

    delegate: ItemDelegate {
        width: ListView.view ? ListView.view.width : 0
        highlighted: root.highlightedIndex === index
        hoverEnabled: true
        contentItem: Text {
            text: modelData.label
            color: Theme.textPrimary
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 10
            color: parent.highlighted ? Theme.accentSoft : (parent.hovered ? "#fbf7f1" : "#fffdfa")
        }
    }

    indicator: Text {
        text: "▼"
        color: Theme.textMuted
        font.pixelSize: 12
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: 12
    }

    contentItem: Text {
        leftPadding: 12
        rightPadding: 30
        text: root.displayText
        color: Theme.textPrimary
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Theme.buttonRadius
        color: mouseArea.containsMouse ? "#fcfbf8" : "#fbfaf7"
        border.width: 1
        border.color: root.popup.visible ? Theme.borderStrong : Theme.border
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
    }

    popup: Popup {
        y: root.height + 4
        width: root.width
        padding: 6
        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 280)
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            clip: true
        }
        background: Rectangle {
            radius: 14
            color: "#fffdfa"
            border.width: 1
            border.color: Theme.border
        }
    }
}