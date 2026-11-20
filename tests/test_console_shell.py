"""Native shell regression: duplicate agents stay quiet and reuse loaded pages."""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("swiftc"), "macOS Swift/WebKit required")
class ConsoleShellTests(unittest.TestCase):
    def test_background_launch_and_reload(self):
        class Page(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.endswith('/v1/console/health'):
                    body = json.dumps({'service': 'context-gate-console', 'pid': self.server.backend_pid,
                                       'memory_documents': 'readable'}).encode()
                else:
                    body = b"<html><body>shell regression</body></html>"
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                backend = subprocess.Popen(['/bin/sleep', '45'])
                self.addCleanup(backend.wait)
                self.addCleanup(backend.terminate)
                server.backend_pid = backend.pid
                source = (Path(__file__).resolve().parents[1] / "console/app_bundle/main.swift").read_text()
                source = source.split("let app = NSApplication.shared\n")[0]
                source = source.replace('let stateDir = NSHomeDirectory() + "/.local/state/context-gate"',
                                        'let stateDir = ProcessInfo.processInfo.environment["SHELL_TEST_DIR"]!')
                native = Path(tmp) / "main.swift"
                native.write_text((source + NATIVE_TEST).replace(
                    "local.context-gate.console.show", "local.context-gate.test." + Path(tmp).name).replace(
                    "local.context-gate.console.ensure-backend", "local.context-gate.test.ensure." + Path(tmp).name))
                executable = Path(tmp) / "shell-test"
                subprocess.run(["swiftc", "-swift-version", "5", str(native), "-o", str(executable)],
                               check=True, capture_output=True, text=True, timeout=90)
                env = dict(os.environ, SHELL_TEST_DIR=tmp,
                           SHELL_TEST_URL="http://127.0.0.1:" + str(server.server_port) + "/first/",
                           SHELL_TEST_PID=str(backend.pid))
                result = subprocess.run([str(executable), "--test"], env=env, capture_output=True,
                                        text=True, timeout=45)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("native shell checks passed", result.stdout)
        finally:
            server.shutdown()
            server.server_close()


NATIVE_TEST = r''' 
let app = NSApplication.shared
app.setActivationPolicy(.accessory) // Test windows must stay behind the user's work.
func spin(_ seconds: Double) {
    let end = Date().addingTimeInterval(seconds)
    while Date() < end { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
}
func check(_ value: Bool, _ label: String) {
    if !value { fputs("FAILED: " + label + "\n", stderr); exit(1) }
}
func js(_ web: WKWebView, _ code: String) -> Any? {
    var done = false
    var result: Any?
    web.evaluateJavaScript(code) { value, error in
        result = value
        done = true
    }
    let end = Date().addingTimeInterval(10)
    while !done && Date() < end { spin(0.02) }
    check(done, "JavaScript callback")
    return result
}
if CommandLine.arguments.contains("--test") {
    let fd = open(stateDir + "/console-app.lock", O_CREAT | O_RDWR, 0o600)
    check(fd >= 0 && flock(fd, LOCK_EX | LOCK_NB) == 0, "test owns instance lock")
    var notifications = 0
    let observer = DistributedNotificationCenter.default().addObserver(
        forName: Notification.Name("local.context-gate.console.show"), object: nil, queue: .main
    ) { _ in notifications += 1 }
    for argument in ["--agent", "--manual"] {
        let child = Process()
        child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
        child.arguments = [argument]
        try! child.run()
        child.waitUntilExit()
        spin(0.5)
        check(child.terminationStatus == 0, "duplicate exits cleanly")
        check(notifications == (argument == "--agent" ? 0 : 1), "only user launch posts show")
    }
    DistributedNotificationCenter.default().removeObserver(observer)
    var startupRequests = 0
    let startupObserver = DistributedNotificationCenter.default().addObserver(
        forName: Notification.Name(ensureBackendName), object: nil, queue: .main
    ) { _ in startupRequests += 1 }
    let wake = Process()
    wake.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
    wake.arguments = ["--ensure-backend"]
    try! wake.run()
    wake.waitUntilExit()
    spin(0.5)
    check(wake.terminationStatus == 0 && startupRequests == 1, "background reload requests a backend")
    check(notifications == 1, "background reload does not ask to show the app")
    DistributedNotificationCenter.default().removeObserver(startupObserver)
    let delegate = AppDelegate()
    delegate.buildWindow() // Hidden window, no focus changes.
    let web = delegate.webView!
    let pid = Int32(ProcessInfo.processInfo.environment["SHELL_TEST_PID"]!)!
    let first = ProcessInfo.processInfo.environment["SHELL_TEST_URL"]!
    func connection(_ url: String) {
        let data = try! JSONSerialization.data(withJSONObject: ["base_url": url, "pid": pid])
        try! data.write(to: URL(fileURLWithPath: stateDir + "/console-connection.json"))
    }
    func awaitPage() {
        let end = Date().addingTimeInterval(10)
        while js(web, "document.body && document.body.textContent") as? String != "shell regression" && Date() < end { spin(0.02) }
        check(js(web, "document.body.textContent") as? String == "shell regression", "page loaded")
    }
    connection(first)
    delegate.reloadPage()
    awaitPage()
    _ = js(web, "window.__probe = 'keep'")
    for _ in 0..<4 { delegate.reloadPage() }
    spin(0.5)
    check(js(web, "window.__probe") as? String == "keep", "same connection preserves page")
    check(delegate.backend == nil, "healthy external backend is reused")
    delegate.reloadConsole(nil)
    spin(0.5)
    awaitPage()
    check(js(web, "typeof window.__probe") as? String == "undefined", "manual reload still works")
    _ = js(web, "window.__probe = 'keep'")
    let second = first.replacingOccurrences(of: "/first/", with: "/second/")
    connection(second)
    delegate.reloadPage()
    spin(0.5)
    awaitPage()
    check(web.url?.absoluteString == second, "new connection loads")
    check(js(web, "typeof window.__probe") as? String == "undefined", "new connection replaces page")
    delegate.applicationWillTerminate(Notification(name: NSApplication.willTerminateNotification))
    check(kill(pid, 0) == 0, "quitting the App leaves a healthy external backend alone")
    print("native shell checks passed")
} else {
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
'''
