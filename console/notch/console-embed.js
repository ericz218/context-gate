'use strict';

// Context Gate 控制台嵌入视图（自研壳专用，从 TO-DO Panel 借鉴期版本收缩而来）。
// 主进程用 WebContentsView 直接加载本机 console/app.py 的页面：
//   - 复用优先：读 ~/.local/state/context-gate/console-connection.json（base_url+pid），
//     pid 存活就直接加载，与其他壳共用同一个后端；
//   - 后端不在才自己拉起一个（默认 state-dir，写回 connection.json 成为公共后端），
//     退出时只回收自己拉起的实例；
//   - 自愈桥与 Swift 壳同协议：guest preload 注入 window.webkit.messageHandlers.reconnect，
//     页面原有的 showReconnect 逻辑探测到后自动上报，这里 15 秒限频重读连接换 URL。
// 几何：控制台 guest 永远铺满窗口内容区（本壳没有 tab 与其他内容），展开后直接取
// getContentBounds 贴合，不需要渲染层上报。

const { app, ipcMain, screen, session, WebContentsView } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const CONNECTION_FILE = path.join(os.homedir(), '.local/state/context-gate/console-connection.json');
// 后端脚本解析顺序：环境变量 > 打包内置副本（extraResources，随构建同步仓库版）> 仓库源码。
// 打包版必须用内置副本：~/Documents 受 TCC 保护，App 的 existsSync 会被静默拒绝，
// 导致 spawn 永远不发生且无任何报错（dev 模式继承终端的 Documents 权限所以没这个问题）。
const PACKAGED_BACKEND = path.join(process.resourcesPath || '', 'console-backend', 'console', 'app.py');
const DEV_BACKEND = path.resolve(__dirname, '..', 'app.py');
const CONSOLE_APP = process.env.CONTEXT_GATE_CONSOLE_APP
  || (app.isPackaged && fs.existsSync(PACKAGED_BACKEND) ? PACKAGED_BACKEND : DEV_BACKEND);
const CONSOLE_PYTHON = process.env.CONTEXT_GATE_CONSOLE_PYTHON
  || ['/usr/bin/python3', '/opt/homebrew/bin/python3', '/usr/local/bin/python3'].find((p) => fs.existsSync(p))
  || 'python3';
const RECONNECT_MIN_INTERVAL_MS = 15000;
const BACKEND_START_TIMEOUT_MS = 20000;
const VIEW_BACKGROUND = '#0B0D10';
// 展开时岛体从大条长到全尺寸（渲染层 300ms 动画），guest 等动画落定再上屏，
// 避免宿主页与 guest 抢首帧合成
const EXPAND_SETTLE_MS = 300;

let getWindow = null;
let view = null;
let viewWindowId = -1;
let expanded = false;
let guestHoldTimer = null;
let viewShown = false;
let lastBoundsSent = null;
let currentUrl = '';
let ownedBackend = null;
let backendStarting = false;
let lastReconnectAt = 0;

function readConnection() {
  try {
    const raw = JSON.parse(fs.readFileSync(CONNECTION_FILE, 'utf8'));
    const baseUrl = String(raw.base_url || '');
    const pid = Number(raw.pid);
    // URL 形态与 console/app.py 的写入保持一致：http://127.0.0.1:<port>/<token>/
    if (!/^http:\/\/127\.0\.0\.1:\d+\/[A-Za-z0-9_-]+\/$/.test(baseUrl)) return null;
    if (!Number.isInteger(pid) || pid <= 0) return null;
    try {
      process.kill(pid, 0);
    } catch (error) {
      return null;
    }
    return { baseUrl, pid };
  } catch (error) {
    return null;
  }
}

function startBackend() {
  // 之前拉起的后端可能已被外部杀掉：pid 死了就清掉持有标记，否则永远不再重新拉
  if (ownedBackend) {
    try {
      process.kill(ownedBackend.pid, 0);
    } catch (error) {
      ownedBackend = null;
    }
  }
  if (backendStarting || ownedBackend) return;
  if (!fs.existsSync(CONSOLE_APP)) {
    console.warn('[panel] backend script not found:', CONSOLE_APP);
    return;
  }
  backendStarting = true;
  console.log('[panel] spawning backend:', CONSOLE_PYTHON, CONSOLE_APP);
  try {
    const child = spawn(CONSOLE_PYTHON, [CONSOLE_APP, '--no-browser'], {
      detached: true,
      stdio: 'ignore',
    });
    child.on('error', () => {
      backendStarting = false;
    });
    // 后端退出（无论何种原因）都解除持有，下次 ensureConnection 才能重新拉起
    child.on('exit', () => {
      if (ownedBackend === child) ownedBackend = null;
    });
    child.unref();
    ownedBackend = child;
  } catch (error) {
    // 拉不起来就留给下一次 reconnect 重试
  } finally {
    setTimeout(() => {
      backendStarting = false;
    }, 4000);
  }
}

function waitForConnection(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const tick = () => {
      const conn = readConnection();
      if (conn) {
        resolve(conn);
        return;
      }
      if (Date.now() >= deadline) {
        resolve(null);
        return;
      }
      setTimeout(tick, 500);
    };
    tick();
  });
}

async function ensureConnection() {
  const existing = readConnection();
  if (existing) return existing;
  startBackend();
  return waitForConnection(BACKEND_START_TIMEOUT_MS);
}

function installGuestGuards(guest) {
  guest.setWindowOpenHandler(() => ({ action: 'deny' }));
  guest.on('will-navigate', (event, url) => {
    if (currentUrl && url.startsWith(currentUrl)) return;
    event.preventDefault();
  });
  guest.on('did-fail-load', (event, code, description, url, isMainFrame) => {
    if (!isMainFrame) return;
    setTimeout(() => queueReconnect(true), 2000);
  });
  guest.on('render-process-gone', () => {
    view = null;
    setTimeout(() => {
      void loadConsole().then(() => syncView());
    }, 1000);
  });
}

function ensureView() {
  const win = typeof getWindow === 'function' ? getWindow() : null;
  if (!win || win.isDestroyed()) return null;
  if (view && (view.webContents.isDestroyed() || viewWindowId !== win.id)) {
    view = null;
  }
  if (view) return view;

  const guestSession = session.fromPartition('persist:context-gate-console');
  guestSession.setPermissionRequestHandler((wc, permission, callback) => {
    callback(permission === 'notifications' || permission === 'clipboard-sanitized-write');
  });

  const created = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, 'console-shim.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: 'persist:context-gate-console',
    },
  });
  created.setBackgroundColor(VIEW_BACKGROUND);
  created.setVisible(false);
  // 岛体底部圆角与 guest 对齐（顶部贴屏幕上沿，四角统一 16px 观感无差）
  if (typeof created.setRoundedCorners === 'function') {
    created.setRoundedCorners({ radius: 16 });
  }
  installGuestGuards(created.webContents);
  win.contentView.addChildView(created);
  view = created;
  viewWindowId = win.id;
  return view;
}

async function loadConsole() {
  const v = ensureView();
  if (!v) return false;
  const conn = await ensureConnection();
  if (!conn) {
    // 兜底：后端彻底拉不起来时别留黑屏，把原因写进 guest 页
    try {
      await v.webContents.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
        '<body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#0B0D10;color:#7E8695;font:14px -apple-system">控制台后端无法启动，请查看 ~/Library/Application Support/Context Gate \u63a7\u5236\u53f0/panel-error.log</body>'
      ));
      currentUrl = '';
    } catch (error) {}
    return false;
  }
  if (conn.baseUrl === currentUrl && v.webContents.getURL() === conn.baseUrl) return true;
  currentUrl = conn.baseUrl;
  try {
    await v.webContents.loadURL(conn.baseUrl);
    return true;
  } catch (error) {
    return false;
  }
}

// 自愈入口：页面 403（后端重启换 token）或加载失败都会走到这里。
// 重读 connection.json 拿新 URL；后端没了就先拉起再等连接文件。
function queueReconnect(immediate = false) {
  const now = Date.now();
  if (!immediate && now - lastReconnectAt < RECONNECT_MIN_INTERVAL_MS) return;
  lastReconnectAt = now;
  void (async () => {
    const v = ensureView();
    if (!v) return;
    const conn = await ensureConnection();
    if (!conn) return;
    if (conn.baseUrl !== currentUrl) {
      currentUrl = conn.baseUrl;
      try {
        await v.webContents.loadURL(conn.baseUrl);
      } catch (error) {}
    } else {
      v.webContents.reload();
    }
  })();
}

function syncView() {
  const win = typeof getWindow === 'function' ? getWindow() : null;
  if (!win || win.isDestroyed()) return;
  if (!view || view.webContents.isDestroyed()) return;
  const shouldShow = expanded && !guestHoldTimer;
  if (shouldShow !== viewShown) {
    view.setVisible(shouldShow);
    viewShown = shouldShow;
  }
  if (!shouldShow) return;
  const { width, height } = win.getContentBounds();
  // 页面内容从菜单栏/物理刘海带下方开始，否则页头正好被刘海硬件挡住
  let top = 0;
  try {
    const d = screen.getDisplayMatching(win.getBounds());
    const menuBar = Math.max(0, d.workArea.y - d.bounds.y);
    if (menuBar > 0 && height > menuBar + 80) top = menuBar;
  } catch (error) {}
  const next = { x: 0, y: top, width, height: height - top };
  const prev = lastBoundsSent;
  if (prev && prev.x === next.x && prev.y === next.y && prev.width === next.width && prev.height === next.height) return;
  view.setBounds(next);
  lastBoundsSent = next;
}

function setExpanded(value) {
  expanded = value === true;
  if (guestHoldTimer) {
    clearTimeout(guestHoldTimer);
    guestHoldTimer = null;
  }
  if (expanded) {
    guestHoldTimer = setTimeout(() => {
      guestHoldTimer = null;
      syncView();
    }, EXPAND_SETTLE_MS);
  }
  syncView();
}

function shutdown() {
  if (ownedBackend && ownedBackend.pid) {
    try {
      process.kill(ownedBackend.pid, 'SIGTERM');
    } catch (error) {}
  }
  ownedBackend = null;
}

// main.js 用于区分宿主页与 guest 页的 IPC 来源（guest 也有自己的拖拽调size通道）
function isConsoleGuest(sender) {
  return Boolean(view && !view.webContents.isDestroyed() && sender === view.webContents);
}

// getMainWindow 用 getter 形式传入：主窗口可能在运行期被销毁重建
function setup(getMainWindow) {
  getWindow = getMainWindow;
  console.log('[panel] embed setup, backend =', CONSOLE_APP);
  ipcMain.on('console:reconnect', (event) => {
    if (!view || view.webContents.isDestroyed() || event.sender !== view.webContents) return;
    queueReconnect();
  });
  app.on('will-quit', shutdown);
  void loadConsole(); // 启动即预载，首次展开控制台时内容已就绪
}

module.exports = { setup, setExpanded, syncView, isConsoleGuest };
