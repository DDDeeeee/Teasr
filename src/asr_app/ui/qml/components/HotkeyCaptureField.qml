import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

FocusScope {
    id: root

    property string value: ""
    property string placeholderText: ""
    signal valueEdited(string value)

    function resolvedPlaceholder() {
        if (root.placeholderText.length > 0) {
            return root.placeholderText
        }
        const translations = appBridge.translations || {}
        return translations.comp_hotkey_placeholder || "Click and press a hotkey"
    }

    implicitHeight: Theme.controlHeight

    function modifierOnly(key) {
        return key === Qt.Key_Control || key === Qt.Key_Shift || key === Qt.Key_Alt || key === Qt.Key_Meta
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) {
            root.value = ""
            root.valueEdited("")
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Escape) {
            root.focus = false
            event.accepted = true
            return
        }
        if (modifierOnly(event.key)) {
            event.accepted = true
            return
        }
        var hotkey = appBridge.buildHotkeyFromEvent(event.key, event.text, event.modifiers)
        if (!hotkey) {
            return
        }
        root.value = hotkey
        root.valueEdited(hotkey)
        root.focus = false
        event.accepted = true
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.buttonRadius
        color: "#fbfaf7"
        border.width: 1
        border.color: root.activeFocus ? Theme.borderStrong : Theme.border
    }

    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        text: root.value ? appBridge.formatHotkeyLabel(root.value) : root.resolvedPlaceholder()
        color: root.value ? Theme.textPrimary : Theme.textMuted
        font.pixelSize: 13
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.forceActiveFocus()
    }
}
