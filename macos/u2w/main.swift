// SPDX-License-Identifier: GPL-3.0-or-later
// Ultimate 2 Wireless Backup: one window, one button. It runs the bundled Python core (python3 -m u2w_backup), which
// only reads the controller, and shows its lines: status, progress, done or fail.
import AppKit
import IOKit.hid

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    let intro = NSTextField(wrappingLabelWithString: """
        This app makes a full backup of your controller's memory and a report to send to the developer. It only reads \
        the controller: nothing on it is changed.

        1. Turn the controller off and unplug its 2.4 GHz adapter.
        2. Connect the controller to this Mac with a USB cable.
        3. Click Make Backup. It takes a few minutes. Keep the cable connected until it finishes.
        """)
    let status = NSTextField(wrappingLabelWithString: "")
    let bar = NSProgressIndicator()
    let button = NSButton(title: "Make Backup", target: nil, action: nil)
    let reveal = NSButton(title: "Show Report in Finder", target: nil, action: nil)
    let log = NSTextView()
    var core: Process?
    var buffer = Data()
    var report: URL?
    var succeeded = false

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        // The controller's update channel is an input-monitoring device: ask once, up front.
        if IOHIDCheckAccess(kIOHIDRequestTypeListenEvent) != kIOHIDAccessTypeGranted {
            _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
        }
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 580, height: 520),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Ultimate 2 Wireless Backup"
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
        window.subtitle = "Prototype \(version) · reads only"
        window.contentMinSize = NSSize(width: 480, height: 420)
        window.delegate = self

        intro.font = .systemFont(ofSize: 13)
        status.font = .systemFont(ofSize: 13, weight: .medium)
        status.stringValue = "Connect the controller by cable, then click Make Backup."
        bar.isIndeterminate = false
        bar.minValue = 0
        bar.maxValue = 1
        button.bezelStyle = .rounded
        button.keyEquivalent = "\r"
        button.target = self
        button.action = #selector(start)
        reveal.bezelStyle = .rounded
        reveal.target = self
        reveal.action = #selector(showReport)
        reveal.isHidden = true
        log.isEditable = false
        log.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        log.textContainerInset = NSSize(width: 6, height: 6)
        let scroll = NSScrollView()
        scroll.documentView = log
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        log.autoresizingMask = [.width]
        log.isVerticallyResizable = true

        let buttons = NSStackView(views: [button, reveal])
        buttons.spacing = 10
        let stack = NSStackView(views: [intro, buttons, status, bar, scroll])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 14
        stack.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        for v in [intro, status, bar, scroll] { v.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40).isActive = true }
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 120).isActive = true
        window.contentView = stack

        let main = NSMenu(), item = NSMenuItem(), menu = NSMenu()
        menu.addItem(withTitle: "Quit Ultimate 2 Wireless Backup", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = menu
        main.addItem(item)
        let editItem = NSMenuItem(), edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)
        NSApp.mainMenu = main

        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func append(_ line: String) {
        log.textStorage?.append(NSAttributedString(string: line + "\n", attributes: [.foregroundColor: NSColor.textColor, .font: log.font!]))
        log.scrollToEndOfDocument(nil)
    }

    func handle(_ line: String) {
        let parts = line.split(separator: " ", maxSplits: 1).map(String.init)
        let word = parts.first ?? "", rest = parts.count > 1 ? parts[1] : ""
        switch word {
        case "status":
            status.stringValue = rest
            append(rest)
        case "progress":
            let n = rest.split(separator: " ").compactMap { Double($0) }
            if n.count == 2, n[1] > 0 { bar.doubleValue = n[0] / n[1] }
        case "note":
            append(rest)
        case "done":
            succeeded = true
            report = URL(fileURLWithPath: rest)
            bar.doubleValue = 1
            status.stringValue = "The backup is done. Send the report file to the developer, and keep the backup file to yourself: it holds your controller's own data, such as its Bluetooth pairings."
            append("Done. The files are in Documents › Ultimate 2 Wireless Backup.")
            reveal.isHidden = false
        case "fail":
            status.stringValue = rest
            append("Stopped: " + rest)
        default:
            append(line)
        }
    }

    @objc func start() {
        guard core == nil, let res = Bundle.main.resourceURL else { return }
        button.isEnabled = false
        reveal.isHidden = true
        succeeded = false
        bar.doubleValue = 0
        log.string = ""
        let p = Process()
        p.executableURL = res.appendingPathComponent("python/bin/python3")
        p.arguments = ["-m", "u2w_backup"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = res.appendingPathComponent("app").path
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p.environment = env
        let out = Pipe()
        p.standardOutput = out
        p.standardError = out
        out.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            guard let self = self, !data.isEmpty else { h.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                self.buffer.append(data)
                while let i = self.buffer.firstIndex(of: 0x0a) {
                    let line = String(decoding: self.buffer[..<i], as: UTF8.self)
                    self.buffer.removeSubrange(...i)
                    self.handle(line)
                }
            }
        }
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !self.buffer.isEmpty { self.handle(String(decoding: self.buffer, as: UTF8.self)); self.buffer.removeAll() }
                self.core = nil
                self.button.isEnabled = true
                self.button.title = self.succeeded ? "Make Another Backup" : "Try Again"
            }
        }
        do { try p.run(); core = p } catch {
            handle("fail The app's core couldn't start: \(error.localizedDescription)")
            button.isEnabled = true
        }
    }

    @objc func showReport() {
        if let r = report { NSWorkspace.shared.activateFileViewerSelecting([r]) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ note: Notification) { core?.terminate() }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
