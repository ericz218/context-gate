'use strict';

// 宿主页逻辑：岛体尺寸/模式由主进程下发；点岛体展开。
// 动画契约：只有 applyMode（展开/收起形态切换）带过渡（body.anim 挂 350ms），
// applySize（拖拽调size的跟随）永远瞬时，否则过渡追帧 = 整个面板抽搐。
const island = document.getElementById('island');
let animTimer = null;

function setIslandSize(width, height) {
  if (Number.isFinite(width)) island.style.width = `${Math.round(width)}px`;
  if (Number.isFinite(height)) island.style.height = `${Math.round(height)}px`;
}

function applyMode(payload) {
  if (!payload || typeof payload !== 'object') return;
  const expanded = payload.mode === 'expanded';
  document.body.classList.add('anim');
  document.body.classList.toggle('expanded', expanded);
  document.body.classList.toggle('collapsed', !expanded);
  setIslandSize(payload.width, payload.height);
  // 展开态岛体从菜单栏带下方开始（top>0），收起小条贴顶（top=0）
  if (Number.isFinite(payload.top)) island.style.top = `${Math.round(payload.top)}px`;
  clearTimeout(animTimer);
  animTimer = setTimeout(() => document.body.classList.remove('anim'), 350);
}

function applySize(payload) {
  if (!payload || typeof payload !== 'object') return;
  document.body.classList.remove('anim'); // 拖拽跟手，绝不过渡
  setIslandSize(payload.width, payload.height);
}

if (window.panelShell) {
  if (typeof window.panelShell.onMode === 'function') window.panelShell.onMode(applyMode);
  if (typeof window.panelShell.onSize === 'function') window.panelShell.onSize(applySize);
  island.addEventListener('click', () => window.panelShell.expand());
}
