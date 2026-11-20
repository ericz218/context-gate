'use strict';

// 宿主页（刘海条）唯一需要的两个能力：点击条体请求展开、跟随主进程切换展开/收起样式。

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('panelShell', {
  expand: () => ipcRenderer.send('panel:expand'),
  onMode: (cb) => {
    if (typeof cb !== 'function') return;
    ipcRenderer.on('panel:mode', (event, payload) => cb(payload));
  },
  onSize: (cb) => {
    if (typeof cb !== 'function') return;
    ipcRenderer.on('panel:size', (event, payload) => cb(payload));
  },
});
