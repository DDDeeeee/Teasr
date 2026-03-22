import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Theme.js" as Theme
import "../components"

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    property var compactKeys: [
        "admin_rights",
        "hotkey_registered",
        "hotkey_mode",
        "primary_hotkey",
        "secondary_hotkey",
        "osd_status",
        "current_mode",
        "current_input_source",
        "phone_service",
        "phone_connection",
        "phone_gain",
        "remote_cert"
    ]
    property var detailKeys: [
        "current_input_device",
        "phone_url",
        "phone_device",
        "remote_session_id",
        "log_path",
        "asr_base_url",
        "text_polish_base_url",
        "non_stream_model",
        "realtime_model",
        "polish_model",
        "polish_output_key",
        "asr_api_key",
        "text_polish_api_key",
        "recent_warning",
        "recent_error",
        "recent_remote_error"
    ]

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    function filteredEntries(keys) {
        var source = appBridge.diagnosticsEntries || []
        var result = []
        for (var i = 0; i < keys.length; i += 1) {
            for (var j = 0; j < source.length; j += 1) {
                if (source[j].id === keys[i]) {
                    result.push(source[j])
                    break
                }
            }
        }
        return result
    }

    Item {
        width: root.availableWidth
        implicitHeight: contentColumn.implicitHeight

        Column {
            id: contentColumn
            width: parent.width
            spacing: Theme.pageGap

            CardSurface {
                width: parent.width
                implicitHeight: snapshotColumn.implicitHeight + Theme.cardPadding * 2

                Column {
                    id: snapshotColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.cardPadding
                    spacing: Theme.cardGap

                    Text {
                        text: root.tr("diag_snapshot", "Diagnostics Snapshot")
                        color: Theme.textPrimary
                        font.pixelSize: 18
                        font.weight: Font.Bold
                    }

                    Flow {
                        width: parent.width
                        spacing: Theme.cardGap

                        Repeater {
                            model: root.filteredEntries(root.compactKeys)

                            delegate: InfoPair {
                                compact: true
                                title: modelData.label
                                value: modelData.value
                            }
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: Theme.cardGap

                        Repeater {
                            model: root.filteredEntries(root.detailKeys)

                            delegate: InfoPair {
                                width: snapshotColumn.width
                                title: modelData.label
                                value: modelData.value
                            }
                        }
                    }
                }
            }

            CardSurface {
                width: parent.width
                hero: true
                implicitHeight: notesColumn.implicitHeight + Theme.cardPadding * 2

                Column {
                    id: notesColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.cardPadding
                    spacing: Theme.cardGap

                    Text {
                        text: root.tr("diag_runtime_notes", "Runtime Notes")
                        color: Theme.textPrimary
                        font.pixelSize: 18
                        font.weight: Font.Bold
                    }

                    Repeater {
                        model: appBridge.runtimeNotes

                        delegate: RowLayout {
                            width: notesColumn.width
                            spacing: 10

                            Rectangle {
                                width: 8
                                height: 8
                                radius: 4
                                color: Theme.accentWarm
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 6
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData
                                color: Theme.textSecondary
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            CardSurface {
                width: parent.width
                implicitHeight: 360

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.cardPadding
                    spacing: Theme.cardGap

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: root.tr("diag_runtime_logs", "Runtime Logs")
                            color: Theme.textPrimary
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }

                        Item { Layout.fillWidth: true }

                        AppButton {
                            text: root.tr("diag_open_log_folder", "Open Log Folder")
                            primary: false
                            onClicked: appBridge.openLogFolder()
                        }
                    }

                    ScrollView {
                        id: logScrollView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOn
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        TextArea {
                            id: logArea
                            width: logScrollView.availableWidth
                            text: appBridge.logText
                            readOnly: true
                            wrapMode: TextEdit.WrapAnywhere
                            color: Theme.textPrimary
                            font.pixelSize: 13
                            font.family: "Cascadia Mono"
                            selectByMouse: true
                            activeFocusOnTab: false
                            focusPolicy: Qt.NoFocus
                            background: Rectangle {
                                radius: Theme.cardRadius
                                color: "#fbfaf7"
                                border.width: 1
                                border.color: Theme.border
                            }
                            onTextChanged: {
                                Qt.callLater(function() {
                                    logScrollView.ScrollBar.vertical.position =
                                        1.0 - logScrollView.ScrollBar.vertical.size;
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}
