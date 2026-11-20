#!/bin/zsh
# 编译并安装到 /Applications/Context Gate 控制台.app，并装登录后台代理（全局快捷键常驻）。
set -e
cd "${0:A:h}"
if [[ ! -s Resources/AppIcon.icns ]]; then
	echo "缺少应用图标 Resources/AppIcon.icns，停止更新。" >&2
	exit 1
fi
REPO_ROOT="${0:A:h:h:h}"
ARCH="$(uname -m)"
APP="build/Context Gate 控制台.app"
rm -rf build
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -swift-version 5 -O -target "${ARCH}-apple-macos13.0" -o "$APP/Contents/MacOS/ContextGateConsole" main.swift
cp Info.plist "$APP/Contents/"
/usr/libexec/PlistBuddy -c "Delete :ContextGateRepoPath" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :ContextGateRepoPath string $REPO_ROOT" "$APP/Contents/Info.plist"
cp Resources/AppIcon.icns "$APP/Contents/Resources/"
# 手工拼的 bundle 必须整体重签名，否则系统判「已损坏」。
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
# 先停保活，避免替换 bundle 期间旧进程被立即重启。
launchctl bootout gui/$UID/local.context-gate.console-app 2>/dev/null || true
pkill -x ContextGateConsole 2>/dev/null && sleep 1 || true
rm -rf "/Applications/Context Gate 控制台.app"
cp -R "$APP" /Applications/
# 登录后台代理：KeepAlive 拉起 --agent 实例注册全局快捷键；关窗/⌘Q 后热键仍可用。
PLIST="$HOME/Library/LaunchAgents/local.context-gate.console-app.plist"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
	<key>Label</key><string>local.context-gate.console-app</string>
	<key>ProgramArguments</key><array>
		<string>/Applications/Context Gate 控制台.app/Contents/MacOS/ContextGateConsole</string>
		<string>--agent</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>StandardErrorPath</key><string>$HOME/.local/state/context-gate/console-app.err.log</string>
</dict></plist>
PLISTEOF
launchctl bootout gui/$UID/local.context-gate.console-app 2>/dev/null || true
launchctl bootstrap gui/$UID "$PLIST"
echo "已安装：/Applications/Context Gate 控制台.app + 登录代理（Shift+Cmd+E 唤起）"
