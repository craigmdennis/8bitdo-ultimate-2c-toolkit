// SPDX-License-Identifier: GPL-3.0-or-later
// Ultimate 2 Wireless Controller Test: a prototype that only reads and shows. What IOKit lists for 8BitDo devices, what
// GameController makes of each controller, every input as it moves, and two rumble tests: through GameController, and
// with 8BitDo's own output report (ID 5: strong, weak, strong, weak, 0-100) sent straight to the controller. It writes
// nothing to the controller's memory.
import AppKit
import CoreHaptics
import GameController
import IOKit.hid

final class App: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let text = NSTextView()
    let status = NSTextField(labelWithString: "")
    var seen = Set<String>()
    var engines: [CHHapticEngine] = []
    var lastNote = ""
    var raw: [UInt32: [UInt8]] = [:]        // report ID -> the latest input report from 2dc8:6012
    var rawRest: [UInt32: [UInt8]] = [:]    // report ID -> the first one seen, when nothing was pressed yet
    var rawState = "Raw reports: waiting for the controller."
    var rawManager: IOHIDManager?

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 640),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Ultimate 2 Wireless Controller Test"
        window.subtitle = "Prototype · reads only"
        text.isEditable = false
        text.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        text.textContainerInset = NSSize(width: 8, height: 8)
        let scroll = NSScrollView()
        scroll.documentView = text
        scroll.hasVerticalScroller = true
        text.autoresizingMask = [.width]
        let intro = NSTextField(wrappingLabelWithString: "Connect the controller over Bluetooth and keep this window in front. Press every button and move each stick and trigger: what macOS's GameController recognises lights up in green under Inputs and gets a ✓ once it has been used; under Raw report, the bytes the controller itself sends are marked ^ while they differ from the controller at rest, which also shows buttons GameController doesn't know. Then click Copy Report and paste it in the issue. Home may also open Apple's Games app; that's macOS.")
        let buttons = NSStackView(views: [
            NSButton(title: "Vibrate with GameController", target: self, action: #selector(vibrate)),
            NSButton(title: "Vibrate with 8BitDo's Report", target: self, action: #selector(direct)),
            NSButton(title: "Copy Report", target: self, action: #selector(copyReport)),
            NSButton(title: "Clear", target: self, action: #selector(clear))])
        buttons.spacing = 8
        let stack = NSStackView(views: [intro, buttons, status, scroll])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 16, left: 16, bottom: 16, right: 16)
        for v in [intro, status, scroll] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32).isActive = true }
        window.contentView = stack
        let menu = NSMenu(), item = NSMenuItem(), sub = NSMenu()
        sub.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = sub
        menu.addItem(item)
        NSApp.mainMenu = menu
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        GCController.startWirelessControllerDiscovery {}
        startRaw()
        Timer.scheduledTimer(withTimeInterval: 1.0 / 20, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // IOKit: every HID interface with 8BitDo's vendor ID, listed without opening it.
    func hidLines() -> [String] {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x2DC8] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        defer { IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone)) }
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        let p = { (d: IOHIDDevice, k: String) in IOHIDDeviceGetProperty(d, k as CFString) }
        return devices.map { d in
            let n = { (k: String) in (p(d, k) as? Int) ?? 0 }
            return String(format: "  %04x:%04x  %@  page %04x usage %04x  in %d out %d  %@", n(kIOHIDVendorIDKey), n(kIOHIDProductIDKey),
                          (p(d, kIOHIDTransportKey) as? String ?? "?"), n(kIOHIDPrimaryUsagePageKey), n(kIOHIDPrimaryUsageKey),
                          n(kIOHIDMaxInputReportSizeKey), n(kIOHIDMaxOutputReportSizeKey), (p(d, kIOHIDProductKey) as? String ?? ""))
        }.sorted()
    }

    // The controller's own input reports, read through IOKit (macOS asks for Input Monitoring the first time).
    func startRaw() {
        let m = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(m, [kIOHIDVendorIDKey: 0x2DC8, kIOHIDProductIDKey: 0x6012] as CFDictionary)
        IOHIDManagerRegisterInputReportCallback(m, { ctx, _, _, _, id, report, length in
            let me = Unmanaged<App>.fromOpaque(ctx!).takeUnretainedValue()
            let bytes = Array(UnsafeBufferPointer(start: report, count: length))
            if me.rawRest[id] == nil { me.rawRest[id] = bytes }
            me.raw[id] = bytes
        }, Unmanaged.passUnretained(self).toOpaque())
        IOHIDManagerScheduleWithRunLoop(m, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        let r = IOHIDManagerOpen(m, IOOptionBits(kIOHIDOptionsTypeNone))
        if r != kIOReturnSuccess {
            rawState = "Raw reports: macOS refused (IOReturn \(String(UInt32(bitPattern: r), radix: 16))). Allow Input Monitoring for this app in System Settings › Privacy & Security, then open it again."
        }
        rawManager = m
    }

    func rawLines() -> [String] {
        if raw.isEmpty { return [rawState] }
        var out: [String] = []
        for id in raw.keys.sorted() {
            let b = raw[id]!, rest = rawRest[id] ?? b
            out.append("  report \(id), \(b.count) bytes:")
            for start in stride(from: 0, to: b.count, by: 16) {
                let idx = Array(start..<min(start + 16, b.count))
                out.append(String(format: "   %3d  ", start) + idx.map { String(format: "%02x", b[$0]) }.joined(separator: " "))
                out.append("        " + idx.map { $0 < rest.count && b[$0] != rest[$0] ? "^^" : "  " }.joined(separator: " "))
            }
        }
        return out
    }

    func bar(_ v: Float) -> String {   // -1...1 as a 21-character bar, centre at 0
        let n = Int((max(-1, min(1, v)) + 1) * 10)
        return "[" + String(repeating: "-", count: n) + "|" + String(repeating: "-", count: 20 - n) + "]"
    }

    func padLines(_ c: GCController) -> [String] {
        var out = ["  name: \(c.vendorName ?? "none")", "  category: \(c.productCategory)",
                   "  profile: \(c.extendedGamepad != nil ? "extended gamepad" : c.microGamepad != nil ? "micro gamepad" : "physical input profile only")"]
        if let h = c.haptics {
            out.append("  vibration: yes, localities \(h.supportedLocalities.map { $0.rawValue }.sorted().joined(separator: ", "))")
        } else {
            out.append("  vibration: not offered")
        }
        if let m = c.motion {
            if m.sensorsRequireManualActivation && !m.sensorsActive { m.sensorsActive = true }
            out.append(String(format: "  motion: yes, rotation rate %@, gravity %@; now rotation %.2f %.2f %.2f",
                              m.hasRotationRate ? "yes" : "no", m.hasGravityAndUserAcceleration ? "yes" : "no",
                              m.rotationRate.x, m.rotationRate.y, m.rotationRate.z))
        } else {
            out.append("  motion: not offered")
        }
        if let b = c.battery {
            out.append(String(format: "  battery: %.0f %%, state %d", b.batteryLevel * 100, b.batteryState.rawValue))
        } else {
            out.append("  battery: not reported")
        }
        let prof = c.physicalInputProfile
        out.append("")
        out.append("  Inputs (\(prof.buttons.count) buttons, \(prof.axes.count) axes, \(prof.dpads.count) pads):")
        for name in prof.buttons.keys.sorted() {
            let b = prof.buttons[name]!
            if b.isPressed { seen.insert(name) }
            out.append("  \(b.isPressed ? "●" : seen.contains(name) ? "✓" : "·") \(name)\(b.isPressed ? String(format: "   PRESSED %.2f", b.value) : "")")
        }
        for name in prof.axes.keys.sorted() {
            let a = prof.axes[name]!
            if abs(a.value) > 0.2 { seen.insert(name) }
            out.append("  \(abs(a.value) > 0.2 ? "●" : seen.contains(name) ? "✓" : "·") \(name.padding(toLength: 26, withPad: " ", startingAt: 0)) \(bar(a.value)) \(String(format: "%+.2f", a.value))")
        }
        for name in prof.dpads.keys.sorted() {
            let d = prof.dpads[name]!, moved = abs(d.xAxis.value) > 0.2 || abs(d.yAxis.value) > 0.2
            if moved { seen.insert(name) }
            out.append("  \(moved ? "●" : seen.contains(name) ? "✓" : "·") \(name.padding(toLength: 26, withPad: " ", startingAt: 0)) x \(bar(d.xAxis.value)) y \(bar(d.yAxis.value))")
        }
        return out
    }

    func report() -> String {
        var lines = ["Ultimate 2 Wireless Controller Test, macOS \(ProcessInfo.processInfo.operatingSystemVersionString)", "", "IOKit (vendor 2dc8):"]
        let hid = hidLines()
        lines += hid.isEmpty ? ["  none"] : hid
        lines += ["", "GameController:"]
        let pads = GCController.controllers()
        if pads.isEmpty { lines.append("  no controller") }
        for c in pads { lines += padLines(c) + [""] }
        lines.append("Used so far: \(seen.sorted().joined(separator: ", "))")
        lines += ["", "Raw report (the controller's own bytes, ^ = differs from rest):"] + rawLines()
        if !lastNote.isEmpty { lines += ["", lastNote] }
        return lines.joined(separator: "\n")
    }

    func refresh() {
        guard NSApp.isActive else { return }
        let r = report()
        guard text.string != r else { return }
        let font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular), bold = NSFont.monospacedSystemFont(ofSize: 12, weight: .bold)
        let out = NSMutableAttributedString()
        for line in r.split(separator: "\n", omittingEmptySubsequences: false) {
            let s = String(line)
            let pressed = s.hasPrefix("  ●") || s.hasPrefix("        ") && s.contains("^")
            out.append(NSAttributedString(string: s + "\n", attributes: [.font: pressed ? bold : font,
                .foregroundColor: pressed ? NSColor.systemGreen : s.hasPrefix("  ✓") ? NSColor.labelColor : NSColor.secondaryLabelColor]))
        }
        let keep = text.enclosingScrollView?.contentView.bounds.origin
        text.textStorage?.setAttributedString(out)
        if let keep { text.enclosingScrollView?.contentView.scroll(to: keep) }
    }

    @objc func vibrate() {
        guard let pad = GCController.controllers().first(where: { $0.haptics != nil }) else { return say("GameController offers no vibration for any connected controller.") }
        guard let engine = pad.haptics?.createEngine(withLocality: .default) else { return say("The vibration couldn't be started.") }
        do {
            try engine.start()
            let event = CHHapticEvent(eventType: .hapticContinuous, parameters: [CHHapticEventParameter(parameterID: .hapticIntensity, value: 1)], relativeTime: 0, duration: 0.7)
            try engine.makePlayer(with: CHHapticPattern(events: [event], parameters: [])).start(atTime: CHHapticTimeImmediate)
            engines.append(engine)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in engine.stop(); self?.engines.removeAll { $0 === engine } }
            say("Sent a 0.7 s vibration through GameController.")
        } catch {
            say("GameController vibration failed: \(error.localizedDescription)")
        }
    }

    // 8BitDo's own rumble: output report 5 (strong, weak, strong, weak, 0-100), then a stop 0.7 s later, since the
    // firmware keeps the motors on until the next report.
    @objc func direct() {
        let manager = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        IOHIDManagerSetDeviceMatching(manager, [kIOHIDVendorIDKey: 0x2DC8, kIOHIDProductIDKey: 0x6012] as CFDictionary)
        IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
        guard let d = devices.first(where: { (IOHIDDeviceGetProperty($0, kIOHIDMaxOutputReportSizeKey as CFString) as? Int ?? 0) >= 4 }) else {
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
            return say("No 2dc8:6012 interface that takes an output report was found.")
        }
        let send = { (v: UInt8) -> IOReturn in let r: [UInt8] = [v, v, v, v]; return IOHIDDeviceSetReport(d, kIOHIDReportTypeOutput, 5, r, r.count) }
        let st = send(60)
        say(st == kIOReturnSuccess ? "Sent 8BitDo's report 5 at 60, and a stop 0.7 s later." : "Report 5 couldn't be sent (IOReturn \(String(UInt32(bitPattern: st), radix: 16))).")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
            _ = send(0)
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        }
    }

    @objc func copyReport() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(report(), forType: .string)
        say("The report is on the clipboard.")
    }

    @objc func clear() { seen.removeAll(); rawRest = raw; lastNote = ""; status.stringValue = "" }

    func say(_ s: String) { lastNote = s; status.stringValue = s }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
