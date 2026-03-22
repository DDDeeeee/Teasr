import QtQuick
import QtQuick.Layouts
import "Theme.js" as Theme
import "components"
import "pages"

Rectangle {
    id: root
    color: Theme.windowBackground

    function tr(name, fallback) {
        const translations = appBridge.translations || {}
        return translations[name] || fallback
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.pageMargin
        spacing: Theme.pageGap

        CardSurface {
            Layout.preferredWidth: Theme.sidebarWidth
            Layout.maximumWidth: Theme.sidebarWidth
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.cardPadding
                spacing: Theme.cardGap

                ColumnLayout {
                    spacing: 4

                    Text {
                        text: "TEASR"
                        color: Theme.textPrimary
                        font.pixelSize: 24
                        font.weight: Font.Bold
                    }

                    Text {
                        text: root.tr("sidebar_subtitle", "Desktop Speech Workspace")
                        color: Theme.textSecondary
                        font.pixelSize: 13
                    }
                }

                SidebarButton {
                    text: root.tr("sidebar_console", "Console")
                    current: appBridge.currentPage === 0
                    Layout.fillWidth: true
                    onClicked: appBridge.setCurrentPage(0)
                }

                SidebarButton {
                    text: root.tr("sidebar_settings", "Settings")
                    current: appBridge.currentPage === 1
                    Layout.fillWidth: true
                    onClicked: appBridge.setCurrentPage(1)
                }

                SidebarButton {
                    text: root.tr("sidebar_diagnostics", "Diagnostics")
                    current: appBridge.currentPage === 2
                    Layout.fillWidth: true
                    onClicked: appBridge.setCurrentPage(2)
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 96
                    radius: Theme.cardRadius
                    color: "#faf5ed"
                    border.width: 1
                    border.color: Theme.border

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 6

                        Text {
                            text: root.tr("sidebar_primary_hotkey", "Primary Hotkey")
                            color: Theme.textMuted
                            font.pixelSize: 11
                            font.capitalization: Font.AllUppercase
                        }

                        Text {
                            text: appBridge.formatHotkeyLabel(appBridge.state.primary_hotkey || "")
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.weight: Font.Bold
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: appBridge.state.hotkey_mode_label || "-"
                            color: Theme.accentWarm
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            maximumLineCount: 1
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: appBridge.currentPage

            HomePage { }
            SettingsPage { }
            DiagnosticsPage { }
        }
    }

    ToastBanner {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: Theme.pageMargin
        anchors.rightMargin: Theme.pageMargin + 6
        width: Math.min(360, parent.width * 0.34)
        message: appBridge.toastMessage
        level: appBridge.toastLevel
    }
}
