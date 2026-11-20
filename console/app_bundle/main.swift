// Context Gate 控制台壳 App：窗口内嵌现有 console/app.py 页面。
// --agent 模式：由 LaunchAgent 在登录时拉起，不出窗口，只注册全局快捷键；
// 热键 / 重复启动 / 点击 Dock 图标都会唤起（或创建）窗口。
import Cocoa
import WebKit
import Carbon.HIToolbox
import UserNotifications

func resolveRepoPath() -> String {
    let fm = FileManager.default
    if let env = ProcessInfo.processInfo.environment["CONTEXT_GATE_ROOT"], !env.isEmpty,
       fm.fileExists(atPath: env + "/console/app.py") {
        return env
    }
    if let configured = Bundle.main.object(forInfoDictionaryKey: "ContextGateRepoPath") as? String,
       !configured.isEmpty, fm.fileExists(atPath: configured + "/console/app.py") {
        return configured
    }
    let bundleDir = URL(fileURLWithPath: Bundle.main.bundlePath)
    for candidate in [
        bundleDir.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path,
        NSHomeDirectory() + "/Projects/context-gate",
    ] {
        if fm.fileExists(atPath: candidate + "/console/app.py") { return candidate }
    }
    if let configured = Bundle.main.object(forInfoDictionaryKey: "ContextGateRepoPath") as? String, !configured.isEmpty {
        return configured
    }
    return NSHomeDirectory() + "/Projects/context-gate"
}

func resolvePythonPath() -> String {
    let fm = FileManager.default
    if let env = ProcessInfo.processInfo.environment["CONTEXT_GATE_PYTHON"], !env.isEmpty,
       fm.isExecutableFile(atPath: env) {
        return env
    }
    for candidate in ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"] {
        if fm.isExecutableFile(atPath: candidate) { return candidate }
    }
    return "/usr/bin/python3"
}

let repoPath = resolveRepoPath()
let stateDir = NSHomeDirectory() + "/.local/state/context-gate"
// 待办浮窗的开关、倍率和窗口位置存在 UserDefaults。
let todoOpenKey = "todoPanelOpen", todoZoomKey = "todoPanelZoom", todoFrameName = "ContextGateTodoPanel"
// 额度提醒只发固定文案；后端用 `--notify <平台>` 转交给常驻实例，由它以本 App 的名义发系统通知。
let notifyName = "local.context-gate.console.notify"
let ensureBackendName = "local.context-gate.console.ensure-backend"
let quotaNotices: [String: String] = [
    "codex": "Codex订阅额度已达到提醒门槛，请查看控制台。",
    "claude": "Claude订阅额度已达到提醒门槛，请查看控制台。",
    "test": "这是一条测试通知：控制台的系统通知已可用。",
]

let quotaNoticesEN: [String: String] = [
    "codex": "Codex quota reached the alert threshold. Check the console.",
    "claude": "Claude quota reached the alert threshold. Check the console.",
    "test": "Test notification: console notifications are available.",
]

// 与 Carbon 键值一致（cmdKey=1<<8、shiftKey=1<<9、optionKey=1<<11、controlKey=1<<12）。
let modCmd: UInt32 = 1 << 8, modShift: UInt32 = 1 << 9, modOption: UInt32 = 1 << 11, modControl: UInt32 = 1 << 12

let keyCodes: [String: UInt32] = [
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07,
    "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10,
    "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19,
    "7": 0x1A, "8": 0x1B, "0": 0x1D, "I": 0x22, "O": 0x1F, "P": 0x23, "L": 0x25, "J": 0x26,
    "K": 0x28, "N": 0x2D, "M": 0x2E, "U": 0x20,
]

struct ConsoleConnection {
    let url: URL
    let pid: Int32
}

final class ConsoleLocalSession: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate, NSWindowDelegate {
    var window: NSWindow?
    var webView: WKWebView?
    var todoPanel: NSPanel?
    var todoWebView: WKWebView?
    var statusItem: NSStatusItem?
    var backend: Process?
    private var connecting = false
    private var pendingForcedReload = false
    private var isQuitting = false
    private var lastBackendRecovery = Date.distantPast
    private var takeoverRetry: DispatchWorkItem?
    private let localSession = URLSession(configuration: .ephemeral, delegate: ConsoleLocalSession(), delegateQueue: nil)
    var hotkeyRef: EventHotKeyRef?
    var appliedHotkey = ""
    var uiLanguage = UserDefaults.standard.string(forKey: "ContextGateUILanguage") ?? "zh"
    var englishUI: Bool { uiLanguage == "en" }
    func ui(_ zh: String, _ en: String) -> String { englishUI ? en : zh }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if CommandLine.arguments.contains("--ensure-backend") {
            // Only ask the already-running App to start its backend. Keep its windows as they are.
            let fd = open(stateDir + "/console-app.lock", O_RDWR | O_CLOEXEC)
            guard fd >= 0, flock(fd, LOCK_EX | LOCK_NB) != 0, errno == EWOULDBLOCK else { exit(2) }
            DistributedNotificationCenter.default().postNotificationName(
                Notification.Name(ensureBackendName), object: nil, userInfo: nil, deliverImmediately: true)
            exit(0)
        }
        if let index = CommandLine.arguments.firstIndex(of: "--notify") {
            // 一次性转交：常驻实例在跑就把平台名发给它；不在跑或平台未知则非零退出，让后端走兜底。
            let platform = index + 1 < CommandLine.arguments.count ? CommandLine.arguments[index + 1] : ""
            let probe = open(stateDir + "/console-app.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
            let resident = probe >= 0 && flock(probe, LOCK_EX | LOCK_NB) != 0
            if resident, platform != "test", quotaNotices[platform] != nil {
                DistributedNotificationCenter.default().postNotificationName(
                    Notification.Name(notifyName), object: platform, userInfo: nil, deliverImmediately: true)
                exit(0)
            }
            exit(2)
        }
        // 用户重复打开才唤起窗口；LaunchAgent 的保活重试不得抢焦点。
        try? FileManager.default.createDirectory(atPath: stateDir, withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: 0o700])
        let fd = open(stateDir + "/console-app.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
        if fd >= 0, flock(fd, LOCK_EX | LOCK_NB) != 0 {
            if !CommandLine.arguments.contains("--agent") {
                DistributedNotificationCenter.default().post(name: Notification.Name("local.context-gate.console.show"), object: nil)
            }
            exit(0)
        }
        DistributedNotificationCenter.default().addObserver(forName: Notification.Name("local.context-gate.console.show"), object: nil, queue: .main) { [weak self] _ in
            self?.showConsole()
        }
        DistributedNotificationCenter.default().addObserver(forName: Notification.Name(ensureBackendName),
                                                           object: nil, queue: .main) { [weak self] _ in
            self?.reloadPage()
        }
        DistributedNotificationCenter.default().addObserver(forName: Notification.Name(notifyName), object: nil, queue: .main) { [weak self] note in
            if let platform = note.object as? String, platform != "test" { self?.postNotice(platform) }
        }
        if hasBundle { UNUserNotificationCenter.current().delegate = self }
        installHotkeyHandler()
        applyHotkey()
        let timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in self?.applyHotkey() }
        RunLoop.main.add(timer, forMode: .common)
        installStatusItem()
        // 待办浮窗：首次默认打开，之后沿用上次关闭/打开的状态。
        if UserDefaults.standard.object(forKey: todoOpenKey) as? Bool ?? true { showTodoPanel() }
        if CommandLine.arguments.contains("--agent") { return } // 后台驻留，等热键/再启动/点 Dock
        showConsole()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showConsole(); return true
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        reportNotifyState() // 从系统设置改完权限切回来，页面跟着更新
    }

    // UNUserNotificationCenter 只能在正式 bundle 里用；裸可执行文件（回归测试）一律跳过。
    var hasBundle: Bool { Bundle.main.bundleIdentifier != nil }

    func postNotice(_ platform: String) {
        let messages = englishUI ? quotaNoticesEN : quotaNotices
        guard hasBundle, let body = messages[platform] else { return }
        let center = UNUserNotificationCenter.current()
        center.getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
                // 还没授权：退回旧的 AppleScript 通知（系统记在「脚本编辑器」名下），提醒不丢。
                if platform != "test" { self.legacyNotice(body) }
                return
            }
            let content = UNMutableNotificationContent()
            content.title = self.ui("订阅额度提醒", "Quota alert")
            content.body = body
            content.sound = .default
            center.add(UNNotificationRequest(identifier: "quota-" + platform + "-" + UUID().uuidString, content: content, trigger: nil))
        }
    }

    func legacyNotice(_ body: String) {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = ["-e", "display notification \"" + body + "\" with title \"" + ui("订阅额度提醒", "Quota alert") + "\""]
        try? task.run()
    }

    func reportNotifyState() {
        guard hasBundle else { return }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let state: String
            switch settings.authorizationStatus {
            case .authorized, .provisional: state = "granted"
            case .denied: state = "denied"
            default: state = "default"
            }
            DispatchQueue.main.async {
                self.webView?.evaluateJavaScript("window.quotaNativeNotify&&window.quotaNativeNotify('" + state + "')", completionHandler: nil)
            }
        }
    }

    func handleNotify(action: String) {
        guard hasBundle else { return }
        let center = UNUserNotificationCenter.current()
        switch action {
        case "request":
            center.getNotificationSettings { settings in
                switch settings.authorizationStatus {
                case .notDetermined:
                    // 系统授权框由这里直接弹出。
                    center.requestAuthorization(options: [.alert, .sound]) { _, _ in self.reportNotifyState() }
                case .denied:
                    DispatchQueue.main.async { self.openNotificationSettings() }
                default:
                    self.reportNotifyState()
                }
            }
        case "settings":
            openNotificationSettings()
        case "test":
            postNotice("test")
        default:
            reportNotifyState()
        }
    }

    func openNotificationSettings() {
        // 已被拒绝后系统不再弹框：直接打开「系统设置 › 通知」里本 App 这一项。
        let id = Bundle.main.bundleIdentifier ?? ""
        if let url = URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension?id=" + id) {
            NSWorkspace.shared.open(url)
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound]) // 控制台在前台时也照常弹出
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        DispatchQueue.main.async { self.showConsole() }
        completionHandler()
    }

    func applicationWillTerminate(_ notification: Notification) {
        isQuitting = true
        takeoverRetry?.cancel()
        localSession.invalidateAndCancel()
        if let backend, backend.isRunning { backend.terminate() }
    }

    func installHotkeyHandler() {
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let callback: EventHandlerUPP = { _, _, userInfo in
            if let userInfo {
                let delegate = Unmanaged<AppDelegate>.fromOpaque(userInfo).takeUnretainedValue()
                DispatchQueue.main.async { delegate.toggleConsole() }
            }
            return noErr
        }
        InstallEventHandler(GetApplicationEventTarget(), callback, 1, &eventType, Unmanaged.passRetained(self).toOpaque(), nil)
    }

    func toggleConsole() {
        // 前台可见时再按 = 收起（NSApp.hide 会把焦点还给上一个 App）；否则唤起。
        // 不判 isKeyWindow：hide→unhide 循环后 key 态有竞态，可见+活跃就够。
        if !NSApp.isHidden, let w = window, w.isVisible, NSApp.isActive {
            // NSApp.hide 会连浮窗一起藏掉：浮窗开着时只收起主窗口。
            if todoPanel?.isVisible == true { w.orderOut(nil) } else { NSApp.hide(nil) }
        } else {
            showConsole()
        }
    }

    func applyHotkey() {
        // 未保存过配置时用默认 ⇧⌘E，保证开箱即用。
        var obj: [String: Any] = ["key": "E", "ctrl": false, "cmd": true, "shift": true]
        if let data = FileManager.default.contents(atPath: stateDir + "/hotkey.json"),
           let saved = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            obj = saved
        }
        guard let key = obj["key"] as? String, let code = keyCodes[key.uppercased()] else { return }
        var mods: UInt32 = 0
        if obj["cmd"] as? Bool == true { mods |= modCmd }
        if obj["shift"] as? Bool == true { mods |= modShift }
        if obj["alt"] as? Bool == true { mods |= modOption }
        if obj["ctrl"] as? Bool == true { mods |= modControl }
        if mods == 0 { mods = modControl | modCmd }
        let sig = "\(mods)/\(code)"
        guard sig != appliedHotkey else { return }
        if let hotkeyRef { UnregisterEventHotKey(hotkeyRef); self.hotkeyRef = nil }
        var ref: EventHotKeyRef?
        var hotKeyID = EventHotKeyID(signature: OSType(0x43_47_48_4B) /* CGHK */, id: 1)
        guard RegisterEventHotKey(code, mods, hotKeyID, GetApplicationEventTarget(), 0, &ref) == noErr else { return }
        hotkeyRef = ref
        appliedHotkey = sig
    }

    func showConsole() {
        // 仅用户唤起时转为普通 App 并激活；后台启动保持 accessory。
        NSApp.setActivationPolicy(.regular)
        if window == nil { buildWindow() }
        if NSApp.isHidden { NSApp.unhide(nil) } // toggle 收起后再次唤起
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
        window?.makeFirstResponder(webView)
        reloadPage()
    }

    func applyWindowTheme(dark: Bool) {
        for w in [window, todoPanel].compactMap({ $0 }) { styleWindow(w, dark: dark) }
    }

    func styleWindow(_ w: NSWindow, dark: Bool) {
        w.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        w.backgroundColor = NSColor(srgbRed: dark ? 14/255 : 250/255,
                                    green: dark ? 17/255 : 249/255,
                                    blue: dark ? 22/255 : 247/255, alpha: 1)
    }

    func buildWindow() {
        // 页面通过 webkit.messageHandlers 上报主题（theme）；后端重启令牌轮换、
        // 页面 403 时发 reconnect，壳 App 重读 connection.json 换新连接自愈。
        let config = WKWebViewConfiguration()
        let bridge = PageBridge(delegate: self)
        config.userContentController.add(bridge, name: "theme")
        config.userContentController.add(bridge, name: "language")
        config.userContentController.add(bridge, name: "reconnect")
        config.userContentController.add(bridge, name: "notify")
        config.userContentController.add(bridge, name: "todoPanel")
        webView = WKWebView(frame: .zero, configuration: config)
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 820),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable],
                         backing: .buffered, defer: false)
        w.title = ui("Context Gate 控制台", "Context Gate Console")
        w.titlebarAppearsTransparent = true
        w.contentView = webView
        w.center()
        w.setFrameAutosaveName("ContextGateConsoleMain")
        window = w
        installPageLanguage(webView)
        applyWindowTheme(dark: true) // 默认深色，页面加载后会再同步一次
        installMenus()
    }

    @objc func reloadConsole(_ sender: Any?) { reloadPage(force: true) }

    func liveConnection() -> ConsoleConnection? {
        guard let data = FileManager.default.contents(atPath: stateDir + "/console-connection.json"),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let urlString = obj["base_url"] as? String,
              urlString.range(of: #"^http://127\.0\.0\.1:[0-9]+/[a-zA-Z0-9_-]+/$"#, options: .regularExpression) != nil,
              let url = URL(string: urlString), let port = url.port, (1...65535).contains(port),
              let number = obj["pid"] as? Int, let pid = Int32(exactly: number), pid > 1,
              kill(pid, 0) == 0 else { return nil }
        return ConsoleConnection(url: url, pid: pid)
    }

    // 浮窗加载同一页面，?mini=todo 让页面只显示待办。
    func todoURL(_ base: URL) -> URL {
        guard var parts = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return base }
        parts.queryItems = [URLQueryItem(name: "mini", value: "todo")]
        return parts.url ?? base
    }

    func reloadPage(force: Bool = false) {
        guard !isQuitting else { return }
        if connecting {
            pendingForcedReload = pendingForcedReload || force
            return
        }
        takeoverRetry?.cancel()
        connecting = true
        guard let connection = liveConnection() else {
            startBackend()
            return
        }
        request(connection, "v1/console/health") { [weak self] status, health in
            guard let self, !self.isQuitting else { return }
            guard status == 200, health?["service"] as? String == "context-gate-console",
                  health?["pid"] as? Int32 == connection.pid else {
                if self.liveConnection()?.pid != connection.pid {
                    self.connecting = false
                    self.reloadPage(force: force)
                } else if status == 404 {
                    self.connecting = false
                    self.showFailure(reason: self.ui("现有后台版本较旧，请退出旧控制台服务后重新加载。",
                                                     "The existing backend is outdated. Quit it, then reload."))
                } else {
                    // A stale registration can point at a live but unrelated process.
                    // The backend lock prevents a second server if the real backend is still running.
                    self.startBackend(after: connection)
                }
                return
            }
            if let owner = health?["app_owner"] as? Int32, owner != ProcessInfo.processInfo.processIdentifier {
                // The previous App's backend will exit as soon as it detects its owner is gone.
                self.waitForRelease(connection.pid, until: Date().addingTimeInterval(10))
            } else if health?["memory_documents"] as? String == "denied",
               self.backend?.processIdentifier != connection.pid {
                self.replaceDeniedBackend(connection, force: force)
            } else {
                self.loadConnection(connection.url, force: force)
            }
        }
    }

    private func request(_ connection: ConsoleConnection, _ route: String, release: Bool = false,
                         completion: @escaping (Int?, [String: Any]?) -> Void) {
        let url = connection.url.appendingPathComponent(route)
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: release ? 10 : 2)
        if release {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = Data("{\"pid\":\(connection.pid)}".utf8)
        }
        localSession.dataTask(with: request) { data, response, _ in
            let object = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            DispatchQueue.main.async { completion((response as? HTTPURLResponse)?.statusCode, object) }
        }.resume()
    }

    private func replaceDeniedBackend(_ connection: ConsoleConnection, force: Bool) {
        request(connection, "v1/console/release", release: true) { [weak self] status, _ in
            guard let self, !self.isQuitting else { return }
            if status == 202 || self.liveConnection()?.pid != connection.pid {
                self.waitForRelease(connection.pid, until: Date().addingTimeInterval(10))
            } else {
                // Busy backends keep serving their other views while work finishes.
                self.loadConnection(connection.url, force: force)
                let retry = DispatchWorkItem { [weak self] in self?.reloadPage() }
                self.takeoverRetry = retry
                DispatchQueue.main.asyncAfter(deadline: .now() + 15, execute: retry)
            }
        }
    }

    private func waitForRelease(_ pid: Int32, until deadline: Date) {
        guard !isQuitting else { return }
        if liveConnection()?.pid != pid {
            connecting = false
            reloadPage()
        } else if Date() < deadline {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
                self?.waitForRelease(pid, until: deadline)
            }
        } else {
            connecting = false
            showFailure(reason: ui("旧后台仍在退出，请重新加载控制台。", "The previous backend is still stopping. Reload the console."))
        }
    }

    private func loadConnection(_ url: URL, force: Bool = false) {
        connecting = false
        let reload = force || pendingForcedReload
        pendingForcedReload = false
        if let webView, reload || webView.url != url { webView.load(URLRequest(url: url)) }
        if let todoWebView, reload || todoWebView.url != todoURL(url) {
            todoWebView.load(URLRequest(url: todoURL(url)))
        }
    }

    private func startBackend(after previous: ConsoleConnection? = nil,
                              until deadline: Date = Date().addingTimeInterval(15)) {
        guard !isQuitting else { return }
        if let backend, backend.isRunning {
            connecting = false
            showFailure(reason: ui("本地后台没有响应，请重新加载控制台。", "The local backend is not responding. Reload the console."))
            return
        }
        let backend = Process()
        backend.executableURL = URL(fileURLWithPath: resolvePythonPath())
        backend.arguments = [repoPath + "/console/app.py", "--no-browser", "--state-dir", stateDir,
                             "--app-owner", String(ProcessInfo.processInfo.processIdentifier)]
        backend.environment = ["PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", "HOME": NSHomeDirectory()]
        backend.standardOutput = FileHandle.nullDevice
        backend.standardError = FileHandle.nullDevice
        backend.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self, !self.isQuitting, !self.connecting, self.backend === process else { return }
                if Date().timeIntervalSince(self.lastBackendRecovery) > 15 {
                    self.lastBackendRecovery = Date()
                    self.reloadPage()
                } else {
                    self.showFailure(reason: self.ui("本地数据服务已退出。请重新加载控制台。",
                                                     "The local data service stopped. Reload the console."))
                }
            }
        }
        do { try backend.run() } catch {
            connecting = false
            showFailure(reason: ui("无法启动后端：", "Could not start the backend: ") + error.localizedDescription)
            return
        }
        self.backend = backend
        waitForBackend(backend, after: previous, until: deadline)
    }

    private func waitForBackend(_ process: Process, after previous: ConsoleConnection?, until deadline: Date) {
        guard !isQuitting, backend === process else { return }
        let running = process.isRunning
        if let connection = liveConnection() {
            if running, connection.pid == process.processIdentifier {
                loadConnection(connection.url)
                return
            }
            if !running, process.terminationStatus == 2,
               connection.pid != previous?.pid || connection.url != previous?.url {
                // Another launcher claimed the lock while this App was starting.
                connecting = false
                reloadPage()
                return
            }
        }
        if !running, process.terminationStatus == 2, liveConnection() == nil, Date() < deadline {
            // A departing server removed its registration before releasing the lock.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
                self?.startBackend(until: deadline)
            }
            return
        }
        if Date() < deadline && (running || process.terminationStatus == 2) {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
                self?.waitForBackend(process, after: previous, until: deadline)
            }
        } else {
            if running { process.terminate() }
            connecting = false
            showFailure(reason: ui("未能启动本地数据服务。请重新加载控制台。",
                                   "The local data service could not start. Reload the console."))
        }
    }

    func showFailure(reason: String) {
        guard let webView else { return }
        let html = """
        <!doctype html><html lang="\(englishUI ? "en" : "zh-CN")"><meta charset="utf-8">
        <body style="font-family:-apple-system,'PingFang SC',sans-serif;background:#0E1116;
        display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
        <div style="text-align:center;color:#8A93A3">
        <div style="font-size:17px;color:#E6E9EE;margin-bottom:8px">\(ui("控制台后端不可用", "Console backend unavailable"))</div>
        <div>\(reason)</div>
        <div style="margin-top:8px">\(ui("请确认项目目录存在：", "Check that the project folder exists: "))\(repoPath)</div>
        </div></body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // ---- 待办浮窗：置顶、可拖动/缩放/关闭；菜单栏图标和控制台「浮窗」按钮可再次打开 ----

    func buildTodoPanel() {
        let config = WKWebViewConfiguration()
        let bridge = PageBridge(delegate: self)
        config.userContentController.add(bridge, name: "theme")
        config.userContentController.add(bridge, name: "language")
        config.userContentController.add(bridge, name: "reconnect")
        let web = WKWebView(frame: .zero, configuration: config)
        let zoom = UserDefaults.standard.double(forKey: todoZoomKey)
        web.pageZoom = zoom > 0 ? CGFloat(zoom) : 1
        let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 320, height: 440),
                            styleMask: [.titled, .closable, .resizable, .utilityWindow],
                            backing: .buffered, defer: false)
        panel.title = ui("待办", "To-do")
        installPageLanguage(web)
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.minSize = NSSize(width: 240, height: 180)
        panel.contentView = web
        panel.delegate = self
        if !panel.setFrameUsingName(todoFrameName) {
            // 第一次：放在主屏幕右上角（菜单栏下方），之后沿用用户拖动/缩放后的位置和大小。
            let area = (NSScreen.main ?? NSScreen.screens[0]).visibleFrame
            let size = panel.frame.size
            panel.setFrameOrigin(NSPoint(x: area.maxX - size.width - 16, y: area.maxY - size.height - 16))
        }
        panel.setFrameAutosaveName(todoFrameName)
        todoPanel = panel
        todoWebView = web
        styleWindow(panel, dark: true) // 页面加载后会按主题再同步一次
        if NSApp.mainMenu == nil { installMenus() } // 浮窗里粘贴/复制/缩放要靠主菜单的快捷键
    }

    func showTodoPanel() {
        if todoPanel == nil { buildTodoPanel() }
        todoPanel?.orderFrontRegardless() // 不抢当前 App 的焦点；点一下浮窗才会激活
        UserDefaults.standard.set(true, forKey: todoOpenKey)
        reloadPage()
    }

    func hideTodoPanel() {
        todoPanel?.orderOut(nil)
        UserDefaults.standard.set(false, forKey: todoOpenKey)
    }

    func toggleTodoPanel() {
        if todoPanel?.isVisible == true { hideTodoPanel() } else { showTodoPanel() }
    }

    // 点标题栏红色关闭钮同样记为「已关闭」，下次启动不再自动弹出。
    func windowWillClose(_ notification: Notification) {
        if (notification.object as? NSPanel) === todoPanel { UserDefaults.standard.set(false, forKey: todoOpenKey) }
    }

    func installStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "checklist", accessibilityDescription: ui("待办", "To-do"))
            button.toolTip = ui("待办浮窗：点一下显示/隐藏，右键更多", "To-do panel: click to show or hide; right-click for more")
            button.target = self
            button.action = #selector(statusClicked(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
        statusItem = item
    }

    @objc func statusClicked(_ sender: NSStatusBarButton) {
        guard NSApp.currentEvent?.type == .rightMouseUp else { toggleTodoPanel(); return }
        let menu = NSMenu()
        let toggle = menu.addItem(withTitle: todoPanel?.isVisible == true ? ui("隐藏待办浮窗", "Hide To-do Panel") : ui("显示待办浮窗", "Show To-do Panel"),
                                  action: #selector(toggleTodoFromMenu(_:)), keyEquivalent: "")
        toggle.target = self
        menu.addItem(withTitle: ui("打开控制台", "Open Console"), action: #selector(openConsoleFromMenu(_:)), keyEquivalent: "").target = self
        statusItem?.menu = menu
        sender.performClick(nil)
        statusItem?.menu = nil // 恢复为「左键直接切换」
    }

    @objc func toggleTodoFromMenu(_ sender: Any?) { toggleTodoPanel() }
    @objc func openConsoleFromMenu(_ sender: Any?) { showConsole() }

    // 放大/缩小作用于当前获得键盘焦点的窗口（浮窗的倍率会记住）。
    func zoom(_ change: (CGFloat) -> CGFloat) {
        let onPanel = NSApp.keyWindow === todoPanel
        guard let target = onPanel ? todoWebView : webView else { return }
        target.pageZoom = min(3, max(0.5, change(target.pageZoom)))
        if onPanel { UserDefaults.standard.set(Double(target.pageZoom), forKey: todoZoomKey) }
    }
    @objc func zoomIn(_ sender: Any?) { zoom { $0 + 0.1 } }
    @objc func zoomOut(_ sender: Any?) { zoom { $0 - 0.1 } }
    @objc func zoomReset(_ sender: Any?) { zoom { _ in 1 } }

    func installPageLanguage(_ web: WKWebView?) {
        guard let controller = web?.configuration.userContentController else { return }
        let prefix = "window.__contextGateLanguage="
        let retained = controller.userScripts.filter { !$0.source.hasPrefix(prefix) }
        controller.removeAllUserScripts()
        retained.forEach { controller.addUserScript($0) }
        let language = englishUI ? "en" : "zh"
        controller.addUserScript(WKUserScript(source: prefix + "'" + language + "';",
                                             injectionTime: .atDocumentStart, forMainFrameOnly: true))
    }

    func applyUILanguage(_ language: String) {
        guard language == "en" || language == "zh" else { return }
        let changed = language != uiLanguage
        uiLanguage = language
        UserDefaults.standard.set(language, forKey: "ContextGateUILanguage")
        window?.title = ui("Context Gate 控制台", "Context Gate Console")
        todoPanel?.title = ui("待办", "To-do")
        statusItem?.button?.setAccessibilityLabel(ui("待办", "To-do"))
        statusItem?.button?.toolTip = ui("待办浮窗：点一下显示/隐藏，右键更多", "To-do panel: click to show or hide; right-click for more")
        if changed {
            installPageLanguage(webView)
            installPageLanguage(todoWebView)
            installMenus()
        }
    }

    func installMenus() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appItem.submenu = appMenu
        appMenu.addItem(withTitle: ui("关于 Context Gate 控制台", "About Context Gate Console"),
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: ui("退出", "Quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); main.addItem(editItem)
        let editMenu = NSMenu(title: ui("编辑", "Edit"))
        editItem.submenu = editMenu
        editMenu.addItem(withTitle: ui("剪切", "Cut"), action: Selector(("cut:")), keyEquivalent: "x")
        editMenu.addItem(withTitle: ui("拷贝", "Copy"), action: Selector(("copy:")), keyEquivalent: "c")
        editMenu.addItem(withTitle: ui("粘贴", "Paste"), action: Selector(("paste:")), keyEquivalent: "v")
        editMenu.addItem(withTitle: ui("全选", "Select All"), action: Selector(("selectAll:")), keyEquivalent: "a")
        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let viewMenu = NSMenu(title: ui("视图", "View"))
        viewItem.submenu = viewMenu
        let reloadItem = viewMenu.addItem(withTitle: ui("重新加载", "Reload"), action: #selector(reloadConsole(_:)), keyEquivalent: "r")
        reloadItem.target = self
        viewMenu.addItem(.separator())
        for (title, key, action) in [(ui("放大", "Zoom In"), "=", #selector(zoomIn(_:))), (ui("缩小", "Zoom Out"), "-", #selector(zoomOut(_:))), (ui("实际大小", "Actual Size"), "0", #selector(zoomReset(_:)))] {
            viewMenu.addItem(withTitle: title, action: action, keyEquivalent: key).target = self
        }
        NSApplication.shared.mainMenu = main
    }
}

// 弱引用桥：userContentController 强持有 bridge，bridge 弱持有 delegate，避免环。
final class PageBridge: NSObject, WKScriptMessageHandler {
    weak var delegate: AppDelegate?
    private var lastReconnect = Date.distantPast
    init(delegate: AppDelegate) { self.delegate = delegate }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let delegate = delegate else { return }
        switch message.name {
        case "language":
            if let language = message.body as? String { delegate.applyUILanguage(language) }
        case "theme":
            if let theme = message.body as? String { delegate.applyWindowTheme(dark: theme != "warm") }
        case "reconnect":
            // 旧页签的令牌已随后端重启失效：按 connection.json 重新加载（服务活着就换
            // 新地址，死了就地补拉一个）；连接未变时保留页面，不循环重载。
            // 限频：后端起不来时页面每 10s 重试一次，别跟着把后端反复重启。
            if Date().timeIntervalSince(lastReconnect) > 15 {
                lastReconnect = Date()
                delegate.reloadPage()
            }
        case "notify":
            delegate.handleNotify(action: message.body as? String ?? "status")
        case "todoPanel":
            delegate.toggleTodoPanel()
        default:
            break
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
let background = CommandLine.arguments.contains("--agent") || CommandLine.arguments.contains("--ensure-backend")
app.setActivationPolicy(background ? .accessory : .regular)
app.run()
