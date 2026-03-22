import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme

Rectangle {
    id: root

    property string message: ""
    property string level: "info"
    visible: message.length > 0
    opacity: visible ? 1 : 0
    radius: 18
    color: level === "error" ? "#f7e2df" : level === "warning" ? "#f9efd9" : "#edf3ff"
    border.width: 1
    border.color: level === "error" ? "#deb4ad" : level === "warning" ? "#e2ce9a" : "#c6d4ee"

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    Behavior on opacity { NumberAnimation { duration: 180 } }

    Timer {
        id: dismissTimer
        interval: 2800
        repeat: false
        onTriggered: appBridge.clearToast()
    }

    Connections {
        target: appBridge
        function onToastMessageChanged() {
            if (appBridge.toastMessage.length > 0) {
                dismissTimer.restart()
            }
        }
    }

    implicitHeight: toastRow.implicitHeight + 28

    RowLayout {
        id: toastRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 14
        spacing: 10

        Text {
            text: root.level === "error"
                ? root.tr("comp_toast_error", "Error")
                : root.level === "warning"
                    ? root.tr("comp_toast_warning", "Notice")
                    : root.tr("comp_toast_info", "Info")
            color: Theme.textPrimary
            font.pixelSize: 13
            font.weight: Font.Bold
            Layout.minimumWidth: implicitWidth
        }

        Text {
            text: root.message
            color: Theme.textPrimary
            font.pixelSize: 13
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}
