import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml
import "../Theme.js" as Theme
import "../components"

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

    property var connectionForm: ({})
    property var behaviorForm: ({})

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    function cloneMap(source) {
        var result = {}
        if (!source) {
            return result
        }
        for (var key in source) {
            result[key] = source[key]
        }
        return result
    }

    function syncForms() {
        connectionForm = cloneMap(appBridge.connectionSettings)
        behaviorForm = cloneMap(appBridge.behaviorSettings)
    }

    Component.onCompleted: syncForms()

    Connections {
        target: appBridge
        function onConnectionSettingsChanged() { syncForms() }
        function onBehaviorSettingsChanged() { syncForms() }
    }

    component FieldLabel: Text {
        color: Theme.textMuted
        font.pixelSize: 11
    }

    component InputField: Rectangle {
        id: fieldRoot

        property alias text: input.text
        property string placeholderText: ""
        property alias echoMode: input.echoMode
        property alias validator: input.validator
        property color textColor: Theme.textPrimary
        signal textEdited(string text)

        implicitHeight: Theme.controlHeight
        radius: Theme.buttonRadius
        color: "#fbfaf7"
        border.width: 1
        border.color: input.activeFocus ? Theme.borderStrong : Theme.border

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            color: fieldRoot.textColor
            font.pixelSize: 13
            verticalAlignment: TextInput.AlignVCenter
            selectByMouse: true
            selectedTextColor: Theme.textPrimary
            selectionColor: Theme.accentSoft
            onTextEdited: fieldRoot.textEdited(text)
        }

        Text {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            visible: input.text.length === 0 && !input.activeFocus && fieldRoot.placeholderText.length > 0
            text: fieldRoot.placeholderText
            color: Theme.textMuted
            font.pixelSize: 13
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onClicked: input.forceActiveFocus()
        }
    }

    Item {
        width: root.availableWidth
        implicitHeight: contentColumn.implicitHeight

        Column {
            id: contentColumn
            width: parent.width
            spacing: Theme.pageGap

            GridLayout {
                width: parent.width
                columns: width >= 760 ? 2 : 1
                columnSpacing: Theme.cardGap
                rowSpacing: Theme.cardGap

                CardSurface {
                    Layout.fillWidth: true
                    implicitHeight: connectionColumn.implicitHeight + Theme.cardPadding * 2

                    Column {
                        id: connectionColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.cardPadding
                        spacing: Theme.cardGap

                        Text {
                            text: root.tr("settings_connection_model", "Connection & Models")
                            color: Theme.textPrimary
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }

                        Text {
                            text: root.tr("settings_asr_service", "ASR Service")
                            color: Theme.textPrimary
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }

                        property bool isDoubao: (connectionForm.asr_provider || "aliyun") === "doubao"

                        FieldLabel { text: root.tr("settings_asr_provider", "ASR Provider") }
                        ValueComboBox {
                            width: parent.width
                            optionsModel: appBridge.asrProviderOptions
                            selectedValue: connectionForm.asr_provider || "aliyun"
                            onValueSelected: function(value) { connectionForm.asr_provider = value }
                        }

                        Column {
                            width: parent.width
                            spacing: Theme.cardGap
                            visible: !connectionColumn.isDoubao

                            FieldLabel { text: root.tr("settings_asr_api_key", "ASR API Key") }

                            Flow {
                                width: parent.width
                                spacing: 8

                                InputField {
                                    width: parent.width >= 360 ? parent.width - 100 : parent.width
                                    text: connectionForm.asr_api_key || ""
                                    echoMode: appBridge.apiKeyVisible ? TextInput.Normal : TextInput.Password
                                    placeholderText: root.tr("settings_asr_api_key_placeholder", "Enter the ASR API Key")
                                    onTextEdited: function(text) { connectionForm.asr_api_key = text }
                                }

                                AppButton {
                                    width: parent.width >= 360 ? 92 : parent.width
                                    text: appBridge.apiKeyVisible ? root.tr("common_hide", "Hide") : root.tr("common_show", "Show")
                                    primary: false
                                    onClicked: appBridge.toggleApiKeyVisibility()
                                }
                            }

                            FieldLabel { text: root.tr("settings_asr_base_url", "ASR Base URL") }
                            InputField {
                                width: parent.width
                                text: connectionForm.asr_base_url || ""
                                placeholderText: root.tr("settings_asr_base_url_placeholder", "Leave blank to use the default endpoint")
                                onTextEdited: function(text) { connectionForm.asr_base_url = text }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: Theme.cardGap
                            visible: connectionColumn.isDoubao

                            FieldLabel { text: root.tr("settings_doubao_app_key", "App Key") }
                            InputField {
                                width: parent.width
                                text: connectionForm.asr_app_key || ""
                                placeholderText: root.tr("settings_doubao_app_key_placeholder", "Enter the Doubao App Key")
                                onTextEdited: function(text) { connectionForm.asr_app_key = text }
                            }

                            FieldLabel { text: root.tr("settings_doubao_access_key", "Access Key") }

                            Flow {
                                width: parent.width
                                spacing: 8

                                InputField {
                                    width: parent.width >= 360 ? parent.width - 100 : parent.width
                                    text: connectionForm.asr_api_key || ""
                                    echoMode: appBridge.apiKeyVisible ? TextInput.Normal : TextInput.Password
                                    placeholderText: root.tr("settings_doubao_access_key_placeholder", "Enter the Doubao Access Key")
                                    onTextEdited: function(text) { connectionForm.asr_api_key = text }
                                }

                                AppButton {
                                    width: parent.width >= 360 ? 92 : parent.width
                                    text: appBridge.apiKeyVisible ? root.tr("common_hide", "Hide") : root.tr("common_show", "Show")
                                    primary: false
                                    onClicked: appBridge.toggleApiKeyVisibility()
                                }
                            }
                        }

                        FieldLabel { text: root.tr("settings_non_stream_model", "Non-realtime ASR Model") }
                        Flow {
                            width: parent.width
                            spacing: 8

                            InputField {
                                width: parent.width >= 360 ? parent.width - 80 : parent.width
                                text: connectionForm.asr_non_stream_model || ""
                                onTextEdited: function(text) { connectionForm.asr_non_stream_model = text }
                            }

                            AppButton {
                                width: parent.width >= 360 ? 72 : parent.width
                                text: root.tr("settings_test", "Test")
                                primary: false
                                onClicked: appBridge.testAsrNonStream()
                            }
                        }

                        FieldLabel { text: root.tr("settings_realtime_model", "Realtime ASR Model") }
                        InputField {
                            width: parent.width
                            text: connectionForm.asr_realtime_model || ""
                            onTextEdited: function(text) { connectionForm.asr_realtime_model = text }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: Theme.border
                            opacity: 0.8
                        }

                        Text {
                            text: root.tr("settings_text_polish_service", "Text Polish Service")
                            color: Theme.textPrimary
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }

                        FieldLabel { text: root.tr("settings_text_polish_api_key", "Text Polish API Key") }

                        Flow {
                            width: parent.width
                            spacing: 8

                            InputField {
                                width: parent.width >= 360 ? parent.width - 100 : parent.width
                                text: connectionForm.text_polish_api_key || ""
                                echoMode: appBridge.textPolishApiKeyVisible ? TextInput.Normal : TextInput.Password
                                placeholderText: root.tr("settings_text_polish_api_key_placeholder", "Leave blank to reuse the ASR API Key")
                                onTextEdited: function(text) { connectionForm.text_polish_api_key = text }
                            }

                            AppButton {
                                width: parent.width >= 360 ? 92 : parent.width
                                text: appBridge.textPolishApiKeyVisible ? root.tr("common_hide", "Hide") : root.tr("common_show", "Show")
                                primary: false
                                onClicked: appBridge.toggleTextPolishApiKeyVisibility()
                            }
                        }

                        FieldLabel { text: root.tr("settings_text_polish_base_url", "Text Polish Base URL") }
                        InputField {
                            width: parent.width
                            text: connectionForm.text_polish_base_url || ""
                            placeholderText: root.tr("settings_text_polish_base_url_placeholder", "Leave blank to reuse the ASR Base URL")
                            onTextEdited: function(text) { connectionForm.text_polish_base_url = text }
                        }

                        FieldLabel { text: root.tr("settings_text_polish_model", "Text Polish Model") }
                        Flow {
                            width: parent.width
                            spacing: 8

                            InputField {
                                width: parent.width >= 360 ? parent.width - 80 : parent.width
                                text: connectionForm.text_polish_model || ""
                                onTextEdited: function(text) { connectionForm.text_polish_model = text }
                            }

                            AppButton {
                                width: parent.width >= 360 ? 72 : parent.width
                                text: root.tr("settings_test", "Test")
                                primary: false
                                onClicked: appBridge.testTextPolish()
                            }
                        }

                        FieldLabel { text: root.tr("settings_primary_hotkey", "Primary Hotkey") }
                        HotkeyCaptureField {
                            width: parent.width
                            value: connectionForm.primary_hotkey || ""
                            placeholderText: root.tr("settings_primary_hotkey_placeholder", "Click and press the primary hotkey, Delete to clear")
                            onValueEdited: function(value) { connectionForm.primary_hotkey = value }
                        }

                        FieldLabel { text: root.tr("settings_secondary_hotkey", "Secondary Hotkey") }
                        HotkeyCaptureField {
                            width: parent.width
                            value: connectionForm.secondary_hotkey || ""
                            placeholderText: root.tr("settings_secondary_hotkey_placeholder", "Click and press the secondary hotkey, Delete to clear")
                            onValueEdited: function(value) { connectionForm.secondary_hotkey = value }
                        }

                        FieldLabel { text: root.tr("settings_log_level", "Log Level") }
                        ValueComboBox {
                            width: parent.width
                            optionsModel: appBridge.logLevelOptions
                            selectedValue: connectionForm.log_level || "INFO"
                            onValueSelected: function(value) { connectionForm.log_level = value }
                        }

                        FieldLabel { text: root.tr("settings_language", "Language") }
                        ValueComboBox {
                            width: parent.width
                            optionsModel: appBridge.languageOptions
                            selectedValue: connectionForm.language || ""
                            onValueSelected: function(value) {
                                connectionForm.language = value
                                appBridge.setLanguage(value)
                            }
                        }

                        Text {
                            width: parent.width
                            text: root.tr("settings_language_hint", "Desktop UI refreshes immediately. The phone page updates after the service reconnects.")
                            color: Theme.textSecondary
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        RowLayout {
                            width: parent.width
                            Item { Layout.fillWidth: true }
                            AppButton {
                                text: root.tr("settings_save", "Save Settings")
                                primary: true
                                onClicked: appBridge.saveConnectionSettings(connectionForm)
                            }
                        }
                    }
                }

                CardSurface {
                    Layout.fillWidth: true
                    implicitHeight: behaviorColumn.implicitHeight + Theme.cardPadding * 2

                    Column {
                        id: behaviorColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: Theme.cardPadding
                        spacing: Theme.cardGap

                        Text {
                            text: root.tr("settings_input_runtime", "Input & Runtime")
                            color: Theme.textPrimary
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }

                        Column {
                            width: parent.width
                            spacing: 8
                            visible: appBridge.state.input_source_type === "local_mic"

                            FieldLabel { text: root.tr("settings_local_audio_device", "Local Audio Input Device") }
                            ValueComboBox {
                                width: parent.width
                                optionsModel: appBridge.deviceOptions
                                selectedValue: behaviorForm.audio_input_device || ""
                                onValueSelected: function(value) { behaviorForm.audio_input_device = value }
                            }
                            AppButton {
                                text: root.tr("settings_refresh_devices", "Refresh Device List")
                                primary: false
                                onClicked: appBridge.refreshAudioDevices()
                            }
                        }

                        FieldLabel { text: root.tr("settings_remote_mic", "Phone Microphone") }

                        Rectangle {
                            width: parent.width
                            implicitHeight: remoteStatusColumn.implicitHeight + 28
                            radius: Theme.cardRadius
                            color: "#faf7f2"
                            border.width: 1
                            border.color: Theme.border

                            Column {
                                id: remoteStatusColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 14
                                spacing: 6

                                Text {
                                    width: parent.width
                                    text: appBridge.state.remote_phone_state_label || "-"
                                    color: Theme.textPrimary
                                    font.pixelSize: 15
                                    font.weight: Font.Bold
                                    wrapMode: Text.WordWrap
                                }

                                Text {
                                    width: parent.width
                                    text: appBridge.state.remote_phone_url || "-"
                                    color: Theme.textSecondary
                                    font.pixelSize: 12
                                    wrapMode: Text.WrapAnywhere
                                }

                                Text {
                                    width: parent.width
                                    text: appBridge.state.remote_phone_last_error || "-"
                                    color: Theme.textSecondary
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }

                                Flow {
                                    width: parent.width
                                    spacing: 8

                                    AppButton {
                                        width: parent.width >= 260 ? (parent.width - 8) / 2 : parent.width
                                        text: root.tr("settings_copy_phone_url", "Copy Phone URL")
                                        primary: false
                                        enabled: (appBridge.state.remote_phone_url || "") !== ""
                                        onClicked: appBridge.copyRemotePhoneUrl()
                                    }

                                    AppButton {
                                        width: parent.width >= 260 ? (parent.width - 8) / 2 : parent.width
                                        text: root.tr("settings_restart_phone_service", "Restart Phone Service")
                                        primary: false
                                        onClicked: appBridge.restartRemotePhoneService()
                                    }
                                }
                            }
                        }

                        FieldLabel { text: root.tr("settings_phone_input_gain", "Phone Input Gain") }
                        InputField {
                            width: parent.width
                            text: behaviorForm.remote_phone_input_gain || "0.75"
                            placeholderText: root.tr("settings_phone_input_gain_placeholder", "0.00 - 4.00")
                            validator: DoubleValidator { bottom: 0.0; top: 4.0; decimals: 2 }
                            onTextEdited: function(text) { behaviorForm.remote_phone_input_gain = text }
                        }

                        Text {
                            width: parent.width
                            text: root.tr("settings_phone_input_gain_hint", "Keep it around 0.50 - 1.20. Watch for clipping above 1.50.")
                            color: Theme.textSecondary
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        CheckBox {
                            text: root.tr("settings_enable_tray", "Enable System Tray")
                            checked: !!behaviorForm.enable_tray
                            focusPolicy: Qt.NoFocus
                            onToggled: behaviorForm.enable_tray = checked
                        }

                        CheckBox {
                            text: root.tr("settings_start_minimized", "Start Minimized to Tray")
                            checked: !!behaviorForm.start_minimized
                            focusPolicy: Qt.NoFocus
                            onToggled: behaviorForm.start_minimized = checked
                        }

                        FieldLabel { text: root.tr("settings_custom_prompt", "Custom Polish Prompt") }

                        Text {
                            width: parent.width
                            text: root.tr("settings_custom_prompt_hint", "When optimization level is set to Custom, this content replaces the built-in style instruction.")
                            color: Theme.textSecondary
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            width: parent.width
                            implicitHeight: Math.max(120, promptArea.implicitHeight + 24)
                            radius: Theme.buttonRadius
                            color: "#fbfaf7"
                            border.width: 1
                            border.color: promptArea.activeFocus ? Theme.borderStrong : Theme.border

                            Flickable {
                                id: promptFlick
                                anchors.fill: parent
                                anchors.margins: 12
                                contentWidth: width
                                contentHeight: promptArea.implicitHeight
                                clip: true
                                flickableDirection: Flickable.VerticalFlick
                                boundsBehavior: Flickable.StopAtBounds

                                function ensureVisible(r) {
                                    if (contentY >= r.y)
                                        contentY = r.y
                                    else if (contentY + height <= r.y + r.height)
                                        contentY = r.y + r.height - height
                                }

                                TextEdit {
                                    id: promptArea
                                    width: promptFlick.width
                                    text: behaviorForm.custom_polish_prompt || ""
                                    color: Theme.textPrimary
                                    font.pixelSize: 13
                                    wrapMode: TextEdit.Wrap
                                    selectByMouse: true
                                    selectedTextColor: Theme.textPrimary
                                    selectionColor: Theme.accentSoft
                                    onTextChanged: behaviorForm.custom_polish_prompt = text
                                    onCursorRectangleChanged: promptFlick.ensureVisible(cursorRectangle)
                                }
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.margins: 12
                                visible: promptArea.text.length === 0 && !promptArea.activeFocus
                                text: root.tr("settings_custom_prompt_placeholder", "Enter a custom polish instruction…")
                                color: Theme.textMuted
                                font.pixelSize: 13
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton
                                propagateComposedEvents: true
                                onClicked: function(mouse) {
                                    promptArea.forceActiveFocus()
                                    mouse.accepted = false
                                }
                            }
                        }

                        RowLayout {
                            width: parent.width
                            Item { Layout.fillWidth: true }
                            AppButton {
                                text: root.tr("settings_save", "Save Settings")
                                primary: true
                                onClicked: appBridge.saveBehaviorSettings(behaviorForm)
                            }
                        }
                    }
                }
            }
        }
    }
}
