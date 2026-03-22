import QtQuick
import QtQuick.Controls
import "../Theme.js" as Theme

Rectangle {
    id: root

    property bool hero: false

    implicitWidth: 240
    implicitHeight: 140
    radius: hero ? Theme.heroRadius : Theme.cardRadius
    color: hero ? Theme.panelMuted : Theme.panelBackground
    border.width: 1
    border.color: hero ? Theme.borderStrong : Theme.border
    clip: true
    gradient: Gradient {
        GradientStop { position: 0.0; color: root.hero ? Theme.heroStart : root.color }
        GradientStop { position: 1.0; color: root.hero ? Theme.heroEnd : root.color }
    }
}