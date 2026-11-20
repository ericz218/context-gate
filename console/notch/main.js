'use strict';

// Context Gate 控制台刘海面板壳（自研，借鉴 TO-DO Panel 的贴顶几何方案）。
// 收起 = 菜单栏高的 200px 小条；⌘⇧E / 点小条展开 = 整个控制台（console/app.py）。
// 展开尺寸默认较小（1080×660），展开后可拖边调整并记忆到 panel-settings.json。
// 动画：原生窗口只做瞬时画布切换，用户可见的岛体形变交给渲染层 CSS
// （展开=画布先变大、岛体长到位、guest 落定后上屏；收起=guest 先藏、岛体缩回、画布再变小）。

const {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  screen,
  Tray,
} = require('electron');
const fs = require('fs');
const path = require('path');
const consoleEmbed = require('./console-embed');

const COLLAPSED_WIDTH = 200;
const DEFAULT_EXPANDED = { width: 1080, height: 660 };
const MIN_EXPANDED = { width: 900, height: 520 };
const SCREEN_MARGIN = 24;
const COLLAPSED_FALLBACK_HEIGHT = 38;
const HOTKEY = 'CommandOrControl+Shift+E';
// 与渲染层岛体动画时长对齐：收起时等岛体缩回再把画布缩小
const COLLAPSE_ANIMATE_MS = 320;
const SETTINGS_FILE = 'panel-settings.json';

let mainWindow = null;
let tray = null;
let mode = 'collapsed';
let savedSize = { ...DEFAULT_EXPANDED };
let collapseTimer = null;
let resizeSyncTimer = null;
let resizeSaveTimer = null;

app.setName('Context Gate 控制台');

// 主进程任何未捕获异常只落盘不弹框：弹框在定时器里会变成点不掉的死循环
process.on('uncaughtException', (error) => {
  try {
    fs.appendFileSync(
      path.join(app.getPath('userData'), 'panel-error.log'),
      `${new Date().toISOString()} ${error && error.stack || error}\n`
    );
  } catch (ignoredError) {}
});

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    expand();
  });
}

function getWindowDisplay() {
  try {
    if (mainWindow) return screen.getDisplayMatching(mainWindow.getBounds());
  } catch (error) {}
  return getCursorDisplay();
}

function getCursorDisplay() {
  try {
    return screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  } catch (error) {
    return screen.getPrimaryDisplay();
  }
}

// 折叠条高度恰好等于菜单栏带（≈物理刘海高）；异常取 0 时回退兜底
function getCollapsedHeight(display) {
  const menuBarHeight = Math.max(0, display.workArea.y - display.bounds.y);
  return menuBarHeight > 0 ? menuBarHeight : COLLAPSED_FALLBACK_HEIGHT;
}

function topCenterBounds(width, height, display) {
  const area = display.bounds;
  return {
    x: Math.round(area.x + (area.width - width) / 2),
    y: area.y,
    width,
    height,
  };
}

function readSizeSetting() {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), SETTINGS_FILE), 'utf8'));
    const width = Number(raw.width);
    const height = Number(raw.height);
    if (Number.isFinite(width)) savedSize.width = Math.max(MIN_EXPANDED.width, Math.round(width));
    if (Number.isFinite(height)) savedSize.height = Math.max(MIN_EXPANDED.height, Math.round(height));
  } catch (error) {}
}

function writeSizeSetting() {
  try {
    const target = path.join(app.getPath('userData'), SETTINGS_FILE);
    const temporary = `${target}.${process.pid}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify({ width: savedSize.width, height: savedSize.height }), { mode: 0o600 });
    fs.renameSync(temporary, target);
  } catch (error) {}
}

function expandedBounds(display) {
  const d = display || getWindowDisplay();
  const width = Math.min(Math.max(savedSize.width, MIN_EXPANDED.width), d.workArea.width - SCREEN_MARGIN);
  const height = Math.min(
    Math.max(savedSize.height, MIN_EXPANDED.height),
    Math.max(getCollapsedHeight(d), d.bounds.height - SCREEN_MARGIN)
  );
  return topCenterBounds(width, height, d);
}

function collapsedBounds(display) {
  const d = display || getWindowDisplay();
  return topCenterBounds(COLLAPSED_WIDTH, getCollapsedHeight(d), d);
}

// 通知渲染层岛体目标几何：展开=菜单栏带下方的全尺寸（页头不能顶进刘海/菜单栏），
// 收起=贴顶小条。岛体尺寸过渡动画在渲染层。
function setMode(next) {
  mode = next === 'expanded' ? 'expanded' : 'collapsed';
  if (!mainWindow || mainWindow.isDestroyed()) return;
  consoleEmbed.setExpanded(mode === 'expanded');
  const d = getWindowDisplay();
  const menuBar = getCollapsedHeight(d); // =菜单栏带高（≈物理刘海高）
  const target = mode === 'expanded'
    ? (() => { const b = expandedBounds(d); return { mode, width: b.width, height: Math.max(80, b.height - menuBar), top: menuBar }; })()
    : { mode, width: COLLAPSED_WIDTH, height: menuBar, top: 0 };
  mainWindow.webContents.send('panel:mode', target);
}

function expand() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
    return;
  }
  if (collapseTimer) {
    clearTimeout(collapseTimer);
    collapseTimer = null;
  }
  // 画布瞬时放大（透明，不可见），岛体从大条长到全尺寸的观感在渲染层
  mainWindow.setBounds(expandedBounds(getCursorDisplay()));
  mainWindow.setMinimumSize(MIN_EXPANDED.width, MIN_EXPANDED.height);
  mainWindow.setResizable(true);
  mainWindow.show();
  mainWindow.focus();
  setMode('expanded');
}

function collapse() {
  if (mode !== 'expanded') return;
  setMode('collapsed'); // guest 立即隐藏，岛体开始收缩
  if (collapseTimer) clearTimeout(collapseTimer);
  collapseTimer = setTimeout(() => {
    collapseTimer = null;
    if (!mainWindow || mainWindow.isDestroyed() || mode === 'expanded') return;
    mainWindow.setResizable(false);
    mainWindow.setMinimumSize(0, 0);
    mainWindow.setBounds(collapsedBounds());
  }, COLLAPSE_ANIMATE_MS);
}

function toggle() {
  if (mode === 'expanded') collapse();
  else expand();
}

let lastResizeActivityAt = 0;
let blurCollapseTimer = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    ...collapsedBounds(),
    frame: false,
    transparent: true,
    // 显式透明底色：避免展开瞬间新暴露区域闪黑块
    backgroundColor: '#00000000',
    resizable: false,
    movable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: true,
    acceptFirstMouse: true,
    hiddenInMissionControl: true,
    fullscreenable: false,
    minimizable: false,
    maximizable: false,
    roundedCorners: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'host-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setAlwaysOnTop(true, 'screen-saver');
  if (process.platform === 'darwin') {
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  }

  // 点别处失焦收起（与旧壳一致的直觉）——但要放过拖拽调size期间的假失焦：
  // 原生边缘缩放/快速拖拽时鼠标会瞬间离开窗口，macOS 短暂转移焦点，
  // 立即收起就会表现成「一碰边缘就收回」。延迟确认 + 近期 resize 活动豁免。
  mainWindow.on('blur', () => {
    if (mode !== 'expanded') return;
    clearTimeout(blurCollapseTimer);
    blurCollapseTimer = setTimeout(() => {
      blurCollapseTimer = null;
      if (mode !== 'expanded' || !mainWindow || mainWindow.isDestroyed()) return;
      if (mainWindow.isFocused()) return;
      if (Date.now() - lastResizeActivityAt < 800) return;
      collapse();
    }, 350);
  });
  mainWindow.on('focus', () => {
    clearTimeout(blurCollapseTimer);
  });

  // 拖边调整大小（原生边缘感应）或把手拖拽触发的窗口 resize：guest 重新贴合 + 记忆尺寸
  mainWindow.on('resize', () => {
    if (mode !== 'expanded') return;
    lastResizeActivityAt = Date.now();
    clearTimeout(resizeSyncTimer);
    resizeSyncTimer = setTimeout(() => {
      if (mode !== 'expanded' || !mainWindow || mainWindow.isDestroyed()) return;
      try {
        consoleEmbed.syncView();
      } catch (error) {}
      const { width, height } = mainWindow.getContentBounds();
      savedSize = { width, height };
      mainWindow.webContents.send('panel:size', { width, height });
      clearTimeout(resizeSaveTimer);
      resizeSaveTimer = setTimeout(writeSizeSetting, 600);
    }, 120);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  mainWindow.once('ready-to-show', () => {
    setMode('collapsed');
    mainWindow.show();
  });
}

ipcMain.on('panel:expand', (event) => {
  if (mainWindow && !mainWindow.isDestroyed() && event.sender === mainWindow.webContents) {
    expand();
  }
});

// ============ 拖拽调size（控制台页面右下角把手 → guest IPC） ============
let pendingResize = null;
let resizeApplyScheduled = false;
let lastResizeApplyAt = 0;
const RESIZE_MIN_INTERVAL_MS = 33; // 拖拽事件再密也最多 ~30fps 应用一次

function applyPendingResize() {
  resizeApplyScheduled = false;
  if (!pendingResize || mode !== 'expanded' || !mainWindow || mainWindow.isDestroyed()) return;
  const now = Date.now();
  const wait = RESIZE_MIN_INTERVAL_MS - (now - lastResizeApplyAt);
  if (wait > 0) {
    // 还在节流窗口内：保留 pendingResize 不丢，到点再应用
    resizeApplyScheduled = true;
    setTimeout(applyPendingResize, wait);
    return;
  }
  const target = pendingResize;
  pendingResize = null;
  lastResizeApplyAt = Date.now();
  const d = getWindowDisplay();
  const width = Math.min(Math.max(target.width, MIN_EXPANDED.width), d.workArea.width - SCREEN_MARGIN);
  const height = Math.min(
    Math.max(target.height, MIN_EXPANDED.height),
    Math.max(getCollapsedHeight(d), d.bounds.height - SCREEN_MARGIN)
  );
  mainWindow.setBounds(topCenterBounds(width, height, d));
  try {
    consoleEmbed.syncView();
  } catch (error) {}
  savedSize = { width, height };
  mainWindow.webContents.send('panel:size', { width, height });
  clearTimeout(resizeSaveTimer);
  resizeSaveTimer = setTimeout(writeSizeSetting, 600);
}

ipcMain.on('panel:resize', (event, size) => {
  if (!mainWindow || mainWindow.isDestroyed() || mode !== 'expanded') return;
  if (event.sender !== mainWindow.webContents && !consoleEmbed.isConsoleGuest(event.sender)) return;
  // 热区拖拽可能只带一个维度（拉左右缘只改宽、拉底缘只改高），缺的维度沿用当前值
  const cur = mainWindow.getContentBounds();
  const width = Number(size && size.width);
  const height = Number(size && size.height);
  if (!Number.isFinite(width) && !Number.isFinite(height)) return;
  lastResizeActivityAt = Date.now();
  pendingResize = {
    width: Number.isFinite(width) ? Math.round(width) : cur.width,
    height: Number.isFinite(height) ? Math.round(height) : cur.height,
  };
  if (!resizeApplyScheduled) {
    // 每帧最多 setBounds 一次，拖拽事件再密也不糊窗口
    resizeApplyScheduled = true;
    setImmediate(applyPendingResize);
  }
});

// ============ 托盘 ============
function refreshTrayMenu() {
  if (!tray) return;
  const autoLaunch = isAutoLaunchEnabled();
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '展开 / 收起控制台', click: toggle },
    { type: 'separator' },
    {
      label: '开机自动启动',
      type: 'checkbox',
      checked: autoLaunch,
      click: (item) => {
        setAutoLaunch(item.checked);
        refreshTrayMenu();
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      accelerator: 'CommandOrControl+Q',
      click: () => app.quit(),
    },
  ]));
}

function createTray() {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'build', 'trayTemplate.png'));
  icon.setTemplateImage(true);
  tray = new Tray(icon);
  tray.setToolTip('Context Gate 控制台（⌘⇧E）');
  tray.on('click', () => expand());
  refreshTrayMenu();
}

// ============ 开机自启 ============
const FIRST_RUN_MARKER = '.first-run-done';

function isAutoLaunchEnabled() {
  try {
    return app.getLoginItemSettings().openAtLogin;
  } catch (error) {
    return false;
  }
}

function setAutoLaunch(enabled) {
  try {
    app.setLoginItemSettings({ openAtLogin: enabled, openAsHidden: false });
    return isAutoLaunchEnabled() === enabled;
  } catch (error) {
    return false;
  }
}

// 首次运行默认开机自启（沿用旧壳常驻可用性的定位）；之后尊重托盘里的选择
function ensureFirstRunAutoLaunch() {
  if (process.platform !== 'darwin') return;
  const marker = path.join(app.getPath('userData'), FIRST_RUN_MARKER);
  if (fs.existsSync(marker)) return;
  try {
    setAutoLaunch(true);
    fs.writeFileSync(marker, String(Date.now()));
  } catch (error) {}
}

// ============ 多屏跟随 ============
function watchDisplayChanges() {
  let timer = null;
  const reposition = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      mainWindow.setBounds(boundsForMode(mode));
      setMode(mode);
    }, 100);
  };
  screen.on('display-added', reposition);
  screen.on('display-removed', reposition);
  screen.on('display-metrics-changed', reposition);
}

function boundsForMode(m) {
  return m === 'expanded' ? expandedBounds() : collapsedBounds();
}

app.whenReady().then(() => {
  console.log('[panel] whenReady entered, isPackaged =', app.isPackaged, 'resources =', process.resourcesPath);
  if (process.platform === 'darwin' && app.dock) app.dock.hide();

  readSizeSetting();
  ensureFirstRunAutoLaunch();
  createWindow();
  consoleEmbed.setup(() => mainWindow);
  createTray();
  watchDisplayChanges();
  globalShortcut.register(HOTKEY, toggle);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
}).catch((error) => {
  // 启动链任何一步崩了都必须留痕，否则就是无窗口僵尸进程
  console.error('[panel] startup failed:', error);
});
