// A dot drawn above every window, so a pedal press is visible without leaving
// the game or the instrument. Compiled by build-pkg.sh and bundled next to the
// frozen daemon; the daemon shows it by spawning this and hides it by closing
// our stdin.
import Cocoa

func arg(_ name: String, _ fallback: Double) -> Double {
    let a = CommandLine.arguments
    guard let i = a.firstIndex(of: name), i + 1 < a.count, let v = Double(a[i + 1]) else {
        return fallback
    }
    return v
}

guard let screen = NSScreen.main else { exit(1) }

let size = arg("--size", 10)
let right = arg("--right", 25)
let ring = arg("--ring", 2)
// visibleFrame stops below the menu bar, so the gap is its height — which
// differs between a notched display and an external one. Centre the dot in
// that strip rather than guessing a constant.
let menuBar = screen.frame.maxY - screen.visibleFrame.maxY
let top = arg("--top", max(0, (menuBar - size) / 2))

let app = NSApplication.shared
// No Dock icon, and orderFrontRegardless below never takes focus: whatever the
// user is playing or recording in must keep it.
app.setActivationPolicy(.accessory)

// The ring grows outwards, so --size and the offsets keep meaning the red core.
let outer = size + ring * 2
let frame = NSRect(
    x: screen.frame.maxX - right - size - ring,
    y: screen.frame.maxY - top - size - ring,
    width: outer,
    height: outer
)
let win = NSWindow(contentRect: frame, styleMask: .borderless, backing: .buffered, defer: false)
win.isOpaque = false
win.backgroundColor = .clear
win.hasShadow = false
win.ignoresMouseEvents = true
// Above the menu bar and above full-screen apps; only a captured display wins.
win.level = .screenSaver
win.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]

// Not pure black and not opaque: the ring should read as the housing the lamp
// sits in, not as a second dot.
let bezel = NSView(frame: NSRect(origin: .zero, size: frame.size))
bezel.wantsLayer = true
bezel.layer?.backgroundColor = NSColor(white: 0.18, alpha: 0.75).cgColor
bezel.layer?.cornerRadius = outer / 2

let dot = NSView(frame: NSRect(x: ring, y: ring, width: size, height: size))
dot.wantsLayer = true
dot.layer?.backgroundColor = NSColor.systemRed.cgColor
dot.layer?.cornerRadius = size / 2
bezel.addSubview(dot)
win.contentView = bezel
win.orderFrontRegardless()

// The daemon holds the write end. EOF means it asked us to go or died trying,
// and either way a dot must never outlive the daemon that put it there.
DispatchQueue.global().async {
    while !FileHandle.standardInput.availableData.isEmpty {}
    DispatchQueue.main.async { app.terminate(nil) }
}

app.run()
