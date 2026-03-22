import QtQuick
import QtQuick.Window

Window {
    id: root

    property real audioLevel: overlayBridge ? overlayBridge.audioLevel : 0.0
    property bool active: overlayBridge ? overlayBridge.active : false

    width: 200
    height: 40
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
          | Qt.WindowDoesNotAcceptFocus
    color: "transparent"
    visible: false

    onActiveChanged: {
        if (active) {
            fadeOut.stop();
            levelStore.reset();
            _reposition();
            visible = true;
            opacity = 1;
            fadeIn.start();
        } else if (visible) {
            fadeIn.stop();
            fadeOut.start();
        }
    }

    function _reposition() {
        var scr = Screen;
        if (!scr) return;
        x = Math.round(scr.virtualX + (scr.width - width) / 2);
        y = Math.round(scr.virtualY + scr.desktopAvailableHeight - height - 48);
    }

    NumberAnimation {
        id: fadeIn
        target: root
        property: "opacity"
        from: 0; to: 1; duration: 200
        easing.type: Easing.OutCubic
    }

    NumberAnimation {
        id: fadeOut
        target: root
        property: "opacity"
        from: root.opacity; to: 0; duration: 200
        easing.type: Easing.OutCubic
        onFinished: {
            root.visible = false;
            root.opacity = 1;
        }
    }

    // --- background pill ---
    Rectangle {
        anchors.fill: parent
        radius: 10
        color: "#d0181818"
    }

    // --- pulsing red dot with ripple (Canvas) ---
    Canvas {
        id: rippleCanvas
        x: 4; y: 0
        width: 48; height: root.height

        property real t1: 0.0
        property real t2: 0.0

        NumberAnimation on t1 {
            from: 0; to: 1; duration: 1600
            easing.type: Easing.OutCubic
            loops: Animation.Infinite
            running: root.visible
        }

        onT1Changed: requestPaint()
        onT2Changed: requestPaint()

        // stagger second ripple
        property bool ring2Active: false
        Timer {
            id: ring2Starter
            interval: 800; repeat: false; running: false
            onTriggered: rippleCanvas.ring2Active = true
        }

        Connections {
            target: root
            function onVisibleChanged() {
                if (root.visible) {
                    rippleCanvas.ring2Active = false;
                    rippleCanvas.t2 = 0;
                    ring2Starter.start();
                }
            }
        }

        Timer {
            interval: 33; repeat: true; running: root.visible && rippleCanvas.ring2Active
            onTriggered: {
                // drive t2 manually to stay offset
                rippleCanvas.t2 += 0.02063;
                if (rippleCanvas.t2 > 1.0) rippleCanvas.t2 -= 1.0;
            }
        }

        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);

            var cx = width / 2;
            var cy = height / 2;
            var coreR = 5;
            var maxR = 12;

            // ripple ring 1
            _drawRipple(ctx, cx, cy, coreR, maxR, t1);

            // ripple ring 2
            if (ring2Active) {
                _drawRipple(ctx, cx, cy, coreR, maxR, t2);
            }

            // core dot
            ctx.beginPath();
            ctx.arc(cx, cy, coreR, 0, 2 * Math.PI);
            ctx.fillStyle = "#f04444";
            ctx.fill();
        }

        function _drawRipple(ctx, cx, cy, minR, maxR, t) {
            var r = minR + (maxR - minR) * t;
            var alpha = 0.7 * (1.0 - t);
            if (alpha < 0.01) return;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, 2 * Math.PI);
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = Qt.rgba(0.94, 0.27, 0.27, alpha);
            ctx.stroke();
        }
    }

    // --- audio level bars ---
    Item {
        id: barArea
        x: 52; y: 0
        width: 24 * 5
        height: root.height

        Repeater {
            model: 24

            Rectangle {
                required property int index

                property real rawLevel: {
                    var hist = levelStore.history;
                    return (index < hist.length) ? hist[index] : 0;
                }
                property real norm: Math.min(1.0, rawLevel / 0.12)
                property real barH: Math.max(2, norm * 28)

                width: 2.5
                height: barH
                x: index * 5
                y: (barArea.height - height) / 2
                radius: 1.25
                antialiasing: true

                color: {
                    if (norm < 0.4)
                        return "#73c080";
                    if (norm < 0.75)
                        return "#e8c840";
                    return "#f05a4a";
                }

                Behavior on height {
                    NumberAnimation { duration: 60; easing.type: Easing.OutQuad }
                }
            }
        }
    }

    // --- level history store ---
    QtObject {
        id: levelStore
        property var history: []
        property real displayLevel: 0.0

        function reset() {
            var empty = [];
            for (var i = 0; i < 24; i++) empty.push(0);
            history = empty;
            displayLevel = 0;
        }
    }

    Timer {
        id: tickTimer
        interval: 33
        repeat: true
        running: root.visible

        onTriggered: {
            var target = root.audioLevel;
            var dl = levelStore.displayLevel;
            dl += (target - dl) * 0.34;
            if (Math.abs(dl) < 0.0005) dl = 0;
            levelStore.displayLevel = dl;

            var h = levelStore.history.slice();
            h.push(dl);
            if (h.length > 24) h.shift();
            levelStore.history = h;
        }
    }
}
