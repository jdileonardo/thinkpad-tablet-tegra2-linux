import QtQuick
import QtQuick.Window

Window {
    id: window
    width: 800
    height: 1280
    visibility: Window.FullScreen
    color: "blue"
    title: "Indigo Qt Quick Wayland check"
    property int frames: 0
    property bool settled: false
    property bool announced: false
    onFrameSwapped: {
        frames++
        if (settled && !announced) {
            announced = true
            console.log("READY_CAPTURE QtQuick frames=" + frames + " size=" + width + "x" + height + " final=left-red,right-blue")
        }
    }
    Rectangle {
        width: window.width / 2
        height: window.height
        color: "red"
    }
    Rectangle {
        id: animated
        width: 96
        height: 96
        anchors.centerIn: parent
        color: "white"
        opacity: 0.5
        NumberAnimation on rotation {
            running: !window.settled
            from: 0
            to: 360
            duration: 2000
            loops: Animation.Infinite
        }
        visible: !window.settled
    }
    Text {
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Qt Quick on Tegra / Wayland"
        color: "white"
        font.pixelSize: 28
        visible: !window.settled
    }
    Timer {
        interval: 6000
        running: true
        onTriggered: window.settled = true
    }
    Timer {
        interval: 13000
        running: true
        onTriggered: Qt.quit()
    }
}
