'use strict';

// Context Gate 控制台页面通过 window.webkit.messageHandlers 探测是否运行在原生壳内
// （Swift 壳的 WKWebView 注入同款协议）；Electron guest 里复刻同一桥，
// 让页面自带的 showReconnect 自愈逻辑零改动生效。theme 桥仅占位。

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('webkit', {
  messageHandlers: {
    reconnect: {
      postMessage: () => {
        try { ipcRenderer.send('console:reconnect'); } catch (error) {}
      },
    },
    theme: {
      postMessage: () => {},
    },
  },
});

// 控制台页面右下角的拖拽调size把手用的通道；Swift 壳/浏览器里没有这个对象，
// 页面据此决定是否渲染把手。
contextBridge.exposeInMainWorld('panelShell', {
  resize: (size) => {
    try { ipcRenderer.send('panel:resize', size); } catch (error) {}
  },
});
