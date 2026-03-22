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

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    function modeLabel(mode) {
        switch (String(mode)) {
        case "1": return tr("mode_non_stream", "File Transcription")
        case "2": return tr("mode_non_stream_polish", "File Transcription + Polish")
        case "3": return tr("mode_realtime", "Realtime Speech Recognition")
        case "4": return tr("mode_realtime_polish", "Realtime Recognition + Polish")
        default: return String(mode)
        }
    }

    function modeDescription(mode) {
        switch (String(mode)) {
        case "1": return tr("mode_desc_non_stream", "Hold the hotkey to record and get the full result after release.")
        case "2": return tr("mode_desc_non_stream_polish", "Recognize the whole segment first, then polish and auto-insert it.")
        case "3": return tr("mode_desc_realtime", "Show a realtime bubble while speaking and insert the final text on release.")
        case "4": return tr("mode_desc_realtime_polish", "Show a realtime bubble while speaking, then polish and stream the final text after release.")
        default: return ""
        }
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
                hero: true
                implicitHeight: overviewLoader.implicitHeight + Theme.cardPadding * 2

                Loader {
                    id: overviewLoader
                    anchors.fill: parent
                    anchors.margins: Theme.cardPadding
                    sourceComponent: overviewWide
                }
            }

            CardSurface {
                width: parent.width
                implicitHeight: modeSection.implicitHeight + Theme.cardPadding * 2

                Column {
                    id: modeSection
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.cardPadding
                    spacing: Theme.cardGap

                    Text {
                        text: root.tr("home_mode_select", "Mode Selection")
                        color: Theme.textPrimary
                        font.pixelSize: 18
                        font.weight: Font.Bold
                    }

                    Text {
                        width: parent.width
                        text: root.tr("home_mode_select_hint", "Choose the current recognition workflow.")
                        color: Theme.textSecondary
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    GridLayout {
                        width: parent.width
                        columns: width >= 760 ? 2 : 1
                        rowSpacing: Theme.cardGap
                        columnSpacing: Theme.cardGap

                        Repeater {
                            model: ["1", "2", "3", "4"]

                            delegate: ModeCard {
                                Layout.fillWidth: true
                                title: root.modeLabel(modelData)
                                description: root.modeDescription(modelData)
                                current: appBridge.state.current_mode === modelData
                                onClicked: appBridge.setMode(modelData)
                            }
                        }
                    }
                }
            }

            GridLayout {
                width: parent.width
                columns: 3
                rowSpacing: Theme.cardGap
                columnSpacing: Theme.cardGap

                SelectorCard {
                    Layout.fillWidth: true
                    eyebrow: root.tr("home_hotkey_mode", "Hotkey Mode")
                    title: appBridge.state.hotkey_mode_label || "-"
                    detail: root.tr("home_hotkey_mode_detail", "Changes take effect immediately.")
                    optionsModel: appBridge.hotkeyModeOptions
                    selectedValue: appBridge.state.hotkey_mode || "hold"
                    onValueSelected: function(value) { appBridge.setHotkeyMode(value) }
                }

                SelectorCard {
                    Layout.fillWidth: true
                    eyebrow: root.tr("home_input_source", "Input Source")
                    title: appBridge.state.input_source_label || "-"
                    detail: root.tr("home_input_source_detail", "Switch the recording input source.")
                    optionsModel: appBridge.inputSourceOptions
                    selectedValue: appBridge.state.input_source_type || "local_mic"
                    onValueSelected: function(value) { appBridge.setInputSourceType(value) }
                }

                SelectorCard {
                    Layout.fillWidth: true
                    eyebrow: root.tr("home_optimization", "Optimization Level")
                    title: appBridge.state.optimization_level_label || "-"
                    detail: root.tr("home_optimization_detail", "Adjust how aggressively the text is polished.")
                    optionsModel: appBridge.optimizationOptions
                    selectedValue: appBridge.state.optimization_level || "normal"
                    onValueSelected: function(value) { appBridge.setOptimizationLevel(value) }
                }
            }

            GridLayout {
                width: parent.width
                columns: width >= 760 ? 2 : 1
                columnSpacing: Theme.cardGap
                rowSpacing: Theme.cardGap

                CardSurface {
                    Layout.fillWidth: true
                    implicitHeight: previewColumn.implicitHeight + Theme.cardPadding * 2

                    Column {
                        id: previewColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.cardPadding
                        spacing: Theme.cardGap

                        Text {
                            text: root.tr("home_recent_result", "Recent Result")
                            color: Theme.textPrimary
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }

                        Text {
                            width: parent.width
                            text: appBridge.state.last_result_preview || root.tr("home_no_result", "No recognition result yet.")
                            color: Theme.textSecondary
                            font.pixelSize: 14
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                CardSurface {
                    Layout.fillWidth: true
                    implicitHeight: remoteLoader.implicitHeight + Theme.cardPadding * 2

                    Loader {
                        id: remoteLoader
                        anchors.fill: parent
                        anchors.margins: Theme.cardPadding
                        sourceComponent: width >= 430 ? remoteWide : remoteNarrow
                    }
                }
            }
        }
    }

    Component {
        id: overviewWide

        RowLayout {
            spacing: Theme.cardGap + 2

            Column {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 6

                Text {
                    width: parent.width
                    text: root.tr("home_current_workflow", "Current Workflow")
                    color: Theme.textMuted
                    font.pixelSize: 11
                    font.capitalization: Font.AllUppercase
                }

                Text {
                    width: parent.width
                    text: appBridge.state.mode_label || "-"
                    color: Theme.textPrimary
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    wrapMode: Text.WordWrap
                }

                Text {
                    width: parent.width
                    text: appBridge.state.active_model_name || "-"
                    color: Theme.accentWarm
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Text {
                    width: parent.width
                    text: appBridge.state.active_model_detail || appBridge.state.mode_description || ""
                    color: Theme.textSecondary
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                Layout.preferredWidth: 292
                Layout.maximumWidth: 292
                Layout.minimumWidth: 260
                implicitHeight: statusColumnWide.implicitHeight + 28
                radius: Theme.cardRadius
                color: "#fffaf6"
                border.width: 1
                border.color: Theme.border

                Column {
                    id: statusColumnWide
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    spacing: 8

                    StatusPill {
                        status: appBridge.state.app_status || "idle"
                        label: appBridge.state.status_label || "-"
                    }

                    Text {
                        width: parent.width
                        text: root.tr("home_hotkey_mode_line", "Hotkey mode: {value}").replace("{value}", appBridge.state.hotkey_mode_label || "-")
                        color: Theme.textPrimary
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: root.tr("home_input_source_line", "Input source: {value}").replace("{value}", appBridge.state.input_source_label || "-")
                        color: Theme.textSecondary
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: root.tr("home_optimization_line", "Optimization level: {value}").replace("{value}", appBridge.state.optimization_level_label || "-")
                        color: Theme.textSecondary
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: root.tr("home_primary_hotkey_line", "Primary hotkey: {value}").replace("{value}", appBridge.formatHotkeyLabel(appBridge.state.primary_hotkey || ""))
                        color: Theme.textMuted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        width: parent.width
                        spacing: 8

                        AppButton {
                            Layout.fillWidth: true
                            text: root.tr("home_start_recording", "Start Recording")
                            primary: true
                            onClicked: appBridge.startRecording()
                        }

                        AppButton {
                            Layout.fillWidth: true
                            text: root.tr("home_stop_transcribing", "Stop Recognition")
                            primary: false
                            onClicked: appBridge.stopRecording()
                        }
                    }
                }
            }
        }
    }

    Component {
        id: remoteWide

        RowLayout {
            spacing: Theme.cardGap

            Rectangle {
                Layout.preferredWidth: 198
                Layout.maximumWidth: 198
                Layout.minimumWidth: 182
                Layout.preferredHeight: 198
                radius: Theme.cardRadius
                color: "#fffdf8"
                border.width: 1
                border.color: Theme.border

                Image {
                    id: wideQrImage
                    anchors.centerIn: parent
                    width: 182
                    height: 182
                    fillMode: Image.PreserveAspectFit
                    source: appBridge.state.remote_phone_qr_source || ""
                    visible: source !== ""
                }

                Text {
                    anchors.centerIn: parent
                    visible: !wideQrImage.visible
                    text: root.tr("home_waiting_address", "Waiting for URL")
                    color: Theme.textMuted
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }

            Column {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: 6

                RowLayout {
                    width: parent.width
                    spacing: 8

                    Text {
                        text: root.tr("home_remote_mic", "Phone Microphone")
                        color: Theme.textPrimary
                        font.pixelSize: 18
                        font.weight: Font.Bold
                    }

                    Item { Layout.fillWidth: true }

                    StatusPill {
                        status: appBridge.state.remote_phone_ready ? "completed" : "idle"
                        label: appBridge.state.remote_phone_state_label || "-"
                    }
                }

                Text {
                    width: parent.width
                    text: root.tr("home_remote_url", "Access URL")
                    color: Theme.textMuted
                    font.pixelSize: 11
                    font.capitalization: Font.AllUppercase
                }

                Text {
                    width: parent.width
                    text: appBridge.state.remote_phone_url || "-"
                    color: Theme.textSecondary
                    font.pixelSize: 13
                    wrapMode: Text.WrapAnywhere
                }

                Text {
                    width: parent.width
                    text: root.tr("home_remote_device", "Connected Device")
                    color: Theme.textMuted
                    font.pixelSize: 11
                    font.capitalization: Font.AllUppercase
                }

                Text {
                    width: parent.width
                    text: appBridge.state.remote_phone_device_name || root.tr("home_remote_device_hint", "Open the phone page and grant permission")
                    color: Theme.textSecondary
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }

                Flow {
                    width: parent.width
                    spacing: 8

                    AppButton {
                        width: parent.width >= 250 ? (parent.width - 8) / 2 : parent.width
                        text: root.tr("home_copy_address", "Copy URL")
                        primary: false
                        enabled: (appBridge.state.remote_phone_url || "") !== ""
                        onClicked: appBridge.copyRemotePhoneUrl()
                    }

                    AppButton {
                        width: parent.width >= 250 ? (parent.width - 8) / 2 : parent.width
                        text: root.tr("home_restart_service", "Restart Service")
                        primary: false
                        onClicked: appBridge.restartRemotePhoneService()
                    }
                }
            }
        }
    }

    Component {
        id: remoteNarrow

        Column {
            spacing: Theme.cardGap

            RowLayout {
                width: parent.width
                spacing: 8

                Text {
                    text: root.tr("home_remote_mic", "Phone Microphone")
                    color: Theme.textPrimary
                    font.pixelSize: 18
                    font.weight: Font.Bold
                }

                Item { Layout.fillWidth: true }

                StatusPill {
                    status: appBridge.state.remote_phone_ready ? "completed" : "idle"
                    label: appBridge.state.remote_phone_state_label || "-"
                }
            }

            Rectangle {
                width: Math.min(parent.width, 198)
                height: width
                radius: Theme.cardRadius
                color: "#fffdf8"
                border.width: 1
                border.color: Theme.border

                Image {
                    id: narrowQrImage
                    anchors.centerIn: parent
                    width: parent.width - 16
                    height: parent.height - 16
                    fillMode: Image.PreserveAspectFit
                    source: appBridge.state.remote_phone_qr_source || ""
                    visible: source !== ""
                }

                Text {
                    anchors.centerIn: parent
                    visible: !narrowQrImage.visible
                    text: root.tr("home_waiting_address", "Waiting for URL")
                    color: Theme.textMuted
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }

            Text {
                width: parent.width
                text: root.tr("home_remote_url", "Access URL")
                color: Theme.textMuted
                font.pixelSize: 11
                font.capitalization: Font.AllUppercase
            }

            Text {
                width: parent.width
                text: appBridge.state.remote_phone_url || "-"
                color: Theme.textSecondary
                font.pixelSize: 13
                wrapMode: Text.WrapAnywhere
            }

            Text {
                width: parent.width
                text: root.tr("home_remote_device", "Connected Device")
                color: Theme.textMuted
                font.pixelSize: 11
                font.capitalization: Font.AllUppercase
            }

            Text {
                width: parent.width
                text: appBridge.state.remote_phone_device_name || root.tr("home_remote_device_hint", "Open the phone page and grant permission")
                color: Theme.textSecondary
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }

            RowLayout {
                width: parent.width
                spacing: 8

                AppButton {
                    Layout.fillWidth: true
                    text: root.tr("home_copy_address", "Copy URL")
                    primary: false
                    enabled: (appBridge.state.remote_phone_url || "") !== ""
                    onClicked: appBridge.copyRemotePhoneUrl()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: root.tr("home_restart_service", "Restart Service")
                    primary: false
                    onClicked: appBridge.restartRemotePhoneService()
                }
            }
        }
    }
}
