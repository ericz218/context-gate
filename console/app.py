# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Local console: read-only ledger views and explicitly invoked management actions.

Every route is protected by the local path token and same-origin checks.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_data import snapshot, snapshot_cached, gate_stream_event, request_detail, external_outcomes, redact_text
from console_search import search, detail as search_detail
from control_center import Center, MODEL_CATALOG, MODEL_EFFORTS, write_json
from console_butler import Butler, load_butler_settings, butler_settings_label
from group_chat import Groups
from console_import import Imports
from console_todo import Todos
from console_schedule import Schedules
from console_quota import Quotas
from console_quota_stop import stop_all_local, Protection
from console_wallet import Wallets
from console_memory import MemoryLibrary
from console_router import RouterManager
from console_capability import CapabilityRegistry
from console_router_fallback import DirectFallback
from console_zcode_sync import options as zcode_options, sync_request as zcode_sync_request, auto_sync as zcode_auto_sync, AUTO_SYNC_COMMANDS
import console_attach
from prices import ensure_config, save_mode, MODES as COST_MODES

HOTKEY_RE = re.compile(r'^[A-Z0-9]$')
# Fixed allowlist: names never reach a shell argument unsanitized.
OPEN_APPS = {
    'claude': ['/usr/bin/open', '-a', 'Claude'],
    'claude-login': ['/usr/bin/osascript', '-e', 'tell application "Terminal" to do script "claude auth login"'],
    'zcode': ['/usr/bin/open', '-a', 'ZCode'],
    'codex': ['/usr/bin/osascript', '-e', 'tell application "Terminal" to do script "codex"'],
}


def run_open(command):
    try:
        return subprocess.run(command, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def load_hotkey(state_dir):
    path = Path(state_dir) / 'hotkey.json'
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and HOTKEY_RE.fullmatch(str(data.get('key', ''))):
            return {'key': data['key'], 'ctrl': bool(data.get('ctrl')),
                    'cmd': bool(data.get('cmd')), 'shift': bool(data.get('shift')),
                    'alt': bool(data.get('alt'))}
    except (OSError, ValueError):
        pass
    return {'key': 'E', 'ctrl': False, 'cmd': True, 'shift': True, 'alt': False}


# 单页控制台。两种风格各有明暗主题；data-theme 仍只在 dark/warm 间切换。
# JS 侧 reconcile() 做子节点级最小 diff，10s 刷新不再整体重建 DOM（悬浮/展开不被打断）。
PAGE = (r'''<!doctype html>
<html lang="zh-CN" data-theme="dark" data-style="prism">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Context Gate 控制台</title>
<style>
:root[data-theme=dark]{color-scheme:dark;--bg:#0B0D10;--card:#12151A;--card2:#171B21;--line:rgba(255,255,255,.06);--line2:rgba(255,255,255,.14);--text:#E2E5EA;--muted:#ADB6C7;--accent:#B2A6FF;--onaccent:#0B0D10;--ok:#34D399;--bad:#F87171;--warn:#F0A32E;--rowhover:rgba(255,255,255,.03);--tipbg:#20262F;--tiptext:#E2E5EA;--pretext:#E0E4EB;--okbg:rgba(52,211,153,.12);--badbg:rgba(248,113,113,.12);--warnbg:rgba(240,163,46,.12);--accentbg:rgba(139,124,246,.14);--mutbg:rgba(126,134,149,.13);--prebg:#080A0D;--shadow:0 4px 16px rgba(0,0,0,.4);--panelshadow:0 10px 36px rgba(0,0,0,.5);--chip:rgba(255,255,255,.045);--g1:rgba(139,124,246,.19);--g2:rgba(94,234,212,.10);--g3:rgba(232,121,249,.08);--cardT:rgba(20,23,30,.78);--cardshadow:0 4px 16px rgba(5,6,10,.18);--glassbg:rgba(22,25,32,.66);--sidebg:rgba(11,13,16,.42);--hl:rgba(255,255,255,.09);--glassline:rgba(255,255,255,.12);--chipbg:rgba(24,27,34,.45);--lift:0 8px 24px rgba(0,0,0,.38);--accent2:#6F61D9;--refreshshadow:0 2px 12px rgba(139,124,246,.35);--side:216px;--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%237E8695' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
:root[data-theme=warm]{color-scheme:light;--bg:#FAF9F7;--card:#FFFFFF;--card2:#F6F3EE;--line:#EAE4DA;--line2:#D9D0C1;--text:#2B2520;--muted:#6E6256;--accent:#C2410C;--onaccent:#FFFFFF;--ok:#1A7F4B;--bad:#B3372C;--warn:#966A08;--rowhover:rgba(43,37,32,.035);--tipbg:#2B2520;--tiptext:#FAF9F7;--pretext:#F1ECE4;--okbg:rgba(26,127,75,.1);--badbg:rgba(179,55,44,.09);--warnbg:rgba(150,106,8,.11);--accentbg:rgba(194,65,12,.09);--mutbg:rgba(138,128,116,.12);--prebg:#25201B;--shadow:0 4px 14px rgba(43,37,32,.1);--panelshadow:0 10px 36px rgba(43,37,32,.16);--chip:rgba(255,255,255,.5);--g1:rgba(194,65,12,.18);--g2:rgba(150,106,8,.12);--g3:rgba(217,119,6,.11);--cardT:rgba(255,255,255,.8);--cardshadow:0 4px 16px rgba(43,37,32,.06);--glassbg:rgba(255,255,255,.76);--sidebg:rgba(250,249,247,.5);--hl:rgba(255,255,255,.85);--glassline:rgba(43,37,32,.10);--chipbg:rgba(255,255,255,.42);--lift:0 8px 22px rgba(43,37,32,.12);--accent2:#A33808;--refreshshadow:0 2px 10px rgba(194,65,12,.28);--side:216px;--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%238A8074' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
:root[data-theme=dark]{--cost:#7DD3FC;--costbg:rgba(125,211,252,.13)}
:root[data-theme=warm]{--cost:#B7791F;--costbg:rgba(183,121,31,.12)}
*{box-sizing:border-box}
main [data-view]:not([data-view=overview]){display:none}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
::selection{background:var(--accentbg)}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-track{background:transparent}
#sidenav{position:fixed;top:0;left:0;bottom:0;width:var(--side);padding:24px 8px 12px;border-right:1px solid var(--line);display:flex;flex-direction:column;gap:4px;z-index:10;overflow:hidden;transition:width .24s cubic-bezier(.2,.75,.25,1)}
body.sidemini #sidenav{width:72px}
body.sidemini main{margin-left:72px}
body.sidemini .brand span,body.sidemini .nav-item span{max-width:0;opacity:0;transform:translateX(-4px);visibility:hidden;transition-delay:0s,0s,0s,.18s}
@media (min-width:55.001em){body.sidemini .nav-item{gap:0;padding:8px 0;justify-content:center}.nav-item{justify-content:flex-start;transition:gap .24s cubic-bezier(.2,.75,.25,1),padding .24s cubic-bezier(.2,.75,.25,1)}}
body.sidemini .nav-sec{opacity:0}
body.sidemini .nav-toggle svg{transform:rotate(180deg)}
.brand span,.nav-item span{display:inline-block;max-width:160px;overflow:hidden;white-space:nowrap;opacity:1;transform:none;visibility:visible;transition:max-width .24s cubic-bezier(.2,.75,.25,1),opacity .14s ease,transform .24s cubic-bezier(.2,.75,.25,1),visibility 0s linear 0s}
.brand span{vertical-align:bottom}
.nav-sec{transition:opacity .14s ease}
.nav-toggle svg{width:18px;height:18px;flex:none;transition:transform .24s cubic-bezier(.2,.75,.25,1)}
.nav-item svg{width:18px;height:18px;flex:none}
.nav-toggle{padding:0;min-width:44px;margin-top:8px;display:flex;align-items:center;justify-content:center;min-height:44px;border-radius:8px;color:var(--muted);cursor:pointer;user-select:none;border:0;background:transparent;flex-shrink:0}
.nav-toggle:hover{color:var(--text);background:var(--rowhover)}
.refresh-note{font-size:12px;color:var(--muted);max-width:260px;overflow-wrap:anywhere}.refresh-note[data-state=error]{color:var(--warn)}
.pagehead{margin:2px 0 16px}
.pagehead h2{font-size:18px;font-weight:650;letter-spacing:-.01em;margin:0 0 3px}
.pagehead p{margin:0;color:var(--muted);font-size:13px}
.pagehead .sums{display:flex;gap:20px;margin-top:10px;flex-wrap:wrap}
.sums .sum{font-size:12px;color:var(--muted)}
.sums .sum b{color:var(--text);font-weight:600;font-size:13px;margin-right:4px;font-variant-numeric:tabular-nums}
.vdiv{width:1px;height:16px;background:var(--line2);margin:0 8px;align-self:center}
.filterbar{display:flex;align-items:center;gap:8px;margin-bottom:14px}
.dd-btn.filtering{color:var(--accent);border-color:var(--accentbg)}
.dd{position:relative}
.dd-btn{height:36px;padding:0 26px 0 10px;font-weight:500;cursor:pointer;background-image:var(--chev);background-repeat:no-repeat;background-position:right 9px center}
.dd-menu{display:none;position:absolute;top:calc(100% + 4px);left:0;min-width:100%;background:var(--card);border:1px solid var(--line2);border-radius:8px;box-shadow:var(--panelshadow);padding:4px;max-height:280px;overflow:auto;z-index:30;opacity:0;transform:translateY(-4px);pointer-events:none;visibility:hidden;transition:opacity .16s ease,transform .16s ease}
.dd.open .dd-menu{display:block;opacity:1;transform:none;pointer-events:auto;visibility:visible;transform-origin:top;animation:ddIn .22s cubic-bezier(.33,1,.68,1)}
/* 菜单靠 display 切换显示，过渡不会播放，所以打开时用关键帧向下展开；曲线与工作台卡片展开一致。 */
.dd.closing:not(.open) .dd-menu{display:block;visibility:visible;pointer-events:none;transform-origin:top;animation:ddOut .16s cubic-bezier(.33,1,.68,1) forwards}
/* 收起要单独起名：沿用 ddIn 只改方向时浏览器不会重播。 */
@keyframes ddOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(-6px) scaleY(.96)}}
@keyframes ddIn{from{opacity:0;transform:translateY(-6px) scaleY(.96)}to{opacity:1;transform:none}}
.dd-it{display:block;width:100%;text-align:left;border:0;background:transparent;min-height:36px;padding:8px 12px;border-radius:5px;font-size:12.5px;cursor:pointer;color:var(--text);white-space:nowrap}
.dd-it:hover{background:var(--rowhover)}
.dd-it.on{color:var(--accent);background:var(--accentbg);font-weight:500}
.dd-it:disabled{opacity:.5;cursor:not-allowed}
.dd-native{position:absolute!important;left:0;bottom:0;width:1px!important;height:1px!important;min-height:0!important;opacity:0;pointer-events:none;padding:0;border:0}
.dd-select{display:inline-block;max-width:100%;vertical-align:middle}
.dd-select>.dd-btn{max-width:100%;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-select>.dd-btn:disabled{opacity:.55;cursor:not-allowed}
.dd-select>.dd-menu[popover]{position:fixed;inset:auto;margin:0;color:var(--text)}
.dd-select.open{z-index:60;position:relative}
.center-form label>.dd-select,.group-dialog label>.dd-select,.router-form label>.dd-select{display:block;width:100%}
.center-form label>.dd-select>.dd-btn,.group-dialog label>.dd-select>.dd-btn,.router-form label>.dd-select>.dd-btn{width:100%}
.flabel{color:var(--muted);font-size:12px;margin:0 6px 0 2px}
.filterbar .vdiv{margin:0 10px}
.pagehead .propbar{display:flex;gap:3px;height:12px;padding:3px;border:1px solid var(--glassline);border-radius:999px;overflow:hidden;background:var(--cardT);box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow);margin-top:12px;width:100%;max-width:420px;box-sizing:border-box}
.propbar i{display:block;height:100%;min-width:0;border-radius:999px;box-shadow:inset 0 1px 0 rgba(255,255,255,.28);transition:flex-grow .28s cubic-bezier(.33,1,.68,1),opacity .22s ease}
.propbar i[hidden]{display:none}.propbar .pp-done{background:linear-gradient(90deg,color-mix(in srgb,var(--ok) 60%,var(--card2)),var(--ok))}
.propbar .pp-run{background:linear-gradient(90deg,var(--accent2),var(--accent))}
.propbar .pp-bad{background:linear-gradient(90deg,color-mix(in srgb,var(--warn) 60%,var(--card2)),var(--warn))}
.setrow{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid var(--line)}
.setrow:last-child{border-bottom:0}
.sname{font-weight:500;font-size:13px}
.sdesc{color:var(--muted);font-size:12px;margin-top:1px}
.ovrow{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.ovrow>section{margin-bottom:0}
.ovrow .ovhalf h2{margin-bottom:6px}
.mrow{display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line);font-size:12px}
#ov-req .mrow,#ov-gt .mrow{cursor:pointer}
#ov-req .mrow:hover,#ov-gt .mrow:hover{background:var(--rowhover)}
@keyframes rowFlash{0%,45%{background:var(--accentbg)}100%{background:transparent}}
.row-flash{animation:rowFlash 1.5s ease}
.mrow:last-child{border-bottom:0}
.mrow .mmodel{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mrow .mtime{color:var(--muted);font-variant-numeric:tabular-nums;flex:none}
.mrow .mtok{color:var(--muted);font-variant-numeric:tabular-nums;flex:none;min-width:64px;text-align:right}
.ovlink{color:var(--accent);font-size:12px;cursor:pointer;margin:8px 0 0;text-align:right}
@media (max-width:1000px){.ovrow{grid-template-columns:1fr}}
#sidenav .brand{flex-shrink:0;font-size:13px;font-weight:650;letter-spacing:-.01em;padding:2px 10px 12px;color:var(--text)}
.nav-item{display:flex;align-items:center;gap:8px;padding:8px;min-height:44px;border:1px solid transparent;background:transparent;text-align:left;flex-shrink:0;border-radius:8px;color:var(--muted);font-size:14px;cursor:pointer;user-select:none}
.nav-item:hover{color:var(--text);background:var(--rowhover)}
#sidenav .nav-item:hover{border-color:transparent}
.nav-list{display:flex;flex-direction:column;gap:4px;flex:1;min-height:0;min-width:0;overflow-y:auto;overflow-x:hidden;scrollbar-gutter:stable}
.nav-list .nav-item{width:100%;min-width:44px}
body.sidemini .brand{padding:0;min-height:24px}
body.sidemini .brand:before{content:"CG";display:block;text-align:center;color:var(--muted);font-size:12px}
.nav-item.on{color:var(--accent);background:var(--accentbg);font-weight:500}
.nav-sec{font-size:10.5px;color:var(--muted);letter-spacing:.06em;padding:12px 10px 4px}
main{margin-left:var(--side);padding:28px 32px 48px;min-width:0;transition:margin-left .24s cubic-bezier(.2,.75,.25,1)}main:focus{outline:none}
header{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:24px}
h1{font-size:20px;font-weight:650;letter-spacing:-.01em;line-height:1.2;margin:0}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;flex:none}
select,button,input:not([type=checkbox]):not([type=radio]),textarea{font:inherit;padding:6px 14px;border:1px solid var(--line2);border-radius:8px;background:var(--cardT);color:var(--text);transition:border-color .12s ease,background-color .12s ease}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input::placeholder,textarea::placeholder{color:var(--muted)}
.gridlabel{font-size:10px;fill:var(--muted);font-variant-numeric:tabular-nums}
.lgd{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px;vertical-align:0}
.tile .v,.sum b,.num{font-variant-numeric:tabular-nums}
select:hover,button:hover{border-color:var(--line2)}
button:active{transform:translateY(.5px)}
button:disabled{opacity:.45;cursor:default}
button:disabled:active{transform:none}
:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#dd-period{margin-left:auto}
#dd-router-period{margin-left:auto}
select{appearance:none;-webkit-appearance:none;height:32px;padding:0 26px 0 10px;font-weight:500;cursor:pointer;background-image:var(--chev);background-repeat:no-repeat;background-position:right 9px center}
header .chk{height:32px;padding:0 10px;border:1px solid var(--line);border-radius:7px;background:var(--cardT);font-size:12px}
header .chk input{accent-color:var(--accent);margin:0}
#svc{display:inline-flex;align-items:center;height:30px;padding:0 10px;border-radius:999px;background:var(--mutbg);font-size:11px;font-weight:500}
#updated{font-size:11px}
.hstatus{display:flex;align-items:center;gap:8px;margin-right:auto}
.iconbtn{width:32px;height:32px;padding:0;display:inline-flex;align-items:center;justify-content:center;color:var(--muted)}
.iconbtn:hover{color:var(--text);border-color:var(--line2)}
#themeicon .ic-sun,#themeicon .ic-moon{display:none}
:root[data-theme=dark] #themeicon .ic-sun{display:block}
:root[data-theme=warm] #themeicon .ic-moon{display:block}
#refresh,#butler-open{height:32px;border-radius:7px;padding:0 12px;font-size:12px}
#butler-open{position:relative}
#butler-open .bdot{position:absolute;top:-4px;right:-4px;width:9px;height:9px;border-radius:50%;background:var(--bad);border:1.5px solid var(--bg)}
#refresh{height:32px;border-radius:7px;padding:0 14px;font-size:12px;color:var(--text);background:var(--cardT)}
#refresh:hover{border-color:var(--line2)}
#refresh:active{transform:translateY(.5px)}
label.chk{color:var(--muted);user-select:none;display:inline-flex;align-items:center;gap:4px}
#banner,#filterchip{display:none;border-radius:8px;padding:6px 10px;margin-bottom:10px;font-size:12px}
#banner{background:var(--badbg);color:var(--bad);border:1px solid var(--badbg)}
#filterchip{background:var(--accentbg);color:var(--accent);border:1px solid var(--accentbg);font-weight:500}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:16px}
.grid>*{min-width:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px;overflow-wrap:anywhere}
.card .k{color:var(--muted);font-size:12px}
.card .v{font-size:28px;font-weight:650;letter-spacing:-.01em;line-height:1.25;font-variant-numeric:tabular-nums;margin:8px 0}
.card .s{color:var(--muted);font-size:12px;line-height:1.5}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px;margin-bottom:16px;min-width:0;overflow-x:auto;contain:layout style}
section h2{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;font-size:14px;font-weight:600;letter-spacing:0;margin:0 0 16px}
.h2-meta{color:var(--muted);font-weight:400;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px;background:var(--chip);border-bottom:1px solid var(--glassline)}
thead th:first-child{border-top-left-radius:8px}
thead th:last-child{border-top-right-radius:8px}
tbody tr{transition:background-color .1s ease}
tbody tr:hover{background:var(--rowhover)}
tbody tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.pos,th.pos{color:var(--ok)}
.tag{padding:0 7px;border-radius:999px;font-size:12px;line-height:19px;display:inline-block;background:var(--mutbg);color:var(--muted)}
.tag.success{background:var(--okbg);color:var(--ok)}
.tag.failed{background:var(--badbg);color:var(--bad)}
.tag.pending{background:var(--warnbg);color:var(--warn)}
.tag.prepared{background:var(--accentbg);color:var(--accent)}
.doing{background:var(--warnbg);color:var(--warn);font-size:11px;padding:0 6px;line-height:17px;display:inline-block;border-radius:999px}
code.file{font-family:ui-monospace,Menlo,monospace;font-size:11px}
.charts{display:flex;gap:5px;align-items:center}
.charts button{font-size:12px;white-space:nowrap;min-height:36px;padding:6px 12px;border-radius:999px;background:var(--chip);border-color:var(--glassline);box-shadow:inset 0 1px 0 var(--hl);color:var(--muted)}
.charts button:hover{color:var(--text);border-color:var(--line2)}
.charts button.on{background:var(--accentbg);border-color:var(--accent);color:var(--accent);font-weight:600;box-shadow:inset 0 1px 0 var(--hl)}
#metric{margin-left:auto;flex:none}
#chartwrap{position:relative}
#chart{width:100%;height:220px;display:block;color:var(--accent);cursor:pointer}
#chartmax{position:absolute;top:2px;right:6px;left:auto;color:var(--muted);font-size:11px;pointer-events:none}
#chartline{position:absolute;top:0;bottom:0;width:1px;background:var(--accent);opacity:0;pointer-events:none;z-index:1;transition:opacity .1s ease}
#chartline.show{opacity:.35}
#charttip{position:absolute;background:var(--tipbg);color:var(--tiptext);border:1px solid var(--line2);border-radius:6px;padding:3px 9px;font-size:11px;pointer-events:none;white-space:nowrap;z-index:2;opacity:0;transition:opacity .1s ease;box-shadow:var(--shadow)}
#charttip.show{opacity:1}
#chart-labels{position:relative;display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:3px;min-height:26px;align-items:flex-start}
#chart-labels,#chartmax,#chart-note,#chart .gridlabel{transition:opacity .18s ease,transform .18s ease}#chart.axis-fade .gridlabel{opacity:.2}#chart-labels.chart-fade,#chartmax.chart-fade,#chart-note.chart-fade{opacity:.2;transform:translateY(3px)}
#chart-labels span.day{position:absolute;transform:translateX(-50%);text-align:center;line-height:1.35;white-space:nowrap}
#chart-labels span.day:first-child{transform:none}#chart-labels span.day:last-child{transform:translateX(-100%)}
#chart-labels span.day i{font-style:normal;display:block;color:var(--text)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}
.tiles>*{min-width:0}
.subhead{grid-column:1/-1;color:var(--muted);font-size:12px;font-weight:600;margin-top:2px}
.tile{border:1px solid var(--line);border-radius:8px;padding:16px;cursor:pointer;background:var(--card);transition:border-color .12s ease,transform .12s ease;overflow-wrap:anywhere;contain:layout style}
.tile:hover{border-color:var(--line2);background:var(--rowhover)}
.tile .t-name{font-size:14px;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.tile .t-name .t-n{font-weight:400;font-size:12px;color:var(--muted);white-space:nowrap}
.freebadge{background:var(--okbg);color:var(--ok);font-size:11px;padding:0 6px;line-height:17px;display:inline-block;border-radius:999px;font-weight:400}
.paidbadge{background:var(--mutbg);color:var(--muted);font-size:11px;padding:0 6px;line-height:17px;display:inline-block;border-radius:999px;font-weight:400}.model-ident{display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0}.t-source{font-size:12px;color:var(--muted);font-weight:400;white-space:nowrap}
.tile .t-row{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--muted);padding:1.5px 0}
.tile .t-row b{color:var(--text);font-variant-numeric:tabular-nums;font-weight:500}
.tile .t-row i{font-style:normal;font-variant-numeric:tabular-nums}
.tile .t-row.save b,.tile .t-row.save i{color:var(--ok)}
.tile .t-row.dim span,.tile .t-row.dim b{color:var(--muted);font-weight:400}
.center-record .usage-warning{color:var(--warn);border-left:3px solid var(--warn);padding:8px 12px;background:var(--panel)}
.tile .warn{color:var(--warn);font-size:11px;margin-top:3px}
.wb{display:grid;grid-template-columns:1fr;gap:8px}
.wb>*{min-width:0}
@media (max-width:1000px){.wb{grid-template-columns:1fr}}
.wb-item{border:1px solid var(--line);border-radius:8px;margin-bottom:6px;overflow-wrap:anywhere;transition:border-color .12s ease,background-color .12s ease,transform .12s ease,box-shadow .12s ease}
.wb-item:hover{background:var(--rowhover)}
.wb-item.open{border-color:var(--line2);background:var(--card2)}
.wb-head{display:flex;align-items:center;gap:8px;width:100%;min-width:0;text-align:left;padding:7px 10px;background:none;border:0;border-radius:8px;color:var(--text);cursor:pointer;font:inherit}
.wb-head:hover{border:0}
.wb-name{font-weight:600;font-size:13px;flex:none;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wb-next{color:var(--muted);font-size:12px;flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wb-upd{color:var(--muted);font-size:12px;flex:none;font-variant-numeric:tabular-nums}
.wb-chev{color:var(--muted);flex:none;font-size:12px;transition:transform .12s ease}
.wb-item.open .wb-chev{transform:rotate(90deg)}
.wb-body{display:grid;grid-template-rows:0fr;transition:grid-template-rows .22s cubic-bezier(.33,1,.68,1)}
.wb-item.open .wb-body{grid-template-rows:1fr}
.wb-body-in{overflow:hidden;min-height:0}
.wb-line{display:flex;gap:8px;padding:2px 10px;font-size:12px;line-height:1.55}
.wb-line .wb-k{flex:none;color:var(--muted);width:56px}
.wb-line .wb-v{white-space:pre-wrap;word-break:break-word;min-width:0}
.wb-foot{margin-top:2px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.gt-live{width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block;animation:pulse 1.6s ease-in-out infinite;margin-right:5px;vertical-align:1px}
.gt-chip{font-size:11px;padding:0 6px;line-height:17px;display:inline-block;border-radius:999px;background:var(--mutbg);color:var(--muted)}
.gt-chip.running{background:var(--okbg);color:var(--ok)}
.gt-chip.failed,.gt-chip.interrupted,.gt-chip.incomplete{background:var(--warnbg);color:var(--warn)}
.gt-req{white-space:pre-wrap;word-break:break-word;margin:3px 0 6px;font-size:12px;line-height:1.5;font-family:inherit;color:var(--text);background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:6px 10px;max-height:110px;overflow:auto}
.modal-backdrop{position:fixed;inset:0;width:100%;height:100%;max-width:none;max-height:none;margin:0;border:0;color:var(--text);background:rgba(0,0,0,.74);z-index:50;display:flex;align-items:center;justify-content:center;padding:20px;animation:fadeIn .12s ease}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes viewIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
.view-in{animation:viewIn .22s ease}
.modal-panel{background:var(--card);border:1px solid var(--line2);border-radius:10px;max-width:860px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:var(--panelshadow);animation:modalIn .14s ease}
@keyframes modalIn{from{opacity:0;transform:scale(.98) translateY(3px)}to{opacity:1;transform:none}}
.modal-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 12px;border-bottom:1px solid var(--line);font-weight:600;font-size:13px;flex:none}
.modal-head button{padding:1px 9px;font-size:12px}
.modal-body{padding:10px 12px;overflow:auto;min-height:0;font-size:13px}
.modal-body pre{max-height:60vh}
.ask-panel{max-width:440px}
.ask-input{width:100%;box-sizing:border-box;margin-top:8px;padding:8px 10px;font-size:13px;border:1px solid var(--line2);border-radius:7px;background:var(--card2);color:var(--text)}
.ask-input:focus{outline:1px solid var(--accent)}
.ask-row{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.ask-row .ask-ok{background:var(--accent);border-color:transparent;color:var(--onaccent)}
tbody tr.gt-turn{cursor:pointer}
.brow{display:grid;grid-template-columns:90px 1fr 92px 74px;gap:10px;align-items:center;font-size:12px;color:var(--muted);padding:3px 0}
.brow .bname{color:var(--text);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bbar{height:8px;border-radius:4px;background:var(--card2);overflow:hidden}
.bbar i{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--accentbg),var(--accent))}
.bval{color:var(--text);text-align:right;font-variant-numeric:tabular-nums;font-weight:500}
.breq{text-align:right;font-variant-numeric:tabular-nums}
/* Shared segmented controls: retain the billing thumb animation. */
.modetog,.quota-seg{position:relative;display:inline-grid;grid-template-columns:1fr 1fr;align-items:center;gap:4px;min-height:36px;padding:4px;border:1px solid var(--glassline);border-radius:999px;background:var(--chipbg);color:var(--muted);font-size:13px;vertical-align:middle}
.modetog{cursor:pointer;transition:background-color .2s ease,border-color .2s ease}
.modetog:hover,.quota-seg:hover{border-color:var(--line2)}
.modetog:active,.quota-seg button:active{transform:scale(.98)}
.modetog span{position:relative;z-index:1;padding:0 14px;line-height:26px;text-align:center;transition:color .28s ease}
.modetog .mt-thumb{position:absolute;top:4px;bottom:4px;left:4px;width:calc(50% - 6px);border-radius:999px;background:var(--costbg);box-shadow:inset 0 0 0 1px var(--cost);transition:transform .28s cubic-bezier(.2,.8,.2,1)}
.modetog[data-mode=usage] .mt-thumb{transform:translateX(calc(100% + 4px))}
.modetog[data-mode=cost] [data-m=cost],.modetog[data-mode=usage] [data-m=usage]{color:var(--cost);font-weight:600}
.quota-seg button{min-height:26px;padding:0 14px;border:0;border-radius:999px;background:transparent;color:var(--muted);font:inherit;cursor:pointer;transition:background-color .2s ease,transform .12s ease}
.quota-seg button:hover{background:var(--rowhover);color:var(--text)}
.quota-seg button[aria-pressed=true]{background:var(--costbg);box-shadow:inset 0 0 0 1px var(--cost);color:var(--cost);font-weight:600}
.costmode-tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;line-height:18px;border:1px solid var(--line2);color:var(--muted);background:var(--chipbg)}.costmode-tag[data-mode=official]{border-color:var(--cost);color:var(--cost);background:var(--costbg)}
#cost-mode button{padding:0 10px;font-size:12px}
.modetog:focus-visible,.quota-seg button:focus-visible{outline:2px solid var(--cost);outline-offset:3px}
.modetog:disabled,.quota-seg button:disabled{opacity:.45;cursor:not-allowed;transform:none}
@media(pointer:coarse){.modetog{min-height:52px}.quota-seg button{min-height:44px}}
#bill-viz{--barc:var(--cost)}#bill-viz[data-mode=usage]{--barc:var(--accent)}
#bill-viz .bbar i{width:var(--wc);background:var(--barc);-webkit-mask-image:linear-gradient(90deg,rgba(0,0,0,.14),#000);mask-image:linear-gradient(90deg,rgba(0,0,0,.14),#000);transition:width .36s cubic-bezier(.2,.8,.2,1),background-color .3s ease}
#bill-viz[data-mode=usage] .bbar i{width:var(--wu)}
#bill-viz .bval2{display:grid;font-size:14px}#bill-viz .bval2>span{grid-area:1/1;opacity:0;visibility:hidden;transform:translateY(4px);transition:opacity .2s ease,transform .2s ease,visibility 0s linear .2s}
#bill-viz:not([data-mode=usage]) .bv-cost,#bill-viz[data-mode=usage] .bv-use{opacity:1;visibility:visible;transform:none;transition:opacity .2s ease,transform .2s ease,visibility 0s}
.bfree{display:inline-block;color:var(--cost);background:var(--costbg);border-radius:999px;padding:1px 8px;font-size:12px;font-weight:500}
#bill-viz .brow{grid-template-columns:150px 1fr 96px 116px;font-size:13px;padding:10px 8px;cursor:pointer;border-radius:6px;transform:translateY(calc(var(--dc,0)*100%));transition:transform .36s cubic-bezier(.2,.8,.2,1)}
#bill-viz .brow:hover{background:var(--rowhover)}
.model-price-source{font-size:12px;color:var(--muted);margin:0 0 10px;line-height:1.6}.price-reference{margin:0 0 20px;font-size:13px;line-height:1.7}.price-reference summary{cursor:pointer;color:var(--accent)}.price-reference-row{padding:12px 0;border-bottom:1px solid var(--line)}.price-reference-row p{margin:5px 0;color:var(--muted)}.price-source-url{display:block;overflow-wrap:anywhere;user-select:text;color:var(--accent)}
.billing-open{display:block;text-align:right;color:var(--accent);font-size:12px;margin-top:12px}.crumb-row strong{font-size:15px}.crumb-row .muted{margin-left:12px;font-size:12px}
.free-shortcut{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:13px;text-align:left}.free-shortcut>span:last-child{color:var(--muted)}
#bill-viz[data-mode=usage] .brow{transform:translateY(calc(var(--du,0)*100%))}
#plat-viz .brow{transform:translateY(calc(var(--dy,0)*100%));transition:transform .36s cubic-bezier(.2,.8,.2,1)}#plat-viz .bbar i{transition:width .36s cubic-bezier(.2,.8,.2,1)}
@keyframes kIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
@keyframes kOut{from{opacity:1;translate:0 0}to{opacity:0;translate:0 12px}}
@keyframes kFade{from{opacity:0}}
.k-enter{animation:kIn .28s ease-out}
.k-leave{animation:kOut .24s ease-in forwards;pointer-events:none}
#bill-viz .k-enter,#plat-viz .k-enter{animation:kFade .28s ease-out}
#bill-viz .breq b{font-size:15px;font-weight:600;color:var(--text)}
.crumb-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.crumb{font-size:12px;color:var(--muted)}
.crumb a{color:var(--accent);cursor:pointer;text-decoration:none}
.crumb a:hover{text-decoration:underline}
details{margin-top:6px}
summary{cursor:pointer;color:var(--muted);font-size:12px}
pre{background:var(--prebg);color:var(--pretext);border:1px solid var(--line);border-radius:6px;padding:10px;font-size:11px;line-height:1.5;max-height:240px;overflow:auto;white-space:pre-wrap}
pre.logview{cursor:pointer;transition:border-color .12s ease}
.filelink{color:var(--accent);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.filelink:hover{text-decoration-thickness:2px}
pre.logview:hover{border-color:var(--line2)}
.scard{display:block;width:100%;text-align:left;margin:0 0 6px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);cursor:pointer;font:inherit;color:var(--text)}
.scard:hover{border-color:var(--line2);background:var(--rowhover)}
.scard .sc-head{display:flex;gap:8px;align-items:baseline;min-width:0}
.scard .sc-src{flex:none;color:var(--accent);font-size:11.5px}
.scard .sc-title{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;font-size:12.5px}
.scard .sc-sum{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin-top:2px;font-size:12px;line-height:1.45;color:var(--muted);overflow-wrap:anywhere;text-align:left}
#search-scroll{max-height:min(320px,35vh);overflow-y:auto;overscroll-behavior:contain;padding:2px}
#search-warn{max-height:120px;overflow-y:auto;overscroll-behavior:contain;font-size:12px;color:var(--warn);white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px}
.daylog-row{cursor:pointer}
.rd-row{display:flex;justify-content:space-between;gap:12px;font-size:12.5px;color:var(--muted);padding:1.5px 0}
.rd-row b{color:var(--text);font-variant-numeric:tabular-nums;font-weight:500;text-align:right;min-width:0;overflow-wrap:anywhere}
pre::-webkit-scrollbar{width:8px;height:8px}
pre::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px}
.muted{color:var(--muted)}
.skip-link{position:fixed;top:8px;left:8px;z-index:100;padding:12px 16px;background:var(--card);color:var(--text);border:2px solid var(--accent);border-radius:8px;transform:translateY(-160%)}
.skip-link:focus{transform:none}
[hidden]{display:none!important}
button{cursor:pointer;min-height:34px}button:disabled{cursor:not-allowed}
.ovlink{display:block;margin-left:auto;background:transparent;border:0;padding:8px;min-height:36px}
.filterbar{flex-wrap:wrap}.dd-menu{min-width:160px;max-width:min(360px,calc(100vw - 32px))}
.card .k{line-height:1.6}.card .s{line-height:1.7}.tile .t-name{flex-wrap:wrap}
.card .c-tps b{color:var(--text);font-size:16px;font-weight:650;font-variant-numeric:tabular-nums}
.tps-panel{margin:0 0 16px;padding:14px 16px;border-radius:8px;background:var(--chip)}.tps-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;font-size:13px;font-weight:600;margin-bottom:10px}.tps-head .muted{font-size:12px;font-weight:400}
.tps-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.tps-stats b{display:block;font-size:20px;font-weight:650;line-height:1.3;font-variant-numeric:tabular-nums}.tps-stats span{font-size:12px;color:var(--muted)}.tps-panel p{margin:10px 0 0;font-size:12px}
@media(max-width:38em){.tps-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
.model-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0 12px;color:var(--muted);font-size:12px;font-weight:400}.model-meta>span:last-child{white-space:nowrap}.model-label{min-width:0;overflow-wrap:anywhere}
#chart-tabs{flex-wrap:wrap;row-gap:8px}#chart-tabs .charts{flex-wrap:wrap}#chart-tabs button{flex-shrink:0}
.setrow{padding:16px 0}.setrow>div{min-width:0}.setrow button{flex-shrink:0}
#banner{line-height:1.7;padding:12px 16px}#svc{white-space:nowrap}
@media (max-width:74em){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:55em){
 #sidenav,body.sidemini #sidenav{position:sticky;top:0;width:auto;max-width:100%;height:64px;bottom:auto;flex-direction:row;align-items:center;padding:8px;gap:4px;overflow-x:auto;overflow-y:hidden;border-right:0;border-bottom:1px solid var(--glassline);background:var(--card)}
 #sidenav .brand,#side-toggle{display:none}
 .nav-list{flex-direction:row;flex:1;min-height:44px;overflow:visible;scrollbar-gutter:auto}.nav-list .nav-item{width:auto}
 #sidenav .nav-item,body.sidemini .nav-item{padding:8px 12px;justify-content:flex-start;white-space:nowrap;min-height:44px}
 body.sidemini .nav-item span{max-width:160px;opacity:1;transform:none;visibility:visible;transition-delay:0s}
 main,body.sidemini main{margin-left:0;padding:20px 16px 32px}
 header{gap:8px;margin-bottom:20px}header h1{width:100%;font-size:20px}#dd-period,#dd-router-period{margin-left:0}
 .hstatus{flex-wrap:wrap;max-width:100%}#updated{font-size:12px}
}
@media (max-width:38em){
 .grid{grid-template-columns:minmax(0,1fr);gap:12px}.ovrow{grid-template-columns:minmax(0,1fr)}
 section{padding:16px}.tiles{grid-template-columns:minmax(0,1fr)}
 .filterbar .vdiv{display:none}.setrow{align-items:flex-start;flex-wrap:wrap}
 .charts{flex-wrap:wrap}#metric{margin-left:0}.wb-name{max-width:50%}.wb-upd{display:none}
 .brow{grid-template-columns:72px minmax(24px,1fr) 70px}.breq{display:none}
 #bill-viz .brow{grid-template-columns:96px minmax(24px,1fr) 78px}
 .modal-backdrop{padding:12px}.modal-panel{max-height:calc(100dvh - 24px)}
}
@media (pointer:coarse){button,select,.dd-btn,#themeicon,#refresh,#butler-open{min-height:44px}.iconbtn{min-width:44px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
.center-form{display:grid;gap:16px}.center-form label{display:grid;gap:8px}.center-form textarea{min-height:96px;resize:vertical;width:100%;box-sizing:border-box;background:var(--card2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:12px;font:inherit}.center-actions{display:flex;gap:8px;flex-wrap:wrap}.center-record{border-top:1px solid var(--line);padding:16px 0}.center-record p{white-space:pre-wrap}.center-actions button:disabled{opacity:.45;cursor:default}
#center-form .center-config{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 20px}#center-form label{min-width:0;font-size:13px}#center-form .center-project-field{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:end}#center-form .center-shortcuts{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:12px;color:var(--muted)}#center-form .center-shortcuts button{background:transparent;border-color:transparent;padding:4px 8px;font-size:12px}#center-form .center-shortcuts button:hover{background:var(--rowhover)}#center-form #center-submit{background:var(--accent);color:var(--onaccent);border-color:transparent;min-width:112px;font-weight:600}#center-acceptance{min-height:72px}#center-note:empty{display:none}#center-form #center-note{margin:0}
@media(max-width:660px){#center-form .center-config{grid-template-columns:1fr}}
#library-project,#library-query{background:var(--card2);color:var(--text);border:1px solid var(--line2);border-radius:8px;padding:8px;font:inherit;width:280px;max-width:100%}
/* —— 质感层：深空辉光背景 + 半透明面板 + 浮层玻璃（规则：单光源、blur≥2×y、暗底禁纯黑、滤镜只给浮层）—— */
/* 辉光直接画进 body 背景（随文档滚动，非 fixed 伪元素）：fixed 合成层在 WKWebView 里换主题后会出现整块残影（16:26 平台汇总渲染错误），纯绘制路径无此问题 */
html{min-height:100%;background:var(--bg)}
body{min-height:100dvh;background-color:var(--bg);background-image:
 radial-gradient(1600px 1000px at 70% 0%,var(--g1),transparent 60%),
 radial-gradient(1300px 900px at 0% 45%,var(--g2),transparent 55%),
 radial-gradient(1400px 1000px at 85% 100%,var(--g3),transparent 55%),
 radial-gradient(1200px 900px at 30% 72%,var(--g1),transparent 60%)}
#sidenav{background:var(--sidebg);backdrop-filter:blur(24px) saturate(170%);-webkit-backdrop-filter:blur(24px) saturate(170%);border-right-color:var(--glassline)}
section,.card,.tile,.wb-item,.scard{background:var(--cardT);border-color:var(--glassline);box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow)}
:root[data-theme=dark] section,:root[data-theme=dark] .card,:root[data-theme=dark] .tile,:root[data-theme=dark] .wb-item,:root[data-theme=dark] .scard,:root[data-theme=dark] .group-pane{background-image:linear-gradient(135deg,rgba(139,124,246,.09),rgba(255,255,255,.015) 45%,rgba(94,234,212,.045))}
:root[data-theme=warm] section,:root[data-theme=warm] .card,:root[data-theme=warm] .tile,:root[data-theme=warm] .wb-item,:root[data-theme=warm] .scard,:root[data-theme=warm] .group-pane{background-image:linear-gradient(135deg,rgba(194,65,12,.09),rgba(217,119,6,.05) 45%,rgba(255,255,255,0))}
:root[data-theme=dark] section,:root[data-theme=dark] .tile{box-shadow:inset 0 1px 0 var(--hl),inset 0 0 40px rgba(139,124,246,.05),var(--cardshadow)}
.tile{transition:border-color .12s ease,transform .12s ease,box-shadow .12s ease}
.tile:hover{box-shadow:var(--lift);border-color:var(--accent)}
.dd-menu,.modal-panel{background:var(--glassbg);backdrop-filter:blur(22px) saturate(160%);-webkit-backdrop-filter:blur(22px) saturate(160%)}
.modal-backdrop:not([open]){display:none}.modal-backdrop::backdrop{background:transparent}
.modal-backdrop{background:rgba(8,9,12,.42);backdrop-filter:blur(10px) saturate(120%);-webkit-backdrop-filter:blur(10px) saturate(120%)}
.modal-panel{border-radius:14px;box-shadow:0 24px 70px rgba(0,0,0,.5)}
header select,header button,header .chk{background:var(--cardT);backdrop-filter:blur(20px) saturate(170%) brightness(1.06);-webkit-backdrop-filter:blur(20px) saturate(170%) brightness(1.06);border-color:var(--glassline)}
:root[data-theme=warm] .modal-backdrop{background:rgba(43,37,32,.28)}
:root[data-theme=warm] .modal-panel{box-shadow:0 24px 70px rgba(43,37,32,.24)}

/* Project summaries are quieter than task detail cards. */
#workbench .wb-item{margin-bottom:0;background:var(--cardT);background-image:none;box-shadow:none;border-color:var(--line2);border-radius:12px}
#workbench .wb-item.open{border-color:var(--line2);transform:none;background:var(--card2);box-shadow:inset 0 1px 0 var(--hl)}
#workbench .wb-head{padding:16px;gap:12px;border-radius:12px;min-height:52px}
#workbench .wb-head:focus-visible{outline:2px solid var(--cost);outline-offset:-3px}
#workbench .wb-name{font-size:14px;max-width:40%;flex-shrink:1}
#workbench .wb-next{font-size:13px}
#workbench .wb-item.open .wb-head{border-bottom:1px solid var(--line);border-bottom-left-radius:0;border-bottom-right-radius:0}
#workbench .wb-item.open .wb-body-in{padding-bottom:12px}
#workbench .wb-line{display:grid;grid-template-columns:88px minmax(0,1fr);gap:16px;padding:8px 16px;font-size:13px;line-height:1.65}
#workbench .wb-line .wb-k{width:auto}
#workbench .wb-empty{margin:0;padding:16px 16px 4px;color:var(--muted);font-size:13px}
@media(max-width:38em){#workbench .wb-head{flex-wrap:wrap;gap:8px}#workbench .wb-name{max-width:calc(100% - 44px);flex:1}#workbench .wb-next{order:1;flex-basis:100%;padding-left:20px;white-space:normal}#workbench .wb-line{grid-template-columns:1fr;gap:4px}}

/* Shared task card spacing and surface for compression and quota records. */
#gt-list .wb-item{border-radius:12px;border-color:var(--glassline);overflow:hidden}
#gt-list .wb-head{padding:16px;gap:12px;min-height:52px;border-radius:12px}
#gt-list .wb-head:focus-visible{outline:2px solid var(--cost);outline-offset:-3px}
#gt-list .wb-item.open .wb-head{border-bottom:1px solid var(--line);border-radius:12px 12px 0 0}
#gt-list .wb-body-in{padding:0 16px}#gt-list .wb-item.open .wb-body-in{padding-bottom:16px}
@media(max-width:38em){#gt-list .wb-head{flex-wrap:wrap;padding:12px;gap:8px}#gt-list .gt-sub{flex-basis:100%;order:1;white-space:normal}#gt-list .wb-chev{margin-left:auto}#gt-list .wb-body-in{padding:0 12px}}
</style>
<script>window.addEventListener('error',e=>{window.__err=(window.__err||[]).concat((e.error&&e.error.stack||e.message).split('\n').slice(0,4).join(' || '));document.title='ERR: '+e.message});try{document.documentElement.dataset.theme=localStorage.getItem('cg-theme')||'dark';var st=localStorage.getItem('cg-theme-style');if(!st||(st==='original'&&!localStorage.getItem('cg-prism-seen'))){st='prism'}localStorage.setItem('cg-prism-seen','1');document.documentElement.dataset.style=st}catch(e){}</script>
</head><body><a class="skip-link" href="#main-content">跳到主要内容</a><nav id="sidenav" aria-label="主导航"><div class="brand"><span>Context Gate</span></div>
<button type="button" class="nav-item on" data-v="overview" title="总览"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg><span>总览</span></button>
<button type="button" class="nav-item" data-v="gt" title="压缩任务"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1.8l6 3-6 3-6-3z"/><path d="M2 8.2l6 3 6-3"/><path d="M2 11.4l6 3 6-3"/></svg><span>压缩任务</span></button>
<button type="button" class="nav-item" data-v="bill" title="计费"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M10.2 5.5C9.6 4.7 6 4.7 6 6.4c0 1.8 4 1.2 4 3 0 1.7-3.6 1.7-4.2.8M8 3.7v8.6"/></svg><span>计费</span></button>
<button type="button" class="nav-item" data-v="plat" title="平台汇总"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 13.5V7.5M8 13.5V2.5M13 13.5V9.5"/></svg><span>平台汇总</span></button>
<button type="button" class="nav-item" data-v="wb" title="工作台"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4.5 6l2.5 2-2.5 2M8.5 10.5h3"/></svg><span>工作台</span></button>
<button type="button" class="nav-item" data-v="center" title="任务中心"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 6h6M5 10h6"/></svg><span>任务中心</span></button>
<button type="button" class="nav-item" data-v="req" title="请求"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M5.5 4h9M5.5 8h9M5.5 12h9"/><circle cx="2.7" cy="4" r=".4" fill="currentColor"/><circle cx="2.7" cy="8" r=".4" fill="currentColor"/><circle cx="2.7" cy="12" r=".4" fill="currentColor"/></svg><span>请求</span></button>
<button type="button" class="nav-item" data-v="sys" title="系统"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M2 4.5h12M2 11.5h12"/><circle cx="6" cy="4.5" r="1.8"/><circle cx="10.5" cy="11.5" r="1.8"/></svg><span>系统</span></button>
<div class="nav-footer"><div class="hstatus"><span id="svc"><span class="dot" style="background:#8A93A3"></span>读取中…</span><span class="muted" id="updated"></span></div><button type="button" class="nav-toggle" id="side-toggle" aria-label="收起/展开侧边栏" aria-expanded="true" title="收起/展开侧边栏"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 3L5 8l4.5 5"/></svg></button></div></nav>
<main id="main-content" tabindex="-1">
<header class="console-header">
<div class="page-heading"><h1 id="page-title">总览</h1><button type="button" id="page-help" class="page-help" aria-label="页面说明" aria-haspopup="dialog">?</button></div>
<div class="global-actions"><button class="iconbtn" id="themeicon" title="切换深浅主题" type="button"><svg class="ic-sun" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M13 3l-1.4 1.4M4.4 11.6L3 13"/></svg><svg class="ic-moon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
<button id="butler-open" title="管家（任意视图可用）" type="button">管家</button>
<div class="refresh-control"><button id="refresh" type="button">刷新</button></div></div>
<div class="page-toolbar" id="page-toolbar"><select id="period" style="display:none"><option value="all">全部时间</option><option value="today">今天</option><option value="week">本周</option><option value="month">本月</option></select>
<div class="dd" id="dd-period"><button class="dd-btn" id="dd-period-btn" type="button">全部时间</button><div class="dd-menu" id="dd-period-menu"></div></div>
<select id="platform" style="display:none"><option value="all">全部平台</option></select>
<div class="dd" id="dd-platform"><button class="dd-btn" id="dd-platform-btn" type="button">全部平台</button><div class="dd-menu" id="dd-platform-menu"></div></div>
<div class="dd" id="dd-router-period" hidden><button class="dd-btn" id="dd-router-period-btn" type="button">全部时间</button><div class="dd-menu" id="dd-router-period-menu"></div></div>
<div class="dd" id="dd-router-provider" hidden><button class="dd-btn" id="dd-router-provider-btn" type="button">全部供应商</button><div class="dd-menu" id="dd-router-provider-menu"></div></div>
<div class="quota-seg" id="cost-mode" role="group" aria-label="价格模式"><button type="button" data-mode="actual" aria-pressed="true" title="免费额度和本地模型按 $0 计算；其余根据价格估算。">按付费设置</button><button type="button" data-mode="official" aria-pressed="false" title="按模型官方标价估算，包含免费请求；缺少价格时只统计用量。">按官方标价</button></div>
</div>
</header>
<div id="refresh-note" class="refresh-note" role="status" aria-live="polite"></div>
<div id="banner" role="alert"></div>
<div id="filterchip"></div>
<section data-view="overview">
<form id="search-form"><label for="search-query">搜索 Gate 内容</label><div style="display:flex;gap:8px;margin-top:8px"><input id="search-query" maxlength="300" required style="flex:1;min-width:0" placeholder="编号、项目、模型名，或描述想找的内容"><button>搜索</button></div></form>
<p id="search-note" class="muted" aria-live="polite">搜索历史任务、请求、日志、成果、项目状态与待办。</p><details id="search-box" hidden><summary id="search-box-head">搜索结果</summary><div id="search-scroll"><div id="search-results"></div></div></details><details id="search-warn-box" hidden><summary id="search-warn-head"></summary><div id="search-warn"></div></details><button id="search-more" style="display:none">继续查看</button>
</section>
<div class="grid" data-view="overview">
<div class="card"><div class="k">已发送请求</div><div class="v" id="c-req">–</div><div class="s" id="c-req-s"></div></div>
<div class="card"><div class="k">实际用量 · tokens</div><div class="v" id="c-act">–</div><div class="s" id="c-act-s"></div><div class="s" id="c-act-free"></div></div>
<div class="card"><div class="k">对照测试节省</div><div class="v" id="c-save">–</div><div class="s" id="c-save-s"></div></div>
<div class="card"><div class="k">平均响应时间</div><div class="v" id="c-ms">–</div><div class="s c-tps" id="c-tps" title="输出 tokens ÷ 请求总耗时（含等待首个 token），只统计有耗时记录的成功请求。"></div><div class="s" id="c-ms-s"></div></div>
</div>
<div class="pagehead" data-view="gt"><h2>压缩任务</h2><p>查看经 Context Gate 发送的任务、内容用量和运行结果。</p><div class="sums" id="gt-sums"></div><div class="propbar" id="gt-prop" role="img"></div>
</div><section id="gatetasks" data-view="gt" style="display:none">
<div class="filterbar" id="gt-filters">
<div class="dd" id="gt-cat-dd"><button class="dd-btn" id="gt-cat-btn" type="button">分类：全部</button><div class="dd-menu" id="gt-cat-menu"><div class="dd-it on" data-v="all">全部</div><div class="dd-it" data-v="running">进行中</div><div class="dd-it" data-v="done">已完成</div><div class="dd-it" data-v="failed">失败/中断</div></div></div>
<div class="dd" id="gt-time-dd"><button class="dd-btn" id="gt-time-btn" type="button">时间：全部</button><div class="dd-menu" id="gt-time-menu"><div class="dd-it on" data-v="all">全部</div><div class="dd-it" data-v="1h">1 小时</div><div class="dd-it" data-v="day">一天</div><div class="dd-it" data-v="week">一周</div><div class="dd-it" data-v="month">一月</div><div class="dd-it" data-v="year">一年</div></div></div>
<span class="fsum" id="gt-fsum"></span>
</div>
<div id="gt-list"></div></section>
<div class="pagehead" data-view="bill"><h2>计费</h2><p id="bill-desc">根据用量和价格估算花费；点平台查看各模型明细。</p><div class="sums" id="bill-sums"></div><div style="margin:10px 0 8px"><button type="button" id="bill-mode" class="modetog" role="switch" aria-checked="false" aria-label="切换计费 / 用量"><i class="mt-thumb"></i><span data-m="cost">计费</span><span data-m="usage">用量</span></button></div><div id="bill-viz" data-mode="cost"></div></div><section data-view="bill">
<div class="bill-page" id="bill-page"><div class="crumb-row"><button id="bill-back" style="display:none">‹ 返回</button><div class="crumb" id="bill-crumb" tabindex="-1"></div></div>
<div class="tiles" id="bill-tiles" data-noleave></div>
<div id="bill-detail" data-noleave style="margin-top:12px"></div></div>
<p class="muted" id="bill-note" style="margin-bottom:0"></p>
</section>
<div class="pagehead" data-view="plat"><h2>平台汇总</h2><p>比较各平台的请求量、用量、花费估算和速度。</p></div><section data-view="plat"><div id="plat-viz" style="margin:2px 0 12px"></div><table id="plat"><thead><tr>
<th>平台</th><th class="num">请求数</th><th class="num">已记录用量的请求</th><th class="num">输入 tokens（含缓存）</th><th class="num">输出 tokens</th><th class="num" id="plat-cost-th">估算花费 $</th><th class="num">对照测试节省</th><th class="num">平均耗时 ms</th>
</tr></thead><tbody></tbody></table>
<p class="muted" id="plat-note" style="margin:8px 0 0">「实测对照」= 同一个任务不开压缩直发 vs 走 Gate 各真实跑一遍（A/B），每对记 1 组；节省 tokens 与金额只累计这样对照过的任务，未对照的流量不推算。</p></section>
<div class="pagehead" data-view="wb"><h2>工作台</h2><p id="wb-meta">各项目的最新进度与下一步。</p></div><section data-view="wb">
<div id="workbench" class="wb"></div>
<div class="wb-foot"><button id="wb-toggle" style="display:none"></button></div>
</section>
<section data-view="overview"><h2>用量趋势</h2>
<div style="display:flex;gap:6px;align-items:center;margin-bottom:12px"><div class="charts" id="chart-tabs" style="margin-bottom:0"><button data-mode="7d" class="on">7 天</button><button data-mode="month">30 天</button><button data-mode="year">本年</button><button data-mode="total">总计</button></div><button id="metric" style="flex:none">显示缓存命中率</button></div>
<div id="chartwrap"><svg id="chart" viewBox="0 0 800 170" preserveAspectRatio="none"></svg><div id="chartmax"></div><div id="chartline"></div><div id="charttip"></div></div>
<div id="chart-labels"></div>
<p class="muted" id="chart-note" style="margin:6px 0 0">输入与输出用量合计，包含缓存。悬停查看数值，点击查看对应请求；时间范围由上方趋势按钮控制。</p></section>
<div class="pagehead" data-view="sys"><h2>系统</h2><p>界面设置、快捷键和问题排查。</p></div><section data-view="sys"><h2>设置</h2>
<div class="setrow setrow-theme"><div class="sinfo"><div class="sname">外观主题</div><div class="sdesc">选择主题风格和明暗模式，全局生效</div></div><div class="sctl"><div class="theme-presets" role="group" aria-label="外观主题">
<fieldset class="theme-family"><legend>黑曜棱镜</legend><div class="theme-choice-row"><button type="button" data-theme-preset data-theme-style="prism" data-theme-mode="warm" aria-pressed="false">浅色</button><button type="button" data-theme-preset data-theme-style="prism" data-theme-mode="dark" aria-pressed="false">深色</button></div></fieldset>
<fieldset class="theme-family"><legend>现有风格</legend><div class="theme-choice-row"><button type="button" data-theme-preset data-theme-style="original" data-theme-mode="warm" aria-pressed="false">浅色</button><button type="button" data-theme-preset data-theme-style="original" data-theme-mode="dark" aria-pressed="false">深色</button></div></fieldset>
<fieldset class="theme-family"><legend>现代简约</legend><div class="theme-choice-row"><button type="button" data-theme-preset data-theme-style="mono" data-theme-mode="warm" aria-pressed="false">浅色</button><button type="button" data-theme-preset data-theme-style="mono" data-theme-mode="dark" aria-pressed="false">深色</button></div></fieldset>
</div></div></div>
<div class="setrow"><div class="sinfo"><div class="sname">自动刷新</div><div class="sdesc">每 5 秒更新显示；编辑中的表单会保留，关闭后可手动刷新</div></div><div class="sctl"><input type="checkbox" id="auto" checked style="width:18px;height:18px;accent-color:var(--accent)"></div></div>
<div class="setrow"><div class="sinfo"><div class="sname">侧边栏收起</div><div class="sdesc">以图标条形态显示；也可用侧边栏底部按钮切换</div></div><div class="sctl"><button id="side-default">切换收起/展开</button></div></div>
<div class="setrow"><div class="sinfo"><div class="sname">管家模型</div><div class="sdesc" id="butler-model-desc">当前：读取中…</div></div><div class="sctl"><button id="butler-model-edit">配置</button></div></div>
<div class="setrow"><div class="sinfo"><div class="sname">界面语言</div><div class="sdesc">中文 / English 切换控制台界面语言，立即生效</div></div><div class="sctl"><select id="lang-select" aria-label="界面语言"><option value="zh">中文</option><option value="en">English</option></select></div></div>
</section>
<section data-view="sys"><h2>控制</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px">
<button class="openapp" data-app="claude">打开 Claude</button>
<button class="openapp" data-app="claude-login">修复 Claude 登录</button>
<button class="openapp" data-app="zcode">打开 ZCode</button>
<button class="openapp" data-app="codex">打开 Codex 终端</button>
<span class="muted" id="open-note"></span>
</div>
<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
<span class="muted">全局快捷键：</span><span id="hk-cur" style="font-weight:600">–</span>
<button id="hk-rec">录制快捷键</button><span class="muted" id="hk-note"></span>
</div>
<p class="muted" style="margin:8px 0 0">快捷键在控制台应用运行时有效，保存后几秒生效。打开 Codex 会新建一个终端会话。</p></section>
<div class="pagehead" data-view="req"><h2>请求</h2><p>最近 50 次请求。这里显示每次请求的用量、结果和耗时。</p><div class="sums" id="req-sums"></div></div><section data-view="req"><table id="recent"><thead><tr>
<th>时间</th><th>平台</th><th>模型</th><th>状态</th><th class="num">压缩前估算</th><th class="num">压缩后估算</th><th class="num">估算减少</th><th class="num">实际输入</th><th class="num">实际输出</th><th class="num">缓存读</th><th class="num">耗时 ms</th>
</tr></thead><tbody></tbody></table><p class="muted" id="recent-note"></p>
<p class="muted" style="margin-bottom:0">压缩前后按文本量估算；实际输入与输出来自供应商，二者不一定相同。耗时为请求开始到结束的时间。</p></section>
<section data-view="sys"><h2>连接与密钥检查<span class="h2-meta">只报状态，不显示内容</span></h2><table id="audit"><thead><tr>
<th>文件</th><th>用途</th><th>权限</th><th>含密钥</th><th>指向</th><th>⚠</th>
</tr></thead><tbody></tbody></table>
<p class="muted" id="audit-note" style="margin:8px 0 0"></p></section>
<div class="ovrow" data-view="overview">
<section class="ovhalf"><h2>最近请求</h2><div id="ov-req"></div><button type="button" class="ovlink" data-goto="req">查看全部 →</button></section>
<section class="ovhalf"><h2>最近压缩任务</h2><div id="ov-gt"></div><button type="button" class="ovlink" data-goto="gt">查看全部 →</button></section>
</div>
<section data-view="sys"><h2>日志（已脱敏）<span class="h2-meta">点击内容可放大查看</span></h2>
<details open><summary>服务日志 service.log</summary><pre id="log-service" class="logview" role="button" tabindex="0" aria-label="展开日志"></pre></details>
<details><summary>指标日志 metrics.jsonl</summary><pre id="log-metrics" class="logview" role="button" tabindex="0" aria-label="展开日志"></pre></details>
</section>
<div class="pagehead" data-view="center"><h2>任务中心</h2><p>交代目标，持续执行，查看成果后验收。</p></div>
<section data-view="center"><form id="center-form" class="center-form">
<div class="center-config"><div class="center-project-field"><label>项目<select id="center-project"></select></label><button type="button" id="add-root-btn">添加文件夹</button></div>
<label>执行平台<select id="center-platform"><option value="codex">GPT / Codex</option><option value="claude">Claude Code</option><option value="zcode">ZCode</option></select></label>
<label>模型<select id="center-model"></select></label>
<label>思考档位<select id="center-reasoning"></select></label>
</div>
<label>任务目标<textarea id="center-goal" maxlength="12000" required placeholder="需要完成什么"></textarea></label>
<label>完成标准（选填）<textarea id="center-acceptance" maxlength="4000" placeholder="怎样确认结果符合要求"></textarea></label>
<label><span><input id="center-tests" type="checkbox">完成后运行项目测试</span></label>
<div class="center-shortcuts"><span>快捷填写</span><button type="button" data-template="只读检查项目当前状态，指出需要处理的问题并提供文件证据。">检查项目</button><button type="button" data-template="只读审查当前修改，列出明确问题、影响和验证方法。">审查修改</button><button type="button" data-template="整理当前工作与未完成事项，生成项目交接文档。保留其他会话的修改。">生成交接</button></div><div class="center-actions"><button id="center-submit">开始任务</button></div>
<p id="center-note" class="muted" aria-live="polite"></p></form></section>
<section data-view="center"><h2>我的常用任务</h2><p class="muted">保存目标、完成标准、项目和平台；点名称填回上方，确认后派发。</p><div class="center-actions"><input id="template-name" aria-label="常用任务名称" maxlength="80" placeholder="给当前任务起个名字"><button id="template-save" type="button">保存当前任务</button></div><div id="template-list" class="center-actions"></div><p id="template-note" class="muted" role="status"></p></section>
<section data-view="center"><h2>任务与成果</h2><div id="center-list"></div></section>
<section data-view="center"><h2>预约执行</h2><p class="muted">使用上方当前填写的任务创建一次预约。关闭窗口后仍执行；电脑睡眠或关机时不会执行，迟到超过10分钟会标为已错过。项目忙或派发状态不确定时保留记录，不自动重派。</p><form id="schedule-form"><label>开始时间<input id="schedule-at" type="datetime-local" required></label> <button id="schedule-create">预约当前任务</button> <button type="button" id="schedule-notify">开启完成通知</button></form><p id="schedule-note" class="muted" role="status"></p><div id="schedule-list" role="log" aria-live="polite"></div></section>
<section data-view="center"><h2>用量提醒</h2><p class="muted">用量达到门槛时提醒，不自动停止。Claude 按本次任务计算；Codex 按整个会话累计，接续任务会包含之前的用量。</p><form id="usage-alert-form"><label><input id="usage-alert-enabled" type="checkbox">启用提醒</label> <label>提醒门槛（token）<input id="usage-alert-threshold" type="number" min="1000" max="100000000" step="1" required></label> <button>保存提醒设置</button></form><p id="usage-alert-note" class="muted" role="status"></p></section>
<section data-view="center"><h2>成果库</h2><p class="muted">集中查看任务与群聊回合的归档文件，保留来源和执行状态。群聊完成不等于验收通过。文字最多8MB并分页；PNG、JPEG、GIF、WebP图片最多2MB。</p><div class="center-actions"><label>项目<select id="library-project"><option value="">全部项目</option></select></label><label>搜索文件或任务<input id="library-query" type="search" placeholder="文件名、目标或任务编号"></label></div><div id="library-list"></div><div id="library-external"></div><div id="library-outcomes"></div><p id="library-count" class="muted" role="status"></p><div class="center-actions"><button id="library-prev" hidden>上一页</button><button id="library-next" hidden>下一页</button></div></section>
<section data-view="center"><h2>版本对比</h2><p class="muted">选择同一项目的两份归档方案、报告或图片。文字每份最多128KB；PNG、JPEG、GIF、WebP图片每份最多2MB。</p><div class="ovrow"><div><label>左侧任务<select id="compare-left-task" aria-label="左侧任务"></select></label><label>左侧成果<select id="compare-left-file" aria-label="左侧成果"></select></label></div><div><label>右侧任务<select id="compare-right-task" aria-label="右侧任务"></select></label><label>右侧成果<select id="compare-right-file" aria-label="右侧成果"></select></label></div></div><button id="compare-open" type="button">并排查看</button><p id="compare-note" class="muted" role="status"></p></section>
<section data-view="center"><h2>连接检查</h2><button id="center-diagnose">一键查故障</button><p class="muted">检查执行入口及本地连接，最近的真实执行结果用于区分登录、模型和网页问题。</p><div id="center-diagnostics"></div></section>
</main>
<dialog id="modal" class="modal-backdrop" aria-labelledby="modal-title"><div class="modal-panel"><div class="modal-head"><span id="modal-title"></span><button id="modal-close" type="button">关闭</button></div><div class="modal-body" id="modal-body" tabindex="0"></div></div></dialog>
<script>
'use strict';
// —— 中英双语：默认中文，设置里切换，存 localStorage（cg-lang）。
// 动态文案经 T() 查表（键=中文原文），静态文案打 data-i18n 标记由 applyStaticLang() 套用；
// 切换后 applyLang() 统一重画静态与动态界面。
let LANG='zh';try{LANG=localStorage.getItem('cg-lang')||window.__contextGateLanguage||'zh'}catch(e){}
if(!['zh','en'].includes(LANG))LANG='zh';
const LOCALE=()=>LANG==='en'?'en-US':'zh-CN';
const EN={
'记忆文档来源配置无效。':'The memory document source is invalid.',
"全新请求，未携带原对话":"A new request without the previous conversation",
"关闭实时事件":"Close live events",
"实时事件 ↗":"Live events ↗",
"已暂停刷新；后台记忆处理继续。":"Refresh paused. Memory processing continues in the background.",
"已连接":"Connected",
"当前记忆与版本历史":"Current memories and version history",
"待接入":"Not connected",
"恢复刷新":"Resume refresh",
"文字模式":"Text mode",
"星云模式":"Nebula mode",
"暂停刷新":"Pause refresh",
"最近事件":"Recent events",
"模型正在处理":"Model is processing",
"版本历史":"Version history",
"独立召回":"Recall from a new session",
"监听中":"Listening",
"等待下一条记忆事件…":"Waiting for the next memory event…",
"记忆实时事件":"Live memory events",
"记忆星云":"Memory nebula",
"记忆显示模式":"Memory display mode",
"读取异常":"Read error",
"输入来源":"Input sources",
"连接中…":"Connecting…",
"连接中断":"Disconnected",
"连接中断，正在重试…":"Disconnected. Reconnecting…",
'无法读取记忆文档。请检查 macOS「隐私与安全性 → 文件与文件夹」里的控制台文稿访问权限。':'Cannot read the memory documents. Check the console’s Documents access under macOS Privacy & Security → Files and Folders.',
'Context Gate 控制台':'Context Gate Console',
'总览':'Overview','压缩任务':'Gate Tasks','计费':'Billing','平台汇总':'Platforms','工作台':'Workbench','任务中心':'Task Center','请求':'Requests','系统':'System','群聊':'Group Chat','文件处理':'Files','记忆':'Memory','收起/展开侧边栏':'Collapse/expand sidebar',
'读取中…':'Loading…','更新于 ':'Updated ','全部时间':'All time','今天':'Today','本周':'This week','本月':'This month','全部平台':'All platforms','切换深浅主题':'Toggle light/dark theme','管家（任意视图可用）':'Butler (works in any view)','管家':'Butler','刷新':'Refresh',
'搜索 Gate 内容':'Search Gate content','编号、项目、模型名，或描述想找的内容':'An ID, project, model name, or describe what you’re looking for','搜索':'Search','搜索历史任务、请求、日志、成果、项目状态与待办。':'Search past tasks, requests, logs, outcomes, project status and to-dos.','搜索结果':'Search results','继续查看':'Show more',
'已发送请求':'Requests (sent)','实际用量 · tokens':'Actual tokens (provider-reported)','对照测试节省':'Compression savings (measured A/B only)','平均响应时间':'Average duration (measured requests)','Local Model Router':'Local Model Router','免费 tokens':'Free tokens','Local Model Router 用量':'Local Model Router (free)','付费':'Paid','来源：':'Source: ','客户端来源：':'Client source: ','来源':'Source','DeepAI Code':'DeepAI Code','Codex 接入':'Codex connection','Cursor 接入':'Cursor connection','直接调用':'Direct call','多个接入':'More than one connection',
'经过 DeepAI Code 的 Codex、Cursor 请求只记在 DeepAI Code，不再计入原来的平台。明确走其他上游（例如 api.openai.com）的请求仍留在原平台。':'Codex and Cursor requests that go through DeepAI Code are counted only there. Requests that clearly use another upstream, such as api.openai.com, stay on their original platform.',
'查看经 Context Gate 发送的任务、内容用量和运行结果。':'Compression sub-sessions dispatched by gate_run: run status, context-pack estimates, and per-turn gateway events.',
'分类：全部':'Category: All','全部':'All','进行中':'Running','已完成':'Done','失败/中断':'Failed/interrupted','时间：全部':'Time: All','1 小时':'1 hour','一天':'A day','一周':'A week','一月':'A month','一年':'A year',
'根据用量和价格估算花费；点平台查看各模型明细。':'Actual spend per platform against reference market prices ($ / million tokens). Click a platform tile to drill into its models.',
'‹ 返回':'‹ Back','平台':'Platform','请求数':'Requests','已记录用量的请求':'Measured','输入 tokens（含缓存）':'Input tokens (incl. cache)','输出 tokens':'Output tokens','估算花费 $':'Spend $','对照测试节省':'A/B savings','平均耗时 ms':'Avg ms',
'「实测对照」= 同一个任务不开压缩直发 vs 走 Gate 各真实跑一遍（A/B），每对记 1 组；节省 tokens 与金额只累计这样对照过的任务，未对照的流量不推算。':'“Measured A/B” = the same task run both ways — direct without compression vs through the Gate — as a real A/B pair; each pair counts once. Savings in tokens and dollars only accumulate for tasks actually measured this way; unmeasured traffic is never extrapolated.',
'各项目的最新进度与下一步。':'Latest handoff summary per project.',
'用量趋势':'Usage Trend','7 天':'7 days','30 天':'30 days','本年':'This year','总计':'All time','显示缓存命中率':'Show cache hit rate','显示 tokens':'Show tokens',
'输入与输出用量合计，包含缓存。悬停查看数值，点击查看对应请求；时间范围由上方趋势按钮控制。':'Daily actual tokens (input + output, cache included). Hover for a day’s value; click a point to open that day’s request log (that month in “All time” view). The “30 days” view also marks each day’s spend. Not affected by the filters above.',
'界面设置、快捷键和问题排查。':'App shortcuts, global hotkey, credential audit and service logs.',
'设置':'Settings','外观主题':'Appearance','选择主题风格和明暗模式，全局生效':'Choose a style and light or dark appearance, applies everywhere','黑曜棱镜':'Obsidian Prism','现有风格':'Original style','现代简约':'Modern','浅色':'Light','深色':'Dark','切换浅色':'Switch to light','切换深色':'Switch to dark',
'自动刷新':'Auto refresh','每 5 秒更新显示；编辑中的表单会保留，关闭后可手动刷新':'Update every 5 seconds; preserve forms being edited. Turn off for manual refresh.',
'侧边栏收起':'Collapse sidebar','以图标条形态显示；也可用侧边栏底部按钮切换':'Show the sidebar as a slim icon strip; also togglable from the button at its bottom','切换收起/展开':'Toggle collapsed/expanded',
'管家模型':'Butler model','当前：读取中…':'Current: loading…','配置':'Configure',
'界面语言':'Interface language','中文 / English 切换控制台界面语言，立即生效':'Switch the console between 中文 and English, effective immediately',
'控制':'Controls','打开 Claude':'Open Claude','修复 Claude 登录':'Repair Claude login','打开 ZCode':'Open ZCode','打开 Codex 终端':'Open Codex (terminal CLI)',
'全局快捷键：':'Global hotkey:','录制快捷键':'Record hotkey','按下组合键…（Esc 取消）':'Press the combo… (Esc to cancel)',
'快捷键在控制台应用运行时有效，保存后几秒生效。打开 Codex 会新建一个终端会话。':'The hotkey is registered by the shell app (it must be running) and takes effect within seconds after saving. “Open Codex” starts a new codex session in Terminal.',
'最近 50 次请求。这里显示每次请求的用量、结果和耗时。':'The 50 most recent ledger requests (unaffected by the time/platform filters above).',
'时间':'Time','模型':'Model','状态':'Status','压缩前估算':'Pack est. before','压缩后估算':'Pack est. after','估算减少':'Pack est. saved','实际输入':'Actual input','实际输出':'Actual output','缓存读':'Cache read','耗时 ms':'Duration ms',
'压缩前后按文本量估算；实际输入与输出来自供应商，二者不一定相同。耗时为请求开始到结束的时间。':'“Pack est.” is a character-count estimate (ASCII÷4, CJK÷1.5) and only exists for requests that went through the Gate — it is not the provider’s bill; the “actual” columns are provider-reported. Duration is wall-clock time from the Gate or the app/proxy.',
'连接与密钥检查':'Credential audit','只报状态，不显示内容':'status only, never contents','文件':'File','用途':'Purpose','权限':'Perms','含密钥':'Contains key','指向':'Points to',
'最近请求':'Recent','查看全部 →':'View all →','最近压缩任务':'Gate tasks at a glance','进行中/其他':'running/other',
'日志（已脱敏）':'Logs (redacted)','点击内容可放大查看':'click log contents to open a large viewer','服务日志 service.log':'Service log service.log','指标日志 metrics.jsonl':'Metrics log metrics.jsonl',
'交代目标，持续执行，查看成果后验收。':'State a goal, keep it running, then review and accept the outcome.',
'分工mod':'Role mode','角色':'Role','决策':'Decision','执行':'Execution','关闭':'Off','分工mod · 决策 / 执行 / 自动交接':'Role mode · Decision / Execution / Auto handoff','启用后，上下文压缩将自动交接到同平台新会话，保留方案、修改与验证结果。Codex：6.1 Sol high；Claude：Sonnet high；ZCode：原生模型。':'When context is compacted, hand off on the same platform, preserving the plan, changes and verification. Codex: 6.1 Sol high; Claude: Sonnet high; ZCode: native model.','多代理':'Subagents','动态工作流':'Dynamic workflows','原生（无推理档）':'Native (no effort control)','项目':'Project','执行平台':'Execution platform','思考档位':'Reasoning effort','low（最快）':'low (fastest)','medium（默认）':'medium (default)','max（最慢）':'max (slowest)',
'想用别的项目文件夹？在这里粘贴完整路径，如 /path/to/your-project':'Want a different project folder? Paste its full path here, e.g. /path/to/your-project','添加文件夹':'Add folder',
'任务目标':'Goal','需要完成什么':'What should be done','完成标准':'Acceptance criteria','完成标准（选填）':'Acceptance criteria (optional)','快捷填写':'Quick fill','怎样确认结果符合要求':'How to verify the result is acceptable','完成后运行项目测试':'Run the project’s tests as verification',
'计费明细':'Billing details','选择平台，查看模型与请求记录':'Choose a platform to see models and request records','查看明细':'View details','开始任务':'Start task','派发任务':'Dispatch task','刷新进度':'Refresh progress','检查项目':'Check project','审查修改':'Review changes','生成交接':'Write handoff',
'我的常用任务':'My saved tasks','保存目标、完成标准、项目和平台；点名称填回上方，确认后派发。':'Saves goal, acceptance criteria, project and platform. Click a name to refill the form above, then dispatch.',
'给当前任务起个名字':'Name this task','保存当前任务':'Save current task',
'任务与成果':'Tasks & Outcomes','预约执行':'Scheduled runs','使用上方当前填写的任务创建一次预约。关闭窗口后仍执行；电脑睡眠或关机时不会执行，迟到超过10分钟会标为已错过。项目忙或派发状态不确定时保留记录，不自动重派。':'Creates one scheduled run from the task form above. It runs even with this window closed; it will NOT run while the Mac is asleep or off, and runs more than 10 minutes late are marked missed. If the project is busy or dispatch status is uncertain the record is kept and not re-dispatched automatically.',
'开始时间':'Start at','预约当前任务':'Schedule this task','开启完成通知':'Enable done-notifications',
'用量提醒':'Usage alerts','用量达到门槛时提醒，不自动停止。Claude 按本次任务计算；Codex 按整个会话累计，接续任务会包含之前的用量。':'Based on input/output tokens already reported by native logs, cache input included. Claude counts per task; Codex counts the native session cumulatively (resumed sessions include history). You get a notice at the threshold and can stop from the task card; tasks are never stopped automatically. Spend shows the platform-reported value only.',
'启用提醒':'Enable alerts','提醒门槛（token）':'Threshold (tokens)','保存提醒设置':'Save alert settings',
'成果库':'Outcome library','集中查看任务与群聊回合的归档文件，保留来源和执行状态。群聊完成不等于验收通过。文字最多8MB并分页；PNG、JPEG、GIF、WebP图片最多2MB。':'Browse archived files from tasks and group-chat rounds in one place, with source and execution status. A finished group-chat round is not the same as an accepted outcome. Text up to 8 MB, paginated; PNG/JPEG/GIF/WebP images up to 2 MB.',
'全部项目':'All projects','搜索文件或任务':'Search files or tasks','文件名、目标或任务编号':'File name, goal, or task ID','上一页':'Previous','下一页':'Next',
'版本对比':'Version compare','选择同一项目的两份归档方案、报告或图片。文字每份最多128KB；PNG、JPEG、GIF、WebP图片每份最多2MB。':'Pick two archived plans, reports or images from the same project. Up to 128 KB of text each; PNG/JPEG/GIF/WebP images up to 2 MB each.',
'左侧任务':'Left task','左侧成果':'Left file','右侧任务':'Right task','右侧成果':'Right file','并排查看':'Compare side by side',
'连接检查':'Connectivity check','一键查故障':'Run diagnostics','检查执行入口及本地连接，最近的真实执行结果用于区分登录、模型和网页问题。':'Checks the execution entry points and local connections; the latest real run results distinguish login, model and web issues.',
'关闭':'Close','重试':'Retry','项目文件夹完整路径':'Full project folder path','展开日志':'Expand log','用量趋势：方向键选择日期，回车查看请求':'Usage trend: use arrow keys to select a date, Enter to view requests','取消':'Cancel','确定':'OK','确认':'Confirm',
'成功':'Success','失败':'Failed','已准备':'Prepared','已阻断':'Blocked',
'在线':'Online','离线':'Offline','已停止':'Stopped',
'运行中':'Running','已中断':'Interrupted','后台未结束':'Still running in background','已拦截':'Declined',
'含已核实账单':'Includes verified provider charges',
'暂无请求':'No requests yet','暂无任务':'No tasks yet','暂无数据':'No data','暂无记录':'No entries','暂无':'None','个模型':' models','轮':' turns','原消耗（推算）':'Original usage (extrapolated)','压缩节省':'Compression savings','无实测对照':'No measured A/B','实际消耗':'Actual usage','其中缓存读':'of which cache reads','未配置价格，未计金额':'unpriced model — not counted in spend',
'平台总览':'Platform overview','平台总览 · 点击方块查看该平台用过的模型':'Platform overview · click a tile for the models it used','实际消耗（全平台合计）':'Actual usage (all platforms)','口径':'Method','$0：免费 key / 本地部署 / :free':'$0: free keys / local deployments / :free tiers',
'免费模型（NVIDIA 免费 key / 本地部署 / :free 档，$0）':'Free models (NVIDIA free keys / local deployments / :free tiers, $0)',
'免费模型（含 Local Model Router，$0）':'Free models (including Local Model Router, $0)',
'该模型没有请求记录':'No requests for this model','正在加载该模型的请求…':'Loading this model’s requests…',
'条请求的模型未配置价格，未计金额':' request(s) used unpriced models — not counted in spend',
'服务已重启，连接令牌已更新，刷新无效。':'The service restarted and the connection token changed; refreshing won’t help.',
'连不上本地数据服务，服务可能已重启或停止。':'Can’t reach the local data service — it may have restarted or stopped.',
'读取统计数据失败：':'Failed to load stats: ','正在自动重连新连接…':'Reconnecting to the new connection automatically…','请按 ':'Please press ',' 重新打开控制台（浏览器页签请关闭后重开）。':' to reopen the console (close and reopen the browser tab).',
'平台':'platforms','估算花费':'Actual spend','用量':'Usage','切换计费 / 用量':'Switch billing / usage','各平台 token 用量（输入 + 输出）；点平台方块下钻到模型明细。':'Token usage per platform (input + output). Click a platform tile to drill into its models.','对照测试节省':'A/B savings','暂无花费记录':'No spend recorded','暂无免费模型记录':'No free-model usage yet','暂无模型记录':'No model usage yet','未知模型':'未知模型',
'价格为 ':'Prices come from ',' 里的市场价参考（$ / 每百万 tokens），编辑后点「刷新」生效。':' as reference market prices ($ / million tokens); edit the file then click “Refresh” to apply.',
'；相关请求计入 tokens 但不计入金额。':'; their requests count in tokens but not in spend.','当前全部模型已配置价格。':'Every model currently has a price configured.',
' 「实测对照」= 同一个任务不开压缩直发 vs 走 Gate 各真实跑一遍的成对 A/B，每对记 1 组，只有这些组有真实节省。':' “Measured A/B” = the same task run both with and without the Gate as a real pair; only those pairs represent real savings.',
'总任务':'total tasks','已完成':'done','筛选显示 ':'shown after filtering','无匹配任务':'No matching tasks','暂无压缩任务':'No Gate tasks yet',
'刚刚':'just now',' 分钟前':' min ago',' 小时前':' h ago','仍在运行':'still running','结束 ':'ended ','开始 ':'started ','退出码 ':'exit code ','输出文件 ':'Output file ','复用Pack':'Pack reuse','逐轮':'per-turn','强制':'forced',
'任务描述':'Task description','处理方式 ':'Handling: ','已筛选':'filtered','小任务跳过':'skipped as small','筛选失败回退':'filter failed, fell back to full pack','模式 ':'Mode ',
'上下文打包：原样 → Pack 后':'Context pack: raw → packed','包内容估价':'Estimated cost of packed content','上下文打包估算：任务上下文原样 → Pack 后（字符法估算，只有走 Gate 的任务有）。负数表示打包后更大；小任务跳过或审核失败回退都可能发生。此处不含原生会话启动及后续工作，不能据此判断实际费用。':'Context-pack estimate: the task context raw → after packing (character-count estimate; only exists for tasks through the Gate). A negative number means packing made it bigger; small-task skips and filter-failure fallbacks both happen. This excludes native-session startup and follow-up work — don’t read it as the actual cost.',
'仅按打包内容及本地价表估算，未包括原生会话说明、工具、后续输入和输出；不是完整任务费用。':'Estimated from the packed content and local price table only; excludes native-session preamble, tools, and later input/output. Not the full task cost.',
'类型':'Type','执行内容':'What ran','点击任意一行查看该步的完整原始日志（超长任务仅保留尾部）。':'Click any row to see that step’s full raw log (very long logs keep only the tail).',
'端点':'Endpoint','压缩前':'Before','压缩后':'After','管理移除':'Removed by manager','上游':'Upstream','逐轮网关事件；点击查看单轮完整日志。':'Per-turn gateway events; click for a single turn’s full log.',
'运行中——执行日志在任务结束后可用。':'Running — the execution log becomes available after the task finishes.','无逐轮执行记录。':'No per-turn execution records.',
'输出文件内容 · ':'Output file · ','（超过 1MB，仅显示尾部）':' (over 1 MB; tail only)','读取失败：':'Failed to read: ','（/tmp 文件可能已被清理）':' (the /tmp file may have been cleaned up)','第 ':'Step ',' 步执行日志':' execution log','网关事件':'Gateway event',
'点击查看这条请求的详细日志':'Click to open this request’s detailed log','仅显示最近 50 条，共 ':'Showing the latest 50 of ',' 条':' entries',
'索引状态':'Index status','最近交接':'Last handoff','做了什么':'Done','当前状态':'Current state','下一步':'Next step',
'共享 Memory OS 尚无项目进度':'No project progress in shared Memory OS yet','个项目':' projects','（其中 ':' (',' 个来自本机登记，共享 Memory OS 暂无进度）':' registered locally; no shared Memory OS progress yet)','收起，只显示最近 3 个':'Collapse to the latest 3','展开全部 ':'Expand all ','共享 Memory OS + 本机登记 · ':'Shared Memory OS + local registry · ','本机登记 · 暂无共享进度':'Registered locally · no shared progress yet',
'本机登记':'Registered locally','本机登记项目':'Registered locally','本机已登记，共享 Memory OS 暂无该项目进度':'Registered on this Mac; shared Memory OS has no progress for it yet',
'是':'Yes','否':'No',' 个文件 · 「含密钥」只报是/否，永不显示内容':' files · “contains key” reports yes/no only, never contents',' 项需要处理':' need(s) attention',
'请求日志 · ':'Request log · ','这一天没有请求记录。':'No requests recorded that day.','缓存命中率 ':'cache hit rate ','%（口径=缓存读/实测输入）':'% (cache reads / measured input)','当前为命中率视图，列表口径相同':'hit-rate view; the list uses the same measure','命中率':'Hit rate','详情':'Detail',
'仅显示最近 300 条，共 ':'Showing the latest 300 of ','条请求 · ':' requests · ','点击任意一行查看该请求的已存账本明细、耗时分段与可关联日志。':'Click any row for the saved ledger detail, timing breakdown and linked logs for that request.',
'账本较大，统计需要几秒，仍在读取…':'The ledger is large; stats take a few seconds — still loading…',
'请求详情 · ':'Request detail · ','‹ 返回当天列表':'‹ Back to that day’s list','记录 ID':'Record ID','平台 / 模型':'Platform / model','供应商实测':'Provider-reported','缓存写入':'Cache write','耗时':'Duration',
'打包估算（仅经 Gate 的请求，字符法估算）':'Pack estimate (Gate-only requests, character-count method)','估算 前 → 后':'Estimate before → after','估算节省':'Estimated savings',
'耗时分段（request_timings，未记录处显示 –）':'Timing breakdown (request_timings; “–” = not recorded)','准备':'Prepare','上游响应头':'Upstream headers','首字节':'First byte','上游总耗时':'Upstream total','端到端':'End-to-end','上游状态':'Upstream status','流式完整':'Stream complete',
'该请求没有已保存的耗时分段记录。':'No saved timing breakdown for this request.','可关联日志 · ':'Linked logs · ','保存字段原文（JSON，已脱敏）':'Saved fields, raw (JSON, redacted)','无输入':'no input','命中率 ':'hit rate ',
'已发起打开':'Open request sent','打开失败':'Failed to open','打开失败：':'Failed to open: ','至少需要 ⌃ 或 ⌘ 修饰键，避免占用裸字母键':'Needs at least ⌃ or ⌘ as a modifier, so plain letter keys stay free','已保存，壳 App 几秒内自动生效。':'Saved — the shell app picks it up within seconds.','保存失败：':'Save failed: ',
'当前筛选：':'Filtered: ','分类：':'Category: ','时间：':'Time: ',
'正在查询…':'Searching…','查询失败':'Query failed','找到 ':'Found ',' 条 · ':' results · ','有 ':' has ',' 项读取提示（见下方折叠区）':' read notices (see the collapsed section below)','项读取提示（点击展开）':' read notices (click to expand)','搜索失败：':'Search failed: ','点击收起/展开':'click to collapse/expand','找到 0 条 · ':'Found 0 results · ',
'本次任务用量：':'Usage for this task: ','平台尚未报告。':'not yet reported by the platform.','用量提醒：已达到 ':'Usage alert: reached the ',' token 门槛。':'-token threshold.','原生会话累计报告（含接续历史）':'native session cumulative report (resumed history included)','本次任务已报告':'reported for this task','目前已报告':'reported so far',' token · 输入 ':' tokens · input ',' / 输出 ':' / output ',' · 缓存读取 ':' · cache read ',' / 写入 ':' / write ','金额未报告':'spend not reported','平台报告 $':'platform-reported $',
'准备执行':'Preparing','待验收':'Awaiting review','验收通过':'Accepted','执行失败':'Failed','意外中断':'Interrupted','验证失败':'Validation failed',
'服务已重启，连接令牌已更新，本次操作没有生效。':'The service restarted and the connection token changed; this action didn’t take effect.','服务已重启，请按横幅提示重开控制台':'The service restarted — reopen the console as the banner suggests','操作失败':'Action failed',
'项目文件夹已添加并选中。':'Folder added and selected.',
'等待预约时间':'Waiting for the scheduled time','正在派发':'Dispatching','已派发':'Dispatched','已取消':'Cancelled','已错过':'Missed','派发状态待核对':'Dispatch status to be confirmed','派发失败':'Dispatch failed',
'预约任务有成果，等待验收。':'The scheduled task produced results, awaiting your review.','预约任务状态：':'Scheduled task status: ','预约任务有新结果':'Scheduled task has new results','任务编号 ':'Task ID ','；进度、停止和成果见任务卡片。':' — progress, stop and outcomes live on the task card.','请选择开始时间':'Pick a start time','预约已保存。':'Schedule saved.','预约已取消。':'Schedule cancelled.','当前浏览器不支持桌面通知':'This browser doesn’t support desktop notifications','已开启本窗口在线期间的完成通知。':'Done-notifications are on while this window stays open.','通知未开启；状态仍在预约列表显示。':'Notifications are off; status still shows in the schedule list.','没有预约任务。':'No scheduled tasks.',
'尚未派发任务。输入目标后开始。':'No tasks dispatched yet. Enter a goal to start.','查看成果':'View outcome','查看修改':'View changes','接续任务':'Continue task','确认验收通过':'Accept outcome','撤回修改':'Roll back changes','停止':'Stop',
'任务已派发，关闭窗口后继续执行。':'Task dispatched — it keeps running after this window closes.',
'事实分类：':'Fact category: ',
'共 ':'Total ',' 个归档文件':' archived files',' · 当前 ':' · showing ','–':'–',' · 外部产出 ':' · external outcomes ','没有匹配的归档文件。':'No matching archived files.','群聊回合':'group-chat round','Gate 任务产出（未归档，来自压缩任务注册表）':'Gate task outputs (not archived, from the compression-task registry)','(无任务描述)':'(no task description)','预览归档':'Preview archive','预览产出':'Preview output','预览 ':'Preview ','群聊修改 · ':'Group-chat edit · ',
'成果 · ':'Outcome · ','已归档文件 · ':'Archived file · ','字符位置 ':'Character offset ',' / ':' / ','上一页':'Previous','图片无法解码，请核对归档文件。':'The image can’t be decoded — check the archived file.','成果读取失败':'Failed to read outcome','外部产出 · ':'External output · ',
'还没有保存常用任务。':'No saved tasks yet.','移除':'Remove','已保存。':'Saved.','已移除常用任务。':'Saved task removed.','已填入 ':'Loaded ','，可调整后派发。':' — adjust it if needed, then dispatch.',
'两份内容完全一致。':'The two files are identical.','两份内容有变化。':'The two files differ.','左侧':'Left','右侧':'Right','已读取两份完整归档成果。':'Both archived outcomes fully loaded.',
'确认撤回':'Confirm rollback','已展示执行期间的修改。确认撤回？存在后续修改时会停止。':'The changes made during the run are shown above. Roll back? If anything was modified afterwards, the rollback stops.','补充接续目标':'Follow-up goal','接续目标…':'Follow-up goal…',
'修改记录':'Change record',' · 有后续修改':' · modified again afterwards',
'(项目列表加载中，请稍后重开)':'(project list still loading — reopen in a moment)','没有想要的文件夹？在这里粘贴完整路径':'Folder missing? Paste its full path here','交代管家':'Tell the butler','例如：读取 TODO.md，告诉我还有哪些任务没完成':'e.g. read TODO.md and tell me which tasks are still open','交给管家':'Send to butler','当前在群聊视图：交代会自动带上这个群组，管家可直接查询和给成员派话。':'You’re in a group-chat view: the request carries this group along, so the butler can query it and message members directly.','NVIDIA NIM · moonshotai/kimi-k3；需要网络。关掉窗口任务仍执行，重开这里看结果。':'NVIDIA NIM · moonshotai/kimi-k3; needs network. The task keeps running after the window closes — reopen this to see the result.',
'管家正在处理，已执行动作会保留。':'The butler is working; actions already taken are kept.','管家已返回结果':'The butler has replied','管家本轮无法继续：':'The butler couldn’t continue this round: ','供应商':'Provider','NVIDIA NIM（复用 ZCode 密钥）':'NVIDIA NIM (reuses the ZCode key)','OpenRouter（复用 ZCode 密钥）':'OpenRouter (reuses the ZCode key)','本地 Ollama（Qwen 14B）':'Local Ollama (Qwen 14B)','自定义（OpenAI 协议）':'Custom (OpenAI-compatible)','模型名':'Model name','如 moonshotai/kimi-k3':'e.g. moonshotai/kimi-k3','接口地址（仅自定义供应商需要）':'API base URL (custom provider only)','API 密钥（留空=沿用已配置或 ZCode 配置）':'API key (leave empty to keep the configured one or reuse ZCode’s)','已配置（不显示）':'Configured (hidden)','未配置':'Not configured','改完下一轮管家生效；NVIDIA/OpenRouter 留空密钥时自动复用 ZCode 里配置的密钥。':'Applies from the butler’s next round. With NVIDIA/OpenRouter and an empty key, the key configured in ZCode is reused automatically.','保存':'Save','（密钥已配置）':' (key configured)','当前：':'Current: ',
'移除 ':'Remove ',
'等待消息':'Waiting','排队中':'Queued','停止中':'Stopping','已移出':'Removed',
'选择群聊':'Pick a group','新建群聊':'New group','改名/换项目':'Rename / re-project','＋ 添加成员':'＋ Add member','换模型':'Change model','移出成员':'Remove member',
'输入 @ 指定成员，不带 @ 发给全群。点击成员查看工作详情。':'Type @ to address one member; without @ it goes to the whole group. Click a member to see their work.',
'成员与进度':'Members & progress','群内简报':'Group briefing','未读消息':'unread messages','无未读消息':'no unread messages','群聊消息':'Group message','输入 @ 指定成员；不指定则发给所有成员。输入 / 查看命令。':'Type @ to address a member; leave it out to send to everyone. Type / for commands.','发给全部成员':'To all members','发送':'Send','成员聊天':'Member chat','打开原平台':'Open in native app','原平台历史':'Native history','放大':'Widen','还原':'Restore','直接给选中的成员发消息':'Message the selected member directly','同一原生聊天继续':'Continues the same native chat','发送给成员':'Send to member','继续加载历史':'Load more history',
'这个框只发给点选的成员——先在左侧成员列表点一个成员；群消息请到「群内简报」发送':'This box only messages the member you pick — click one in the member list first; send group messages from “Group briefing”',
'成员列表':'Members','并排':'Side by side','单栏':'Single pane','并排时同时显示群内简报和成员聊天':'Side by side shows the group briefing and the member chat together','窗口不够宽，放不下两栏：把窗口拉宽，或先收起左侧成员栏。':'Not enough room for two panes — widen the window or collapse the member list first.','收起/展开成员栏':'Collapse / expand member list',
'成员':'Member','群名':'Group name','改名 / 换项目':'Rename / re-project','添加成员':'Add member','成员名':'Member name','例如 reviewer':'e.g. reviewer','ZCode · 基础版（能接续会话，暂不能跨发消息）':'ZCode · basic (can resume sessions; no cross-messaging yet)','推理档':'Reasoning effort','⚡ 快速（额外推理选项，勾选时不用档位）':'⚡ Fast (extra reasoning option; ignores the effort tier when checked)','同一聊天换模型':'Change model in this chat','本轮继续使用当前模型，下一轮在同一聊天应用。':'This round keeps the current model; the change applies to the next round in the same chat.','移出成员，保留历史':'Remove members, keep history','终止所选成员的工作并移出群聊。聊天记录保留。':'Stops the selected members’ work and removes them from the group. Chat history is kept.',
'先新建群聊':'Create a group first','进入':'Enter','恢复':'Restore','归档所选（':'Archive selected (','删除所选（':'Delete selected (','还没有群聊':'No groups yet','已归档（从列表隐藏，可恢复）':'Archived (hidden from the list, restorable)',
'删除群聊':'Delete groups','确认删除所选 ':'Delete the ',' 个群聊？成员、消息与任务记录将一并删除，不可恢复。':' selected group(s)? Members, messages and task records go too — this can’t be undone.','归档群聊':'Archive groups','确认归档所选 ':'Archive the ',' 个群聊？归档后从列表隐藏（记录保留），下拉底部可恢复。':' selected group(s)? They hide from the list (records kept) and can be restored at the bottom of this menu.','已请求打开 ':'Requested to open ',' 原 App 的同一聊天。':'’s native app with the same chat.','原平台聊天记录':'Native chat history',' · 本页位置 ':' · offset in this page ','共 ':'total ','工具与结果':'Tools & results',
'移出成员，终止工作并保留历史':'/delete — remove members, stop their work, keep history','在同一聊天换模型':'/model — change model in this chat','消息此前已登记，已确认原请求；没有重复派发。':'This message was already registered; the original request is confirmed — nothing was dispatched twice.','消息已登记，成功接收后成员会确认。':'Message registered; members will confirm once it’s received.','；同内容重试会核对原请求。':' Retrying with identical content verifies against the original request.','选择后再次点停止。未选择时双击停止全部。':'Select members, then press stop again. With nothing selected, double-click stops everyone.','请选择成员；未选择时双击停止全部。':'Pick members first; with nothing selected, double-click stops everyone.','成员指令：/model 在同一聊天换模型；/stop 停止此成员；其余原生指令请点“打开原平台”使用。':'Member commands: /model changes the model in this chat; /stop stops this member; use other native commands via “Open in native app”.','此原生指令请在“打开原平台”中使用，避免当普通消息发送。':'That’s a native command — use it via “Open in native app” instead of sending it as a message.',
'你':'You','系统':'System','已移出成员':'removed member','消息会保存在这里。':'Messages will be kept here.','添加一个成员，开始交代任务。':'Add a member to start assigning tasks.','原生会话 ':'Native session ','发送第一条消息后建立原生会话':'A native session is created after the first message','最近实际模型：':'Latest actual model: ','。原 App 下拉框的默认选择可能不同。':'. The native app’s own picker may default differently.',
'文件处理':'Files','导入文字或表格，整理结构并查看内容。':'Import text or spreadsheets, tidy the structure and read the contents.',
'拖文件到这里，或点击选择':'Drop files here, or click to choose','TXT、Markdown、CSV、TSV、JSON、DOCX、XLSX、PDF · 每份最多512KB':'TXT, Markdown, CSV, TSV, JSON, DOCX, XLSX, PDF · up to 512 KB each',
'选择或拖入文件':'Choose or drop a file','原件保存在本机导入库；结构整理不调用模型。文字文件需UTF-8；Word/Excel支持DOCX/XLSX，PDF提取文字，尚不支持OCR；旧版DOC/XLS暂未支持。':'Originals are kept in the local import library; structure tidying never calls a model. Text files must be UTF-8. Word/Excel support DOCX/XLSX; PDF is text-extracted, no OCR yet; legacy DOC/XLS not supported.',
'已导入文件':'Imported files','删除此文件':'Delete this file','删除导入文件':'Delete imported file','确认删除':'Delete','已删除导入文件：':'Imported files deleted: ',' 份。':'.','将从本机导入库删除以下文件的保存副本和记录，删除后无法恢复：':'This removes the saved copies and records of these files from the local import library and cannot be undone:','多选':'Select','全选':'Select all','取消多选':'Cancel selection','全不选':'Select none','删除所选':'Delete selected','你电脑上的原始文件不受影响。':'The original file on your computer is not affected.','对比导入文件':'Compare imported files','并排对比':'Compare side by side','按行位置比较内容；表格可查看不同的单元格数量。黄色标出对应位置的表格变化；左右独立分页。':'Compares content by line position; spreadsheets also show how many cells differ. Yellow marks table changes at matching positions; each side pages independently.',
'导入文件对比':'Import comparison','比较提取后的文字与单元格记录，不比较排版、图表等未提取内容。':'Compares the extracted text and cell records, not layout, charts or anything else that isn’t extracted.',
'两份原件完全一致。':'The two originals are identical.','原件不同，整理后的内容一致。':'The originals differ but the tidied content matches.','两份内容不同。':'The two contents differ.','按':'Compared by ','表格行':'table rows','文本行':'text lines','位置比较：':'position: ',' 处行内容不同':' row(s) differ',' 处单元格不同':' cell(s) differ','左侧':'Left','右侧':'Right','行':'row','字符':'chars','尚未导入文件。':'Nothing imported yet.','正在导入…':'Importing…','已保存原件并整理结构。':'Original saved and structure tidied.','文件每份最多512KB。':'Each file is limited to 512 KB.','请一次导入一个文件。':'Import one file at a time.','行宽度不同':'rows with differing widths',' 个空单元格':' empty cells',' 页 · ':' pages · ',' 字符 · ':' chars · ',' 页没有可提取文字':' pages with no extractable text',' 个正文段落 · ':' body paragraphs · ',' 个表格 · ':' tables · ','JSON ':'JSON ',' 项':' items',' 行 · ':' rows · ',' 个标题':' headings','上方列出前20个标题；完整内容见下方分页。':'Only the first 20 headings are listed; the full text follows in the paginated view.','工作表：':'Sheets: ',' 个已存单元格 · ':' stored cells · ',' 个公式 · ':' formulas · ',' 个公式缺少保存结果':' formulas lack saved results','当前':'At ','位置 ':'offset ',' · 原件摘要 ':' · original checksum ',
'记忆':'Memory','按主题查找共享记忆，中文要点、完整正文和原文依据放在一起。':'Find shared memory by topic, with plain-language summaries, full text and source quotes together.',
'搜索记忆':'Search memory','标题、内容、项目或关键词':'Titles, contents, projects, or keywords','同步记忆':'Sync memory','打开文档文件夹':'Open documents folder','总览':'Overview','目录':'Directory','大纲':'Outline','详细':'Detail','减小文字':'Smaller text','增大文字':'Larger text',
'导出记忆':'Export memory','1. 全文合并':'1. Full-text merge','全部阅读文档合成一个文件，并附完整原始快照。含归档或到期记录。':'All reading documents merged into one file, with the complete raw snapshot attached. Archived and expired records included.','TXT 文本':'TXT text','导出全文':'Export full text','2. 人话版 ZIP':'2. Plain-language ZIP','保留目录、大纲、详细文档、历史生成和原始依据，以及文件夹结构。':'Keeps the directory, outline, detail documents, history and raw evidence, plus the folder structure.','导出人话版':'Export plain-language ZIP','3. 原始版 ZIP':'3. Raw ZIP','保留原始记录文件夹及全部内容，含归档或到期记录。':'Keeps the raw record folder and everything in it, archived and expired records included.','导出原始版':'Export raw ZIP',
'点击后现场生成，保存到文档文件夹中的“导出”，并在访达显示。同步时不会制作导出文件。':'Exports are generated on the spot, saved under “导出” in the documents folder and revealed in Finder. Syncing never builds exports.',
'进入记忆页后读取本地文档。':'Opens the local documents when you enter the Memory view.',
'同步中…':'Syncing…','重试同步':'Retry sync','文档更新于 ':'documents updated ','本地文档 · 更新于 ':'Local documents · updated ','每 30 分钟自动同步':'auto-syncs every 30 minutes','点击“同步记忆”生成完整阅读文档。':'Click “Sync memory” to build the full reading documents.','读取记忆失败：':'Failed to read memory: ','。请重试刷新。':' Retry or refresh.',
'权重 ':'weight ',' · 已固定':' · pinned','置信度 ':'confidence ','置信度定于 ':'confidence set ','有效期至 ':'valid until ','⚠︎ 置信度已过期，建议重新核实':'⚠︎ Confidence has lapsed — worth re-verifying','这条记录没有正文，可展开查看原始记录。':'This entry has no body; expand the raw record instead.','版':'v','时间待核对':'time unverified','记录中的完整正文':'Full body from the record','原文依据（':'Source quotes (',' 段）':' excerpts）','原始记录（凭据已隐藏）':'Raw record (credentials hidden)','查看原文与依据 →':'Open the record with its sources →',
'当前记忆':'current memories','主题':'topics','归档或到期（原始快照保留）':'archived or expired (raw snapshots kept)','从一个主题开始':'Start with a topic',' 条':' items','阅读主题 →':'Read this topic →','中文要点逐条整理，完整原文始终保留。主题和条目随文档同步更新。':'Plain-language summaries item by item, with the full original text always kept. Topics and entries follow each document sync.',
' 条记忆':' memories','选择一条记忆，查看完整内容。':'Pick an entry to read it in full.','没有找到相关记忆':'No matching memories','试试更短的关键词，或清空搜索查看全部。':'Try shorter keywords, or clear the search to see everything.','还没有可读取的记忆文档。点击“同步记忆”生成。':'No readable memory documents yet. Click “Sync memory” to build them.',
'已打开文档文件夹，可查看目录、大纲和详细文档。':'Documents folder opened — browse the directory, outline and detail documents.','正在整理完整文档…':'Assembling the full documents…','已生成 ':'Generated ','，已在访达显示。':' — revealed in Finder.','。请用“打开文档文件夹”进入“导出”查看。':' Use “Open documents folder” and look inside “导出”.','正在启动同步…':'Starting sync…','同步正在进行，完成后自动更新。':'A sync is already running; it will update automatically when done.','同步未能启动。请检查 Memory OS 安装位置后重试。':'Sync couldn’t start. Check where Memory OS is installed and retry.','正在读取记忆库，生成完整中文文档…':'Reading the memory store and building the full documents…','同步完成，完整文档已更新。':'Sync complete — the full documents are updated.','另一处正在同步，完成后会自动更新。':'Another sync is in progress elsewhere; this view updates when it finishes.','同步失败，上次完整内容已保留。请重试，或查看 MemoryOS 同步日志。':'Sync failed; the last full content is kept. Retry, or check the MemoryOS sync log.','共享 Memory OS 不可用：':'Shared Memory OS unavailable: ',
'导入文件读取失败，请核对原件与翻页位置':'Failed to read the import — check the original and the page offset','无法读取群聊':'Failed to read group chats','原生历史读取失败':'Failed to read native history','常用任务读取失败':'Failed to read saved tasks','提醒设置读取失败':'Failed to read alert settings','预约读取失败':'Failed to read schedules','无法读取任务记录':'Failed to read task records','没有这条请求记录':'No such request record','记录已刷新，请重新搜索':'Records were refreshed — search again','搜索读取失败或查询无效':'Search failed or the query is invalid','未知群聊操作':'Unknown group action','未知操作':'Unknown action','撤回前需确认修改详情':'Review the change details before rolling back','未知供应商':'Unknown provider','自定义供应商需要 http 接口地址与模型名':'A custom provider needs an http base URL and a model name','未知的 App':'Unknown app','文档文件夹尚未生成，请先同步记忆。':'The documents folder doesn’t exist yet — sync memory first.','文件夹未能打开，请重试。':'The folder couldn’t be opened — try again.','导出失败，请检查文档文件夹后重试。':'Export failed — check the documents folder and retry.','快捷键需要一个字母/数字，且至少带 ⌃ 或 ⌘':'The hotkey needs a letter/digit plus at least ⌃ or ⌘','缺少 API 密钥（系统设置里补全，或留空以复用 ZCode 配置）':'Missing API key (add it in settings, or leave empty to reuse the ZCode configuration)','本地 Ollama':'Local Ollama','自定义':'Custom','默认':'default','权限过宽':'permissions too open','拖拽调整面板大小（边角均可拖）':'Drag to resize the panel (edges and corners)',
' —— 下面所有数字只统计该范围；要看累计请切回「全部时间」。':' — all numbers below count this range only; switch back to “All time” for cumulative totals.',
' 列 · ':' columns · ',' 字符':' chars',' 行 · 最多 ':' rows · up to ',' 行宽度不同 · ':' rows with uneven widths · ',
' 项读取提示（点击展开）':' read notices (click to expand)','· 强制':'· forced','· 有后续修改':'· changed again afterwards',
'任务 · ':'Task · ','免费':'Free','写入 ':'write ','原件摘要 ':'original checksum ','发给指定成员':'To one member',
'取消预约':'Cancel','同一任务分别使用和不使用压缩，运行后才计算节省。':'Only tasks actually run both with and without the Gate (measured A/B) represent real savings',
'同步未能启动：':'Sync couldn’t start: ','外部产出 ':'external outcomes: ','失败 ':'failed ','实测 ':'measured ',
'尚无最终答复，任务仍可能执行中。':'No final reply yet — the task may still be running.','工具执行':'Tool run',
'已准备 ':'prepared ','已阻断 ':'blocked ','当前 ':'showing ','当前群组ID：':'Current group ID: ',
'当前：读取失败':'Current: failed to load','执行中':'Running','找到 0 条':'Found 0 results',
'选择其他文件夹…':'Choose another folder…','附件':'Attach','选择文件超时，请重试':'File selection timed out. Try again.','没能打开文件选择框，请把文件拖进输入框':'Could not open the file picker. Drag files into the input instead.','读取失败':'could not be read','添加图片或文件（也可以拖进来或粘贴）':'Add images or files (drag in or paste also works)','移除':'Remove','附件每份最多8MB':'Attachments are limited to 8 MB each','附件还在上传，请稍候':'Attachments are still uploading. Please wait.','请查看附件。':'Please see the attachments.','附件（已保存在项目内，可按路径直接读取）：':'Attachments (saved in the project; read them by path):','松开即可添加附件':'Drop to attach','附件无效':'Invalid attachment','附件名称无效':'Invalid attachment name','文件名含敏感字样（密钥/凭据等），不允许附加':'File name looks sensitive (keys/credentials); not attached','附件内容无效':'Invalid attachment content','附件每份需在1字节至8MB之间':'Each attachment must be between 1 byte and 8 MB','附件目录不在项目内，已拒绝写入':'Attachment folder is outside the project; write refused','选择项目文件夹':'Choose project folder','选择文件夹超时，请重试':'Folder selection timed out. Try again.','没能打开文件夹选择框，请重试或稍后再试':'Could not open the folder picker. Try again or come back later.','换项目后下一轮生效；已有原生会话会带着原项目的上下文继续，建议重要群聊保持项目不变。':'Applies from the next round; an existing native session continues with the previous project’s context — keep important groups on the same project.',
'暂无对照':'no A/B yet','未配置价格的模型：':'Unpriced models: ','本页位置 ':'offset ','筛选中：':'Filtered: ',
'缓存 ':'cache ','缓存读取 ':'cache read ','群聊 · ':'Group · ','计时请求数 ':'timed requests ',
'读取失败':'Failed to read','输入 ':'input ','输出 ':'output ','进行中':'Running','进行中 ':'running ','Memory OS 返回范围受限，部分项目状态可能未包含':'Memory OS returned a limited scope; some project status may be missing.','执行期间符合备份规则的文件变化；不代表每处变化均由模型写入。排除秘密文件、依赖/工作目录、符号链接及超过10MiB的文件。':'Changes to files covered by the backup rules during the run; not every change was necessarily written by the model. Secret files, dependency/work directories, symlinks and files over 10 MiB are excluded.',' · 已归档 ':' · archived ',' 个文件，见成果库':' files; see the outcome library','shell 配置（Anthropic key）':'shell config (Anthropic key)','Claude Code 设置（env 指向哨兵）':'Claude Code settings (env points at the sentinel)','ZCode App 供应商配置（含 apiKey）':'ZCode app provider config (contains apiKey)','Codex CLI 凭据':'Codex CLI credentials','Gate 服务令牌':'Gate service token','Gate 连接信息':'Gate connection info','控制台连接信息（URL 即凭据）':'Console connection info (the URL is the credential)','ZCode 哨兵脚本':'ZCode sentinel script','ZCode 哨兵连接信息':'ZCode sentinel connection info','Claude 哨兵脚本':'Claude sentinel script','Claude 哨兵连接信息':'Claude sentinel connection info','价格表':'Price table','日志导入器':'Log importer','哨兵(本机)':'sentinel (local)','直连':'direct','执行期间符合备份规则的文件变化；不代表每处变化均由模型写入。排除秘密文件、依赖/工作目录、符号链接及超过10MiB的文件':'Changes to files covered by the backup rules during the run; not every change was necessarily written by the model. Secret files, dependency/work directories, symlinks and files over 10 MiB are excluded.',
'共同交代目标，点开成员查看原生会话的完整执行消息。':'State a shared goal together; open a member to read their native session’s full messages.',
'右侧文件':'Right file','左侧文件':'Left file',
'比较各平台的请求量、用量、花费估算和速度。':'Full comparison table of requests, tokens and measured A/B savings per platform.',
'输出速度':'Output speed','输出速度 ':'Output speed ','中位 ':'median ','中位数':'Median','平均 tokens/s':'Average tokens/s','常见范围（P10–P90）':'Typical range (P10–P90)','测速请求 ':'Timed requests ','输出速度 tok/s':'Output tok/s',
'该模型的请求没有耗时记录，无法计算输出速度。':'No request for this model has a recorded duration, so output speed cannot be calculated.',
'输出 tokens ÷ 请求总耗时（含等待首个 token），只统计有耗时记录的成功请求。':'Output tokens ÷ total request time (including the wait for the first token); only successful requests with a recorded duration count.',
'全文文件格式':'Full-text file format','常用任务名称':'Saved task name','成员消息':'Member message','记忆列表':'Memory list','记忆阅读方式':'Memory reading mode',
};
Object.assign(EN,{"价格模式": "Cost basis", "按付费设置": "Show free", "按官方标价": "Official price", "价格模式：按付费设置": "Cost basis: configured payment settings", "价格模式：按官方标价折算（含免费请求）": "Cost basis: official list price (free requests included)", "免费额度和本地模型按 $0 计算；其余根据价格估算。": "Free quotas / free keys / local deploys / Local Model Router count as $0 (what you actually pay)", "按模型官方标价估算，包含免费请求；缺少价格时只统计用量。": "Every request valued at the model's official list price (free requests included); models without an official price count tokens only", "无官方价": "No official price", "无官方价（未计金额）": "No official price (not counted)", "官方 $0": "Official $0", "官方标价 $0": "Official list price $0", "官方标价 $0 的模型": "Models with an official list price of $0", "按官方标价折算": "At official price", "官方价折算 $": "Official-price $", "无官方价，只计 tokens，未计金额": "No official price — tokens only, not counted in spend", "切换价格模式失败：": "Switching cost basis failed: ", "按各模型官方标价折算（含实际免费的请求）的各平台金额；无官方价的模型只计 tokens。点平台方块下钻到模型明细。": "Per-platform amounts at each model's official list price (free requests included); models without an official price count tokens only. Click a platform tile to drill into its models.", "按官方标价估算：免费请求也按标价计算；缺少价格的模型只统计用量。": "Current basis: official price — requests that were free in practice (free quotas, free keys, Local Model Router…) are valued at the model's official list price; models without an official price count tokens only. ", "按付费设置估算：免费额度、免费密钥和本地模型按 $0 计算。": "Current basis: free shown — free quotas, free keys, local deploys and Local Model Router count as $0. ", "无官方价的模型：": "Models without an official price: "});
Object.assign(EN,{'统计显示已更新，额度正在刷新':'Stats display updated; quota is refreshing','刷新中…':'Refreshing…','正在更新显示…':'Updating the display…','显示已更新 · ':'Display updated · ','连接已失效，请重新打开控制台':'Connection expired; reopen the console','显示部分更新，额度读取失败，请重试':'Display partly updated; quota read failed, try again','更新失败：':'Update failed: ','主导航':'Main navigation','跳到主要内容':'Skip to content','关闭':'Close','重试':'Retry','项目文件夹完整路径':'Full project folder path','展开日志':'Expand log','用量趋势：方向键选择日期，回车查看请求':'Usage trend: use arrow keys to select a date, Enter to view requests'});
const T=s=>LANG==='en'?(EN[s]??s):s;
const Tc=(n,zh,one,many)=>LANG==='en'?(n===1?one:many):zh; // 数字量词：n===1 用单数
// 静态 HTML 文案：英文模式下启动时按词典精确匹配替换文本节点/placeholder/title/aria-label/option。
// 只在启动跑一次，此时动态数据尚未渲染，绝不会碰用户数据；切语言走整页刷新，重跑安全。
function applyStaticLang(){
  document.title=T('Context Gate 控制台');
  document.documentElement.lang=LANG==='en'?'en':'zh-CN';
  try{window.webkit?.messageHandlers?.language?.postMessage(LANG)}catch(e){}
  if(LANG!=='en')return;
  const skip=n=>n.parentElement&&n.parentElement.closest('script,style,pre,#modal-body');
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:n=>(n.nodeValue.trim()&&!skip(n))?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT});
  const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  nodes.forEach(n=>{const v=EN[n.nodeValue.trim()];if(v!==undefined)n.nodeValue=v;});
  document.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el=>{const v=EN[el.getAttribute('placeholder')];if(v!==undefined)el.setAttribute('placeholder',v);});
  document.querySelectorAll('[title]').forEach(el=>{const v=EN[el.getAttribute('title')];if(v!==undefined)el.setAttribute('title',v);});
  document.querySelectorAll('[aria-label]').forEach(el=>{const v=EN[el.getAttribute('aria-label')];if(v!==undefined)el.setAttribute('aria-label',v);});
  document.querySelectorAll('option').forEach(el=>{const v=EN[el.textContent.trim()];if(v!==undefined&&el.textContent.trim())el.textContent=v;});
}
applyStaticLang();
(function(){const sel=document.getElementById('lang-select');if(!sel)return;sel.value=LANG;
  sel.addEventListener('change',()=>{try{localStorage.setItem('cg-lang',sel.value)}catch(e){}try{window.webkit?.messageHandlers?.language?.postMessage(sel.value)}catch(e){}location.reload();});})();
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>(n===null||n===undefined||isNaN(n))?'–':Number(n).toLocaleString(LOCALE());
// compact：k/M/B/T（kilo/million/billion/trillion），<1000 保持原样
const compact=n=>{
  if(n===null||n===undefined||isNaN(n))return '–';
  const a=Math.abs(Number(n));let v,suf;
  if(a>=1e12){v=n/1e12;suf='T';}else if(a>=1e9){v=n/1e9;suf='B';}else if(a>=1e6){v=n/1e6;suf='M';}else if(a>=1e3){v=n/1e3;suf='k';}else return num(n);
  const av=Math.abs(v);
  return (av>=100?v.toFixed(0):av>=10?v.toFixed(1):v.toFixed(2))+suf;
};
const ms=n=>(n===null||n===undefined)?'–':Number(n).toLocaleString(LOCALE(),{maximumFractionDigits:1});
const STATUS={success:T('成功'),failed:T('失败'),pending:T('进行中'),prepared:T('已准备'),blocked:T('已阻断')};
const SVC={online:['#34D399',T('在线')],offline:['#F87171',T('离线')],stopped:['#8A93A3',T('已停止')]};
const PERIODS={today:T('今天'),week:T('本周'),month:T('本月')};
let timer=null,lastData=null,chartMode='7d';
const bill={platform:null,model:null};
let billTargets=[];
let billNavigation={generation:0,animation:null};
function navigateBilling(platform,model,direction){
  const page=$('bill-page'),state=billNavigation,generation=++state.generation;
  state.animation?.cancel();state.animation=null;
  bill.platform=platform;bill.model=model;renderBilling();
  (platform===null?$('bill-crumb'):$('bill-back')).focus({preventScroll:true});
  if(REDUCE()||!page)return;
  // Navigation takes effect immediately; the short entrance never locks clicks.
  page.querySelectorAll('#bill-tiles .k-enter,#bill-detail .k-enter').forEach(el=>el.classList.remove('k-enter'));
  const enter=page.animate([{opacity:.65,transform:'translateX('+(direction==='forward'?8:-8)+'px)'},{opacity:1,transform:'translateX(0)'}],{duration:150,easing:'ease-out'});
  state.animation=enter;
  enter.onfinish=()=>{if(state.generation===generation)state.animation=null;};
}
function syncThemePresets(){const root=document.documentElement;for(const button of document.querySelectorAll('[data-theme-preset]')){button.setAttribute('aria-pressed',String(button.dataset.themeStyle===root.dataset.style&&button.dataset.themeMode===root.dataset.theme));button.textContent=T(button.dataset.themeMode==='warm'?'浅色':'深色')}}
function applyThemeAttr(t,style){const root=document.documentElement;root.dataset.theme=t;root.dataset.style=style;syncThemePresets()}
function setAppearance(style,t){
  style=style==='mono'||style==='original'?style:'prism';t=t==='warm'?'warm':'dark';
  try{localStorage.setItem('cg-theme',t);localStorage.setItem('cg-theme-style',style)}catch(e){}
  const root=document.documentElement;
  root.classList.add('switching-appearance');
  applyThemeAttr(t,style);
  // Resolve the new palette together before restoring normal hover transitions.
  void getComputedStyle(document.body).backgroundColor;
  root.classList.remove('switching-appearance');
  try{if(window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.theme)window.webkit.messageHandlers.theme.postMessage(t)}catch(e){}
}
function setTheme(t){setAppearance(document.documentElement.dataset.style||'prism',t)}
document.querySelectorAll('[data-theme-preset]').forEach(button=>button.onclick=()=>setAppearance(button.dataset.themeStyle,button.dataset.themeMode));
setTheme(document.documentElement.dataset.theme||'dark');
// 子节点级最小 diff：内容没变的行不碰 DOM，10s 刷新不再打断悬浮/展开（丝滑的前提）。
function reconcile(el,html){
  if(el.__h===html)return;
  el.__h=html;
  const t=document.createElement('template');t.innerHTML=html;
  const fresh=t.content.childNodes,old=Array.from(el.childNodes),n=Math.max(old.length,fresh.length);
  const fk=Array.from(fresh).map(f=>f.nodeType===1?f.getAttribute('data-k'):null);
  if(fk.every(k=>k)&&new Set(fk).size===fk.length&&(fk.length||old.some(o=>o.nodeType===1&&o.getAttribute('data-k'))))return reconcileKeyed(el,fresh,fk);
  for(let i=0;i<n;i++){
    const o=old[i],f=fresh[i];
    if(o&&!f){o.remove();continue;}
    if(!o&&f){el.appendChild(document.importNode(f,true));continue;}
    if(o.nodeType===1&&f.nodeType===1&&o.tagName==='DETAILS'&&f.tagName==='DETAILS')f.open=o.open;
    const os=o.nodeType===1?o.outerHTML:o.nodeValue;
    const fs=f.nodeType===1?f.outerHTML:f.nodeValue;
    if(os!==fs)el.replaceChild(document.importNode(f,true),o);
  }
}
const REDUCE=()=>window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function reconcileKeyed(el,fresh,fk){
  const moving=(el.id==='bill-viz'||el.id==='plat-viz')&&!REDUCE(),before=new Map(),requested=new Set(fk);
  Array.from(el.children).forEach(o=>{if(moving&&o.dataset.k&&!o.dataset.kLeaving)before.set(o.dataset.k,o.getBoundingClientRect());if(o.__flip){o.__flip.cancel();o.__flip=null;}});
  const map=new Map();
  Array.from(el.childNodes).forEach(o=>{
    if(o.nodeType===1&&o.dataset.kLeaving){if(requested.has(o.dataset.k))o.remove();return;}
    const k=o.nodeType===1?o.getAttribute('data-k'):null;
    if(!k||map.has(k))o.remove();else map.set(k,o);
  });
  if(moving&&getComputedStyle(el).position==='static')el.style.position='relative';
  const keep=new Set(),live=o=>{let s=o.nextSibling;while(s&&s.dataset&&s.dataset.kLeaving)s=s.nextSibling;return s;};
  let ref=null;
  for(let i=fresh.length-1;i>=0;i--){
    let o=map.get(fk[i]);
    if(o){morph(o,fresh[i]);if(live(o)!==ref)el.insertBefore(o,ref);keep.add(fk[i]);}
    else{o=document.importNode(fresh[i],true);o.classList.add('k-enter');const done=()=>o.classList.remove('k-enter');o.addEventListener('animationend',e=>{if(e.target===o)done();});setTimeout(done,400);el.insertBefore(o,ref);}
    ref=o;
  }
  map.forEach((o,k)=>{
    if(keep.has(k))return;
    if(REDUCE()||el.hasAttribute('data-noleave')){o.remove();return;}
    o.classList.add('k-leave');o.dataset.kLeaving='1';
    const old=before.get(k);if(moving&&old){const p=el.getBoundingClientRect();Object.assign(o.style,{position:'absolute',top:(old.top-p.top)+'px',left:(old.left-p.left)+'px',width:old.width+'px',margin:'0',transform:'none',translate:'none'});}
    const gone=()=>o.remove();o.addEventListener('animationend',e=>{if(e.target===o)gone();});setTimeout(gone,400);
  });
  if(moving&&!REDUCE())for(const o of el.children){const old=before.get(o.dataset.k);if(!old||o.dataset.kLeaving)continue;const now=o.getBoundingClientRect(),dx=old.left-now.left,dy=old.top-now.top;if(Math.abs(dx)+Math.abs(dy)>1)o.__flip=o.animate([{translate:dx+'px '+dy+'px'},{translate:'0 0'}],{duration:360,easing:'cubic-bezier(.2,.8,.2,1)'});}
}
function morph(o,f){
  if(o.tagName==='DETAILS')f.open=o.open;
  if(o.__nv===undefined&&o.hasAttribute('data-n')){o.__nv=o.__v=Number(o.getAttribute('data-n'));o.__nf=o.getAttribute('data-f');}
  let cls=f.getAttribute('class')||'';if(o.classList.contains('k-enter'))cls=(cls+' k-enter').trim();
  if(cls!==(o.getAttribute('class')||''))cls?o.setAttribute('class',cls):o.removeAttribute('class');
  for(const a of Array.from(f.attributes)){if(a.name!=='class'&&o.getAttribute(a.name)!==a.value)o.setAttribute(a.name,a.value);}
  for(const a of Array.from(o.attributes)){if(a.name!=='class'&&!f.hasAttribute(a.name))o.removeAttribute(a.name);}
  if(f.hasAttribute('data-n')&&o.__nf!==undefined&&o.__nf===f.getAttribute('data-f')){
    const to=Number(f.getAttribute('data-n'));
    if(o.__nv!==to){const from=o.__v;o.__nv=to;tweenNum(o,from,to,o.__nf);}
    return;
  }
  if(o.__tw){cancelAnimationFrame(o.__tw);o.__tw=0;}
  o.__nv=o.__v=o.__nf=undefined;
  if(f.hasAttribute('data-n')){o.__nv=o.__v=Number(f.getAttribute('data-n'));o.__nf=f.getAttribute('data-f');}
  const oc=o.childNodes,fc=f.childNodes;let same=oc.length===fc.length;
  for(let i=0;same&&i<oc.length;i++)same=oc[i].nodeType===fc[i].nodeType&&(oc[i].nodeType!==1||oc[i].tagName===fc[i].tagName);
  if(!same){o.innerHTML=f.innerHTML;return;}
  for(let i=0;i<oc.length;i++){
    if(oc[i].nodeType===1)morph(oc[i],fc[i]);else if(oc[i].nodeValue!==fc[i].nodeValue)oc[i].nodeValue=fc[i].nodeValue;
  }
}
// SVG 的 innerHTML 解析上下文必须是 SVG 命名空间，走「没变就不动」的守卫即可。
function setSvg(el,html){if(el.__h===html)return;el.__h=html;el.innerHTML=html;}
function money(n){
  if(n===null||n===undefined||isNaN(n))return T('未配置');
  if(n===0)return '$0.00';
  if(n<0)return '-$'+(-n).toFixed(-n>=0.01?2:4);
  return '$'+(n>=1?n.toFixed(2):n>=0.01?n.toFixed(4):n.toFixed(6));
}
function tps(n){return n===null||n===undefined||isNaN(n)?'–':n>=100?String(Math.round(n)):Number(n).toFixed(1);}
function tok(n){
  if(n===null||n===undefined||isNaN(n))return '–';
  return compact(n);
}
const NUMF={tps:n=>tps(n),tok:n=>tok(n),num:n=>num(n),money:n=>money(n),compact:n=>compact(n),int:n=>num(Math.round(n)),ms:n=>ms(n),msu:n=>num(Math.round(n))+' ms',secms:n=>n?(n>=1000?(n/1000).toFixed(1)+'s':ms(n)+'ms'):'–'},NUMR={tok:1,num:1,compact:1,int:1,msu:1};
function tweenAt(from,to,t){return t>=1?to:t<=0?from:from+(to-from)*(1-Math.pow(1-t,3));}
function tweenNum(el,from,to,fmt){
  const f=NUMF[fmt]||num,r=NUMR[fmt]?Math.round:x=>x;
  if(el.__tw){cancelAnimationFrame(el.__tw);el.__tw=0;}
  el.__nv=to;
  if(!(isFinite(from)&&isFinite(to))||document.hidden||(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)){el.__v=to;el.textContent=f(to);return;}
  const t0=performance.now();
  const step=now=>{
    const t=(now-t0)/600;
    if(t>=1){el.__tw=0;el.__v=to;el.textContent=f(to);return;}
    el.__v=tweenAt(from,to,t);el.textContent=f(r(el.__v));el.__tw=requestAnimationFrame(step);
  };
  el.__tw=requestAnimationFrame(step);
}
function setNum(el,value,fmt,fallbackText){
  const ok=typeof value==='number'&&isFinite(value),prev=el.__n;
  el.__n=ok?value:undefined;
  if(ok&&prev===value&&el.__tw)return;
  if(ok&&typeof prev==='number'&&prev!==value){tweenNum(el,el.__v!==undefined?el.__v:prev,value,fmt);return;}
  if(el.__tw){cancelAnimationFrame(el.__tw);el.__tw=0;}
  el.__v=ok?value:undefined;
  el.textContent=ok?(NUMF[fmt]||num)(value):(fallbackText===undefined?'–':fallbackText);
}
function dnA(v,f){return (typeof v==='number'&&isFinite(v))?' data-n="'+v+'" data-f="'+f+'"':'';}
function nsp(v,f,txt,tag){tag=tag||'span';return dnA(v,f)?'<'+tag+dnA(v,f)+'>'+txt+'</'+tag+'>':txt;}
function platformLabel(platform){const names={router:'Local Model Router',zcode:'ZCode',claude:'Claude',codex:'Codex',gpt:'GPT / Codex',deepai:'DeepAI Code'};return T(names[platform]||platform);}
function accessLabel(access){const names={codex:'Codex 接入',cursor:'Cursor 接入',direct:'直接调用'};return names[access]?T(names[access]):platformLabel(access);}
function primaryAccess(m){const src=m.sources||[];return src.length===1?src[0]:'mixed';}
function row(label,tokens,cost,cls){
  return '<div class="t-row '+(cls||'')+'"><span>'+label+'</span><span><b'+dnA(tokens,'tok')+'>'+tok(tokens)+'</b> <i'+(cost===undefined?'':dnA(cost,'money'))+'>'+(cost===undefined?'':money(cost))+'</i></span></div>';
}
let costMode='actual';
const officialMode=()=>costMode==='official';
function name_badge(name,free,priced){
  if(officialMode())return esc(name)+(free?'<span class="freebadge">'+T('官方 $0')+'</span>':priced?'':'<span class="paidbadge">'+T('无官方价')+'</span>');
  return esc(name)+(free?'<span class="freebadge">'+T('免费')+'</span>':priced?'<span class="paidbadge">'+T('付费')+'</span>':'');
}
function platformTile(g,i){
  const warn=g.unpriced_requests?(officialMode()?g.unpriced_requests+Tc(g.unpriced_requests,' 条请求的模型无官方价，未计金额',' request used a model without an official price — not counted',' requests used models without an official price — not counted'):g.unpriced_requests+Tc(g.unpriced_requests,' 条请求的模型未配置价格，未计金额',' request used an unpriced model — not counted in spend',' requests used unpriced models — not counted in spend')):'';
  const actual=(g.input_tokens||0)+(g.output_tokens||0);
  let html='<div role="button" tabindex="0" class="tile" data-k="'+esc(g.platform)+'" data-t="'+i+'"><div class="t-name">'+esc(platformLabel(g.platform))+'<span class="t-n">'+nsp(g.requests,'num',num(g.requests))+Tc(g.requests,' 请求',' request',' requests')+'</span></div>';
  if(g.ab_pairs){
    const pctLabel=(g.ab_reduction_pct===null||g.ab_reduction_pct===undefined)?'' :(LANG==='en'?' · saved '+g.ab_reduction_pct+'%':' · 省 '+g.ab_reduction_pct+'%');
    html+=row(T('原消耗（推算）'),actual+g.ab_saved_tokens,(g.cost_actual_usd??0)+(g.ab_saved_usd||0))
         +row(LANG==='en'?('Compression savings (measured '+(g.ab_pairs||0)+' A/B pairs'+pctLabel+')'):('压缩节省（实测对照 '+(g.ab_pairs||0)+' 组'+pctLabel+'）'),g.ab_saved_tokens,g.ab_saved_usd,'save');
  }else{
    html+='<div class="t-row dim"><span>'+T('压缩节省')+'</span><span>'+T('无实测对照')+'</span></div>';
  }
  html+=row(T('实际消耗'),actual,g.cost_actual_usd)
       +(warn?'<div class="warn">⚠ '+esc(warn)+'</div>':'')+'<span class="billing-open">'+T('查看明细')+' →</span></div>';
  return html;
}
function priceSourceLabel(source){return T(source.price_basis==='provider'?'服务商参考价':'厂商官方价')+' · '+(source.source_name||T('价格来源'));}
function priceSourceDetails(model){
 if(!officialMode()||!model?.price_sources?.length)return '';
 const notes={contributor:'Contributor 档位按其官方优惠价计算。',peak_reference:'按 DeepSeek 高峰标价比较；低谷与节假日优惠不另算。',standard_list:'按常规标价比较，不使用限时首发优惠。',implicit_cache:'缓存读取采用隐式缓存价；原始记录未区分显式缓存。',qwen_flash_reference:'Flash-Next 按官方对应的 Qwen3.8-Flash 服务价格比较。',no_cache_discount:'未公布缓存优惠，缓存输入按普通输入价比较。'};
 return '<details class="price-reference"><summary>'+T('价格依据')+'</summary>'+model.price_sources.map(source=>{
  const link=/^https:\/\//i.test(source.source||'')?'<span class="price-source-url">'+esc(source.source)+'</span>':'';
  return '<div class="price-reference-row"><strong>'+esc(priceSourceLabel(source))+'</strong><p>'+T('美元 / 百万 tokens')+' · '+T('输入')+' '+num(source.input)+' · '+T('输出')+' '+num(source.output)+' · '+T('缓存读')+' '+num(source.cache_read)+' · '+T('缓存写')+' '+num(source.cache_write)+'</p>'+(source.price_note&&notes[source.price_note]?'<p>'+esc(T(notes[source.price_note]))+'</p>':'')+'<p>'+T('核对日期')+' '+esc(source.verified_at||'—')+' · '+link+'</p></div>';
 }).join('')+'</details>';
}
function modelTile(m,i){
  let html='<div role="button" tabindex="0" class="tile" data-k="'+esc(m.platform+':'+m.model+(m.platform==='deepai'?':'+primaryAccess(m):''))+'" data-t="'+i+'"><div class="t-name"><span class="model-label">'+esc(m.model)+'</span></div><div class="model-meta"><span>'+esc(platformLabel(m.platform))+' '+name_badge('',m.free,m.priced)+'</span><span>'+num(m.requests)+Tc(m.requests,' 请求',' request',' requests')+'</span></div>';
  if(m.platform==='deepai')html+='<div class="t-source">'+esc((m.sources&&m.sources.length?m.sources:[primaryAccess(m)]).map(accessLabel).join(' · '))+'</div>';
  if(officialMode()&&m.price_sources?.length)html+='<div class="model-price-source">'+m.price_sources.map(source=>esc(priceSourceLabel(source))).join(' · ')+'</div>';
  html+=row(T('实际消耗'),(m.actual_input||0)+(m.actual_output||0),m.cost_actual_usd);
  if(m.provider_billed_usd)html+='<div class="muted">'+T('含已核实账单')+' '+money(m.provider_billed_usd)+'</div>';
  html+='<div class="t-row'+(m.tps_requests?'':' dim')+'"><span>'+T('输出速度')+'</span><span>'+(m.tps_requests?'<b>'+tps(m.output_tps)+'</b> tokens/s':'–')+'</span></div>';
  if(m.cached)html+=row(T('其中缓存读'),m.cached);
  html+=(m.priced?'':'<div class="warn">⚠ '+T(officialMode()?'无官方价，只计 tokens，未计金额':'未配置价格，未计金额')+'</div>')+'</div>';
  return html;
}
let refreshController=null,refreshGeneration=0;
function refreshFeedback(state,message){const note=$('refresh-note'),button=$('refresh');if(note){note.dataset.state=state;note.textContent=message;note.title=message;}button.textContent=T(state==='busy'?'刷新中…':'刷新');button.setAttribute('aria-busy',String(state==='busy'));}
async function refreshView(view,options){
  // These live views already poll every 2–4 seconds without repainting edits.
  if(options?.automatic&&['center','group','quota','todo'].includes(view))return null;
  switch(view){
    case 'wallet':return loadWallet(options);
    case 'memory':return loadMemory(!options?.automatic);
    case 'router':return loadRouter();
    case 'git':return loadGit();
    case 'todo':return loadTodo();
    case 'center':return loadCenter();
    case 'group':return groupLoad();
    case 'quota':{const results=await Promise.all([loadQuota(),loadQuotaLog()]);return results.some(r=>r===false)?false:results.every(r=>r===true)?true:null;}
    default:return true;
  }
}
async function refresh(options={}){
  const automatic=options?.automatic===true;
  if(automatic&&(document.hidden||$('refresh').getAttribute('aria-busy')==='true')){schedule();return;}
  const view=curView,generation=++refreshGeneration;
  if(refreshController)refreshController.abort();
  const controller=refreshController=new AbortController();
  if(!automatic){$('refresh').disabled=true;refreshFeedback('busy',T('正在更新当前页…'));}
  try{
    const q=new URLSearchParams({period:$('period').value,platform:$('platform').value});
    const r=await fetch('v1/stats?'+q,{cache:'no-store',signal:controller.signal});
    if(generation!==refreshGeneration)return;
    if(r.status===403){showReconnect(T('服务已重启，连接令牌已更新，刷新无效。'));refreshFeedback('error',T('连接已失效，请重新打开控制台'));return;}
    if(!r.ok)throw new Error('HTTP '+r.status);
    const data=await r.json();if(generation!==refreshGeneration)return;
    if(!automatic)modelDetail.key='';
    render(data,{force:!automatic});
    const result=view===curView?await refreshView(view,{automatic}):null;
    if(generation!==refreshGeneration)return;
    $('banner').style.display='none';
    if(result===false)refreshFeedback('error',T('当前页更新失败，已保留上次结果；请查看页内提示。'));
    else if(!automatic)refreshFeedback(result===null?'waiting':'ok',view!==curView?T('已切换页面，请刷新当前页'):result===null?T('正在编辑或处理其他操作，稍后再刷新'):T('已更新 · ')+new Date().toLocaleTimeString(LOCALE(),{hour:'2-digit',minute:'2-digit',second:'2-digit'}));
  }catch(e){
    if(generation!==refreshGeneration||e.name==='AbortError')return;refreshFeedback('error',T('更新失败：')+e.message);
    if(e instanceof TypeError)showReconnect(T('连不上本地数据服务，服务可能已重启或停止。'));
    else{$('banner').textContent=T('读取数据失败：')+e.message;$('banner').style.display='block';}
  }finally{if(generation===refreshGeneration){$('refresh').disabled=false;$('refresh').removeAttribute('aria-busy');schedule();}}
}
function showReconnect(reason){
  const shell=!!(window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.reconnect);
  const hk=lastData&&lastData.hotkey?fmtHotkey(lastData.hotkey):'⇧⌘E';
  $('banner').textContent=reason+(shell?T('正在自动重连新连接…'):(T('请按 ')+hk+T(' 重新打开控制台（浏览器页签请关闭后重开）。')));
  $('banner').style.display='block';
  if(shell){try{window.webkit.messageHandlers.reconnect.postMessage('stale');}catch(e){}}
}
function schedule(){
  if(timer)clearTimeout(timer);timer=null;
  if($('auto').checked)timer=setTimeout(()=>refresh({automatic:true}),5000);
}
function renderOverview(d){
  reconcile($('ov-req'),(d.recent||[]).slice(0,6).map((r,ri)=>{
    const at=r.at?new Date(r.at*1000).toLocaleString(LOCALE(),{hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'–';
    return '<div role="button" tabindex="0" class="mrow" data-ri="'+ri+'"><span class="tag '+esc(r.status||'')+'">'+esc(STATUS[r.status]||'–')+'</span><span class="mtime">'+esc(at)+'</span><span class="mmodel">'+esc(r.model||'—')+'</span><span class="mtok">'+num((r.actual_input||0)+(r.actual_output||0))+'</span></div>';
  }).join('')||'<span class="muted">'+T('暂无请求')+'</span>');
reconcile($('ov-gt'),(lastGate||[]).slice(0,4).map((t,gi)=>{
    const root=(t.root||'').split('/').filter(Boolean).pop()||'—';
    return '<div role="button" tabindex="0" class="mrow" data-gi="'+gi+'"><span class="gt-chip '+esc(t.display_status)+'">'+esc(GT_STATUS[t.display_status]||t.display_status)+'</span><span class="mmodel">'+esc(root)+'</span><span class="mtok">'+num((t.turns||[]).length)+Tc((t.turns||[]).length,' 轮',' turn',' turns')+'</span></div>';
  }).join('')||'<span class="muted">'+T('暂无任务')+'</span>');
}
function renderRequestSummary(d){
  const rows=d.recent||[];
  const cs={success:0,failed:0,other:0};
  rows.forEach(r=>{cs[r.status==='success'?'success':r.status==='failed'?'failed':'other']++;});
  const tsum=rows.reduce((a,r)=>a+(r.actual_input||0)+(r.actual_output||0),0);
  reconcile($('req-sums'),'<span class="sum"><b>'+num(rows.length)+'</b>'+T('最近请求')+'</span><span class="sum"><b>'+num(cs.success)+'</b>'+T('成功')+'</span><span class="sum"><b>'+num(cs.failed)+'</b>'+T('失败')+'</span><span class="sum"><b>'+num(cs.other)+'</b>'+T('进行中/其他')+'</span><span class="sum"><b>'+tok(tsum)+'</b>tokens</span>');
}
function renderPlatformViz(d){
  const groups=(d.by_platform||[]).filter(g=>g.requests>0||g.cost_actual_usd>0).sort((a,b)=>((b.input_tokens||0)+(b.output_tokens||0))-((a.input_tokens||0)+(a.output_tokens||0)));
  const mx=Math.max(1,...groups.map(g=>(g.input_tokens||0)+(g.output_tokens||0)));
  const pg=groups.slice().sort((a,b)=>a.platform<b.platform?-1:a.platform>b.platform?1:0);
  reconcile($('plat-viz'),pg.map((g,i)=>{const tk=(g.input_tokens||0)+(g.output_tokens||0);
    return '<div class="brow" data-k="'+esc(g.platform)+'" style="--dy:'+(groups.indexOf(g)-i)+'"><span class="bname">'+esc(platformLabel(g.platform))+'</span><span class="bbar"><i style="width:'+Math.round(100*tk/mx)+'%"></i></span><span class="bval"'+dnA(tk,'tok')+'>'+tok(tk)+'</span><span class="breq">'+nsp(g.requests,'num',num(g.requests))+Tc(g.requests,' 请求',' request',' requests')+'</span></div>';
  }).join('')||'<span class="muted">'+T('暂无数据')+'</span>');
}
let billMode='cost';try{if(localStorage.getItem('cg-billmode')==='usage')billMode='usage'}catch(e){}
function applyBillMode(){
  const u=billMode==='usage',viz=$('bill-viz'),btn=$('bill-mode'),desc=$('bill-desc');
  if(viz)viz.dataset.mode=billMode;
  if(btn){btn.setAttribute('aria-checked',u?'true':'false');btn.dataset.mode=billMode;}
  if(desc)desc.textContent=T(u?'各平台 token 用量（输入 + 输出）；点平台方块下钻到模型明细。':officialMode()?'按各模型官方标价折算（含实际免费的请求）的各平台金额；无官方价的模型只计 tokens。点平台方块下钻到模型明细。':'根据用量和价格估算花费；点平台查看各模型明细。');
}
{const bm=$('bill-mode');if(bm)bm.addEventListener('click',()=>{billMode=billMode==='usage'?'cost':'usage';try{localStorage.setItem('cg-billmode',billMode)}catch(e){}applyBillMode()})}
applyBillMode();
function applyCostMode(m){
  costMode=m==='official'?'official':'actual';
  document.querySelectorAll('.cm-label').forEach(el=>{el.textContent=T(officialMode()?'价格模式：按官方标价折算（含免费请求）':'价格模式：按付费设置');el.dataset.mode=costMode;});
  document.querySelectorAll('#cost-mode button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.mode===costMode?'true':'false'));
  const th=$('plat-cost-th');if(th)th.textContent=T(officialMode()?'官方价折算 $':'估算花费 $');
  applyBillMode();
}
applyCostMode('actual');
// 价格模式存在后端（cost-mode.json），重启后保持；切换后立即重取统计。
document.querySelectorAll('#cost-mode button').forEach(b=>b.addEventListener('click',async()=>{
  if(b.dataset.mode===costMode)return;
  const prev=costMode,btns=[...document.querySelectorAll('#cost-mode button')];
  applyCostMode(b.dataset.mode);btns.forEach(x=>x.disabled=true);
  try{
    const r=await fetch('v1/settings/cost-mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:b.dataset.mode})});
    if(r.status===403){showReconnect(T('服务已重启，连接令牌已更新，本次操作没有生效。'));throw new Error('HTTP 403');}
    if(!r.ok)throw new Error('HTTP '+r.status);
  }catch(e){applyCostMode(prev);refreshFeedback('error',T('切换价格模式失败：')+e.message);return;}
  finally{btns.forEach(x=>x.disabled=false);}
  refresh();
}));
function renderBilling(){
  if(!lastData)return;
  const bgroups=(lastData.by_platform||[]).filter(g=>g.requests>0);
  const totalCost=bgroups.reduce((a,g)=>a+(g.cost_actual_usd||0),0);
  const bsum=$('bill-sums');
  if(bsum){const ab=lastData.global_ab||{};reconcile(bsum,'<span class="sum" data-k="count"><b'+dnA(bgroups.length,'num')+'>'+num(bgroups.length)+'</b>'+(LANG==='en'?'platforms':'平台')+'</span><span class="sum" data-k="cost"><b'+dnA(totalCost,'money')+'>'+money(totalCost)+'</b>'+T(officialMode()?'按官方标价折算':'估算花费')+'</span><span class="sum" data-k="save"><b'+(ab.pairs?dnA(savingsOf(lastData),'money'):'')+'>'+(ab.pairs?money(savingsOf(lastData)):'—')+'</b>'+T('对照测试节省')+'</span>');}
  const bviz=$('bill-viz');
  const btok=g=>(g.input_tokens||0)+(g.output_tokens||0);
  const urank=bgroups.slice().sort((a,b)=>btok(b)-btok(a)||(b.cost_actual_usd||0)-(a.cost_actual_usd||0)),crank=bgroups.slice().sort((a,b)=>(b.cost_actual_usd||0)-(a.cost_actual_usd||0)||btok(b)-btok(a));
  const brows=bgroups.slice().sort((a,b)=>a.platform<b.platform?-1:a.platform>b.platform?1:0);
  const cmax=Math.max(1e-9,...brows.map(g=>g.cost_actual_usd||0)),umax=Math.max(1,...brows.map(btok));
  if(bviz){bviz.hidden=bill.platform!==null;reconcile(bviz,brows.map((g,i)=>{
    const c=g.cost_actual_usd||0,tk=btok(g),wc=c>0?Math.max(1,Math.round(100*c/cmax)):0,wu=tk>0?Math.max(1,Math.round(100*tk/umax)):0,nm=esc(platformLabel(g.platform));
    const free=c===0&&!(g.unpriced_requests>0);
    const cv=free?'<span class="bfree">'+T(officialMode()?'官方 $0':'免费')+'</span>':money(c);
    return '<div role="button" tabindex="0" class="brow" data-bill-platform="'+esc(g.platform)+'" data-k="'+esc(g.platform)+'" style="--wc:'+wc+'%;--wu:'+wu+'%;--du:'+(urank.indexOf(g)-i)+';--dc:'+(crank.indexOf(g)-i)+'"><span class="bname" title="'+nm+'">'+nm+'</span><span class="bbar"><i></i></span><span class="bval bval2"><span class="bv-cost"'+(free?'':dnA(c,'money'))+'>'+cv+'</span><span class="bv-use"'+dnA(tk,'tok')+'>'+tok(tk)+'</span></span><span class="breq"><b'+dnA(g.requests,'num')+'>'+num(g.requests)+'</b>'+Tc(g.requests,' 请求',' request',' requests')+'</span></div>';
  }).join('')||'<span class="muted">'+T('暂无花费记录')+'</span>');}
  const crumb=$('bill-crumb'),tilesEl=$('bill-tiles'),detail=$('bill-detail');
  const back=$('bill-back');
  back.style.display=bill.platform===null?'none':'inline-block';
  const groups=lastData.by_platform||[];
  const models=lastData.by_model||[];
  if(bill.platform===null){
    reconcile(crumb,'<strong>'+T('计费明细')+'</strong><span class="muted">'+T('选择平台，查看模型与请求记录')+'</span>');
    const freeModels=models.filter(m=>m.free);
    billTargets=groups.map(g=>({platform:g.platform,model:null}));
    let html=groups.filter(g=>g.requests>0||g.ab_pairs>0||g.cost_actual_usd>0).map(g=>platformTile(g,groups.indexOf(g))).join('');
    if(freeModels.length){
      const agg=freeModels.reduce((a,m)=>({requests:a.requests+m.requests,tokens:a.tokens+(m.actual_input||0)+(m.actual_output||0),cost:a.cost+(m.cost_actual_usd||0)}),{requests:0,tokens:0,cost:0});
      billTargets.push({platform:'__free__',model:null});
      html+='<button type="button" class="tile free-shortcut" data-k="__free__" data-t="'+(billTargets.length-1)+'"><span>'+T(officialMode()?'官方 $0':'免费')+' · '+num(freeModels.length)+Tc(freeModels.length,' 个模型',' model',' models')+'</span><span>'+tok(agg.tokens)+' tokens · '+money(agg.cost)+' →</span></button>';
    }
    reconcile(tilesEl,html||'<span class="muted">'+T('暂无数据')+'</span>');
    reconcile(detail,'');
  }else if(bill.platform==='__free__'&&bill.model===null){
    reconcile(crumb,'<a href="#" data-act="root">'+T('平台总览')+'</a> › '+T('免费'));
    const freeModels=models.filter(m=>m.free);
    billTargets=freeModels.map(m=>({platform:m.platform,model:m.model}));
    reconcile(tilesEl,freeModels.map((m,i)=>modelTile(m,i)).join('')||'<span class="muted">'+T('暂无免费模型记录')+'</span>');
    reconcile(detail,'');
  }else if(bill.model===null&&bill.platform==='deepai'){
    reconcile(crumb,'<a href="#" data-act="root">'+T('平台总览')+'</a> › '+esc(platformLabel('deepai')));
    const list=models.filter(m=>m.platform==='deepai');
    const order=[['codex','Codex 接入'],['cursor','Cursor 接入'],['direct','直接调用'],['mixed','多个接入']];
    billTargets=[];
    let html='';
    order.forEach(pair=>{
      const group=list.filter(m=>primaryAccess(m)===pair[0]);
      if(!group.length)return;
      html+='<div class="subhead">'+T(pair[1])+'</div>';
      html+=group.map(m=>{const i=billTargets.length;billTargets.push({platform:'deepai',model:m.model});return modelTile(m,i);}).join('');
    });
    reconcile(tilesEl,html||'<span class="muted">'+T('暂无模型记录')+'</span>');
    reconcile(detail,'');
  }else if(bill.model===null){
    reconcile(crumb,'<a href="#" data-act="root">'+T('平台总览')+'</a> › '+esc(platformLabel(bill.platform)));
    const list=models.filter(m=>m.platform===bill.platform);
    const paid=list.filter(m=>!m.free),free=list.filter(m=>m.free);
    billTargets=paid.concat(free).map(m=>({platform:bill.platform,model:m.model}));
    let html=paid.map((m,i)=>modelTile(m,i)).join('');
    if(free.length)html+='<div class="subhead">'+T(officialMode()?'官方标价 $0 的模型':'免费模型（含 Local Model Router，$0）')+'</div>'+free.map((m,i)=>modelTile(m,paid.length+i)).join('');
    reconcile(tilesEl,html||'<span class="muted">'+T('暂无模型记录')+'</span>');
    reconcile(detail,'');
  }else{
    reconcile(crumb,'<a href="#" data-act="root">'+T('平台总览')+'</a> › <a href="#" data-act="plat">'+esc(bill.platform==='__free__'?T('免费'):platformLabel(bill.platform))+'</a> › '+esc(bill.model));
    ensureModelDetail();
    const rows=modelDetail.key===detailKey()&&modelDetail.rows?modelDetail.rows:null;
    reconcile(tilesEl,'');
    const pricedModel=models.find(m=>m.model===bill.model&&(bill.platform==='__free__'||m.platform===bill.platform));
    const showAccess=bill.platform==='deepai'||(rows||[]).some(r=>r.platform==='deepai');
    const cols=showAccess?10:9;
    reconcile(detail,priceSourceDetails(pricedModel)+(rows?speedPanel(modelDetail.summary):'')+'<table><thead><tr><th>'+T('时间')+'</th>'+(showAccess?'<th>'+T('来源')+'</th>':'')+'<th>'+T('状态')+'</th><th class="num">'+T('压缩前估算')+'</th><th class="num">'+T('压缩后估算')+'</th><th class="num">'+T('实际输入')+'</th><th class="num">'+T('实际输出')+'</th><th class="num">'+T('缓存读')+'</th><th class="num">'+T('耗时 ms')+'</th><th class="num">'+T('输出速度 tok/s')+'</th></tr></thead><tbody>'
      +(rows?(rows.map(r=>{
        const at=r.at?new Date(r.at*1000).toLocaleString(LOCALE(),{hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'–';
        const st=STATUS[r.status]||r.status||'–';
        return '<tr><td>'+esc(at)+'</td>'+(showAccess?'<td>'+esc(accessLabel(r.client_platform||(r.platform==='deepai'?'direct':'')))+'</td>':'')+'<td><span class="tag '+esc(r.status||'')+'">'+esc(st)+'</span></td><td class="num">'+num(r.before_est)+'</td><td class="num">'+num(r.after_est)+'</td><td class="num">'+num(r.actual_input)+'</td><td class="num">'+num(r.actual_output)+'</td><td class="num">'+num(r.cached)+'</td><td class="num">'+ms(r.duration_ms)+'</td><td class="num">'+tps(r.output_tps)+'</td></tr>';
      }).join('')||'<tr><td colspan="'+cols+'" class="muted">'+(modelDetail.error?T('读取失败：')+esc(modelDetail.error)+' <button type="button" id="model-retry">'+T('重试')+'</button>':T('该模型没有请求记录'))+'</td></tr>'):'<tr><td colspan="'+cols+'" class="muted">'+T('正在加载该模型的请求…')+'</td></tr>')+'</tbody></table>'
      +(rows&&!modelDetail.error?'<p class="muted">'+(LANG==='en'?('Latest '+rows.length+' entries for this model (independent query, up to 500, not limited by the platform overview window).'):('该模型最近 '+rows.length+' 条（独立查询，最多 500 条，不受平台总览窗口限制）。'))+'</p>':''));
  }
  const retry=$('model-retry');if(retry)retry.onclick=()=>{modelDetail.key='';renderBilling();};
  const unpriced=lastData.unpriced_models||[];
  const priceBasis=T(officialMode()?'按官方标价估算，包含免费请求；这不是实际账单。':'按当前付费设置估算；免费额度和本地调用记为 $0。');
  const missing=unpriced.length?(LANG==='en'?unpriced.length+(unpriced.length===1?' model has no price; only usage is counted.':' models have no price; only usage is counted.'):T('有 ')+unpriced.length+T(' 个模型缺少价格，只统计用量。')):'';
  reconcile($('bill-note'),'<span>'+esc(priceBasis+' '+missing)+'</span><details style="margin-top:10px"><summary>'+T('价格与统计说明')+'</summary><p>'+T('同一模型的不同思考档位合并统计，原始名称保留在请求详情。')+'</p><p>'+T('Local Model Router 汇总自定义连接与本地模型；付费模型仍按原价格计算，不因分类改变而变成免费。')+'</p><p>'+T('经过 DeepAI Code 的 Codex、Cursor 请求只记在 DeepAI Code，不再计入原来的平台。明确走其他上游（例如 api.openai.com）的请求仍留在原平台。')+'</p><p>'+T('官方标价优先用厂商价格；开源模型可用已注明来源的服务商参考价。价格按核对日的公开标价比较，不是历史账单。')+'</p><p>'+T('只有同一任务分别使用和不使用压缩后，才计算对照节省。')+'</p>'+(unpriced.length?'<p>'+esc(T('尚无价格：')+unpriced.join(', '))+'</p>':'')+'<p>'+esc(T('价格配置：')+(lastData.prices_file||'prices.json'))+'</p></details>');
}
$('bill-tiles').addEventListener('click',e=>{
  const t=e.target.closest('.tile');if(!t)return;
  const target=billTargets[Number(t.dataset.t)];if(!target)return;
  navigateBilling(target.platform,target.model,'forward');
});
$('bill-tiles').addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' ')return;
  const t=e.target.closest('.tile[role="button"]');if(!t)return;
  e.preventDefault();t.click();
});
$('bill-crumb').addEventListener('click',e=>{
  const a=e.target.closest('a[data-act]');if(!a)return;
  e.preventDefault();if(a.dataset.act==='root')navigateBilling(null,null,'back');
  else navigateBilling(bill.platform,null,'back');
});
$('bill-back').onclick=()=>{if(bill.model!==null)navigateBilling(bill.platform,null,'back');else navigateBilling(null,null,'back');};
$('bill-viz').addEventListener('click',e=>{const row=e.target.closest('[data-bill-platform]');if(row)navigateBilling(row.dataset.billPlatform,null,'forward');});
$('bill-viz').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const row=e.target.closest('[data-bill-platform]');if(row){e.preventDefault();navigateBilling(row.dataset.billPlatform,null,'forward');}}});
let modelDetail={key:'',rows:null,error:''};
function detailKey(){
  if(bill.platform===null||bill.model===null)return '';
  return $('period').value+'|'+(bill.platform==='__free__'?'all':bill.platform)+'|'+bill.model;
}
function speedPanel(s){
  if(!s)return '';
  const head='<div class="tps-head"><span>'+T('输出速度')+'</span><span class="muted">'+T('测速请求 ')+num(s.tps_requests||0)+' / '+num(s.requests||0)+'</span></div>';
  if(!s.tps_requests)return '<div class="tps-panel" data-k="tps">'+head+'<p class="muted">'+T('该模型的请求没有耗时记录，无法计算输出速度。')+'</p></div>';
  const stat=(v,label)=>'<div><b>'+v+'</b><span>'+T(label)+'</span></div>';
  return '<div class="tps-panel" data-k="tps">'+head+'<div class="tps-stats">'+stat(tps(s.output_tps),'平均 tokens/s')+stat(tps(s.tps_median),'中位数')+stat(tps(s.tps_p10)+' – '+tps(s.tps_p90),'常见范围（P10–P90）')+stat(NUMF.secms(s.mean_ms),'平均响应时间')+'</div><p class="muted">'+T('输出 tokens ÷ 请求总耗时（含等待首个 token），只统计有耗时记录的成功请求。')+'</p></div>';
}
function ensureModelDetail(){
  const key=detailKey();
  if(!key||modelDetail.key===key)return;
  const pending=modelDetail={key,rows:modelDetail.rowsKey===key?modelDetail.rows:null,summary:modelDetail.rowsKey===key?modelDetail.summary:null,rowsKey:key,error:''};
  const parts=key.split('|');
  const q=new URLSearchParams({period:parts[0],platform:parts[1],model:parts.slice(2).join('|')});
  fetch('v1/stats?'+q,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();}).then(d=>{
    if(modelDetail===pending){modelDetail.rows=d.recent||[];modelDetail.summary=d.summary||null;}
  }).catch(e=>{if(modelDetail===pending){modelDetail.rows=[];modelDetail.error=e.message;}})
   .finally(()=>{if(modelDetail===pending){if(curView==='bill')renderBilling();else renderedStats.delete('bill');}});
}
function chartBuckets(mode,series,nowMs){
  const byDay=new Map((series||[]).map(p=>[p.day,p]));
  const key=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
  let points=[];
  if(mode==='total'){
    const byMonth={},byMonthCost={},byCached={},byInput={};
    (series||[]).forEach(p=>{const k=p.day.slice(0,7);byMonth[k]=(byMonth[k]||0)+p.tokens;byMonthCost[k]=(byMonthCost[k]||0)+(p.cost||0);byCached[k]=(byCached[k]||0)+(p.cached||0);byInput[k]=(byInput[k]||0)+(p.input||0);});
    const months=Object.keys(byMonth).sort();
    if(months.length){
      const parse=k=>[Number(k.slice(0,4)),Number(k.slice(5,7))-1];
      const [fy,fm]=parse(months[0]),[ly,lm]=parse(months[months.length-1]);
      for(let d=new Date(fy,fm,1);d<=new Date(ly,lm,1);d.setMonth(d.getMonth()+1)){
        const k=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');
        points.push({label:k.replace('-','/'),day:k,tokens:byMonth[k]||0,cost:byMonthCost[k]||0,
                     hitrate:byInput[k]?Math.round(100*byCached[k]/byInput[k]*100)/100:null});
      }
    }
  }else if(mode==='year'){
    const y=new Date(nowMs).getFullYear();
    for(let d=new Date(y,0,1);d<=new Date(nowMs);d.setDate(d.getDate()+1)){
      const p=byDay.get(key(d));
      points.push({label:(d.getMonth()+1)+'/'+d.getDate(),day:key(d),tokens:p?p.tokens:0,cost:p?(p.cost||0):0,hitrate:p?(p.hitrate??null):null});
    }
  }else if(mode==='month'){
    // rolling 30 days ending today, every day present (zero-filled)
    for(let i=29;i>=0;i--){const d=new Date(nowMs);d.setDate(d.getDate()-i);const p=byDay.get(key(d));points.push({label:(d.getMonth()+1)+'/'+d.getDate(),day:key(d),tokens:p?p.tokens:0,cost:p?(p.cost||0):0,hitrate:p?(p.hitrate??null):null});}
  }else{
    for(let i=6;i>=0;i--){const d=new Date(nowMs);d.setDate(d.getDate()-i);const p=byDay.get(key(d));points.push({label:(d.getMonth()+1)+'/'+d.getDate(),day:key(d),tokens:p?p.tokens:0,cost:p?(p.cost||0):0,hitrate:p?(p.hitrate??null):null});}
  }
  return points;
}
function moneyShort(n){
  if(!n)return '$0';
  if(n>=1000)return '$'+(n/1000).toFixed(1)+'k';
  if(n>=100)return '$'+Math.round(n);
  if(n>=10)return '$'+n.toFixed(0);
  if(n>=1)return '$'+n.toFixed(1);
  return '$'+n.toFixed(2);
}
let chartPts=[],chartMetric='tokens';
let chartState=null,chartRaf=0,chartKey='',chartAuxGen=0;
function paintChart(sc,withDots,withLabels,maxText){
  const W=sc.W,H=sc.H,pad=sc.pad;
  const defs='<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".26"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>';
  const maxNow=maxText!==undefined?maxText:sc.max;
  let grid='';
  for(const frac of [1/3,2/3,1]){
    const y=(H-pad)-(H-2*pad)*frac;
    grid+='<line x1="'+pad+'" x2="'+(W-pad)+'" y1="'+y.toFixed(1)+'" y2="'+y.toFixed(1)+'" stroke="var(--line)" stroke-width="1"/>';
    if(frac<1){const lab=sc.hit?(frac*100).toFixed(0)+'%':tok(maxNow*frac);
      grid+='<text x="'+(W-pad-4)+'" y="'+(y-3).toFixed(1)+'" text-anchor="end" class="gridlabel">'+lab+'</text>';}
  }
  let area='',line='',dots='';
  const xy=sc.xs.map((x,i)=>[x,H-pad-(H-2*pad)*sc.fs[i]]);
  if(sc.xs.length===1){dots='<circle cx="'+xy[0][0].toFixed(1)+'" cy="'+xy[0][1].toFixed(1)+'" r="3" fill="currentColor"/>';}
  else if(sc.xs.length>1){
    line='<polyline fill="none" stroke="currentColor" stroke-width="2" points="'+xy.map(c=>c[0].toFixed(1)+','+c[1].toFixed(1)).join(' ')+'"/>';
    area='<polygon fill="url(#ag)" points="'+pad+','+(H-pad)+' '+xy.map(c=>c[0].toFixed(1)+','+c[1].toFixed(1)).join(' ')+' '+(W-pad)+','+(H-pad)+'"/>';
    if(withDots)dots=sc.xs.map((x,i)=>'<circle cx="'+x.toFixed(1)+'" cy="'+xy[i][1].toFixed(1)+'" r="3" fill="currentColor"/>').join('');
  }
  setSvg($('chart'),defs+grid+area+line+dots);
  $('chartmax').textContent=sc.xs.length?(sc.hit?'100%':tok(maxNow)):T('暂无数据');
  if(withDots)chartPts=sc.points.map((p,i)=>({x:sc.xs[i],y:xy[i][1],...p}));
  if(withLabels){
    const labelsEl=$('chart-labels');const points=sc.points;
    if(sc.mode==='month'&&points.length){
      const stride=Math.max(1,Math.ceil(points.length/Math.max(2,Math.floor(labelsEl.clientWidth/64))));
      reconcile(labelsEl,points.map((p,i)=>({p,i})).filter(({i})=>i===0||i===points.length-1||(i%stride===0&&i<points.length-1-stride/2)).map(({p,i})=>'<span class="day" style="left:'+(sc.xs[i]/800*100).toFixed(2)+'%"><i>'+(sc.hit?((p.hitrate===null||p.hitrate===undefined)?'–':p.hitrate.toFixed(0)+'%'):moneyShort(p.cost))+'</i>'+esc(p.label)+'</span>').join(''));
    }else{
      const labels=points.length>2?[points[0].label,points[Math.floor((points.length-1)/2)].label,points[points.length-1].label]:points.length===2?[points[0].label,points[1].label]:[points.length?points[0].label:''];
      reconcile(labelsEl,labels.map(l=>'<span>'+esc(l)+'</span>').join(''));
    }
  }
}
function renderChart(){
  const series=lastData&&lastData.series||[];
  const points=chartBuckets(chartMode,series,(lastData.updated_at||0)*1000||Date.now());
  const hit=chartMetric==='hitrate';
  const val=p=>hit?(p.hitrate||0):p.tokens;
  const W=800,H=170,pad=8;
  const max=hit?100:Math.max(1,...points.map(val));
  const scene={points,hit,mode:chartMode,W,H,pad,max,
    xs:points.map((p,i)=>points.length>1?pad+i*(W-2*pad)/(points.length-1):W/2),
    fs:points.map(p=>Math.min(1.05,max?val(p)/max:0))};
  const key=chartMode+'|'+chartMetric;
  const switched=chartKey!==key;chartKey=key;const auxGen=switched?++chartAuxGen:chartAuxGen;const finishAux=()=>{if(auxGen===chartAuxGen)requestAnimationFrame(()=>{if(auxGen===chartAuxGen){$('chart-labels').classList.remove('chart-fade');$('chartmax').classList.remove('chart-fade');$('chart-note').classList.remove('chart-fade');$('chart').classList.remove('axis-fade');}});};if(switched){$('chart-labels').classList.add('chart-fade');$('chartmax').classList.add('chart-fade');$('chart-note').classList.add('chart-fade');$('chart').classList.add('axis-fade');}
  const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  cancelAnimationFrame(chartRaf);
  const from=(switched&&chartState&&chartState.fs.length&&scene.fs.length)?chartState:null;
  if(!from||reduce){chartState=scene;paintChart(scene,true,true);finishAux();return;}
  // 周期/指标切换：从上一条曲线按 x 重采样，rAF 逐帧插值滑到新曲线（纯 transform 级重绘，无布局动画）
  const srcN=from.fs.length,dstN=scene.fs.length;
  const sample=x01=>{if(srcN===1)return from.fs[0];const f=Math.max(0,Math.min(1,x01))*(srcN-1),i=Math.min(srcN-2,Math.floor(f)),r=f-i;return from.fs[i]*(1-r)+from.fs[i+1]*r;};
  const t0=performance.now(),dur=380,max0=from.max,max1=scene.max;
  const step=now=>{
    const t=Math.min(1,(now-t0)/dur),k=1-Math.pow(1-t,3);
    const maxNow=max0+(max1-max0)*k;
    const mid=Object.assign({},scene,{fs:scene.xs.map((x,i)=>{const x01=dstN>1?(x-pad)/(W-2*pad):0.5;const s=sample(x01);return s+(scene.fs[i]-s)*k;}),max:maxNow});
    chartState=mid; // 动画途中再切换：下一轮从当前画面续接，不跳变
    paintChart(mid,dstN<=30,false,scene.max);
    if(t<1)chartRaf=requestAnimationFrame(step);
    else{chartState=scene;paintChart(scene,true,true);finishAux();}
  };
  chartRaf=requestAnimationFrame(step);
}
let chartResizeTimer;
function scheduleChartResize(){clearTimeout(chartResizeTimer);chartResizeTimer=setTimeout(()=>{if(lastData&&$('chart').getBoundingClientRect().width>0)renderChart();},120);}
window.addEventListener('resize',scheduleChartResize);
// Sidebar transitions resize the content, not the window; redraw after its width settles.
if(typeof ResizeObserver!=='undefined')new ResizeObserver(scheduleChartResize).observe($('chartwrap'));
let lastWorkbench=[],lastAudit=[];
const wbOpen=new Set();
let wbShowAll=true;
function dotColor(s){
  if((s||'').indexOf('🔴')===0)return 'var(--bad)';
  if((s||'').indexOf('🟢')===0)return 'var(--ok)';
  if((s||'').indexOf('🟡')===0)return 'var(--warn)';
  return 'var(--muted)';
}
function wbDate(u){
  const m=/\[?(\d{4})-(\d{2})-(\d{2})/.exec(u||'');
  return m?m[2]+'-'+m[3]:'—';
}
function wbLine(k,v){return v?'<div class="wb-line"><span class="wb-k">'+k+'</span><span class="wb-v">'+esc(v)+'</span></div>':'';}
function renderWorkbench(d){
  if(d.workbench)lastWorkbench=d.workbench;
  const rows=lastWorkbench||[];
  const doingN=rows.filter(w=>w.doing).length;
  const localN=rows.filter(w=>w.source==='本机登记').length;
  $('wb-meta').textContent=(rows.length?(T('共享 Memory OS + 本机登记 · ')+rows.length+Tc(rows.length,' 个项目',' project',' projects')+(localN?T('（其中 ')+localN+T(' 个来自本机登记，共享 Memory OS 暂无进度）'):'')):T('共享 Memory OS 尚无项目进度'))+(d.workbench_error?' · '+T(d.workbench_error):'');
  const t=$('wb-toggle');
  t.style.display=rows.length>3?'':'none';
  t.textContent=wbShowAll?T('收起，只显示最近 3 个'):(T('展开全部 ')+rows.length+Tc(rows.length,' 个项目',' project',' projects'));
  const shown=wbShowAll?rows:rows.slice(0,3);
  reconcile($('workbench'),shown.map(w=>{
    const open=wbOpen.has(w.project);
    const noProgress=w.source==='本机登记'&&!w.updated&&!w.done&&!w.next;
    const date=wbDate(w.updated);
    return '<div class="wb-item'+(open?' open':'')+'"><button type="button" class="wb-head" aria-expanded="'+(open?'true':'false')+'" data-k="'+esc(w.project)+'">'
      +'<span class="dot" style="background:'+dotColor(w.status)+'"></span>'
      +'<span class="wb-name">'+esc(w.project)+'</span>'
      +(w.doing?'<span class="doing">doing</span>':'')
      +'<span class="wb-next">'+esc(w.next||w.updated||(w.source==='本机登记'?T('本机登记 · 暂无共享进度'):'—'))+'</span>'
      +(date==='—'?'':'<span class="wb-upd">'+esc(date)+'</span>')
      +'<span class="wb-chev">›</span></button>'
      +'<div class="wb-body"><div class="wb-body-in">'
      +(noProgress?'<p class="wb-empty">'+esc(T('本机已登记，共享 Memory OS 暂无该项目进度'))+'</p>':wbLine(T('当前状态'),T(w.state_text)||T(w.status))+wbLine(T('最近交接'),w.updated)+wbLine(T('做了什么'),w.done)+wbLine(T('下一步'),w.next))
      +'</div></div></div>';
  }).join('')||'');
}
$('workbench').addEventListener('click',e=>{
  const h=e.target.closest('.wb-head');if(!h)return;
  const item=h.parentElement,open=!item.classList.contains('open');
  item.classList.toggle('open',open);
  h.setAttribute('aria-expanded',open?'true':'false');
  if(open)wbOpen.add(h.dataset.k);else wbOpen.delete(h.dataset.k);
});
$('wb-toggle').onclick=()=>{wbShowAll=!wbShowAll;renderWorkbench(lastData||{});};
function renderAudit(d){
  if(d.audit)lastAudit=d.audit;
  const rows=lastAudit||[];
  reconcile(document.querySelector('#audit tbody'),rows.map(a=>
    '<tr><td><code class="file">'+esc(a.file)+'</code></td><td>'+esc(T(a.label))+'</td><td class="num">'+esc(a.mode||'—')+'</td><td>'+(a.has_key===null||a.has_key===undefined?'—':(a.has_key?T('是'):T('否')))+'</td><td>'+esc(T(a.target)||a.target||'—')+'</td><td>'+(a.warn?'<span class="doing">'+esc(T(a.warn))+'</span>':'—')+'</td></tr>').join('')
    ||'<tr><td colspan="6" class="muted">'+T('暂无')+'</td></tr>');
  const warns=rows.filter(a=>a.warn).length;
  $('audit-note').textContent=rows.length?(T('共 ')+rows.length+T(' 个文件 · 「含密钥」只报是/否，永不显示内容')+(warns?' · '+warns+T(' 项需要处理'):'')):'';
}
// Keep the latest snapshot for every destination, but only build the visible page.
const renderedStats=new Map();
function renderActiveStats(force=false){
  const d=lastData;if(!d)return;
  const key=[d.updated_at,d.period,d.platform,d.cost_mode,Math.floor(Date.now()/60000)].join('|');
  if(!force&&renderedStats.get(curView)===key)return;
  switch(curView){
    case 'overview':renderSummary(d);renderChart();renderOverview(d);break;
    case 'bill':renderBilling();break;
    case 'plat':renderPlatformTable(d);renderPlatformViz(d);break;
    case 'req':renderRecent(d);renderRequestSummary(d);break;
    case 'wb':renderWorkbench(d);break;
    case 'sys':renderSystem(d);renderAudit(d);break;
    case 'gt':renderGateTasks(d);break;
    default:return;
  }
  renderedStats.set(curView,key);
}
function render(d,options={}){
  if(!lastData||d.updated_at!==lastData.updated_at||d.cost_mode!==lastData.cost_mode)modelDetail.key='';
  lastData=d;
  if(d.gate_tasks)lastGate=d.gate_tasks;
  applyCostMode(d.cost_mode);
  const svc=SVC[d.service]||SVC.offline;
  $('svc').innerHTML='<span class="dot" style="background:'+svc[0]+'"></span>'+svc[1];
  $('updated').textContent=T('更新于 ')+new Date((d.updated_at||0)*1000).toLocaleString(LOCALE(),{hour12:false});
  const cur=$('platform').value;
  const knownPlatforms=[...new Set([...(platItems||[]).slice(1).map(x=>x.v),...(d.platforms||[]),...(cur!=='all'?[cur]:[])])].sort();
  platItems=[{v:'all',l:T('全部平台')}].concat(knownPlatforms.map(p=>({v:p,l:platformLabel(p)})));
  const platformOptions=platItems.map(x=>'<option value="'+esc(x.v)+'">'+esc(x.l)+'</option>').join('');
  if($('platform').__options!==platformOptions){$('platform').innerHTML=platformOptions;$('platform').__options=platformOptions;}$('platform').value=cur;
  ddSync(ddPlatEl||$('dd-platform'),platItems,$('platform').value);
  syncFilterChip();
  renderActiveStats(options.force===true);
}
function renderSummary(d){
  const s=d.summary||{};
  setNum($('c-req'),s.requests,'compact',compact(s.requests));
  reconcile($('c-req-s'),'<span data-k="summary">'+T('进行中 ')+nsp(s.pending_requests,'compact',compact(s.pending_requests),'span')+' · '+T('失败 ')+nsp(s.failed_requests,'compact',compact(s.failed_requests),'span')+'</span>');
  setNum($('c-act'),s.actual_tokens,'compact',compact(s.actual_tokens));
  reconcile($('c-act-s'),'<span data-k="summary">'+T('输入 ')+nsp(s.input_tokens,'compact',compact(s.input_tokens),'span')+' · '+T('输出 ')+nsp(s.output_tokens,'compact',compact(s.output_tokens),'span')+' · '+T('缓存 ')+nsp(s.cached_tokens,'compact',compact(s.cached_tokens),'span')+' · Jev '+nsp(s.jev_tokens,'compact',compact(s.jev_tokens),'span')+' · '+nsp(s.cost_actual_usd,'money',money(s.cost_actual_usd),'span')+'</span>');
  reconcile($('c-act-free'),officialMode()
    ?'<span data-k="official">'+T('无官方价（未计金额）')+' '+nsp(s.unpriced_tokens,'compact',compact(s.unpriced_tokens),'span')+' tokens · '+nsp(s.unpriced_requests,'num',num(s.unpriced_requests),'span')+Tc(s.unpriced_requests,' 请求',' request',' requests')+'</span>'
    :'<span data-k="summary">'+T('免费 tokens')+' '+nsp(s.free_tokens,'compact',compact(s.free_tokens),'span')+' · '+T('Local Model Router 用量')+' '+nsp(s.local_router_tokens,'compact',compact(s.local_router_tokens),'span')+'</span>');
  const ab=d.global_ab||{};
  setNum($('c-save'),ab.pairs?ab.saved:null,'tok',ab.pairs?'–':T('暂无对照'));
  reconcile($('c-save-s'),'<span data-k="summary">'+(ab.pairs?(num(ab.pairs)+T(' 组对照')+' · '+T('省 ')+num(ab.reduction_pct)+'% · '+money(savingsOf(d))):T('尚无实测对照'))+'</span>');
  setNum($('c-ms'),s.mean_ms||null,'secms','–');
  reconcile($('c-ms-s'),'<span data-k="summary">'+T('计时请求数 ')+nsp(s.timed_requests,'compact',compact(s.timed_requests),'span')+'</span>');
  reconcile($('c-tps'),'<span data-k="tps">'+T('输出速度 ')+(s.tps_requests?'<b'+dnA(s.output_tps,'tps')+'>'+tps(s.output_tps)+'</b> tokens/s · '+T('中位 ')+tps(s.tps_median):'–')+'</span>');
}
function renderPlatformTable(d){
  reconcile(document.querySelector('#plat tbody'),(d.by_platform||[]).map(g=>
    '<tr data-k="'+esc(g.platform)+'"><td>'+esc(platformLabel(g.platform))+'</td><td class="num">'+nsp(g.requests,'num',num(g.requests))+'</td><td class="num">'+nsp(g.measured_requests,'num',num(g.measured_requests))+'</td><td class="num">'+nsp(g.input_tokens,'num',num(g.input_tokens))+'</td><td class="num">'+nsp(g.output_tokens,'num',num(g.output_tokens))+'</td><td class="num">'+nsp(g.cost_actual_usd,'money',money(g.cost_actual_usd))+(officialMode()&&g.unpriced_requests?' <small class="muted">+'+num(g.unpriced_requests)+' '+T('无官方价')+'</small>':'')+'</td><td class="num'+(g.ab_pairs?' pos':'')+'">'+(g.ab_pairs?num(g.ab_saved_tokens)+((g.ab_saved_usd===null||g.ab_saved_usd===undefined)?'':' · '+money(g.ab_saved_usd)):'–')+'</td><td class="num">'+nsp(g.mean_ms,'ms',ms(g.mean_ms))+'</td></tr>').join('')||'<tr data-k="__empty"><td colspan="8" class="muted">'+T('暂无数据')+'</td></tr>');
}
function renderRecent(d){
  const rows=(d.recent||[]).slice(0,50);
  reconcile(document.querySelector('#recent tbody'),rows.map(r=>{
    const at=r.at?new Date(r.at*1000).toLocaleString(LOCALE(),{hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'–';
    const st=STATUS[r.status]||r.status||'–';
    return '<tr class="daylog-row" data-k="'+esc(r.id?String(r.id):'')+'" data-req-detail="'+esc(r.id?String(r.id):'')+'" title="'+T('点击查看这条请求的详细日志')+'"><td>'+esc(at)+'</td><td>'+esc(platformLabel(r.platform||'–'))+'</td><td>'+esc(r.model||'—')+'</td><td><span class="tag '+esc(r.status||'')+'">'+esc(st)+'</span></td><td class="num">'+num(r.before_est)+'</td><td class="num">'+num(r.after_est)+'</td><td class="num">'+num(r.saved_estimated)+'</td><td class="num">'+num(r.actual_input)+'</td><td class="num">'+num(r.actual_output)+'</td><td class="num">'+num(r.cached)+'</td><td class="num">'+ms(r.duration_ms!==undefined?r.duration_ms:r.total_ms)+'</td></tr>';
  }).join('')||'<tr data-k="__empty"><td colspan="11" class="muted">'+T('暂无数据')+'</td></tr>');
  $('recent-note').textContent=(d.recent&&d.recent.length>50)?(T('仅显示最近 50 条，共 ')+d.recent.length+Tc(d.recent.length,' 条',' entry',' entries')):'';
}
function renderSystem(d){
  $('log-service').textContent=d.logs&&d.logs.service||T('暂无记录');
  $('log-metrics').textContent=d.logs&&d.logs.metrics||T('暂无记录');
  if(d.hotkey)$('hk-cur').textContent=fmtHotkey(d.hotkey);
}
let lastGate=[],gtOpen=null,gtCat='all',gtTime='all';
const GT_WINDOWS={'1h':3600,'day':86400,'week':7*86400,'month':30*86400,'year':365*86400};

function fmtAt(ts){
  if(!ts)return '—';
  const d=new Date(ts*1000),diff=(Date.now()-d.getTime())/1000;
  if(diff<60)return T('刚刚');
  if(diff<3600)return Math.floor(diff/60)+T(' 分钟前');
  if(diff<86400)return Math.floor(diff/3600)+T(' 小时前');
  return (d.getMonth()+1)+'-'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
const GT_STATUS={running:T('运行中'),done:T('已完成'),failed:T('失败'),interrupted:T('已中断'),incomplete:T('后台未结束'),declined:T('已拦截'),remote_queued:T('另一台排队中'),remote_starting:T('另一台准备执行'),remote_running:T('另一台执行中'),remote_stopping:T('另一台停止中')};
function gtRowItem(t,i){
  const running=t.display_status==='running';
  const root=(t.root||'').split('/').filter(Boolean).pop()||t.root;
  const est=t.estimates||{};
  const mode=t.mode==='reuse-pack'?T('复用Pack'):t.mode==='initial-only'?'initial-only':T('逐轮');
  const head='<span class="gt-chip '+esc(t.display_status)+'">'+(running?'<span class="gt-live"></span>':'')+(GT_STATUS[t.display_status]||t.display_status)+'</span>'
    +'<span class="gt-name">'+esc(root)+'</span>'
    +'<span class="gt-sub">'+esc(t.platform||'')+(t.force_gate?' '+T('· 强制'):'')+' · '+esc(mode)+' · '+num((t.turns||[]).length)+Tc((t.turns||[]).length,' 轮',' turn',' turns')+' · '+fmtAt(t.started_at)+'</span>'
    +'<span class="wb-chev">›</span>';
  return '<div class="wb-item'+(i===gtOpen?' open':'')+'" data-i="'+i+'"><button class="wb-head" type="button" aria-expanded="'+(i===gtOpen?'true':'false')+'">'+head+'</button><div class="wb-body"><div class="wb-body-in">'+(i===gtOpen?gtDetailHTML(t):'')+'</div></div></div>';
}
function gtDetailHTML(t){
  const stream=t.stream||[],turns=t.turns||[];
  const est=t.estimates||{};
  let html='<div class="card"><div class="k">'+T('任务描述')+'</div><div class="gt-req">'+esc(t.request||'')+'</div>'
    +(t.pack_mode?'<div class="s">'+T('处理方式 ')+' '+esc(({filtered:T('已筛选'),bypass_small:T('小任务跳过'),full_fallback:T('筛选失败回退')})[t.pack_mode]||t.pack_mode)+'</div>':'')+'<div class="s">'+T('模式 ')+' '+esc(t.mode||'')+' · '+T('开始 ')+fmtAt(t.started_at)+(t.ended_at?(' · '+T('结束 ')+fmtAt(t.ended_at)):' · '+T('仍在运行'))+(t.exit_code!==undefined&&t.exit_code!==null?(' · '+T('退出码 ')+esc(t.exit_code)):'')+'<br>'+T('输出文件 ')+'<span class="filelink" data-open-output="1">'+esc(t.output||'—')+'</span>'+(t.error?'<br><span style="color:var(--warn)">⚠ '+esc(String(t.error))+'</span>':'')+'</div></div>'
    +(est.before!==undefined?'<div class="card" style="margin-top:8px"><div class="t-row" title="'+T('上下文打包估算：任务上下文原样 → Pack 后（字符法估算，只有走 Gate 的任务有）。负数表示打包后更大；小任务跳过或审核失败回退都可能发生。此处不含原生会话启动及后续工作，不能据此判断实际费用。')+'"><span>'+T('上下文打包：原样 → Pack 后')+'</span><span><b>'+tok(est.before)+' → '+tok(est.after)+'</b> <i>'+(est.pct!==null&&est.pct!==undefined?((est.pct>=0?'-':'')+est.pct+'%'):'')+'</i></span></div>'+(est.cost_usd!==null&&est.cost_usd!==undefined?'<div class="t-row" title="'+T('仅按打包内容及本地价表估算，未包括原生会话说明、工具、后续输入和输出；不是完整任务费用。')+'"><span>'+T('包内容估价')+'</span><span><b>$'+est.cost_usd.toFixed(2)+'</b>'+(est.model?' · '+esc(est.model):'')+'</span></div>':'')+'</div>':'');
  if(stream.length){
    html+='<table style="margin-top:10px"><thead><tr><th>#</th><th>'+T('类型')+'</th><th>'+T('执行内容')+'</th></tr></thead><tbody>'
      +stream.map((e,j)=>'<tr class="gt-turn" data-kind="stream" data-j="'+j+'"><td>'+(j+1)+'</td><td><span class="tag '+(e.k==='AI'?'prepared':e.k==='结果'?'success':'blocked')+'">'+esc(e.k)+'</span></td><td class="wrap">'+esc(e.s)+'</td></tr>').join('')
      +'</tbody></table><p class="muted" style="margin:8px 0 0">'+T('点击任意一行查看该步的完整原始日志（超长任务仅保留尾部）。')+'</p>';
  } else if(turns.length){
    html+='<table style="margin-top:10px"><thead><tr><th>#</th><th>'+T('时间')+'</th><th>'+T('端点')+'</th><th class="num">'+T('压缩前')+'</th><th class="num">'+T('压缩后')+'</th><th class="num">'+T('管理移除')+'</th><th class="num">'+T('耗时 ms')+'</th><th class="num">'+T('上游')+'</th></tr></thead><tbody>'
      +turns.map((e,j)=>'<tr class="gt-turn" data-kind="gate" data-j="'+j+'"><td>'+(j+1)+'</td><td>'+fmtAt(e.at)+'</td><td>'+esc((e.endpoint||'').replace('/v1/',''))+'</td><td class="num">'+num(e.request_before_tokens_estimated)+'</td><td class="num">'+num(e.request_after_tokens_estimated)+'</td><td class="num pos">'+(e.managed_tokens_removed_estimated?num(e.managed_tokens_removed_estimated):'–')+'</td><td class="num">'+ms(e.total_ms)+'</td><td class="num">'+esc(String(e.upstream_status||'–'))+'</td></tr>').join('')
      +'</tbody></table><p class="muted" style="margin:8px 0 0">'+T('逐轮网关事件；点击查看单轮完整日志。')+'</p>';
  } else {
    html+='<p class="muted" style="margin-top:10px">'+(t.display_status==='running'?T('运行中——执行日志在任务结束后可用。'):T('无逐轮执行记录。'))+'</p>';
  }
  return html;
}
function renderGateTasks(d){
  if(d.gate_tasks)lastGate=d.gate_tasks;
  const sec=$('gatetasks');
  if(curView!=='gt'){sec.style.display='none';return;}
  sec.style.display='block';  // 样式表默认隐藏非 overview 视图，必须写内联 'block'；'' 会落回 display:none 把整个区块连同筛选器藏掉
  if(!lastGate.length){gtOpen=null;reconcile($('gt-list'),'<span class="muted">'+T('暂无压缩任务')+'</span>');gtFilterLabels();return;}
  const win=gtTime==='all'?0:Date.now()/1000-GT_WINDOWS[gtTime];
  const view=lastGate.map((t,i)=>({t,i})).filter(({t})=>{
    const okCat=gtCat==='all'||(gtCat==='running'?t.display_status==='running'
      :gtCat==='done'?t.display_status==='done'
      :(t.display_status==='failed'||t.display_status==='interrupted'||t.display_status==='incomplete'||t.display_status==='declined'));
    return okCat&&(t.started_at||0)>=win;
  });
  const running=lastGate.filter(t=>t.display_status==='running').length;
  const filtered=gtCat!=='all'||gtTime!=='all';
  const c={running:0,done:0,bad:0};
  lastGate.forEach(t=>{c[t.display_status==='running'?'running':t.display_status==='done'?'done':'bad']++;});
  const gtSum=$('gt-sums');
  if(gtSum)gtSum.innerHTML='<span class="sum"><b>'+lastGate.length+'</b>'+T('总任务')+'</span><span class="sum"><i class="lgd" style="background:var(--accent)"></i><b>'+running+'</b>'+T('运行中')+'</span><span class="sum"><i class="lgd" style="background:var(--ok)"></i><b>'+c.done+'</b>'+T('已完成')+'</span><span class="sum"><i class="lgd" style="background:var(--warn)"></i><b>'+c.bad+'</b>'+T('失败/中断')+'</span>'
    +(filtered?'<span class="sum">'+T('筛选显示 ')+'<b>'+view.length+'</b></span>':'');
  const prop=$('gt-prop');
  if(prop){const pc={done:0,run:0,bad:0};
    lastGate.forEach(t=>{pc[t.display_status==='done'?'done':t.display_status==='running'?'run':'bad']++;});
    if(!prop.children.length)prop.innerHTML='<i class="pp-done"></i><i class="pp-run"></i><i class="pp-bad"></i>';
    for(const [index,key] of ['done','run','bad'].entries()){const segment=prop.children[index];segment.hidden=!pc[key];segment.style.flex=pc[key]+' 1 0%';}
    prop.setAttribute('aria-label',T('已完成')+' '+pc.done+' · '+T('运行中')+' '+pc.run+' · '+T('失败/中断')+' '+pc.bad);}
  gtFilterLabels();
  reconcile($('gt-list'),view.map(({t,i})=>gtRowItem(t,i)).join('')||'<span class="muted">'+T('无匹配任务')+'</span>');
  if(gtOpen!==null&&(gtOpen>=lastGate.length||!view.some(v=>v.i===gtOpen)))gtOpen=null;
}
$('gt-list').addEventListener('click',e=>{
  const head=e.target.closest('.wb-head');
  if(head){
    const item=head.parentElement;
    const open=item.classList.toggle('open');
    gtOpen=open?Number(item.dataset.i):null;
    if(open)reconcile(item.querySelector('.wb-body-in'),gtDetailHTML(lastGate[gtOpen]||{}));
    head.setAttribute('aria-expanded',String(open));
    return;
  }
  const item=e.target.closest('.wb-item');
  const gi=item?Number(item.dataset.i):gtOpen;
  const t=lastGate[gi]||{};
  const fl=e.target.closest('[data-open-output]');
  if(fl){
    openModal(T('输出文件内容 · ')+(t.output||'').split('/').pop(),'<p class="muted">'+T('读取中…')+'</p>');
    const gen=modalGen;
    fetch('v1/gate-task-output?id='+encodeURIComponent(t.task_id||''),{cache:'no-store'})
      .then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
      .then(d=>{
        if(gen!==modalGen)return;
        $('modal-body').innerHTML='<p class="muted" style="margin-top:0">'+esc(d.file)+(d.truncated?'（超过 1MB，仅显示尾部）':'')+'</p><pre>'+esc(d.content)+'</pre>';
      })
      .catch(err=>{if(gen!==modalGen)return;$('modal-body').innerHTML='<p class="muted">'+T('读取失败：')+esc(err.message)+T('（/tmp 文件可能已被清理）')+'</p>';});
    return;
  }
  const tr=e.target.closest('tr.gt-turn');if(!tr)return;
  gtOpen=gi;
  const j=Number(tr.dataset.j);
  if(tr.dataset.kind==='stream'){
    openModal(T('第 ')+(j+1)+T(' 步执行日志'),'<p class="muted">'+T('读取中…')+'</p>');
    const gen=modalGen;
    fetch('v1/gate-task-log?id='+encodeURIComponent(t.task_id||'')+'&i='+j,{cache:'no-store'})
      .then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
      .then(ev=>{if(gen!==modalGen)return;let pretty=String(ev.raw||'');try{pretty=JSON.stringify(JSON.parse(pretty),null,2);}catch(err){}
        $('modal-title').textContent=T('第 ')+(j+1)+T(' 步执行日志')+' · '+(ev.k||'');
        $('modal-body').innerHTML='<p class="muted">'+esc(ev.s||'')+'</p><pre>'+esc(pretty)+'</pre>';})
      .catch(err=>{if(gen!==modalGen)return;$('modal-body').innerHTML='<p class="muted">'+T('读取失败：')+esc(err.message)+'</p>';});
    return;
  }
  const ev=(t.turns||[])[j];if(ev)openModal(T('网关事件'),'<pre>'+esc(JSON.stringify(ev,null,2))+'</pre>');
});
const dialogMotion=new WeakMap(),dialogCancelBound=new WeakSet();
function dialogOpen(d){let state=dialogMotion.get(d)||{gen:0,anim:null};const wasOpen=d.open,cs=wasOpen?getComputedStyle(d):null,from=cs?{opacity:cs.opacity,transform:cs.transform}:null;state.gen++;const gen=state.gen;state.anim?.cancel();state.anim=null;dialogMotion.set(d,state);if(!d.open)d.showModal();if(REDUCE())return;const first=from?{opacity:from.opacity,transform:from.transform}:{opacity:0,transform:'translateY(6px) scale(.98)'};const anim=d.animate([first,{opacity:1,transform:'none'}],{duration:180,easing:'ease-out'});state.anim=anim;anim.onfinish=()=>{if(state.gen===gen&&state.anim===anim)state.anim=null;};}
function dialogClose(d,after){let state=dialogMotion.get(d)||{gen:0,anim:null};const gen=++state.gen;if(!d.open){state.anim?.cancel();state.anim=null;if(after)after();return;}const cs=getComputedStyle(d),from={opacity:cs.opacity,transform:cs.transform};state.anim?.cancel();state.anim=null;dialogMotion.set(d,state);const finish=()=>{if(state.gen!==gen||!d.open)return;state.anim=null;d.close();if(after)after();};if(REDUCE()){finish();return;}state.anim=d.animate([{opacity:from.opacity,transform:from.transform},{opacity:0,transform:'translateY(6px) scale(.98)'}],{duration:160,easing:'ease-in'});state.anim.onfinish=finish;}
function dialogCancelAnimation(d){if(dialogCancelBound.has(d))return;dialogCancelBound.add(d);d.addEventListener('cancel',e=>{e.preventDefault();if(d.dataset.busy==='1')return;dialogClose(d);});}
function openModal(title,html){modalGen++;$('modal-title').textContent=title;$('modal-body').innerHTML=html;dialogOpen($('modal'));}
function closeModal(){dialogClose($('modal'));modalGen++;dayLogSaved=null;}
$('modal').addEventListener('close',()=>{if(!$('modal').open)$('modal-body').replaceChildren();});
// askModal：confirm/prompt 的内联替代（Electron 不支持 window.prompt，原生弹窗体验也差）。
// opts.placeholder 存在=prompt 模式返回输入串（空输入返回 null），否则=confirm 模式返回 true；取消/Esc 一律 null。
function askModal(opts={}){return new Promise(resolve=>{
 const isPrompt=typeof opts.placeholder==='string',ov=document.createElement('dialog');ov.className='modal-backdrop';ov.setAttribute('aria-label',opts.title||T('确认'));
 ov.innerHTML='<div class="modal-panel ask-panel"><div class="modal-head"><span>'+esc(opts.title||T('确认'))+'</span><button type="button" class="ask-cancel" aria-label="'+T('关闭')+'">×</button></div><div class="modal-body">'+(opts.message?'<p>'+esc(opts.message)+'</p>':'')+(isPrompt?'<label>'+esc(opts.placeholder)+'<input class="ask-input" type="text" value="'+esc(opts.value||'')+'"></label>':'')+'<div class="ask-row"><button type="button" class="ask-cancel">'+T('取消')+'</button><button type="button" class="ask-ok">'+T('确定')+'</button></div></div></div>';
 let settled=false;const done=v=>{if(settled||!ov.isConnected)return;settled=true;const remove=()=>{ov.remove();resolve(v);};if(ov.open)dialogClose(ov,remove);else remove();};
 ov.addEventListener('close',()=>{if(!settled){settled=true;ov.remove();resolve(null);}},{once:true});
 ov.addEventListener('cancel',e=>{e.preventDefault();done(null);});
 ov.querySelectorAll('.ask-cancel').forEach(b=>b.onclick=()=>done(null));
 ov.querySelector('.ask-ok').onclick=()=>done(isPrompt?(ov.querySelector('.ask-input').value.trim()||null):true);
 const input=ov.querySelector('.ask-input');if(input)input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();ov.querySelector('.ask-ok').click();}});
 ov.addEventListener('click',e=>{if(e.target===ov)done(null);});document.body.appendChild(ov);dialogOpen(ov);(input||ov.querySelector('.ask-cancel')).focus();
});}
// Electron 自研壳的拖拽调size：四边/两下角热区 + 右下角把手视觉。Swift 壳/浏览器里
// window.panelShell 不存在，不渲染。岛体贴顶居中：宽度按「光标相对窗口中线×2」、
// 高度按光标 Y，热区始终跟手；顶边不可调（窗口顶锚定屏幕上沿）。
if (window.panelShell && typeof window.panelShell.resize==='function'){
  const grip=document.createElement('div');grip.id='panel-grip';grip.title=T('拖拽调整面板大小（边角均可拖）');
  grip.innerHTML='<i></i><i></i><i></i>';
  document.body.appendChild(grip);
  const zoneStyle=document.createElement('style');
  zoneStyle.textContent='#panel-resize-zone{position:fixed;z-index:9998}#panel-resize-zone.z-e{right:0;top:0;bottom:0;width:6px;cursor:ew-resize}#panel-resize-zone.z-w{left:0;top:0;bottom:0;width:6px;cursor:ew-resize}#panel-resize-zone.z-s{left:0;right:0;bottom:0;height:6px;cursor:ns-resize}#panel-resize-zone.z-se{right:0;bottom:0;width:26px;height:26px;cursor:nwse-resize}#panel-resize-zone.z-sw{left:0;bottom:0;width:16px;height:16px;cursor:nesw-resize}#panel-grip{position:fixed;right:7px;bottom:7px;width:30px;height:30px;z-index:9999;display:flex;align-items:flex-end;justify-content:center;gap:3px;cursor:nwse-resize;opacity:.45;pointer-events:none}#panel-grip i{width:11px;height:2px;background:var(--muted,#7E8695);border-radius:1px;transform:rotate(-45deg);margin:-4px 0}';
  document.head.appendChild(zoneStyle);
  let rzDir=null;
  const rzCompute=e=>{
    if(!rzDir)return;
    const cx=window.innerWidth/2;const p={};
    if(rzDir.indexOf('e')>=0&&rzDir!=='s')p.width=Math.round(2*(e.clientX-cx));
    if(rzDir.indexOf('w')>=0)p.width=Math.round(2*(cx-e.clientX));
    if(rzDir.indexOf('s')>=0)p.height=Math.round(e.clientY);
    if(p.width!==undefined||p.height!==undefined)window.panelShell.resize(p);
  };
  const rzEnd=()=>{rzDir=null;};
  [['se','se'],['sw','sw'],['e','e'],['w','w'],['s','s']].forEach(([dir,cls])=>{
    const z=document.createElement('div');z.id='panel-resize-zone';z.className='z-'+cls;
    z.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();rzDir=dir;z.setPointerCapture(e.pointerId);});
    z.addEventListener('pointermove',rzCompute);
    z.addEventListener('pointerup',rzEnd);z.addEventListener('pointercancel',rzEnd);
    document.body.appendChild(z);
  });
}
$('modal-close').onclick=closeModal;
$('modal').addEventListener('click',e=>{if(e.target===$('modal'))closeModal();});
document.addEventListener('keydown',e=>{
 const tab=e.target.closest('[role=tab]');
 if(tab&&['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){
  const tabs=[...tab.closest('[role=tablist]').querySelectorAll('[role=tab]')],i=tabs.indexOf(tab);
  const next=tabs[e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];
  e.preventDefault();next.focus();next.click();return;
 }
 if(e.key!=='Tab')return;
 const dialog=e.target.closest('dialog[open]');if(!dialog)return;
 const controls=[...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled):not(.dd-native),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(el=>el.getClientRects().length);
 if(!controls.length){e.preventDefault();return;}
 const first=controls[0],last=controls[controls.length-1];
 if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
 else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
});
$('modal').addEventListener('cancel',e=>{e.preventDefault();closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.dd.open').forEach(d=>ddClose(d,true));});
document.addEventListener('keydown',e=>{const target=e.target.closest('[role=button]:not(button)');if(target===e.target&&(e.key==='Enter'||e.key===' ')&&target.id!=='chart'&&target.id!=='import-drop'){e.preventDefault();target.click();}});
document.querySelectorAll('.logview').forEach(p=>p.addEventListener('click',()=>{
  openModal(p.id==='log-service'?T('服务日志 service.log'):T('指标日志 metrics.jsonl'),'<pre>'+esc(p.textContent)+'</pre>');
}));
function fmtHotkey(h){return (h.ctrl?'⌃':'')+(h.alt?'⌥':'')+(h.shift?'⇧':'')+(h.cmd?'⌘':'')+h.key;}
function savingsOf(d){
  const ab=d.global_ab||{};
  if(!ab.pairs)return null;
  return (d.by_platform||[]).reduce((sum,g)=>sum+(g.ab_saved_usd||0),0);
}
$('refresh').onclick=refresh;
$('period').onchange=$('platform').onchange=refresh;
$('auto').onchange=schedule;
document.querySelectorAll('#chart-tabs button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('#chart-tabs button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');chartMode=b.dataset.mode;renderChart();
});
const chartEl=$('chart');
let tipPending=null,tipRaf=0;
function nearestChartPoint(e){
  if(!chartPts.length||!e)return null;
  const rect=chartEl.getBoundingClientRect();
  const vx=(e.clientX-rect.left)/rect.width*800;
  let best=chartPts[0],bd=Infinity;
  for(const p of chartPts){const d=Math.abs(p.x-vx);if(d<bd){bd=d;best=p;}}
  return {p:best,rect};
}
function drawTip(e){
  tipRaf=0;
  const tip=$('charttip'),vline=$('chartline');
  const hit=nearestChartPoint(e);
  if(!hit){tip.classList.remove('show');vline.classList.remove('show');return;}
  const left=(hit.p.x/800)*hit.rect.width,top=(hit.p.y/170)*hit.rect.height;
  tip.classList.add('show');
  tip.style.left=Math.min(hit.rect.width-170,Math.max(0,left-80))+'px';
  tip.style.top=Math.max(0,top-46)+'px';
  tip.innerHTML='<b>'+esc(hit.p.label)+'</b> '+(chartMetric==='hitrate'
    ?(hit.p.hitrate===null||hit.p.hitrate===undefined?T('无输入'):T('命中率 ')+hit.p.hitrate.toFixed(1)+'%')
    :(tok(hit.p.tokens)+' tokens'+(hit.p.cost?' · '+money(hit.p.cost):'')));
  vline.classList.add('show');
  vline.style.left=left+'px';
}
// 单击数据点=打开悬停指向的那一天（整列都是命中区，不存在点不准的问题）。
chartEl.setAttribute('tabindex','0');chartEl.setAttribute('role','button');chartEl.setAttribute('aria-label',T('用量趋势：方向键选择日期，回车查看请求'));
let chartKeyIndex=-1;
chartEl.addEventListener('keydown',e=>{if(!chartPts.length)return;if(['ArrowLeft','ArrowRight','Home','End','Enter',' '].includes(e.key)){e.preventDefault();chartKeyIndex=e.key==='Home'?0:e.key==='End'?chartPts.length-1:chartKeyIndex<0||chartKeyIndex>=chartPts.length?chartPts.length-1:Math.max(0,Math.min(chartPts.length-1,chartKeyIndex+(e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0)));const point=chartPts[chartKeyIndex];if(e.key==='Enter'||e.key===' ')openDayLog(point);else chartEl.setAttribute('aria-label',point.label+' · '+num(point.tokens)+' tokens');}});
chartEl.addEventListener('click',e=>{
  const hit=nearestChartPoint(e);
  if(hit)openDayLog(hit.p);
});
let modalGen=0,dayLogSaved=null;
function openDayLog(p){
  if(!p||!p.day)return;
  dayLogSaved=null;
  openModal(T('请求日志 · ')+p.day,'<p class="muted">'+T('读取中…')+'</p>');
  const gen=modalGen; // openModal/closeModal 都会推进代次：关闭或换日期后，慢响应不再写回弹窗。
  const slowHint=setTimeout(()=>{const b=$('modal-body');if(gen===modalGen&&b.querySelector('p.muted'))b.innerHTML='<p class="muted">'+T('账本较大，统计需要几秒，仍在读取…')+'</p>';},3000);
  fetch('v1/stats?day='+encodeURIComponent(p.day)+'&platform=all',{cache:'no-store'})
    .then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(d=>{
      if(gen!==modalGen)return;
      const rows=d.day_recent||[];
      const agg=rows.reduce((a,r)=>{const i=r.actual_input||0,o=r.actual_output||0;a.tok+=i+o;a.input+=i;a.cached+=Math.min(r.cached||0,i);return a;},{tok:0,input:0,cached:0});
      const pct=agg.input?Math.round(100*agg.cached/agg.input*100)/100:null;
      const head=T('共 ')+num(d.day_total!==null&&d.day_total!==undefined?d.day_total:rows.length)+Tc(rows.length,' 条请求',' request',' requests')+' · '+tok(agg.tok)+' tokens'
        +(pct!==null?' · '+T('缓存命中率 ')+pct+T('%（口径=缓存读/实测输入）'):'')
        +(chartMetric==='hitrate'?' · '+T('当前为命中率视图，列表口径相同'):'');
      const body=rows.length?('<table><thead><tr><th>'+T('时间')+'</th><th>'+T('平台')+'</th><th>'+T('模型')+'</th><th>'+T('状态')+'</th><th class="num">'+T('实际输入')+'</th><th class="num">'+T('实际输出')+'</th><th class="num">'+T('缓存读')+'</th><th class="num">'+T('命中率')+'</th><th class="num">'+T('耗时 ms')+'</th><th>'+T('详情')+'</th></tr></thead><tbody>'
        +rows.map(r=>{
          const at=r.at?new Date(r.at*1000).toLocaleString(LOCALE(),{hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'–';
          const st=STATUS[r.status]||r.status||'–';
          const hr=(r.actual_input&&r.cached!==null&&r.cached!==undefined)?(Math.round(Math.min(r.cached,r.actual_input)/r.actual_input*1000)/10+'%'):'–';
          const cell='<td>'+esc(at)+'</td><td>'+esc(platformLabel(r.platform||'–'))+'</td><td>'+esc(r.model||'—')+'</td><td><span class="tag '+esc(r.status||'')+'">'+esc(st)+'</span></td><td class="num">'+num(r.actual_input)+'</td><td class="num">'+num(r.actual_output)+'</td><td class="num">'+num(r.cached)+'</td><td class="num">'+hr+'</td><td class="num">'+ms(r.duration_ms!==undefined?r.duration_ms:r.total_ms)+'</td>';
          const rid=r.id?String(r.id):'';
          return rid?('<tr class="daylog-row" data-req-detail="'+esc(rid)+'" title="'+T('点击查看这条请求的详细日志')+'">'+cell+'<td><button type="button" data-req-detail="'+esc(rid)+'">'+T('详情')+'</button></td></tr>')
                    :('<tr>'+cell+'<td class="muted">–</td></tr>');
        }).join('')+'</tbody></table><p class="muted" style="margin:8px 0 0">'+T('点击任意一行查看该请求的已存账本明细、耗时分段与可关联日志。')+'</p>')
        :'<p class="muted">'+T('这一天没有请求记录。')+'</p>';
      clearTimeout(slowHint);
      $('modal-title').textContent=T('请求日志 · ')+p.day;
      $('modal-body').innerHTML='<p class="muted" style="margin-top:0">'+head+'</p>'+body
        +((d.day_total||0)>rows.length?('<p class="muted">'+T('仅显示最近 300 条，共 ')+num(d.day_total)+Tc(d.day_total||0,' 条。',' entry.',' entries.')+'</p>'):'');
    })
    .catch(err=>{clearTimeout(slowHint);if(gen!==modalGen)return;$('modal-title').textContent=T('请求日志 · ')+p.day;$('modal-body').innerHTML='<p class="muted">'+T('读取失败：')+esc(err.message)+'</p>';});
}
function openRequestDetail(rid){
  if(!rid)return;
  // 只有从「当天列表」弹窗进来才存返回档；从请求视图直接打开时 modal-body 是空的，
  // 存空档再点返回会还原出空弹窗。
  if(($('modal-title').textContent||'').startsWith('请求日志')){
    // 先存滚动位置再摘内容：容器空了 scrollTop 就归零，顺序反了会存成 0。
    const savedTop=$('modal-body').scrollTop;
    const frag=document.createDocumentFragment();
    while($('modal-body').firstChild)frag.appendChild($('modal-body').firstChild);
    dayLogSaved={frag,scrollTop:savedTop,title:$('modal-title').textContent};
  }else dayLogSaved=null;
  const label=String(rid).length>24?String(rid).slice(0,24)+'…':String(rid);
  openModal(T('请求详情 · ')+label,'<p class="muted">'+T('读取中…')+'</p>');
  const gen=modalGen;
  fetch('v1/request-detail?id='+encodeURIComponent(rid),{cache:'no-store'})
    .then(async r=>{const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d;})
    .then(d=>{if(gen===modalGen)renderRequestDetail(d);})
    .catch(err=>{if(gen===modalGen)$('modal-body').innerHTML='<p class="muted">读取失败：'+esc(err.message)+'</p>';});
}
function backToDayLog(){
  if(!dayLogSaved)return;
  $('modal-body').replaceChildren(dayLogSaved.frag);
  $('modal-title').textContent=dayLogSaved.title;
  $('modal-body').scrollTop=dayLogSaved.scrollTop;
  dayLogSaved=null;
}
function renderRequestDetail(d){
  const r=d.request||{},t=d.timing||{};
  const at=r.at?new Date(r.at*1000).toLocaleString(LOCALE(),{hour12:false}):'–';
  const st=STATUS[r.status]||r.status||'–';
  const kv=(k,v)=>'<div class="rd-row"><span>'+k+'</span><b>'+v+'</b></div>';
  let html='<div class="center-actions"><button id="rd-back" type="button"'+(dayLogSaved?'':' style="display:none"')+'>‹ 返回当天列表</button></div>'
    +'<div class="card" style="margin-top:8px"><div class="k">'+T('记录 ID')+'</div><div class="s" style="overflow-wrap:anywhere">'+esc(r.id||d.id||'')+'</div>'
    +kv(T('平台 / 模型'),esc(platformLabel(r.platform||'–')+(r.platform==='deepai'&&r.client_platform?' · '+accessLabel(r.client_platform):(r.client_platform&&r.client_platform!==r.platform?' · '+T('客户端来源：')+platformLabel(r.client_platform):''))+' · '+(r.model||T('未知模型'))))
    +kv(T('状态'),esc(st))
    +(r.original_model?kv(T('原始模型名'),esc(r.original_model)):'')
    +(r.reasoning_effort?kv(T('思考档位'),esc(r.reasoning_effort)):'')
    +kv(T('时间'),esc(at))+'</div>';
  html+='<div class="card" style="margin-top:8px"><div class="k">'+T('供应商实测')+'</div>'
    +kv(T('实际输入'),num(r.actual_input))+kv(T('实际输出'),num(r.actual_output))
    +kv(T('缓存读'),num(r.cached))
    +(r.cache_creation!==null&&r.cache_creation!==undefined?kv(T('缓存写入'),num(r.cache_creation)):'')
    +kv(T('耗时'),ms(r.duration_ms)+' ms')+'</div>';
  if((r.before_est!==null&&r.before_est!==undefined)||(r.after_est!==null&&r.after_est!==undefined)){
    html+='<div class="card" style="margin-top:8px"><div class="k">'+T('打包估算（仅经 Gate 的请求，字符法估算）')+'</div>'
      +kv(T('估算 前 → 后'),num(r.before_est)+' → '+num(r.after_est))
      +kv(T('估算节省'),num(r.saved_estimated))+'</div>';
  }
  const hasTiming=t&&['prepare_ms','upstream_headers_ms','first_response_byte_ms','upstream_total_ms','total_ms','upstream_status','stream_completed'].some(k=>t[k]!==null&&t[k]!==undefined);
  if(hasTiming){
    html+='<div class="card" style="margin-top:8px"><div class="k">'+T('耗时分段（request_timings，未记录处显示 –）')+'</div>'
      +kv(T('准备'),ms(t.prepare_ms)+' ms')+kv(T('上游响应头'),ms(t.upstream_headers_ms)+' ms')
      +kv(T('首字节'),ms(t.first_response_byte_ms)+' ms')+kv(T('上游总耗时'),ms(t.upstream_total_ms)+' ms')
      +kv(T('端到端'),ms(t.total_ms)+' ms')
      +kv(T('端点'),esc(t.endpoint||'–'))
      +kv(T('上游状态'),t.upstream_status===null||t.upstream_status===undefined?'–':esc(String(t.upstream_status)))
      +kv(T('流式完整'),t.stream_completed===null||t.stream_completed===undefined?'–':(t.stream_completed?T('是'):T('否')))+'</div>';
  }else{
    html+='<p class="muted" style="margin-top:8px">'+T('该请求没有已保存的耗时分段记录。')+'</p>';
  }
  (d.logs||[]).forEach(l=>{
    html+='<div class="card" style="margin-top:8px"><div class="k">'+T('可关联日志 · ')+esc(l.source||'')+'</div><div class="s">'+esc(l.summary||'')+'</div>'
      +(l.request?'<div class="gt-req">'+esc(l.request)+'</div>':'')+'</div>';
  });
  if(d.notice)html+='<p class="muted" style="margin-top:8px">'+esc(d.notice)+'</p>';
  html+='<details style="margin-top:8px"><summary>'+T('保存字段原文（JSON，已脱敏）')+'</summary><pre>'+esc(JSON.stringify({request:r,timing:t},null,2))+'</pre></details>';
  $('modal-body').innerHTML=html;
}
chartEl.addEventListener('mousemove',e=>{
  tipPending=e;
  if(!tipRaf)tipRaf=requestAnimationFrame(()=>drawTip(tipPending));
});
chartEl.addEventListener('mouseleave',()=>{
  if(tipRaf){cancelAnimationFrame(tipRaf);tipRaf=0;}
  $('charttip').classList.remove('show');$('chartline').classList.remove('show');
});
$('metric').onclick=()=>{
  chartMetric=chartMetric==='tokens'?'hitrate':'tokens';
  $('metric').textContent=chartMetric==='tokens'?T('显示缓存命中率'):T('显示 tokens');
  renderChart();
};
document.querySelectorAll('.openapp').forEach(b=>b.onclick=async()=>{
  b.disabled=true;
  try{
    const r=await fetch('v1/open-app',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app:b.dataset.app})});
    const j=await r.json();
    $('open-note').textContent=j.ok?T('已发起打开'):T('打开失败');
  }catch(e){$('open-note').textContent=T('打开失败：')+e.message;}
  setTimeout(()=>{b.disabled=false;},1500);
});
let recording=false;
$('hk-rec').onclick=()=>{recording=true;$('hk-rec').textContent=T('按下组合键…（Esc 取消）');};
document.addEventListener('keydown',async e=>{
  if(!recording)return;
  if(e.key==='Escape'){recording=false;$('hk-rec').textContent=T('录制快捷键');return;}
  const key=e.key.length===1?e.key.toUpperCase():'';
  if(!/^[A-Z0-9]$/.test(key))return; // 只按修饰键时等待字母/数字
  e.preventDefault();e.stopPropagation();
  recording=false;$('hk-rec').textContent=T('录制快捷键');
  const body={key,ctrl:e.ctrlKey,cmd:e.metaKey,shift:e.shiftKey,alt:e.altKey};
  if(!body.ctrl&&!body.cmd){$('hk-note').textContent=T('至少需要 ⌃ 或 ⌘ 修饰键，避免占用裸字母键');return;}
  try{
    const r=await fetch('v1/settings/hotkey',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.error||('HTTP '+r.status));}
    $('hk-cur').textContent=fmtHotkey(body);
    $('hk-note').textContent=T('已保存，壳 App 几秒内自动生效。');
  }catch(err){$('hk-note').textContent=T('保存失败：')+err.message;}
},true);
let gtFold=false;
function gtFoldSync(){
  const bar=$('gt-filters');if(!bar)return;
  bar.classList.toggle('folded',gtFold);
  const cat=gtCat==='all'?T('全部'):gtCat==='running'?T('进行中'):gtCat==='done'?T('已完成'):T('失败/中断');
  const tm={all:T('全部'),'1h':T('1 小时'),day:T('一天'),week:T('一周'),month:T('一月'),year:T('一年')}[gtTime]||gtTime;
  $('gt-fsum').textContent=(gtCat!=='all'||gtTime!=='all')?(T('当前筛选：')+cat+' · '+tm):'';
}
const CAT_LABEL={all:T('全部'),running:T('进行中'),done:T('已完成'),failed:T('失败/中断')};
const TIME_LABEL={all:T('全部'),'1h':T('1 小时'),day:T('一天'),week:T('一周'),month:T('一月'),year:T('一年')};
function gtFilterLabels(){
  const cb=$('gt-cat-btn'),tb=$('gt-time-btn');
  if(!cb||!tb)return;
  cb.textContent=T('分类：')+CAT_LABEL[gtCat];
  tb.textContent=T('时间：')+TIME_LABEL[gtTime];
  cb.classList.toggle('filtering',gtCat!=='all');
  tb.classList.toggle('filtering',gtTime!=='all');
}
function syncGtMenu(menuId,v){
  const m=document.getElementById(menuId);
  if(m)m.querySelectorAll('.dd-it').forEach(x=>x.classList.toggle('on',x.dataset.v===v));
}
function wireGtFilters(){
  ddWire($('gt-cat-dd'),null,v=>{gtCat=v;syncGtMenu('gt-cat-menu',v);gtFilterLabels();renderGateTasks(lastData||{});});
  ddWire($('gt-time-dd'),null,v=>{gtTime=v;syncGtMenu('gt-time-menu',v);gtFilterLabels();renderGateTasks(lastData||{});});
  gtFilterLabels();
}

let searchVersion=0,searchOffset=0,searchQuery='',searchRecords=[];
function searchCard(x,i){
  return '<button type="button" class="scard" data-search-index="'+i+'"><span class="sc-head"><span class="sc-src">'+esc(x.source)+'</span><span class="sc-title">'+esc(x.id)+'</span></span><span class="sc-sum">'+esc(x.summary)+'</span></button>';
}
async function runSearch(more=false){
  const version=++searchVersion;
  if(!more){
    searchQuery=$('search-query').value.trim();searchOffset=0;searchRecords=[];
    $('search-results').textContent='';$('search-scroll').scrollTop=0;
    $('search-box').hidden=true;$('search-warn-box').hidden=true;
  }
  $('search-note').textContent=T('正在查询…');$('search-more').style.display='none';
  try{
    const r=await fetch('v1/search?q='+encodeURIComponent(searchQuery)+'&offset='+searchOffset);
    const d=await r.json();if(version!==searchVersion)return;
    if(!r.ok)throw new Error(T(d.error||'查询失败'));
    // 追加页用 insertAdjacentHTML：已有卡片节点不动，列表滚动位置自然保持。
    const base=searchRecords.length;
    searchRecords.push(...d.results);searchOffset=searchRecords.length;
    const fresh=d.results.map((x,i)=>searchCard(x,base+i)).join('');
    if(more)$('search-results').insertAdjacentHTML('beforeend',fresh);
    $('search-note').textContent=T('找到 ')+d.total+Tc(d.total,' 条',' result',' results')+' · '+d.notice+(d.warnings.length?' · '+T('有 ')+d.warnings.length+T(' 项读取提示（见下方折叠区）'):'');
    if(d.warnings.length){
      $('search-warn-head').textContent=T('有 ')+d.warnings.length+T(' 项读取提示（点击展开）');
      $('search-warn').textContent=d.warnings.join('\n');
      $('search-warn-box').hidden=false;
    }
    if(searchRecords.length){
      $('search-box').hidden=false;
      $('search-box-head').textContent=T('搜索结果')+' · '+searchRecords.length+Tc(searchRecords.length,' 条',' result',' results')+' ('+T('共 ')+d.total+Tc(d.total,' 条',' results',' results')+') · '+T('点击收起/展开');
      if(!more){$('search-box').open=true;$('search-scroll').scrollTop=0;$('search-results').innerHTML=fresh;}
    }else{
      $('search-box').hidden=true;
      if(!d.warnings.length)$('search-note').textContent=T('找到 0 条')+' · '+d.notice;
    }
    $('search-more').style.display=searchOffset<d.total?'':'none';
  }catch(e){if(version===searchVersion){$('search-note').textContent=T('搜索失败：')+e.message;if(!more&&!searchRecords.length)$('search-box').hidden=true;}}
}
$('search-form').onsubmit=e=>{e.preventDefault();runSearch();};
$('search-query').oninput=()=>{searchVersion++;$('search-more').style.display='none';};
$('search-more').onclick=()=>runSearch(true);
$('search-results').onclick=async e=>{const b=e.target.closest('[data-search-index]');if(!b)return;const x=searchRecords[+b.dataset.searchIndex];try{const r=await fetch('v1/search-detail?id='+encodeURIComponent(x.id));const d=await r.json();if(!r.ok)throw new Error(d.error);openModal(d.title,'<p class="muted">'+esc(d.source+' · '+d.location)+'</p><pre>'+esc(d.content)+'</pre>');}catch(err){openModal(T('读取失败'),'<p>'+esc(err.message)+'</p>');}};
let centerTasks=[],groupOutcomes=[],externalOutcomes=[],centerBusy=false;
let usageAlert={enabled:true,threshold:100000};
function taskUsage(t){const u=t.usage;if(!u)return '<p class="muted">'+T('本次任务用量：')+esc(t.usage_error||T('平台尚未报告。'))+'</p>';const over=usageAlert.enabled&&u.total_tokens>=usageAlert.threshold;return '<p class="'+(over?'usage-warning':'muted')+'">'+(over?T('用量提醒：已达到 ')+num(usageAlert.threshold)+T(' token 门槛。'):'')+(u.scope==='native_thread_total'?T('原生会话累计报告（含接续历史）'):u.final?T('本次任务已报告'):T('目前已报告'))+' '+num(u.total_tokens)+' token · '+T('输入 ')+num(u.input_tokens)+' / '+T('输出 ')+num(u.output_tokens)+' · '+T('缓存读取 ')+num(u.cached_input_tokens)+' / '+T('写入 ')+num(u.cache_write_input_tokens)+' · '+(u.reported_usd===null?T('金额未报告'):T('平台报告 $')+u.reported_usd.toFixed(4))+'</p>';}
async function loadUsageAlert(){try{usageAlert=await centerApi('center/usage-alert');$('usage-alert-enabled').checked=usageAlert.enabled;$('usage-alert-threshold').value=usageAlert.threshold;}catch(e){$('usage-alert-note').textContent=e.message;}}
$('usage-alert-form').onsubmit=async e=>{e.preventDefault();try{usageAlert=await centerApi('center/usage-alert',{enabled:$('usage-alert-enabled').checked,threshold:Number($('usage-alert-threshold').value)});$('usage-alert-note').textContent='提醒设置已保存。';await loadCenter();}catch(err){$('usage-alert-note').textContent=err.message;}};
loadUsageAlert();
const CENTER_STATUS={attention:T('需人工核对'),uncertain:T('启动状态待核对'),starting:T('准备执行'),running:T('执行中'),pending_review:T('待验收'),accepted:T('验收通过'),failed:T('执行失败'),stopped:T('已停止'),interrupted:T('意外中断'),validation_failed:T('验证失败'),remote_queued:T('另一台排队中'),remote_starting:T('另一台准备执行'),remote_running:T('另一台执行中'),remote_stopping:T('另一台停止中')};
async function centerApi(path,body){const r=await fetch('v1/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});if(r.status===403){showReconnect(T('服务已重启，连接令牌已更新，本次操作没有生效。'));throw new Error(T('服务已重启，请按横幅提示重开控制台'));}const d=await r.json();if(!r.ok)throw new Error(T(d.error||'操作失败'));return d;}
const CENTER_MODELS=__CENTER_MODELS__,CENTER_EFFORTS=__CENTER_EFFORTS__;
function effortLabel(v){return v==='ultra'?'ultra · '+T('多代理'):v==='ultracode'?'ultracode · '+T('动态工作流'):v==='native'?T('原生（无推理档）'):v;}
function centerEfforts(){const p=$('center-platform').value,tiers=CENTER_EFFORTS[p]?.[$('center-model').value]||[],old=$('center-reasoning').value;$('center-reasoning').innerHTML=tiers.map(v=>'<option value="'+esc(v)+'">'+esc(effortLabel(v))+'</option>').join('');$('center-reasoning').value=tiers.includes(old)?old:tiers.includes('medium')?'medium':tiers[0]||'';$('center-reasoning').disabled=p==='zcode'||tiers.length===1;}
$('center-model').onchange=centerEfforts;
$('center-platform').onchange=()=>{const p=$('center-platform').value;$('center-model').innerHTML=CENTER_MODELS[p].map(v=>'<option>'+esc(v)+'</option>').join('');centerEfforts();};$('center-platform').onchange();
function centerRequest(){return {root:$('center-project').value,platform:$('center-platform').value,goal:$('center-goal').value,acceptance:$('center-acceptance').value,checks:$('center-tests').checked?['tests']:[],reasoning:$('center-reasoning').value,model:$('center-platform').value==='zcode'?null:$('center-model').value};}
async function addProjectFolder(noteId,buttonId='add-root-btn'){
 const b=$(buttonId),note=$(noteId);if(b.disabled)return;b.disabled=true;if(note)note.textContent='';
 try{const d=await centerApi('center/pick-root',{});if(!d.path)return;await loadCenter();const cp=$('center-project');if([...cp.options].some(o=>o.value===d.path))cp.value=d.path;const sel=document.getElementById('butler-root');if(sel){sel.innerHTML=[...cp.options].map(o=>'<option value="'+esc(o.value)+'">'+esc(o.textContent)+'</option>').join('');sel.value=d.path;}if(note)note.textContent=T('项目文件夹已添加并选中。');}
 catch(e){if(note)note.textContent=e.message;}finally{b.disabled=false;}
}
$('add-root-btn').onclick=()=>addProjectFolder('center-note');
let scheduleSeen={},scheduleBusy=false;
const SCHEDULE_STATUS={waiting:T('等待预约时间'),dispatching:T('正在派发'),dispatched:T('已派发'),cancelled:T('已取消'),missed:T('已错过'),uncertain:T('派发状态待核对'),failed:T('派发失败'),remote_waiting:T('另一台等待预约时间'),remote_dispatching:T('另一台正在派发')};
async function loadSchedules(){if(scheduleBusy)return;scheduleBusy=true;try{const d=await centerApi('center/schedules');for(const s of d.schedules){const status=s.task_status||s.status;if(scheduleSeen[s.id]&&scheduleSeen[s.id]!==status&&!['pending_review','accepted','failed','stopped','interrupted','validation_failed'].includes(scheduleSeen[s.id])&&['pending_review','accepted','failed','stopped','interrupted','validation_failed'].includes(status)){const text=status==='pending_review'?T('预约任务有成果，等待验收。'):(T('预约任务状态：')+(CENTER_STATUS[status]||status));$('schedule-note').textContent=text;if('Notification' in window&&Notification.permission==='granted')new Notification(T('预约任务有新结果'),{body:text});}scheduleSeen[s.id]=status;}reconcile($('schedule-list'),d.schedules.map(s=>'<div class="center-record"><strong>'+esc(SCHEDULE_STATUS[s.status]||s.status)+(s.task_status?' · '+esc(CENTER_STATUS[s.task_status]||s.task_status):'')+'</strong><p>'+esc(s.task.goal)+'</p><p class="muted">'+esc(new Date(s.at*1000).toLocaleString(LOCALE()))+' · '+esc(s.task.platform)+(s.error?' · '+esc(s.error):'')+'</p>'+(s.status==='waiting'?'<button data-schedule-cancel="'+esc(s.id)+'">'+T('取消预约')+'</button>':'')+(s.task_id?'<p class="muted">'+T('任务编号 ')+esc(s.task_id)+T('；进度、停止和成果见任务卡片。')+'</p>':'')+'</div>').join('')||'<p class="muted">'+T('没有预约任务。')+'</p>');}catch(e){$('schedule-note').textContent=e.message;}finally{scheduleBusy=false;}}
$('schedule-form').onsubmit=async e=>{e.preventDefault();const b=$('schedule-create');b.disabled=true;try{const at=new Date($('schedule-at').value).getTime()/1000;if(!Number.isFinite(at))throw new Error(T('请选择开始时间'));await centerApi('center/schedule-create',{at,task:centerRequest()});$('schedule-note').textContent=T('预约已保存。');await loadSchedules();}catch(err){$('schedule-note').textContent=err.message;}finally{b.disabled=false;}};
$('schedule-list').onclick=async e=>{const b=e.target.closest('[data-schedule-cancel]');if(!b)return;b.disabled=true;try{await centerApi('center/schedule-cancel',{id:b.dataset.scheduleCancel});$('schedule-note').textContent=T('预约已取消。');await loadSchedules();}catch(err){$('schedule-note').textContent=err.message;}finally{b.disabled=false;}};
$('schedule-notify').onclick=async()=>{try{if(!('Notification' in window))throw new Error(T('当前浏览器不支持桌面通知'));const permission=await Notification.requestPermission();$('schedule-note').textContent=permission==='granted'?T('已开启本窗口在线期间的完成通知。'):T('通知未开启；状态仍在预约列表显示。');}catch(e){$('schedule-note').textContent=e.message;}};
setInterval(()=>{if(curView==='center'&&$('auto').checked&&!document.hidden)loadSchedules();},5000);
async function loadCenter(){if(centerBusy)return null;centerBusy=true;try{const d=await centerApi('center/tasks');centerTasks=d.tasks;groupOutcomes=d.group_outcomes||[];externalOutcomes=d.external_outcomes||[];const p=$('center-project');const want=(d.projects||[]).join('|');if(p.dataset.roots!==want){p.innerHTML=d.projects.map(x=>'<option value="'+esc(x)+'">'+esc(x.split('/').pop())+'</option>').join('');p.dataset.roots=want;}compareChoices();renderLibrary();reconcile($('center-list'),d.tasks.map(t=>'<div class="center-record"><strong>'+esc(CENTER_STATUS[t.status]||t.status)+' · '+esc(t.platform)+'</strong><p>'+esc(t.goal)+'</p>'+taskUsage(t)+'<p class="muted">'+esc(t.task_id)+(t.error?' · '+esc(t.error):'')+'</p><div class="center-actions"><button data-action="result" data-id="'+esc(t.task_id)+'">'+T('查看成果')+'</button><button data-action="changes" data-id="'+esc(t.task_id)+'">'+T('查看修改')+'</button>'+(['starting','running'].includes(t.status)?'<button data-action="stop" data-id="'+esc(t.task_id)+'">'+T('停止')+'</button>':'<button data-action="continue" data-id="'+esc(t.task_id)+'">'+T('接续任务')+'</button>')+(t.status==='pending_review'?'<button data-action="accept" data-id="'+esc(t.task_id)+'">'+T('确认验收通过')+'</button>':'')+(t.changes&&t.changes.length&&!t.rolled_back&&!['starting','running'].includes(t.status)?'<button data-action="rollback" data-id="'+esc(t.task_id)+'">'+T('撤回修改')+'</button>':'')+'</div></div>').join('')||'<p class="muted">'+T('尚未派发任务。输入目标后开始。')+'</p>');return true;}catch(e){$('center-note').textContent=e.message;return false;}finally{centerBusy=false;}}
$('center-form').onsubmit=async e=>{e.preventDefault();const b=$('center-submit');b.disabled=true;try{await centerApi('center/create',centerRequest());$('center-note').textContent=T('任务已派发，关闭窗口后继续执行。');await loadCenter();}catch(err){$('center-note').textContent=err.message;}finally{b.disabled=false;}};

$('center-diagnose').onclick=async()=>{const b=$('center-diagnose');b.disabled=true;try{const d=await centerApi('center/diagnostics');$('center-diagnostics').innerHTML=d.connections.map(x=>'<div class="center-record"><strong>'+esc(x.name)+'</strong><p>'+esc(x.status)+'</p>'+(x.category?'<p class="muted">'+T('事实分类：')+esc(x.category)+'</p>':'')+'<p class="muted">'+esc(x.last_error||x.last_task?.error||'')+'</p><pre>'+esc(JSON.stringify(x.last_task||{},null,2))+'</pre></div>').join('')+'<p class="muted">'+esc(d.local_fallback)+'</p>';}catch(e){$('center-diagnostics').textContent=e.message;}finally{b.disabled=false;}};
let libraryOffset=0;
function renderLibrary(){
 const tasks=[...centerTasks,...groupOutcomes];
 const select=$('library-project'),selected=select.value,roots=[...new Set([...tasks.filter(t=>t.artifacts?.length).map(t=>t.root),...externalOutcomes.map(t=>t.root).filter(Boolean)])];
 reconcile(select,'<option value="">'+T('全部项目')+'</option>'+roots.map(root=>'<option value="'+esc(root)+'">'+esc(root)+'</option>').join(''));
 if(roots.includes(selected))select.value=selected;
 const query=$('library-query').value.trim().toLocaleLowerCase();
 const rows=tasks.filter(t=>!select.value||t.root===select.value).flatMap(t=>(t.artifacts||[]).map(file=>({t,file}))).filter(x=>(x.file.path+' '+x.t.goal+' '+x.t.task_id).toLocaleLowerCase().includes(query));
 if(libraryOffset>=rows.length)libraryOffset=Math.max(0,Math.floor((rows.length-1)/25)*25);
 reconcile($('library-list'),rows.slice(libraryOffset,libraryOffset+25).map(({t,file})=>'<div class="center-record"><strong>'+esc(file.path)+'</strong><p>'+esc(t.goal)+'</p><p class="muted">'+esc(t.root.split('/').pop()+' · '+t.platform+' · '+(CENTER_STATUS[t.status]||t.status))+' · '+esc(t.task_id)+(t.source==='group'?' · 群聊回合':'')+'</p><button data-library-source="'+esc(t.source||'center')+'" data-library-task="'+esc(t.task_id)+'" data-library-path="'+esc(file.path)+'">'+T('预览归档')+'</button></div>').join('')||'<p class="muted">'+T('没有匹配的归档文件。')+'</p>');
 const extRows=externalOutcomes.filter(t=>!select.value||t.root===select.value).filter(t=>(t.file+' '+t.goal+' '+t.task_id).toLocaleLowerCase().includes(query));
 reconcile($('library-external'),(extRows.length?'<p class="subhead">'+T('Gate 任务产出（未归档，来自压缩任务注册表）')+'</p>':'')+extRows.map(t=>'<div class="center-record"><strong>'+esc(t.file)+'</strong><p>'+esc(t.goal||T('(无任务描述)'))+'</p><p class="muted">'+esc((t.root||'').split('/').pop()+' · '+t.platform+' · '+(GT_STATUS[t.status]||t.status))+' · '+esc(t.task_id)+'</p><button data-external-task="'+esc(t.task_id)+'">'+T('预览产出')+'</button></div>').join(''));
 reconcile($('library-outcomes'),groupOutcomes.filter(t=>(!select.value||t.root===select.value)&&(t.goal+' '+t.task_id).toLocaleLowerCase().includes(query)).slice(0,25).map(t=>'<details><summary>'+esc(T('群聊修改 · ')+t.goal.slice(0,80)+' · '+t.status)+'</summary><p>'+esc(t.note||'')+'</p><p>'+esc(t.archive_error||'')+'</p><pre>'+esc(JSON.stringify(t.changes,null,2))+'</pre></details>').join(''));
 $('library-count').textContent=T('共 ')+rows.length+T(' 个归档文件')+(rows.length?(' · '+T('当前 ')+(libraryOffset+1)+'–'+Math.min(rows.length,libraryOffset+25)):'')+(extRows.length?(' · '+T('外部产出 ')+extRows.length):'');
 $('library-prev').hidden=libraryOffset===0;$('library-next').hidden=libraryOffset+25>=rows.length;
}
$('library-query').oninput=$('library-project').onchange=()=>{libraryOffset=0;renderLibrary();};
$('library-prev').onclick=()=>{libraryOffset=Math.max(0,libraryOffset-25);renderLibrary();};
$('library-next').onclick=()=>{libraryOffset+=25;renderLibrary();};
$('library-list').onclick=e=>{const b=e.target.closest('[data-library-task]');if(b)showArtifact(b.dataset.libraryTask,b.dataset.libraryPath,0,b.dataset.librarySource).catch(err=>openModal(T('成果读取失败'),'<p>'+esc(err.message)+'</p>'));};
$('library-external').onclick=e=>{const b=e.target.closest('[data-external-task]');if(!b)return;const t=externalOutcomes.find(x=>x.task_id===b.dataset.externalTask);if(!t)return;openModal(T('外部产出 · ')+(t.file||'').split('/').pop(),'<p class="muted">'+T('读取中…')+'</p>');const gen=modalGen;fetch('v1/gate-task-output?id='+encodeURIComponent(t.task_id),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(d=>{if(gen!==modalGen)return;$('modal-body').innerHTML='<p class="muted" style="margin-top:0">'+esc(d.file)+(d.truncated?T('（超过 1MB，仅显示尾部）'):'')+'</p><pre>'+esc(d.content)+'</pre>';}).catch(err=>{if(gen!==modalGen)return;$('modal-body').innerHTML='<p class="muted">'+T('读取失败：')+esc(err.message)+'</p>';});};
async function showArtifact(id,path,offset=0,source='center'){
 const d=await centerApi((source==='group'?'groups':'center')+'/artifact?id='+encodeURIComponent(id)+'&path='+encodeURIComponent(path)+'&offset='+offset);
 openModal(T('成果 · ')+d.path,'<p class="muted">'+T('已归档文件 · ')+esc(d.sha256)+'</p>'+(d.kind==='image'?'<img id="artifact-image" style="max-width:100%;height:auto" alt="'+esc(d.path)+'" src="'+esc(d.data_url)+'">':'<p class="muted">'+T('字符位置 ')+d.offset+' / '+d.total+'</p><pre>'+esc(d.content)+'</pre><div class="center-actions">'+(d.offset>0?'<button id="artifact-prev">'+T('上一页')+'</button>':'')+(d.next_offset!==null?'<button id="artifact-next">'+T('下一页')+'</button>':'')+'</div>'));
 if(d.offset>0)$('artifact-prev').onclick=()=>showArtifact(id,path,Math.max(0,d.offset-32000),source).catch(e=>openModal(T('读取失败'),'<p>'+esc(e.message)+'</p>'));
 if(d.next_offset!==null)$('artifact-next').onclick=()=>showArtifact(id,path,d.next_offset,source).catch(e=>openModal(T('读取失败'),'<p>'+esc(e.message)+'</p>'));
 if(d.kind==='image')$('artifact-image').onerror=()=>{$('artifact-image').replaceWith(document.createTextNode(T('图片无法解码，请核对归档文件。')));};
}
$('modal-body').addEventListener('click',e=>{const b=e.target.closest('[data-artifact]');if(b)showArtifact(b.dataset.id,b.dataset.artifact).catch(err=>openModal('成果读取失败','<p>'+esc(err.message)+'</p>'));});
$('modal-body').addEventListener('click',e=>{
  if(e.target.closest('#rd-back')){backToDayLog();return;}
  const b=e.target.closest('[data-req-detail]');
  if(b)openRequestDetail(b.dataset.reqDetail);
});
document.querySelectorAll('[data-template]').forEach(b=>b.onclick=()=>{$('center-goal').value=b.dataset.template;$('center-goal').focus();});
let taskTemplates=[];
async function loadTemplates(){try{taskTemplates=(await centerApi('center/templates')).templates;reconcile($('template-list'),taskTemplates.map(t=>'<span><button data-template-use="'+t.id+'">'+esc(t.name)+'</button> <button data-template-remove="'+t.id+'" aria-label="'+T('移除 ')+' '+esc(t.name)+'">'+T('移除')+'</button></span>').join('')||'<p class="muted">'+T('还没有保存常用任务。')+'</p>');}catch(e){$('template-note').textContent=e.message;}}
$('template-save').onclick=async()=>{const b=$('template-save');b.disabled=true;try{await centerApi('center/template-save',{name:$('template-name').value,root:$('center-project').value,platform:$('center-platform').value,goal:$('center-goal').value,acceptance:$('center-acceptance').value,tests:$('center-tests').checked});$('template-name').value='';$('template-note').textContent=T('已保存。');await loadTemplates();}catch(e){$('template-note').textContent=e.message;}finally{b.disabled=false;}};
$('template-list').onclick=async e=>{const b=e.target.closest('button');if(!b)return;const t=taskTemplates.find(x=>x.id===(b.dataset.templateUse||b.dataset.templateRemove));if(!t)return;try{if(b.dataset.templateRemove){await centerApi('center/template-delete',{id:t.id});await loadTemplates();$('template-note').textContent=T('已移除常用任务。');}else{$('center-project').value=t.root;$('center-platform').value=t.platform;$('center-platform').onchange();$('center-goal').value=t.goal;$('center-acceptance').value=t.acceptance;$('center-tests').checked=t.checks.includes('tests');$('center-goal').focus();$('template-note').textContent=T('已填入 ')+t.name+T('，可调整后派发。');}}catch(e){$('template-note').textContent=e.message;}};
loadTemplates();
function compareRecords(){return [...centerTasks,...groupOutcomes].map(t=>({...t,selection:(t.source||'center')+':'+t.task_id}));}
function compareFiles(side){const task=compareRecords().find(t=>t.selection===$('compare-'+side+'-task').value);reconcile($('compare-'+side+'-file'),(task?.artifacts||[]).map(x=>'<option value="'+esc(x.path)+'">'+esc(x.path)+'</option>').join(''));}
function compareChoices(){for(const side of ['left','right']){const select=$('compare-'+side+'-task'),value=select.value;reconcile(select,compareRecords().filter(t=>t.artifacts?.length).map(t=>'<option value="'+esc(t.selection)+'">'+esc((t.source==='group'?T('群聊 · '):T('任务 · '))+t.goal.slice(0,60)+' · '+t.task_id.slice(0,8))+'</option>').join(''));if([...select.options].some(x=>x.value===value))select.value=value;compareFiles(side);}}
for(const side of ['left','right'])$('compare-'+side+'-task').onchange=()=>compareFiles(side);
$('compare-open').onclick=async()=>{const b=$('compare-open');b.disabled=true;'''
    r'''try{const d=await centerApi('center/compare',Object.fromEntries(['left','right'].map(side=>{const [source,task]=$('compare-'+side+'-task').value.split(':');return [side,{source,task,path:$('compare-'+side+'-file').value}];})));openModal(T('版本对比'),'<p>'+ (d.equal?T('两份内容完全一致。'):T('两份内容有变化。'))+'</p><div class="ovrow">'+['left','right'].map(side=>'<div><h3>'+esc((side==='left'?T('左侧'):T('右侧'))+' · '+d[side].path)+'</h3><p class="muted">'+esc(d[side].task)+'</p>'+(d[side].kind==='image'?'<img style="width:100%;height:auto" alt="'+esc(d[side].path)+'" src="'+esc(d[side].data_url)+'">':'<pre>'+esc(d[side].content)+'</pre>')+'</div>').join('')+'</div>');$('modal-body').querySelectorAll('img').forEach(img=>{img.onerror=()=>{const note=document.createElement('p');note.textContent=T('图片无法解码，请核对归档文件。');img.replaceWith(note);};});$('compare-note').textContent=T('已读取两份完整归档成果。');}catch(e){$('compare-note').textContent=e.message;}finally{b.disabled=false;}}
$('center-list').onclick=async e=>{const b=e.target.closest('[data-action]');if(!b)return;const t=centerTasks.find(x=>x.task_id===b.dataset.id);if(!t)return;b.disabled=true;try{const a=b.dataset.action;if(a==='result'){openModal(T('成果 · ')+t.platform,'<p>'+esc(CENTER_STATUS[t.status])+'</p><pre>'+esc(t.final||T('尚无最终答复，任务仍可能执行中。'))+'</pre><pre>'+esc(JSON.stringify({validation:t.validation||[],artifacts:t.artifacts||[],identity:{platform:t.platform,session_id:t.session_id,model:t.actual_model||t.model,model_verified:!!t.actual_model,reasoning:t.reasoning}},null,2))+'</pre>'+(t.artifacts||[]).map(x=>'<button data-artifact="'+esc(x.path)+'" data-id="'+esc(t.task_id)+'">'+T('预览 ')+esc(x.path)+'</button>').join(''));}else if(a==='changes'||a==='rollback'){const d=await centerApi('center/changes?id='+t.task_id);openModal(T('修改记录'),'<p>'+esc(T(d.note))+'</p>'+d.changes.map(x=>'<h3>'+esc(x.path)+(x.conflict?' '+T('· 有后续修改'):'')+'</h3><pre>'+esc(x.diff)+'</pre>').join(''));if(a==='rollback'&&await askModal({title:T('确认撤回'),message:T('已展示执行期间的修改。确认撤回？存在后续修改时会停止。')})){await centerApi('center/rollback',{id:t.task_id,confirmed:true});await loadCenter();}}else if(a==='continue'){const goal=await askModal({title:T('补充接续目标'),placeholder:T('接续目标…'),value:t.goal});if(goal){await centerApi('center/create',{root:t.root,platform:t.platform,goal,acceptance:t.acceptance,checks:t.checks,parent:t.task_id});await loadCenter();}}else{await centerApi('center/'+a,{id:t.task_id});await loadCenter();}}catch(err){$('center-note').textContent=err.message;}finally{b.disabled=false;}};
let butlerId=localStorage.getItem('cg-butler')||'',butlerPolling=false;
function openButler(){
  const proj=$('center-project');
  const opts=proj?[...proj.options].map(o=>'<option value="'+esc(o.value)+'"'+(o.value===proj.value?' selected':'')+'>'+esc(o.textContent)+'</option>').join(''):'';
  const inGroup=(typeof curView!=='undefined'&&curView==='group'&&typeof groupId!=='undefined'&&groupId);
  openModal(T('管家'),'<form id="butler-form" class="center-form"><label>'+T('项目')+'<select id="butler-root">'+(opts||'<option value="">'+T('(项目列表加载中，请稍后重开)')+'</option>')+'</select></label><div class="center-actions"><button type="button" id="butler-add-btn">'+T('添加文件夹')+'</button></div><label>'+T('交代管家')+'<textarea id="butler-request" maxlength="12000" required placeholder="'+T('例如：读取 TODO.md，告诉我还有哪些任务没完成')+'"></textarea></label><div><button id="butler-submit" type="submit">'+T('交给管家')+'</button></div></form><p id="butler-note" class="muted" aria-live="polite">'+(inGroup?T('当前在群聊视图：交代会自动带上这个群组，管家可直接查询和给成员派话。'):T('NVIDIA NIM · moonshotai/kimi-k3；需要网络。关掉窗口任务仍执行，重开这里看结果。'))+'</p><div id="butler-result"></div>');
  if(butlerId)pollButler();
}
$('butler-open').onclick=openButler;
async function checkButlerBadge(){try{const d=await centerApi('butler?id='+butlerId);const key=butlerId+':'+(d.ended_at||d.status);if((d.status==='done'||d.status==='failed'||d.status==='unavailable')&&localStorage.getItem('cg-butler-seen')!==key){const b=document.getElementById('butler-open');if(b&&!b.querySelector('.bdot')){const s=document.createElement('i');s.className='bdot';b.appendChild(s);}}}catch(e){}}
async function pollButler(){if(!butlerId||butlerPolling)return;const note=document.getElementById('butler-note');if(!note){checkButlerBadge();return;}butlerPolling=true;try{const d=await centerApi('butler?id='+butlerId);localStorage.setItem('cg-butler-seen',butlerId+':'+(d.ended_at||d.status));const bb=document.getElementById('butler-open');if(bb){const dot=bb.querySelector('.bdot');if(dot)dot.remove();}note.textContent=d.status==='running'?T('管家正在处理，已执行动作会保留。'):(d.error?T('管家本轮无法继续：')+d.error:T('管家已返回结果'));const result=document.getElementById('butler-result');if(result)result.innerHTML='<p style="white-space:pre-wrap">'+esc(d.reply||'')+'</p>'+d.actions.map(a=>'<details><summary>'+esc(a.tool+' · '+a.status)+'</summary><pre>'+esc(JSON.stringify(a.result||a.error||{},null,2))+'</pre></details>').join('');const submit=document.getElementById('butler-submit');if(submit)submit.disabled=d.status==='running';}catch(e){note.textContent=e.message;}finally{butlerPolling=false;}}
function butlerLabel(d){const names={nvidia:'NVIDIA NIM',openrouter:'OpenRouter',ollama:T('本地 Ollama'),custom:T('自定义')};return (names[d.provider]||'?')+' · '+(d.model||T('默认'));}
async function loadButlerModelSetting(){try{const d=await centerApi('settings/butler');const el=document.getElementById('butler-model-desc');if(el)el.textContent=T('当前：')+butlerLabel(d)+(d.has_key?T('（密钥已配置）'):'');}catch(e){const el=document.getElementById('butler-model-desc');if(el)el.textContent=T('当前：读取失败');}}
$('butler-model-edit').onclick=async()=>{
 let cur={provider:'nvidia',model:'',base_url:'',has_key:false};
 try{cur=await centerApi('settings/butler');}catch(e){}
 const provName={nvidia:T('NVIDIA NIM（复用 ZCode 密钥）'),openrouter:T('OpenRouter（复用 ZCode 密钥）'),ollama:T('本地 Ollama（Qwen 14B）'),custom:T('自定义（OpenAI 协议）')};
 openModal(T('管家模型'),'<form id="butler-model-form" class="center-form">'
  +'<label>'+T('供应商')+'<select id="bm-provider">'+Object.entries(provName).map(([v,l])=>'<option value="'+v+'"'+(cur.provider===v?' selected':'')+'>'+esc(l)+'</option>').join('')+'</select></label>'
  +'<label>'+T('模型名')+'<input id="bm-model" placeholder="'+T('如 moonshotai/kimi-k3')+'" value="'+esc(cur.model||'')+'"></label>'
  +'<label>'+T('接口地址（仅自定义供应商需要）')+'<input id="bm-url" placeholder="https://…/v1" value="'+esc(cur.base_url||'')+'"></label>'
  +'<label>'+T('API 密钥（留空=沿用已配置或 ZCode 配置）')+'<input id="bm-key" type="password" placeholder="'+(cur.has_key?T('已配置（不显示）'):T('未配置'))+'"></label>'
  +'<p class="muted">'+T('改完下一轮管家生效；NVIDIA/OpenRouter 留空密钥时自动复用 ZCode 里配置的密钥。')+'</p>'
  +'<div class="center-actions"><button type="submit">'+T('保存')+'</button></div></form>');
 $('butler-model-form').onsubmit=async ev=>{ev.preventDefault();
  try{const d=await centerApi('settings/butler',{provider:$('bm-provider').value,model:$('bm-model').value,base_url:$('bm-url').value,api_key:$('bm-key').value});
   const el=document.getElementById('butler-model-desc');if(el)el.textContent=T('当前：')+butlerLabel(d)+(d.has_key?T('（密钥已配置）'):'');
   closeModal();
  }catch(err){const el=document.getElementById('butler-model-desc');if(el)el.textContent=T('保存失败：')+err.message;}};
};
$('modal-body').addEventListener('click',e=>{if(e.target.closest('#butler-add-btn'))addProjectFolder('butler-note','butler-add-btn');});
$('modal-body').addEventListener('submit',async e=>{
  if(e.target.id!=='butler-form')return;
  e.preventDefault();
  const submit=document.getElementById('butler-submit');submit.disabled=true;
  try{
    const groupCtx=(typeof curView!=='undefined'&&curView==='group'&&typeof groupId!=='undefined'&&groupId)?(T('当前群组ID：')+groupId+' '):'';
    const d=await centerApi('butler',{root:(document.getElementById('butler-root')||{}).value||$('center-project').value,request:groupCtx+document.getElementById('butler-request').value});
    butlerId=d.id;localStorage.setItem('cg-butler',butlerId);await pollButler();
  }catch(err){document.getElementById('butler-note').textContent=err.message;submit.disabled=false;}
});
loadCenter();setInterval(()=>{if(curView==='center'&&$('auto').checked&&!document.hidden)loadCenter();if(document.getElementById('butler-note'))pollButler();else if(butlerId)checkButlerBadge();},4000);
let curView='overview';
const VIEWS={overview:['overview'],gt:['gt'],bill:['bill'],plat:['plat'],wb:['wb'],req:['req'],sys:['sys'],center:['center']};
let viewRenderGeneration=0;
const viewSections=[...document.querySelectorAll('main [data-view]')];
function syncFilterChip(){const period=$('period').value,visible=period!=='all'&&['overview','bill','plat','req'].includes(curView);$('filterchip').style.display=visible?'block':'none';if(visible)$('filterchip').textContent=T('筛选中：')+PERIODS[period]+T(' —— 下面所有数字只统计该范围；要看累计请切回「全部时间」。');}
function applyView(v){
  if(!VIEWS[v])return;
  curView=v;
  document.querySelectorAll('.nav-item').forEach(n=>{const on=n.dataset.v===v;n.classList.toggle('on',on);if(on)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
  const show=new Set(VIEWS[v]||[]);
  const reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  viewSections.forEach(el=>{
    const should=show.has(el.dataset.view),was=el.style.display!=='none';
    el.style.display=should?(el.classList.contains('grid')||el.classList.contains('ovrow')?'grid':'block'):'none';
    if(should&&!was&&!reduce)el.animate([{opacity:.65},{opacity:1}],{duration:140,easing:'ease-out'});
  });
  const hasFilters=['overview','bill','plat','req'].includes(v),routerFilters=v==='router';$('dd-period').hidden=!hasFilters;$('dd-platform').hidden=!hasFilters;$('dd-router-period').hidden=!routerFilters;$('dd-router-provider').hidden=!routerFilters;
  if(routerFilters)syncRouterFilters();
  syncFilterChip();
  updatePageGuide(v);
  document.querySelectorAll('.dd.open').forEach(d=>ddClose(d));
  // Paint the selected destination first. Rapid clicks cancel obsolete work.
  const generation=++viewRenderGeneration;
  requestAnimationFrame(()=>setTimeout(()=>{
    if(generation!==viewRenderGeneration||curView!==v)return;
    renderActiveStats();loadView(v);
  },0));
}
function loadView(v){
  if(v==='sys')loadButlerModelSetting();
  if(v==='memory')loadMemory();
  if(v==='center'){loadCenter();loadSchedules();}
  if(v==='group')groupLoad();
}
document.querySelectorAll('.nav-item').forEach(n=>n.onclick=()=>{applyView(n.dataset.v);window.scrollTo({top:0});});
$('recent').addEventListener('click',e=>{const b=e.target.closest('[data-req-detail]');if(b)openRequestDetail(b.dataset.reqDetail);});
const periodItems=[{v:'all',l:T('全部时间')},{v:'today',l:T('今天')},{v:'week',l:T('本周')},{v:'month',l:T('本月')}];
let platItems=[{v:'all',l:T('全部平台')}];
function ddSync(root,items,value){
  if(!root)return;
  reconcile(root.querySelector('.dd-menu'),items.map(it=>'<button type="button" role="menuitemradio" aria-checked="'+(it.v===value)+'" class="dd-it'+(it.v===value?' on':'')+'" data-v="'+esc(it.v)+'">'+esc(it.l)+'</button>').join(''));
  const it=items.find(x=>x.v===value)||items[0];
  root.querySelector('.dd-btn').textContent=it?it.l:value;
}
// 关闭时先挂 closing 播收起动画 ddOut，播完再真正隐藏；期间又被打开就只摘掉 closing。减少动态效果时直接隐藏。
function ddClose(root,restore=false){const was=root.classList.contains('open');root.classList.remove('open');root.querySelector('.dd-btn')?.setAttribute('aria-expanded','false');const m=root.querySelector('.dd-menu');const hide=()=>{root.__ddCloseT=null;root.classList.remove('closing');if(root.classList.contains('open'))return;if(m&&m.hasAttribute('popover')){try{if(m.matches(':popover-open'))m.hidePopover();}catch(e){}}};clearTimeout(root.__ddCloseT);if(was&&m&&!matchMedia('(prefers-reduced-motion: reduce)').matches){root.classList.add('closing');root.__ddCloseT=setTimeout(hide,180);}else hide();root.__ddOff?.();root.__ddOff=null;if(restore)root.querySelector('.dd-btn')?.focus();}
function ddWire(root,items,onPick){
  if(!root||root.__wired)return;root.__wired=true;
  const button=root.querySelector('.dd-btn'),menu=root.querySelector('.dd-menu');
  button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',menu.id);menu.setAttribute('role','menu');
  const open=()=>{document.querySelectorAll('.dd.open').forEach(d=>{if(d!==root)ddClose(d);});root.classList.add('open');button.setAttribute('aria-expanded','true');menu.style.left='0px';const bounds=menu.getBoundingClientRect();if(bounds.right>innerWidth-16)menu.style.left=Math.min(0,innerWidth-16-bounds.right)+'px';};
  button.addEventListener('click',e=>{e.stopPropagation();if(root.classList.contains('open'))ddClose(root);else open();});
  button.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();open();const choices=menu.querySelectorAll('.dd-it');(e.key==='ArrowUp'?choices[choices.length-1]:menu.querySelector('.on')||choices[0])?.focus();}});
  menu.addEventListener('keydown',e=>{const choices=[...menu.querySelectorAll('.dd-it')],i=choices.indexOf(document.activeElement);if(!choices.length)return;if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();choices[e.key==='Home'?0:e.key==='End'?choices.length-1:(i+(e.key==='ArrowDown'?1:-1)+choices.length)%choices.length].focus();}if(e.key==='Escape'){e.preventDefault();e.stopPropagation();ddClose(root,true);}if(e.key==='Tab')ddClose(root);});
  menu.addEventListener('click',e=>{const it=e.target.closest('.dd-it');if(!it)return;ddClose(root,true);onPick(it.dataset.v);});
  root.addEventListener('focusout',e=>{if(!root.contains(e.relatedTarget))ddClose(root);});
}
// 原生 <select> 外观统一：原生控件保留为值的唯一来源（隐藏），dd 外观覆盖其上；选择时同步触发 input/change。
let ddSelSeq=0,ddSelObs=null;
function ddSelect(sel){
  if(!sel||sel.tagName!=='SELECT'||!sel.parentNode||sel.multiple||sel.dataset.ddNative!==undefined||sel.style.display==='none'||(sel.__dd&&sel.__dd.isConnected&&sel.__dd.contains(sel)))return;
  const wrap=document.createElement('span'),btn=document.createElement('button'),menu=document.createElement('div');
  wrap.className='dd dd-select';btn.type='button';btn.className='dd-btn';menu.className='dd-menu';menu.id='dd-sel-menu-'+(++ddSelSeq);menu.setAttribute('role','listbox');
  const pop='showPopover' in menu;if(pop)menu.setAttribute('popover','manual');
  btn.setAttribute('aria-haspopup','listbox');btn.setAttribute('aria-expanded','false');btn.setAttribute('aria-controls',menu.id);
  if(sel.getAttribute('aria-label'))btn.setAttribute('aria-label',sel.getAttribute('aria-label'));
  sel.parentNode.insertBefore(wrap,sel);
  wrap.appendChild(sel);wrap.appendChild(btn);wrap.appendChild(menu);
  sel.classList.add('dd-native');sel.tabIndex=-1;sel.setAttribute('aria-hidden','true');
  sel.__dd=wrap;
  const isOpen=()=>{try{return menu.matches(':popover-open')}catch(e){return false}};
  const sync=()=>{const opts=[...sel.options],cur=sel.selectedIndex;btn.textContent=opts[cur]?opts[cur].textContent:'';btn.disabled=sel.disabled;menu.innerHTML=opts.map((o,i)=>'<button type="button" role="option" class="dd-it'+(i===cur?' on':'')+'" data-i="'+i+'" aria-selected="'+(i===cur)+'"'+(o.disabled?' disabled':'')+'>'+esc(o.textContent)+'</button>').join('');};
  sync();
  new MutationObserver(sync).observe(sel,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['disabled','selected','label']});
  ['value','selectedIndex','disabled'].forEach(k=>{const d=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,k);Object.defineProperty(sel,k,{configurable:true,get(){return d.get.call(this)},set(v){d.set.call(this,v);sync();}});});
  sel.addEventListener('change',sync);
  if(sel.form)sel.form.addEventListener('reset',()=>setTimeout(sync,0));
  sel.addEventListener('focus',()=>btn.focus());
  const place=()=>{if(!isOpen())return;const r=btn.getBoundingClientRect();menu.style.maxHeight='280px';menu.style.minWidth=r.width+'px';const below=innerHeight-r.bottom-12,above=r.top-12,ledger=!!sel.closest('#mw-root .mw-ledger'),up=!ledger&&below<Math.min(menu.scrollHeight,280)&&above>below,room=up?above:below;menu.style.maxHeight=Math.max(ledger?0:80,Math.min(280,room))+'px';menu.style.left=Math.max(8,Math.min(r.left,innerWidth-8-menu.offsetWidth))+'px';const h=menu.offsetHeight;menu.style.top=(up?Math.max(8,r.top-4-h):r.bottom+4)+'px';};
  const close=()=>ddClose(wrap);
  const onScroll=e=>{if(!menu.contains(e.target))ddClose(wrap);};
  const open=()=>{document.querySelectorAll('.dd.open').forEach(d=>{if(d!==wrap)ddClose(d);});wrap.classList.add('open');btn.setAttribute('aria-expanded','true');if(pop){try{if(!isOpen())menu.showPopover();}catch(e){}place();}menu.querySelector('.on')?.scrollIntoView({block:'nearest'});if(!wrap.contains(document.activeElement))btn.focus({preventScroll:true});const dlg=wrap.closest('dialog');const onCancel=e=>{e.preventDefault();e.stopImmediatePropagation();ddClose(wrap,true);};const onEsc=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();ddClose(wrap,true);}};if(dlg)dlg.addEventListener('cancel',onCancel,true);document.addEventListener('keydown',onEsc,true);window.addEventListener('resize',close);window.addEventListener('scroll',onScroll,true);wrap.__ddOff=()=>{if(dlg)dlg.removeEventListener('cancel',onCancel,true);document.removeEventListener('keydown',onEsc,true);window.removeEventListener('resize',close);window.removeEventListener('scroll',onScroll,true);};};
  const picks=()=>[...menu.querySelectorAll('.dd-it:not(:disabled)')];
  btn.addEventListener('mousedown',e=>{if(wrap.classList.contains('open'))e.preventDefault();});
  btn.addEventListener('click',e=>{e.stopPropagation();if(wrap.classList.contains('open'))ddClose(wrap);else open();});
  btn.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(!wrap.classList.contains('open'))open();const c=picks();(e.key==='ArrowUp'?c[c.length-1]:menu.querySelector('.on:not(:disabled)')||c[0])?.focus();}else if(e.key==='Escape'&&wrap.classList.contains('open')){e.preventDefault();e.stopPropagation();ddClose(wrap,true);}else if(e.key==='Tab'&&wrap.classList.contains('open'))ddClose(wrap);});
  menu.addEventListener('keydown',e=>{const c=picks(),i=c.indexOf(document.activeElement);if(!c.length)return;if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();c[e.key==='Home'?0:e.key==='End'?c.length-1:(i+(e.key==='ArrowDown'?1:-1)+c.length)%c.length].focus();}else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();ddClose(wrap,true);}else if(e.key==='Tab')ddClose(wrap);});
  menu.addEventListener('mousedown',e=>e.preventDefault());
  menu.addEventListener('click',e=>{const it=e.target.closest('.dd-it');if(!it||it.disabled)return;ddClose(wrap,true);const i=+it.dataset.i;if(i!==sel.selectedIndex){sel.selectedIndex=i;sel.dispatchEvent(new Event('input',{bubbles:true}));sel.dispatchEvent(new Event('change',{bubbles:true}));}});
  wrap.addEventListener('focusout',e=>{const t=e.relatedTarget;if(t&&!wrap.contains(t))ddClose(wrap);});
}
function ddSelectAll(root){root=root||document;if(root.tagName==='SELECT')ddSelect(root);root.querySelectorAll('select').forEach(s=>ddSelect(s));}
function ddSelectBoot(){try{if(!ddSelObs&&document.body){ddSelObs=new MutationObserver(recs=>recs.forEach(r=>r.addedNodes.forEach(n=>{if(n.nodeType===1)ddSelectAll(n);})));ddSelObs.observe(document.body,{childList:true,subtree:true});}ddSelectAll(document);}catch(e){window.__ddSelErr=String(e).slice(0,80);}}
ddSelectBoot();
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ddSelectBoot);
let ddPeriodEl=null,ddPlatEl=null,ddRouterPeriodEl=null,ddRouterProviderEl=null,tailTried=0,uiWired=false;
function bootTail(){
  if(uiWired||tailTried>=20)return;tailTried++;
  try{
    ddPeriodEl=ddPeriodEl&&ddPeriodEl.__wired?ddPeriodEl:$('dd-period');
    ddPlatEl=ddPlatEl&&ddPlatEl.__wired?ddPlatEl:$('dd-platform');
    ddRouterPeriodEl=ddRouterPeriodEl&&ddRouterPeriodEl.__wired?ddRouterPeriodEl:$('dd-router-period');
    ddRouterProviderEl=ddRouterProviderEl&&ddRouterProviderEl.__wired?ddRouterProviderEl:$('dd-router-provider');
    if(!ddPeriodEl||!ddPlatEl||!ddRouterPeriodEl||!ddRouterProviderEl)throw new Error('dd nodes missing');
    ddWire(ddPeriodEl,periodItems,v=>{$('period').value=v;ddSync(ddPeriodEl,periodItems,v);refresh();});
    ddWire(ddPlatEl,platItems,v=>{const sel=$('platform');sel.innerHTML=platItems.map(x=>'<option value="'+esc(x.v)+'">'+esc(x.l)+'</option>').join('');sel.value=v;ddSync(ddPlatEl,platItems,v);refresh();});
    ddWire(ddRouterPeriodEl,periodItems,v=>setRouterFilters(v,routerProvider));
    ddWire(ddRouterProviderEl,routerProviderItems,v=>setRouterFilters(routerPeriod,v));
    ddSync(ddPeriodEl,periodItems,'all');
    initRouterFilters();
    syncRouterFilters();
    $('router-show-all').onclick=()=>setRouterFilters('all',routerProvider);
    if(!uiWired){document.addEventListener('click',e=>{document.querySelectorAll('.dd.open').forEach(d=>{if(!d.contains(e.target))ddClose(d);});});}
    try{if(localStorage.getItem('cg-side')==='mini')document.body.classList.add('sidemini');}catch(e){}
    $('side-toggle').setAttribute('aria-expanded',String(!document.body.classList.contains('sidemini')));
    const st=$('side-toggle');if(st)st.onclick=()=>{const m=document.body.classList.toggle('sidemini');st.setAttribute('aria-expanded',String(!m));try{localStorage.setItem('cg-side',m?'mini':'full')}catch(e){}};
    const ti=$('themeicon');if(ti)ti.onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'warm':'dark');
    const sd=$('side-default');if(sd)sd.onclick=()=>{const t=$('side-toggle');if(t)t.onclick();};
    wireGtFilters();
    document.querySelectorAll('.ovlink').forEach(el=>el.onclick=()=>applyView(el.dataset.goto));
    $('ov-gt').addEventListener('click',e=>{
      const r=e.target.closest('.mrow');if(!r||r.dataset.gi===undefined)return;
      applyView('gt');gtOpen=+r.dataset.gi;renderGateTasks(lastData||{});
      const openItem=document.querySelector('#gt-list .wb-item.open');if(openItem)openItem.scrollIntoView({block:'start'});
    });
    $('ov-req').addEventListener('click',e=>{
      const r=e.target.closest('.mrow');if(!r||r.dataset.ri===undefined)return;
      applyView('req');renderActiveStats();
      const tb=document.querySelector('#recent tbody');const tr=tb&&Array.from(tb.children).filter(x=>!x.dataset.kLeaving)[+r.dataset.ri];
      if(tr){tr.scrollIntoView({block:'center'});tr.classList.remove('row-flash');void tr.offsetWidth;tr.classList.add('row-flash');}
    });
    applyView('overview');
    uiWired=true;
    refresh({automatic:true});
  }catch(e){window.__tailErr=String(e).slice(0,80);}
}
document.addEventListener('click',e=>{document.querySelectorAll('.dd.open').forEach(d=>{if(!d.contains(e.target))ddClose(d);});});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootTail);else bootTail();
setTimeout(bootTail,500);setTimeout(bootTail,1500);setTimeout(bootTail,4000);
</script></body></html>''')


PAGE = PAGE.replace('__CENTER_MODELS__',json.dumps(MODEL_CATALOG)).replace('__CENTER_EFFORTS__',json.dumps(MODEL_EFFORTS))

from console.group_ui import CSS as GROUP_CSS, HTML as GROUP_HTML, JS as GROUP_JS

PAGE = PAGE.replace('</style>', GROUP_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="center"', '<button type="button" class="nav-item" data-v="group" title="群聊"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h12v8H6l-4 3z"/></svg><span>群聊</span></button>\n<button type="button" class="nav-item" data-v="center"', 1)
PAGE = PAGE.replace('</main>', GROUP_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const VIEWS={overview:', GROUP_JS + '\nconst VIEWS={group:["group"],overview:', 1)
from console.import_ui import CSS as IMPORT_CSS, HTML as IMPORT_HTML, JS as IMPORT_JS
PAGE = PAGE.replace('</style>', IMPORT_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="group"', '<button type="button" class="nav-item" data-v="files" title="文件处理"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 1h6l3 3v11H4zM10 1v4h3"/></svg><span>文件处理</span></button>\n<button type="button" class="nav-item" data-v="group"', 1)
PAGE = PAGE.replace('</main>', IMPORT_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const VIEWS={group:', IMPORT_JS + '\nconst VIEWS={files:["files"],group:', 1)


from console.memory_ui import CSS as MEMORY_CSS, HTML as MEMORY_HTML, JS as MEMORY_JS
PAGE = PAGE.replace('</style>', MEMORY_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-toggle"', '<button type="button" class="nav-item" data-v="memory" title="记忆" role="button" tabindex="0"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2h8a2 2 0 0 1 2 2v10H5a2 2 0 0 1-2-2zM3 11h10M6 5h4M6 8h3"/></svg><span>记忆</span></button>\n<button type="button" class="nav-toggle"', 1)
PAGE = PAGE.replace('</main>', MEMORY_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const VIEWS={files:', MEMORY_JS + '\nconst VIEWS={memory:["memory"],files:', 1)

# Local Model Router integration: keep the original AppCore as service owner.
from console.router_ui import CSS as ROUTER_CSS, HTML as ROUTER_HTML, JS as ROUTER_JS, EN as ROUTER_EN
PAGE = PAGE.replace('</style>', ROUTER_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="memory"', '<button type="button" class="nav-item" data-v="router" title="模型路由" role="button" tabindex="0"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="1" y="6" width="4" height="4" rx="1"/><rect x="11" y="1" width="4" height="4" rx="1"/><rect x="11" y="11" width="4" height="4" rx="1"/><path d="M5 8h3V3h3M8 8v5h3"/></svg><span>模型路由</span></button>\n<button type="button" class="nav-item" data-v="memory"', 1)
PAGE = PAGE.replace('</main>', ROUTER_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const T=s=>', 'for(const [k,v] of Object.entries(' + json.dumps(ROUTER_EN, ensure_ascii=False) + ')){if(!(k in EN))EN[k]=v;}\nconst T=s=>', 1)
PAGE = PAGE.replace('const VIEWS={memory:', ROUTER_JS + '\nconst VIEWS={router:["router"],memory:', 1)
PAGE = PAGE.replace("if(v==='memory')loadMemory();", "if(v==='memory')loadMemory();if(v==='router')loadRouter();", 1)
PAGE = PAGE.replace("hidden=v==='memory'", "hidden=(v==='memory'||v==='router')")


from console.quota_ui import CSS as QUOTA_CSS, HTML as QUOTA_HTML, JS as QUOTA_JS, EN as QUOTA_EN
PAGE = PAGE.replace('</style>', QUOTA_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="plat"', '<button type="button" class="nav-item" data-v="quota" title="订阅额度"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2"/></svg><span>订阅额度</span></button>\n<button type="button" class="nav-item" data-v="plat"', 1)
PAGE = PAGE.replace('</main>', QUOTA_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const T=s=>', 'Object.assign(EN,' + json.dumps(QUOTA_EN, ensure_ascii=False) + ');\nconst T=s=>', 1)
PAGE = PAGE.replace('const VIEWS={router:', QUOTA_JS + '\nconst VIEWS={quota:["quota"],router:', 1)
PAGE = PAGE.replace("if(v==='memory')loadMemory();", "if(v==='quota')loadQuota();if(v==='memory')loadMemory();", 1)


from console.wallet_ui import CSS as WALLET_CSS, HTML as WALLET_HTML, JS as WALLET_JS, EN as WALLET_EN
PAGE = PAGE.replace('</style>', WALLET_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="quota"', '<button type="button" class="nav-item" data-v="wallet" title="模型钱包"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="4" width="12" height="9" rx="2"/><path d="M2 7h12M10 10h2"/></svg><span>模型钱包</span></button>\n<button type="button" class="nav-item" data-v="quota"', 1)
PAGE = PAGE.replace('</main>', WALLET_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const T=s=>', 'for(const [k,v] of Object.entries(' + json.dumps(WALLET_EN, ensure_ascii=False) + ')){if(!(k in EN))EN[k]=v;}\nconst T=s=>', 1)
PAGE = PAGE.replace('const VIEWS={quota:', WALLET_JS + '\nconst VIEWS={wallet:["wallet"],quota:', 1)
PAGE = PAGE.replace("if(v==='quota')loadQuota();", "if(v==='wallet')loadWallet({automatic:true});if(v==='quota')loadQuota();", 1)


from console.git_ui import CSS as GIT_CSS, HTML as GIT_HTML, JS as GIT_JS, EN as GIT_EN
PAGE = PAGE.replace('</style>', GIT_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="req"', '<button type="button" class="nav-item" data-v="git" title="项目同步"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="4" r="2"/><circle cx="11.5" cy="12" r="2"/><path d="M5.5 6v3a1.5 1.5 0 0 0 1.5 1.5h2.5"/></svg><span>项目同步</span></button>\n<button type="button" class="nav-item" data-v="req"', 1)
PAGE = PAGE.replace('</main>', GIT_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const T=s=>', 'for(const [k,v] of Object.entries(' + json.dumps(GIT_EN, ensure_ascii=False) + ')){if(!(k in EN))EN[k]=v;}\nconst T=s=>', 1)
PAGE = PAGE.replace('const VIEWS={wallet:', GIT_JS + '\nconst VIEWS={git:["git"],wallet:', 1)
PAGE = PAGE.replace("if(v==='quota')loadQuota();", "if(v==='git')loadGit();if(v==='quota')loadQuota();", 1)
PAGE = PAGE.replace("if(curView==='router')loadRouter();", "if(curView==='router')loadRouter();if(curView==='git')loadGit();", 1)


from console.todo_ui import CSS as TODO_CSS, HTML as TODO_HTML, JS as TODO_JS, EN as TODO_EN
PAGE = PAGE.replace('</style>', TODO_CSS + '\n</style>', 1)
PAGE = PAGE.replace('<button type="button" class="nav-item" data-v="files"', '<button type="button" class="nav-item" data-v="todo" title="待办"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 8.2l2 2 4-4.4"/></svg><span>待办</span></button>\n<button type="button" class="nav-item" data-v="files"', 1)
PAGE = PAGE.replace('</main>', TODO_HTML + '\n</main>', 1)
PAGE = PAGE.replace('const T=s=>', 'for(const [k,v] of Object.entries(' + json.dumps(TODO_EN, ensure_ascii=False) + ')){if(!(k in EN))EN[k]=v;}\nconst T=s=>', 1)
PAGE = PAGE.replace('const VIEWS={git:', TODO_JS + '\nconst VIEWS={git:', 1)
PAGE = PAGE.replace('function syncFilterChip(){', 'VIEWS.todo=["todo"];\nfunction syncFilterChip(){', 1)
PAGE = PAGE.replace("if(v==='git')loadGit();", "if(v==='git')loadGit();if(v==='todo')loadTodo();", 1)
# 原生浮窗用 ?mini=todo 打开：启动收尾（bootTail）里默认进总览，这里改成直接进待办。
PAGE = PAGE.replace("    applyView('overview');\n    uiWired=true;", "    applyView(todoMini?'todo':'overview');\n    uiWired=true;", 1)


# ---------------- Git 同步分类（只读） ----------------
GIT_SYNC_HOME_DEFAULT = os.path.expanduser('~/.local/state/context-gate/git-sync')
GIT_ERR_MARKERS = ('出错', '失败', '阻止', '冲突', '超时', '通知发送失败')
GIT_NOTICE_LOCK = threading.Lock()
GIT_NOTIFY_THROTTLE = 6 * 3600


def git_sync_home():
    return os.path.expanduser(os.environ.get('GITSYNC_HOME') or GIT_SYNC_HOME_DEFAULT)


def scrub_git_message(text):
    """日志消息进入 JSON 前：先复用现有 redact_text，再额外遮蔽 URL 凭据、
    Authorization/Bearer、token/key/password 类片段，并截断到 512。"""
    out = redact_text(str(text))
    out = re.sub(r'(?i)(https?://)([^/\s:@]+):([^@\s/]+)@', r'\1[REDACTED]:[REDACTED]@', out)
    out = re.sub(r'(?i)(https?://)([^/\s@]{8,})@', r'\1[REDACTED]@', out)
    out = re.sub(r'(?i)(bearer\s+|authorization\s*:\s*(?:bearer\s+)?)([^\s,}\"]{16,})', r'\1[REDACTED]', out)
    out = re.sub(r'(?i)\b(token|key|password|secret|credential)\b\s*[:=]\s*[^\s,}\"]+', r'\1=[REDACTED]', out)
    return out[:512]


def git_error_judge(status, last_result, reason):
    """status conflict/blocked 直接判错；其余状态仅当整体或某个分号片段以错误
    前缀开头、或含完整错误短语时判错，普通文案里的『权限/密钥』不误判。
    paused/disabled 不算 error。"""
    if status == 'conflict':
        return True, 'conflict'
    if status == 'blocked':
        return True, 'blocked'
    blob = ((last_result or '') + ' ' + (reason or '')).strip()
    if not blob:
        return False, ''
    if blob.startswith(('出错', '阻止', '超时')) \
            or '写入被拒' in blob or '通知发送失败' in blob or '补写出错' in blob:
        return True, 'error'
    for segment in blob.split('；'):
        seg = segment.strip()
        if seg.startswith(('出错', '失败', '阻止', '超时')) \
                or '写入被拒' in seg or '通知发送失败' in seg or '补写出错' in seg:
            return True, 'error'
    return False, ''


def classify_git_event(message):
    """一行日志 -> (kind, result)。无法可靠判断时归 info，绝不伪造 pull/push。
    已解决/恢复行单独标 resolved，不算冲突；『按规则不自动合并』是警告归 warning。"""
    m = (message or '').strip()
    if '已解决' in m or '恢复自动同步' in m:
        return 'resolved', 'ok'
    if '不自动合并' in m or '本轮不推送' in m or '基线分支' in m and '新提交' in m:
        return 'warning', 'info'
    if '冲突' in m:
        return 'conflict', 'conflict'
    if m.startswith('阻止') or '已拦下' in m or '本轮不提交' in m:
        return 'blocked', 'blocked'
    if m.startswith('出错') or '补写出错' in m or '写入被拒' in m or '通知发送失败' in m \
            or m.startswith('MemoryOS 补写出错'):
        return 'error', 'error'
    if m.startswith('自动提交'):
        return 'commit', 'ok'
    if m.startswith('已推送') or m.startswith('推送'):
        if '失败' in m:
            return 'error', 'error'
        return 'push', 'ok'
    if m.startswith('尾部追加自动合并'):
        return 'merge', 'ok'
    mm = re.match(r'^(快进|合并)\s+(\S+)\s+→\s+\S+', m)
    if mm:
        label = mm.group(2)
        if label.startswith('origin/'):
            return 'pull', 'ok'
        return 'merge', 'ok'
    if m.startswith('结果：'):
        if '已解决' in m or '恢复自动同步' in m:
            return 'resolved', 'ok'
        if '冲突' in m:
            return 'conflict', 'conflict'
        if '阻止' in m:
            return 'blocked', 'blocked'
        if '出错' in m or '失败' in m or '超时' in m:
            return 'error', 'error'
        if '已推送' in m:
            return 'push', 'ok'
        if '自动提交' in m:
            return 'commit', 'ok'
        if '无变化' in m:
            return 'skip', 'ok'
        return 'info', 'info'
    if m.startswith('跳过') or '防重入' in m or '本轮跳过' in m:
        return 'skip', 'skip'
    return 'info', 'info'


def parse_git_logs(home):
    """只读解析同步日志。只接受普通文件，拒绝符号链接，避免被带出日志目录。"""
    log_dir = os.path.join(home, 'logs')
    rows = []
    try:
        names = sorted(n for n in os.listdir(log_dir)
                       if n.startswith('git-sync-') and n.endswith('.log'))
    except OSError:
        return rows
    for name in names:
        path = os.path.join(log_dir, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for line in lines:
            m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}) \[([0-9a-f]+)\] (?:\[([^\]]+)\] )?(.*)$', line.strip())
            if not m:
                continue
            at, run_id, repo, msg = m.groups()
            kind, result = classify_git_event(msg)
            rows.append({'at': at, 'run_id': run_id, 'repo': repo,
                         'kind': kind, 'result': result,
                         'message': scrub_git_message(msg)})
    return rows


def git_sync_relocate(body):
    name = body.get('name')
    path = body.get('path')
    if not isinstance(name, str) or not 1 <= len(name) <= 120 or name.startswith('-'):
        raise ValueError('请选择要重新定位的项目')
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise ValueError('请选择项目文件夹')
    home = Path(git_sync_home())
    registry = json.loads((home/'registry.json').read_text())
    if not any(r.get('name') == name for r in registry.get('repos', [])):
        raise ValueError('项目尚未登记，请刷新后重试')
    result = subprocess.run([sys.executable, str(home/'gitsync.py'), 'set', name, 'path', path],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(scrub_git_message((result.stderr or result.stdout).strip())[:240] or '未能更新项目位置')
    return {'ok': True, 'message': '项目位置已更新，下一轮将检查同步'}


def _git_registered(name):
    """校验项目名（同 relocate 规则）并返回登记项；未登记则拒绝。"""
    if not isinstance(name, str) or not 1 <= len(name) <= 120 or name.startswith('-'):
        raise ValueError('请选择项目')
    home = Path(git_sync_home())
    registry = json.loads((home/'registry.json').read_text())
    for r in registry.get('repos', []):
        if isinstance(r, dict) and r.get('name') == name:
            return home, r
    raise ValueError('项目尚未登记，请刷新后重试')


def _git_cli(home, args, fallback):
    result = subprocess.run([sys.executable, str(home/'gitsync.py')] + args,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError(scrub_git_message((result.stderr or result.stdout).strip())[:240] or fallback)


def git_sync_toggle(body):
    home, r = _git_registered(body.get('name'))
    on = body.get('on')
    if not isinstance(on, bool):
        raise ValueError('请选择开启或关闭')
    if on and not r.get('remote_url'):
        raise ValueError('这个项目没连接 GitHub，无法开启同步')
    _git_cli(home, ['set', r['name'], 'enable' if on else 'disable'], '未能更改同步设置')
    return {'ok': True, 'message': '已开启同步，下一轮开始' if on else '已关闭同步：只取回 GitHub 上的版本信息，不改本机文件'}


def git_sync_retry(body):
    home, r = _git_registered(body.get('name'))
    # 后台跑一轮，不等结果；引擎自带防重入锁和网络超时，控制台不会被卡住。
    subprocess.Popen([sys.executable, str(home/'gitsync.py'), 'run', '--only', r['name']],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)
    return {'ok': True, 'message': '已开始重新同步，约 1 分钟后刷新查看结果'}


def git_sync_command(body, action):
    home, r = _git_registered(body.get('name'))
    if action not in ('pause', 'resume', 'resolve'):
        raise ValueError('未知操作')
    _git_cli(home, [action, r['name']], '操作未完成')
    return {'ok': True, 'message': {'pause': '已暂停自动同步', 'resume': '已恢复自动同步，下一轮开始',
                                    'resolve': '已标记解决，下一轮恢复同步'}[action]}


def git_sync_reveal(body):
    home, r = _git_registered(body.get('name'))
    path = os.path.realpath(r.get('path') or '')
    if not r.get('path') or not os.path.exists(path):
        raise ValueError('找不到项目文件夹，可能已移动或硬盘未连接')
    subprocess.run(['open', '-R', path], capture_output=True, timeout=15)
    return {'ok': True, 'message': '已在访达中打开'}


# 每种已知问题：详细原因 / 解决办法 / 可用按钮。字符串固定，便于 EN 翻译；可变部分放在 detail。
GIT_CAUSES = (
    ('secret', r'gitleaks|疑似密钥|密钥扫描失败',
     '待上传的文件里像是有密码或密钥，为了安全没有上传。',
     ['点“打开文件夹”，找到下面列出的文件', '删掉里面的密码，或把这个文件加入 .gitignore', '点“重试”'], ['reveal', 'retry']),
    ('bigfile', r'超过\s*\d+MB|大文件',
     '有文件超过 90MB，GitHub 放不下，这个文件没有上传（其他文件照常同步）。',
     ['点“打开文件夹”找到这个文件', '把它移出项目，或加入 .gitignore', '点“重试”'], ['reveal', 'retry']),
    ('fda', r'完全磁盘访问|无权读取|Operation not permitted',
     'macOS 不允许同步程序读取这个文件夹。',
     ['打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限', '打开 GitSync 的开关', '回到这里点“重试”'], ['retry']),
    ('missing', r'路径不存在|外接卷|文件夹不存在',
     '找不到登记的项目文件夹：项目可能被移动了，或所在硬盘没有连接。',
     ['如果在外接硬盘上，先接上硬盘再点“重试”', '如果项目搬了位置，点“重新定位”选新的文件夹'], ['locate', 'retry']),
    ('auth', r'Authentication|Username|publickey|Permission denied|凭据|鉴权|认证|\b40[13]\b',
     'GitHub 拒绝了登录，这台电脑现在没法上传或取回。',
     ['用 GitHub Desktop 或浏览器重新登录 GitHub', '确认你对这个项目有权限', '点“重试”'], ['retry']),
    ('network', r'network|timed out|Could not resolve|Failed to connect|超时|连接.*失败',
     '连不上 GitHub（网络断了或很慢）。',
     ['检查网络是否正常', '稍后会自动再试，也可以点“重试”'], ['retry']),
    ('detached', r'分离 HEAD|不在任何分支',
     '项目现在没有停在任何分支上（例如正在看某个旧版本），所以只取回不上传。',
     ['在你的 Git 工具里切回一个分支（例如 main）', '点“重试”'], ['reveal', 'retry']),
    ('busy', r'index\.lock|占用|正在.*合并|MERGE_HEAD|rebase',
     '项目正被别的程序（编辑器或 Git 工具）占用，这一轮先跳过。',
     ['等那个操作结束（或关掉卡住的 Git 工具）', '点“重试”'], ['retry']),
)


def git_has_remote(r):
    if 'remote_url' in r:
        return bool(r.get('remote_url'))
    return not ('没有远程' in (r.get('status_reason') or '') or r.get('mode') == 'none' and r.get('status') == 'disabled' and not r.get('enabled_mode'))


def git_diagnose(r):
    """把登记项的状态翻成：原因 / 办法 / 按钮。没有问题返回 None。"""
    st = r.get('status')
    blob = '%s %s' % (r.get('last_result') or '', r.get('status_reason') or '')
    warns = ' '.join(str(w) for w in (r.get('warnings') or []))
    if not git_has_remote(r):
        return {'cause': 'no_remote', 'reason': '这个项目没连接 GitHub，所以无法同步。',
                'fix': ['在 GitHub 上建一个项目，并把它设为这个文件夹的远程仓库', '刷新本页后勾选“同步”'],
                'actions': ['reveal'], 'detail': ''}
    if st == 'conflict' or r.get('conflict'):
        branch = (r.get('conflict') or {}).get('branch') or ''
        m = re.search(r'冲突分支\s*(\S+?)）', blob)
        branch = branch or (m.group(1) if m else '')
        return {'cause': 'conflict', 'reason': '这台电脑和 GitHub 改到了同一处。两边内容都保留了，自动同步先停下等你合并。',
                'fix': ['另一边的版本放在冲突分支里（见下方分支名）', '用你的 Git 工具把它合并进当前分支', '合并好后点“标记已解决”'],
                'actions': ['resolve', 'reveal', 'pause'], 'detail': branch}
    if st in ('paused', 'disabled'):
        return None
    for cause, pat, reason, fix, actions in GIT_CAUSES:
        source = blob + (' ' + warns if cause == 'bigfile' else '')
        if re.search(pat, source, re.I):
            return {'cause': cause, 'reason': reason, 'fix': list(fix), 'actions': list(actions) + ['pause'],
                    'detail': scrub_git_message((r.get('status_reason') or r.get('last_result') or '').strip())}
    is_error, _ = git_error_judge(st, r.get('last_result'), r.get('status_reason'))
    if is_error:
        return {'cause': 'other', 'reason': '自动同步遇到了问题，原始记录见下方。',
                'fix': ['点“重试”', '如果还不行，展开“详细信息”把原始记录发给维护的人'],
                'actions': ['retry', 'reveal', 'pause'],
                'detail': scrub_git_message((r.get('status_reason') or r.get('last_result') or '').strip())}
    return None


def git_sync_snapshot(state_dir, query, notify=True):
    """状态/事件快照。status 与 repo 同时过滤 repos 和 events；summary 始终为全量口径。
    通知的恢复清除始终基于未过滤的全量仓库列表，过滤视图不会让复发静默。"""
    home = git_sync_home()
    status = query.get('status', ['all'])[0]
    if status not in ('all', 'ok', 'error', 'paused', 'disabled'):
        raise ValueError('status 只支持 all/ok/error/paused/disabled')
    repo = query.get('repo', [''])[0].strip()
    try:
        limit = int(query.get('limit', ['100'])[0])
    except (TypeError, ValueError):
        raise ValueError('limit 必须是整数')
    if not 1 <= limit <= 200:
        raise ValueError('limit 范围 1..200')
    reg = {}
    try:
        with open(os.path.join(home, 'registry.json'), encoding='utf-8') as f:
            reg = json.load(f)
    except (OSError, ValueError):
        reg = {}
    raw = (reg.get('repos') or []) if isinstance(reg, dict) else (reg if isinstance(reg, list) else [])
    repos_all = []
    for r in raw:
        if not isinstance(r, dict) or not r.get('name'):
            continue
        st = r.get('status') or 'unknown'
        is_error, error_kind = git_error_judge(st, r.get('last_result'), r.get('status_reason'))
        if st not in ('paused', 'disabled') and '路径不存在' in ((r.get('last_result') or '') + (r.get('status_reason') or '')):
            is_error, error_kind = True, 'missing_path'
        if st in ('paused', 'disabled'):
            is_error, error_kind = False, ''
        repos_all.append({'name': r['name'], 'status': st, 'mode': r.get('mode') or 'none',
                          'branch': r.get('branch') or '', 'last_sync': r.get('last_sync'),
                          'last_check': r.get('last_check'),
                          'path': r.get('path') or '',
                          'pending_changes': r.get('pending_changes') or 0,
                          'auto_commit': r.get('auto_commit', True),
                          'last_result': scrub_git_message(r.get('last_result') or ''),
                          'status_reason': scrub_git_message(r.get('status_reason') or ''),
                          'is_error': is_error, 'error_kind': error_kind,
                          'has_remote': git_has_remote(r),
                          'on_volume': (r.get('path') or '').startswith('/Volumes/'),
                          'help': git_diagnose(r)})
    summary = {'total': len(repos_all), 'ok': 0, 'error': 0, 'stopped': 0, 'last_round': None}
    for r in repos_all:
        if r['is_error']:
            summary['error'] += 1
        elif r['status'] == 'ok':
            summary['ok'] += 1
        if r['status'] in ('paused', 'disabled'):
            summary['stopped'] += 1
    last_sync = max((r['last_sync'] for r in repos_all if r.get('last_sync')), default=None)
    events_all = parse_git_logs(home)
    for r in repos_all:
        own = [e for e in events_all if e.get('repo') == r['name'] and e.get('result') == 'ok']
        r['last_push'] = max((e['at'] for e in own if e.get('kind') == 'push'), default=None)
        r['last_pull'] = max((e['at'] for e in own if e.get('kind') in ('pull', 'merge')), default=None)
    summary['last_push'] = max((r['last_push'] for r in repos_all if r['last_push']), default=None)
    summary['last_pull'] = max((r['last_pull'] for r in repos_all if r['last_pull']), default=None)
    round_at = max((e['at'] for e in events_all
                    if e['kind'] == 'info' and e['message'].startswith('====')), default=None)
    summary['last_round'] = round_at or last_sync
    notices = maybe_notify_git_errors(repos_all) if notify else []
    repos = list(repos_all)
    events = list(events_all)
    if status != 'all':
        if status == 'error':
            keep = {r['name'] for r in repos_all if r['is_error']}
            repos = [r for r in repos if r['is_error']]
            events = [e for e in events if e['repo'] in keep
                      or e['result'] in ('error', 'conflict', 'blocked')]
        elif status == 'ok':
            repos = [r for r in repos if not r['is_error'] and r['status'] == 'ok']
            events = [e for e in events if e['repo'] is None or e['repo'] in
                      {r['name'] for r in repos_all
                       if not r['is_error'] and r['status'] == 'ok'}]
        elif status in ('paused', 'disabled'):
            repos = [r for r in repos if r['status'] == status]
            events = [e for e in events if e['repo'] in {r['name'] for r in repos}]
    if repo:
        repos = [r for r in repos if r['name'] == repo]
        events = [e for e in events if e['repo'] == repo]
    events.sort(key=lambda e: e['at'], reverse=True)
    host = os.uname().nodename.split('.')[0] if hasattr(os, 'uname') else ''
    device = host or '这台电脑'
    activity = [e for e in events if e.get('repo') and e['kind'] not in ('info', 'skip') and not e['message'].startswith('结果：')]
    return {'repos': repos, 'events': events[:limit], 'activity': activity[:limit], 'summary': summary, 'notices': notices, 'device': device, 'data_sync': {}}


def git_notify_default(repo, kind, summary):
    """默认桌面通知：与 git-sync 自身一致的 osascript display notification（任意正文）。
    不走 console App --notify：Swift 端只接受 codex/claude/test 固定文案，无法携带仓库名。"""
    try:
        return subprocess.run(['/usr/bin/osascript', '-e', 'on run argv',
                               '-e', 'display notification (item 2 of argv) with title (item 1 of argv) sound name "Basso"',
                               '-e', 'end run', 'Git 同步提醒', summary[:900]],
                              timeout=20, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


git_notify_native = git_notify_default  # 测试替换此名字，绝不真弹通知


def _git_notice_path(home):
    return os.path.join(home, 'state', 'git-sync-notice.json')


def _load_git_notices(home):
    try:
        with open(_git_notice_path(home), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('notified'), dict) and isinstance(data.get('pending'), dict):
            return data['notified'], data['pending']
    except (OSError, ValueError):
        pass
    return {}, {}


def _save_git_notices(home, notified, pending):
    path = _git_notice_path(home)
    d = os.path.dirname(path)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return False
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.notice-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'version': 1, 'notified': notified, 'pending': pending},
                      f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def maybe_notify_git_errors(repos):
    """对比 notice 文件指纹：新 error 首次出现才通知；恢复 ok 清除指纹；
    通知失败不影响 API，记录 notified=false 并在 6 小时节流窗口内重试。
    必须传入未过滤的仓库全量列表，否则恢复清除会失效。"""
    home = git_sync_home()
    notices = []
    with GIT_NOTICE_LOCK:
        notified, pending = _load_git_notices(home)
        changed = False
        now = time.time()
        for r in repos:
            name = r['name']
            fp = hashlib.sha256((name + '\0' + r['error_kind']).encode()).hexdigest()[:24]
            if r['is_error']:
                if notified.get(name) == fp:
                    continue
                pend = pending.get(name)
                if pend and pend.get('fp') == fp and now - pend.get('at', 0) < GIT_NOTIFY_THROTTLE:
                    continue
                summary = '「%s」状态为 %s：%s' % (
                    name, r['status'], (r['status_reason'] or r['last_result'] or '')[:80])
                ok = git_notify_native(name, r['error_kind'], scrub_git_message(summary))
                rec = {'repo': name, 'kind': r['error_kind'], 'notified': bool(ok)}
                if ok:
                    notified[name] = fp
                    pending.pop(name, None)
                    changed = True
                else:
                    rec['error'] = 'osascript-failed'
                    pending[name] = {'fp': fp, 'at': now}
                    changed = True
                notices.append(rec)
            else:
                if name in notified or name in pending:
                    notified.pop(name, None)
                    pending.pop(name, None)
                    changed = True
        if changed:
            _save_git_notices(home, notified, pending)
        return notices



# Keep navigation scrolling separate from the collapse control in short windows.
PAGE = PAGE.replace('<div class="brand"><span>Context Gate</span></div>', '<div class="brand"><span>Context Gate</span></div><div class="nav-list">', 1)
PAGE = PAGE.replace('<div class="nav-footer">', '</div><div class="nav-footer">', 1)
from console.usability_ui import improve_page
PAGE = improve_page(PAGE)
from console.tutorial_ui import apply_tutorial_and_i18n
PAGE = apply_tutorial_and_i18n(PAGE)
THEME_STYLE_CSS = r'''
:root.switching-appearance *, :root.switching-appearance *::before, :root.switching-appearance *::after{transition:none!important}
html{scrollbar-gutter:stable}
.setrow-theme{align-items:flex-start}.setrow-theme .sinfo{flex:0 1 240px}.setrow-theme .sctl{flex:1 1 480px;display:block}
.theme-presets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;width:100%}
.theme-family{min-width:0;margin:0;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--cardT)}
.theme-family legend{padding:0 6px;color:var(--muted);font-size:12px;font-weight:500}
.theme-choice-row{display:flex;gap:8px}.theme-choice-row button{flex:1;min-width:0;height:40px;padding:0 12px;border-radius:8px;border-color:var(--line2);background:var(--cardT);color:var(--text);font-size:12px}
.theme-choice-row button:hover{border-color:var(--accent)}.theme-choice-row button:active{transform:translateY(.5px)}
.theme-choice-row button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--onaccent);font-weight:600}
.theme-choice-row button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(max-width:38em){.theme-presets{grid-template-columns:1fr}}
@media(pointer:coarse){.theme-choice-row button{min-height:44px;height:44px}}
:root[data-style=mono][data-theme=dark]{color-scheme:dark;--bg:#202020;--card:#2B2B2B;--card2:#353535;--line:rgba(255,255,255,.09);--line2:rgba(255,255,255,.18);--text:#E7E7E7;--muted:#B2B2B2;--accent:#D0D0D0;--onaccent:#242424;--rowhover:rgba(255,255,255,.045);--tipbg:#383838;--tiptext:#F1F1F1;--pretext:#ECECEC;--okbg:rgba(52,211,153,.12);--badbg:rgba(248,113,113,.12);--warnbg:rgba(240,163,46,.12);--accentbg:rgba(255,255,255,.10);--mutbg:rgba(255,255,255,.08);--prebg:#262626;--shadow:0 4px 16px rgba(0,0,0,.28);--panelshadow:0 10px 32px rgba(0,0,0,.34);--chip:rgba(255,255,255,.05);--g1:rgba(255,255,255,.035);--g2:rgba(255,255,255,.02);--g3:rgba(255,255,255,.015);--cardT:rgba(44,44,44,.9);--cardshadow:0 4px 16px rgba(0,0,0,.2);--glassbg:rgba(43,43,43,.86);--sidebg:rgba(32,32,32,.92);--hl:rgba(255,255,255,.08);--glassline:rgba(255,255,255,.12);--chipbg:rgba(62,62,62,.55);--lift:0 8px 24px rgba(0,0,0,.25);--accent2:#A9A9A9;--refreshshadow:0 2px 10px rgba(0,0,0,.22);--cost:#D4D4D4;--costbg:rgba(255,255,255,.09);--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%23A3A3A3' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
:root[data-style=mono][data-theme=warm]{color-scheme:light;--bg:#F5F5F5;--card:#FFFFFF;--card2:#ECECEC;--line:#E2E2E2;--line2:#C9C9C9;--text:#272727;--muted:#676767;--accent:#3E3E3E;--onaccent:#FFFFFF;--rowhover:rgba(0,0,0,.035);--tipbg:#303030;--tiptext:#F5F5F5;--pretext:#EEEEEE;--okbg:rgba(26,127,75,.1);--badbg:rgba(179,55,44,.09);--warnbg:rgba(150,106,8,.11);--accentbg:rgba(0,0,0,.065);--mutbg:rgba(0,0,0,.06);--prebg:#2C2C2C;--shadow:0 4px 14px rgba(0,0,0,.08);--panelshadow:0 10px 30px rgba(0,0,0,.14);--chip:rgba(255,255,255,.62);--g1:rgba(0,0,0,.025);--g2:rgba(0,0,0,.018);--g3:rgba(0,0,0,.012);--cardT:rgba(255,255,255,.86);--cardshadow:0 4px 16px rgba(0,0,0,.055);--glassbg:rgba(255,255,255,.9);--sidebg:rgba(245,245,245,.9);--hl:rgba(255,255,255,.82);--glassline:rgba(0,0,0,.11);--chipbg:rgba(255,255,255,.68);--lift:0 8px 22px rgba(0,0,0,.1);--accent2:#5B5B5B;--refreshshadow:0 2px 10px rgba(0,0,0,.12);--cost:#444444;--costbg:rgba(0,0,0,.07);--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%237A7A7A' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
:root[data-style=mono] section,:root[data-style=mono] .card,:root[data-style=mono] .tile,:root[data-style=mono] .wb-item,:root[data-style=mono] .scard,:root[data-style=mono] .group-pane{background-image:none}
:root[data-style=mono][data-theme=dark] section,:root[data-style=mono][data-theme=dark] .tile{box-shadow:var(--cardshadow)}
/* Neutral surfaces with a restrained violet accent; values are local design choices. */
:root[data-style=mono][data-theme=dark]{--bg:#191A1D;--sidebg:#131417;--card:#202125;--card2:#28292E;--cardT:#24252A;--text:#ECECEF;--muted:#A7A8B2;--line:#303137;--line2:#464750;--accent:#B7ACEC;--accent2:#9C8DDD;--onaccent:#211B35;--accentbg:#302B42;--glassbg:#24252A;--glassline:#33343B;--chipbg:#2B2C32;--prebg:#15161A;--cost:#C0B5EF;--costbg:#302B42;--g1:transparent;--g2:transparent;--g3:transparent;--shadow:0 8px 28px #00000024;--cardshadow:none;--lift:none;--refreshshadow:none}
:root[data-style=mono][data-theme=warm]{--bg:#FFFFFF;--sidebg:#F5F5F7;--card:#FFFFFF;--card2:#F5F5F8;--cardT:#F7F7F9;--text:#24242A;--muted:#686874;--line:#ECECF0;--line2:#D2D2DA;--accent:#6E52AC;--accent2:#5B4394;--onaccent:#FFFFFF;--accentbg:#F0ECF8;--glassbg:#FFFFFF;--glassline:#E7E7ED;--chipbg:#F0F0F4;--prebg:#24242B;--cost:#6E52AC;--costbg:#F0ECF8;--g1:transparent;--g2:transparent;--g3:transparent;--shadow:0 8px 28px #24242A12;--cardshadow:none;--lift:none;--refreshshadow:none}
:root[data-style=mono] body{background:var(--bg)}
:root[data-style=mono] body::before,:root[data-style=mono] body::after{display:none}
:root[data-style=mono] #sidenav{border-right:0;backdrop-filter:none}
:root[data-style=mono] #sidenav .brand{letter-spacing:-.02em;font-weight:650}
:root[data-style=mono] #sidenav .nav-item{border-radius:9px;min-height:40px;color:var(--muted)}
:root[data-style=mono] #sidenav .nav-item.on,:root[data-style=mono] #sidenav .nav-item.is-current-section{background:var(--accentbg);color:var(--accent);font-weight:600}
:root[data-style=mono] section{background:transparent;border:0;border-radius:0;box-shadow:none;padding:24px 0;margin-bottom:16px}
:root[data-style=mono] .card,:root[data-style=mono] .tile{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:none}
:root[data-style=mono] section>h2{font-size:16px;font-weight:650;letter-spacing:-.02em;margin-bottom:20px}
:root[data-style=mono] .setrow{padding:20px 0;border-color:var(--line)}
:root[data-style=mono] .sname{font-size:14px;font-weight:550}
:root[data-style=mono] .sdesc{font-size:12px;line-height:1.7;margin-top:5px;max-width:38em}
:root[data-style=mono] .console-header{padding-bottom:8px}
:root[data-style=mono] .console-header h1{font-weight:600;letter-spacing:-.035em}
:root[data-style=mono] .global-actions button{background:transparent;border-color:transparent;box-shadow:none}
:root[data-style=mono] .global-actions button:hover{background:var(--rowhover)}
:root .setrow-theme{display:block;padding-top:8px}
:root .setrow-theme .sctl{margin-top:20px}
:root .theme-presets{max-width:640px;gap:28px}
:root .theme-family{padding:0;border:0;background:none}
:root .theme-family legend{padding:0;margin-bottom:12px;font-size:13px;color:var(--text)}
:root .theme-choice-row{gap:12px}
:root .theme-choice-row button{position:relative;height:106px;padding:74px 12px 10px;background:var(--card2);border:1px solid var(--line);color:var(--muted);text-align:left;font-size:12px;border-radius:10px}
:root .theme-choice-row button::before{content:'';position:absolute;inset:10px 10px 34px;border-radius:5px;background:linear-gradient(90deg,#EDEDF1 0 23%,transparent 23%),linear-gradient(#DBDBE3,#DBDBE3) 36% 24%/40% 3px no-repeat,linear-gradient(#ECECF1,#ECECF1) 55% 56%/58% 3px no-repeat,linear-gradient(#ECECF1,#ECECF1) 55% 73%/58% 3px no-repeat,#FFF;box-shadow:0 1px 3px #00000012}
:root .theme-choice-row button[data-theme-mode=dark]::before{background:linear-gradient(90deg,#14151A 0 23%,transparent 23%),linear-gradient(#666575,#666575) 36% 24%/40% 3px no-repeat,linear-gradient(#3D3E48,#3D3E48) 55% 56%/58% 3px no-repeat,linear-gradient(#3D3E48,#3D3E48) 55% 73%/58% 3px no-repeat,#24252C}
:root .theme-choice-row button[data-theme-style=original]::before{box-shadow:inset 3px 0 #B2A6FF,0 1px 3px #00000012}
:root .theme-choice-row button[aria-pressed=true]{border-color:var(--accent);background:var(--accentbg);color:var(--accent);font-weight:600}
:root .theme-choice-row button[aria-pressed=true]::after{content:'✓';position:absolute;right:12px;bottom:10px;font-size:13px}
:root .theme-choice-row button:hover{border-color:var(--accent)}
@media(max-width:38em){:root .theme-presets{gap:20px}:root[data-style=mono] section{padding:16px 0}}


:root[data-style] body[data-console-view=sys] #refresh-note:empty{display:none}
:root[data-style] body[data-console-view=sys] .console-header{padding-bottom:0;margin-bottom:16px}
:root[data-style] body[data-console-view=sys] section[data-view=sys]{padding:20px;border-width:1px;border-style:solid;margin-bottom:16px}
:root[data-style=mono] body[data-console-view=sys] section[data-view=sys]{border-color:transparent}
:root[data-style] body[data-console-view=sys] section[data-view=sys]>h2{font-size:16px;line-height:24px;margin:0 0 12px}
:root[data-style] body[data-console-view=sys] .setrow{padding:14px 0;width:100%;max-width:840px;gap:16px}
:root[data-style] body[data-console-view=sys] .sname{font-size:14px;line-height:20px}
:root[data-style] body[data-console-view=sys] .sdesc{font-size:12px;line-height:18px;margin-top:3px}
:root[data-style] body[data-console-view=sys] .setrow-theme .sctl{margin-top:12px}
:root[data-style] body[data-console-view=sys] .theme-presets{max-width:none;gap:20px}
@media(max-width:38em){:root[data-style] body[data-console-view=sys] section[data-view=sys]{padding:12px}:root[data-style] body[data-console-view=sys] .theme-presets{gap:12px}}

'''
PAGE = PAGE.replace('</style>', THEME_STYLE_CSS + '\n</style>', 1)
from console.prism_ui import CSS as PRISM_CSS
PAGE = PAGE.replace('</style>', PRISM_CSS + '\n</style>', 1)
from console.surface_ui import CSS as SURFACE_CSS
PAGE = PAGE.replace('</style>', SURFACE_CSS + '\n</style>', 1)



class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args): pass

    def reply(self, code, body, content_type):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        # Path token like gate_proxy. Browsers only reach same-origin routes;
        # GETs carry no Origin header, while fetch POSTs do — either way a
        # foreign Origin means cross-site and is rejected.
        prefix = '/' + self.server.local_token
        if not self.path.startswith(prefix + '/'):
            return False
        origin = self.headers.get('Origin')
        return origin in (None, 'http://127.0.0.1:' + str(self.server.server_port))

    def do_GET(self):
        if not self._authorized():
            return self.reply(403, '{"error":"Unauthorized local route"}', 'application/json')
        route = urllib.parse.urlsplit(self.path[len(self.server.local_token) + 1:])
        if route.path == '/v1/console/health':
            data = {'service': 'context-gate-console', 'pid': os.getpid(),
                    'app_owner': self.server.app_owner,
                    'memory_documents': self.server.memory.access_status()}
            return self.reply(200, json.dumps(data), 'application/json')
        if route.path == '/v1/router/zcode':
            try:
                data = zcode_options(self.server.router, Path.home())
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError, TypeError, KeyError):
                return self.reply(400, json.dumps({'error': '无法读取 ZCode 同步选项，请刷新模型路由后重试。'}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/router/capabilities':
            try:
                data = self.server.capabilities.snapshot()
                if data.get('router') and not data['router'].get('reachable'):
                    data = dict(data, fallback=self.server.fallback.status())
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (OSError, ValueError) as error:
                return self.reply(400, json.dumps({'error': '能力表读取失败：' + type(error).__name__}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/router':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = self.server.router.snapshot(query.get('period', ['all'])[0], query.get('provider', ['all'])[0])
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except ValueError as error:
                return self.reply(400, json.dumps({'error': str(error)}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/live':
            from console.memory_live import snapshot as memory_live_snapshot
            return self.reply(200, json.dumps(memory_live_snapshot(), ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/galaxy-view':
            from console.galaxy_bridge import page
            try: return self.reply(200, page(self.server.memory.root), 'text/html; charset=utf-8')
            except (OSError, ValueError): return self.reply(503, '星云组件暂不可用，请切回文字模式。', 'text/plain; charset=utf-8')
        if route.path == '/v1/memory':
            query = urllib.parse.parse_qs(route.query)
            return self.reply(200, json.dumps(self.server.memory.snapshot(query.get('since', [''])[0]), ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path in ('/v1/imports','/v1/imports/preview'):
            query=urllib.parse.parse_qs(route.query)
            try:
                data={'items':self.server.imports.list()} if route.path=='/v1/imports' else self.server.imports.preview(query.get('id',[''])[0],int(query.get('offset',['0'])[0]))
                return self.reply(200,json.dumps(data,ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError,KeyError):return self.reply(400,'{"error":"导入文件读取失败，请核对原件与翻页位置"}','application/json; charset=utf-8')
        if route.path in ('/v1/todos','/v1/todos/export'):
            try:
                data=self.server.todos.list() if route.path=='/v1/todos' else self.server.todos.export()
                return self.reply(200,json.dumps(data,ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError,KeyError,TypeError) as error:return self.reply(400,json.dumps({'error':str(error) if isinstance(error,ValueError) else '待办读取失败'},ensure_ascii=False),'application/json; charset=utf-8')
        if route.path == '/v1/groups':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = self.server.groups.snapshot(query.get('id',[None])[0], int(query.get('after',['0'])[0]))
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError):
                return self.reply(400, '{"error":"无法读取群聊"}', 'application/json')
        if route.path == '/v1/groups/native':
            query=urllib.parse.parse_qs(route.query)
            try:
                data=self.server.groups.native_history(query.get('id',[''])[0],query.get('member',[''])[0],query.get('offset',['0'])[0])
                return self.reply(200,json.dumps(data,ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError):
                return self.reply(400,'{"error":"原生历史读取失败"}','application/json')
        if route.path == '/':
            return self.reply(200, PAGE, 'text/html; charset=utf-8')
        if route.path.startswith('/v1/wallet/'):
            query = {k: v[-1] for k, v in urllib.parse.parse_qs(route.query).items()}
            status, data = self.server.wallets.handle('GET', route.path[len('/v1/wallet'):], query, {})
            return self.reply(status, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/quota':
            return self.reply(200,json.dumps(self.server.quotas.snapshot(),ensure_ascii=False),'application/json')
        if route.path == '/v1/quota/usage':
            query = urllib.parse.parse_qs(route.query)
            try:
                data=self.server.quotas.usage(query.get('platform',[''])[0],query.get('account',['all'])[0],
                                              query.get('range',['all'])[0],query.get('tier',['5h'])[0],
                                              detail=query.get('detail',['0'])[0]=='1',
                                              start=query.get('start',[None])[0],end=query.get('end',[None])[0])
                return self.reply(200,json.dumps(data,ensure_ascii=False),'application/json')
            except ValueError as exc:return self.reply(400,json.dumps({'error':str(exc)},ensure_ascii=False),'application/json')
        if route.path == '/v1/center/templates':
            try:return self.reply(200,json.dumps({'templates':self.server.center.templates()},ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError):return self.reply(400,'{"error":"常用任务读取失败"}','application/json')
        if route.path == '/v1/center/usage-alert':
            try:return self.reply(200,json.dumps(self.server.center.usage_settings()),'application/json')
            except (ValueError,OSError):return self.reply(400,'{"error":"提醒设置读取失败"}','application/json')
        if route.path == '/v1/center/schedules':
            try:
                from console_search import public
                return self.reply(200,json.dumps(public({'schedules':self.server.schedules.list()}),ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError):return self.reply(400,'{"error":"预约读取失败"}','application/json; charset=utf-8')
        if route.path in ('/v1/center/tasks','/v1/center/changes','/v1/center/diagnostics','/v1/center/artifact','/v1/groups/artifact','/v1/butler'):
            query = urllib.parse.parse_qs(route.query)
            try:
                if route.path == '/v1/center/tasks':
                    data = {'tasks': self.server.center.list(), 'group_outcomes':self.server.groups.outcomes(),
                            'external_outcomes': external_outcomes(self.server.state_dir),
                            'projects': [str(p) for p in self.server.center.roots]}
                elif route.path == '/v1/center/changes':
                    data = self.server.center.changes(query.get('id', [''])[0])
                elif route.path == '/v1/center/diagnostics':
                    data = self.server.center.diagnostics()
                elif route.path in ('/v1/center/artifact','/v1/groups/artifact'):
                    owner=self.server.groups if route.path=='/v1/groups/artifact' else self.server.center
                    data = owner.artifact(query.get('id',[''])[0],query.get('path',[''])[0],int(query.get('offset',['0'])[0]))
                else:
                    data = self.server.butler.get(query.get('id', [''])[0])
                from console_search import public
                return self.reply(200, json.dumps(public(data), ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError) as e:
                if route.path in ('/v1/center/artifact','/v1/groups/artifact'):
                    from console_search import public
                    return self.reply(400,json.dumps({'error':public(str(e))},ensure_ascii=False),'application/json; charset=utf-8')
                return self.reply(400, '{"error":"无法读取任务记录"}', 'application/json; charset=utf-8')
        if route.path == '/v1/request-detail':
            # Read-only single ledger row + saved timing/log links (token-gated GET).
            query = urllib.parse.parse_qs(route.query)
            try:
                data = request_detail(self.server.state_dir, query.get('id', [''])[0])
            except ValueError:
                return self.reply(400, '{"error":"bad id"}', 'application/json; charset=utf-8')
            except KeyError:
                return self.reply(404, '{"error":"没有这条请求记录"}', 'application/json; charset=utf-8')
            from console_search import public
            return self.reply(200, json.dumps(public(data), ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/search-detail':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = search_detail(self.server.state_dir, query.get('id', [''])[0])
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError, sqlite3.Error):
                return self.reply(404, '{"error":"记录已刷新，请重新搜索"}', 'application/json; charset=utf-8')
        if route.path == '/v1/search':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = search(self.server.state_dir, query.get('q', [''])[0],
                              int(query.get('offset', ['0'])[0]))
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError, sqlite3.Error):
                return self.reply(400, '{"error":"搜索读取失败或查询无效"}', 'application/json; charset=utf-8')
        if route.path == '/v1/settings/butler':
            cfg = load_butler_settings(self.server.state_dir)
            return self.reply(200, json.dumps({'provider':cfg.get('provider'),'model':cfg.get('model'),
                                               'base_url':cfg.get('base_url'),'has_key':bool(cfg.get('api_key')),
                                               'label':butler_settings_label(cfg)},ensure_ascii=False),'application/json')
        if route.path == '/v1/stats':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = snapshot_cached(self.server.state_dir,
                                query.get('period', ['all'])[0],
                                query.get('platform', ['all'])[0],
                                model=query.get('model', [None])[0],
                                day=query.get('day', [None])[0])
                if query.get('model', [None])[0] is None:
                    data = {**data, 'hotkey': load_hotkey(self.server.state_dir)}
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (OSError, ValueError) as error:
                return self.reply(400, json.dumps({'error': '读取统计失败：' + type(error).__name__}, ensure_ascii=False), 'application/json; charset=utf-8')
            except Exception:
                return self.reply(500, '{"error":"读取统计失败"}', 'application/json; charset=utf-8')
        if route.path == '/v1/gate-task-log':
            # Read-only per-step log for the 压缩任务 view; same token gate as every GET.
            query = urllib.parse.parse_qs(route.query)
            event = gate_stream_event(self.server.state_dir,
                                      query.get('id', [''])[0], query.get('i', [''])[0])
            if event is None:
                return self.reply(404, '{"error":"Not found"}', 'application/json')
            from console_search import public
            return self.reply(200, json.dumps(public(event), ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/gate-task-output':
            # 只读：按注册表 task_id 读取 gate_run 登记的输出文件内容（令牌门内）
            query = urllib.parse.parse_qs(route.query)
            tid = query.get('id', [''])[0]
            if not re.fullmatch(r'[0-9a-f-]{8,64}', tid):
                return self.reply(400, '{"error":"bad id"}', 'application/json; charset=utf-8')
            reg = Path(self.server.state_dir) / 'gate-tasks' / (tid + '.json')
            try:
                meta = json.loads(reg.read_text())
            except (OSError, ValueError):
                return self.reply(404, '{"error":"no-registry"}', 'application/json; charset=utf-8')
            out = meta.get('output') or ''
            if not out or not os.path.isfile(out):
                return self.reply(404, '{"error":"file-gone"}', 'application/json; charset=utf-8')
            try:
                size = os.path.getsize(out)
                with open(out, 'rb') as f:
                    f.seek(max(0, size - 1048576))
                    data = f.read(1048576).decode('utf-8', errors='replace')
            except OSError:
                return self.reply(404, '{"error":"unreadable"}', 'application/json; charset=utf-8')
            return self.reply(200, json.dumps({'file': out, 'truncated': size > 1048576, 'content': redact_text(data)}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/git-sync':
            query = urllib.parse.parse_qs(route.query)
            try:
                data = git_sync_snapshot(self.server.state_dir, query)
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except ValueError as error:
                return self.reply(400, json.dumps({'error': str(error)}, ensure_ascii=False), 'application/json; charset=utf-8')
            except (OSError, TypeError, KeyError):
                return self.reply(500, '{"error":"读取 Git 同步数据失败"}', 'application/json; charset=utf-8')
        return self.reply(404, '{"error":"Not found"}', 'application/json; charset=utf-8')

    def do_POST(self):
        if not self._authorized():
            return self.reply(403, '{"error":"Unauthorized local route"}', 'application/json')
        if not isinstance(self.server, ConsoleServer):
            return self.handle_post()
        with self.server.post_lock:
            if self.server.releasing:
                return self.reply(503, '{"error":"Console is restarting"}', 'application/json')
            self.server.active_posts += 1
        try:
            self.handle_post()
        finally:
            with self.server.post_lock:
                self.server.active_posts -= 1

    def handle_post(self):
        route = urllib.parse.urlsplit(self.path[len(self.server.local_token) + 1:])
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= (750000 if route.path=='/v1/imports/add' else 650000 if route.path=='/v1/todos/import' else 11500000 if route.path=='/v1/groups/attach' else 30000):
                return self.reply(413, '{"error":"Body limit"}', 'application/json')
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, OSError, RecursionError):
            return self.reply(400, '{"error":"Invalid body"}', 'application/json')
        if not isinstance(body, dict):
            return self.reply(400, '{"error":"Invalid object"}', 'application/json')
        if route.path in ('/v1/git-sync/toggle', '/v1/git-sync/retry', '/v1/git-sync/pause',
                          '/v1/git-sync/resume', '/v1/git-sync/resolve', '/v1/git-sync/reveal'):
            action = route.path.rsplit('/', 1)[1]
            try:
                data = (git_sync_toggle(body) if action == 'toggle' else git_sync_retry(body) if action == 'retry'
                        else git_sync_reveal(body) if action == 'reveal' else git_sync_command(body, action))
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json')
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                return self.reply(400, json.dumps({'error': str(exc)}, ensure_ascii=False), 'application/json')
        if route.path == '/v1/console/release':
            if not isinstance(self.server, ConsoleServer):
                return self.reply(404, '{"error":"Not found"}', 'application/json')
            if (body.get('pid') != os.getpid() or self.server.app_owner is not None
                    or self.server.memory.access_status() != 'denied'):
                return self.reply(409, '{"error":"Backend cannot be replaced"}', 'application/json')
            from console_reload import precheck
            base = f'http://127.0.0.1:{self.server.server_port}/{self.server.local_token}/'
            with self.server.post_lock:
                if self.server.active_posts != 1:
                    return self.reply(409, '{"error":"Console has active requests"}', 'application/json')
                self.server.releasing = True
            approved = False
            try:
                try:
                    with self.server.groups.submission():
                        precheck(base, timeout=3)
                        sync = self.server.memory.process
                        if sync is not None and sync.poll() is None:
                            raise RuntimeError('Memory document sync is running')
                except (RuntimeError, OSError, ValueError, KeyError, TypeError):
                    return self.reply(409, '{"error":"Console is busy or could not be checked"}', 'application/json')
                approved = True
                self.reply(202, '{"ok":true}', 'application/json')
            finally:
                if approved:
                    self.server.shutdown()
                else:
                    with self.server.post_lock:
                        self.server.releasing = False
            return
        if route.path == '/v1/git-sync/locate':
            try:
                data = git_sync_relocate(body)
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json')
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                return self.reply(400, json.dumps({'error': str(exc)}, ensure_ascii=False), 'application/json')
        if route.path.startswith('/v1/wallet/'):
            # Console has only GET/POST; the prototype's PATCH routes arrive as POST ?_method=PATCH.
            query = {k: v[-1] for k, v in urllib.parse.parse_qs(route.query).items()}
            method = query.get('_method', 'POST')
            if method not in ('POST', 'PATCH'):
                return self.reply(400, '{"error":{"code":"INVALID_INPUT","message":"_method must be POST or PATCH"}}', 'application/json; charset=utf-8')
            status, data = self.server.wallets.handle(method, route.path[len('/v1/wallet'):], query, body)
            return self.reply(status, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path in ('/v1/quota/settings','/v1/quota/refresh','/v1/quota/claude-login'):
            try:
                if route.path.endswith('/settings'):
                    data=self.server.quotas.settings(body)
                elif route.path.endswith('/claude-login'):
                    data=self.server.quotas.claude_login()
                else:
                    data=self.server.quotas.request(body.get('platform'))
                return self.reply(200,json.dumps(data,ensure_ascii=False),'application/json')
            except ValueError as exc:return self.reply(400,json.dumps({'error':str(exc)},ensure_ascii=False),'application/json')
        if route.path == '/v1/router/zcode/sync':
            try:
                data = zcode_sync_request(self.server.router, Path.home(), body)
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError, TypeError, KeyError):
                return self.reply(400, json.dumps({'error': '同步参数无效、所选模型已禁用或账号不可用，请刷新后重试。'}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/router/action':
            try:
                data = self.server.router.action(body)
                command = body.get('command')
                if isinstance(command, str) and command in AUTO_SYNC_COMMANDS and isinstance(data, dict):
                    try:
                        data['zcodeSync'] = zcode_auto_sync(self.server.router, Path.home())
                    except Exception:
                        data['zcodeSync'] = {'ok': False, 'accounts': 0, 'changed': 0, 'failed': 0}
                return self.reply(200, json.dumps(data, ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError) as error:
                return self.reply(400, json.dumps({'error': str(error)}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/galaxy-data':
            from console.galaxy_bridge import read
            try: return self.reply(200, read(self.server.memory.root, body.get('command'), body.get('args')), 'application/json; charset=utf-8')
            except ValueError as exc: return self.reply(400, json.dumps({'error':'unavailable','message':str(exc)}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/open-folder':
            folder = self.server.memory.out
            if not folder.is_dir():
                return self.reply(400, json.dumps({'error': '文档文件夹尚未生成，请先同步记忆。'}, ensure_ascii=False), 'application/json; charset=utf-8')
            ok = run_open(['/usr/bin/open', str(folder)])
            return self.reply(200 if ok else 500, json.dumps({'ok': True} if ok else {'error': '文件夹未能打开，请重试。'}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/export':
            try:
                dest = self.server.memory.export(body.get('kind'))
                opened = run_open(['/usr/bin/open', '-R', str(dest)])
                return self.reply(200, json.dumps({'ok': True, 'filename': dest.name, 'opened': opened}, ensure_ascii=False), 'application/json; charset=utf-8')
            except (OSError, ValueError, StopIteration) as error:
                message = str(error) if isinstance(error, ValueError) else '导出失败，请检查文档文件夹后重试。'
                return self.reply(400, json.dumps({'error': message}, ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/memory/sync':
            return self.reply(200, json.dumps(self.server.memory.sync(), ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path=='/v1/imports/add':
            try:return self.reply(200,json.dumps(self.server.imports.add(body),ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError) as error:return self.reply(400,json.dumps({'error':str(error)},ensure_ascii=False),'application/json; charset=utf-8')
        if route.path=='/v1/imports/delete':
            try:return self.reply(200,json.dumps(self.server.imports.remove(body),ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError) as error:return self.reply(400,json.dumps({'error':str(error)},ensure_ascii=False),'application/json; charset=utf-8')
        if route.path.startswith('/v1/todos/'):
            actions={'add':self.server.todos.add,'import':self.server.todos.import_text,'done':self.server.todos.set_done,
                     'edit':self.server.todos.edit,'delete':self.server.todos.remove,'clear_done':self.server.todos.clear_done}
            action=actions.get(route.path[len('/v1/todos/'):])
            if action is None:return self.reply(404,'{"error":"Not found"}','application/json; charset=utf-8')
            try:return self.reply(200,json.dumps(action(body),ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError,KeyError,TypeError) as error:return self.reply(400,json.dumps({'error':str(error) if isinstance(error,ValueError) else '待办保存失败'},ensure_ascii=False),'application/json; charset=utf-8')
        if route.path=='/v1/imports/compare':
            try:return self.reply(200,json.dumps(self.server.imports.compare(body),ensure_ascii=False),'application/json; charset=utf-8')
            except (ValueError,OSError,KeyError) as error:return self.reply(400,json.dumps({'error':str(error)},ensure_ascii=False),'application/json; charset=utf-8')
        if route.path.startswith('/v1/groups/'):
            try:
                actions = {'create':self.server.groups.create, 'add':self.server.groups.add,
                           'send':self.server.groups.send, 'stop':self.server.groups.stop,
                           'model':self.server.groups.model, 'mod':self.server.groups.mod, 'remove':self.server.groups.remove_groups,
                           'archive':self.server.groups.archive_groups, 'rename':self.server.groups.rename_group,
                           'open':self.server.groups.open_native,
                           'attach':lambda b:console_attach.save(self.server.groups,b),
                           'pick-files':lambda b:console_attach.pick(self.server.groups,b),
                           'delete':lambda b:self.server.groups.stop(b,remove=True)}
                action = route.path.removeprefix('/v1/groups/')
                if action not in actions: raise ValueError('未知群聊操作')
                data = actions[action](body)
                return self.reply(200, json.dumps(data,ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError) as error:
                return self.reply(400, json.dumps({'error':str(error)},ensure_ascii=False), 'application/json')
        if route.path.startswith('/v1/center/') or route.path == '/v1/butler':
            try:
                if route.path == '/v1/center/add-root': data = self.server.center.add_root(body)
                elif route.path == '/v1/center/pick-root': data = self.server.center.pick_root(body)
                elif route.path == '/v1/center/create': data = self.server.center.create(body)
                elif route.path == '/v1/center/template-save': data = self.server.center.save_template(body)
                elif route.path == '/v1/center/template-delete': data = self.server.center.delete_template(body)
                elif route.path == '/v1/center/compare': data = self.server.center.compare(body,self.server.groups)
                elif route.path == '/v1/center/usage-alert': data = self.server.center.usage_settings(body)
                elif route.path == '/v1/center/schedule-create': data = self.server.schedules.create(body)
                elif route.path == '/v1/center/schedule-cancel': data = self.server.schedules.cancel(body)
                elif route.path == '/v1/center/stop': data = self.server.center.stop(body.get('id',''))
                elif route.path == '/v1/center/accept': data = self.server.center.accept(body.get('id',''))
                elif route.path == '/v1/center/rollback':
                    if body.get('confirmed') is not True: raise ValueError('撤回前需确认修改详情')
                    data = self.server.center.rollback(body.get('id',''))
                elif route.path == '/v1/butler': data = self.server.butler.start(body.get('root',''),body.get('request',''))
                else: raise ValueError('未知操作')
                from console_search import public
                return self.reply(200, json.dumps(public(data), ensure_ascii=False), 'application/json; charset=utf-8')
            except (ValueError, OSError, KeyError) as error:
                return self.reply(400, json.dumps({'error':str(error)},ensure_ascii=False), 'application/json; charset=utf-8')
        if route.path == '/v1/settings/butler':
            provider = str(body.get('provider', ''))
            if provider not in ('nvidia', 'openrouter', 'ollama', 'custom'):
                return self.reply(400, '{"error":"未知供应商"}', 'application/json')
            model = str(body.get('model', '')).strip()[:120]
            base_url = str(body.get('base_url', '')).strip()[:300]
            api_key = str(body.get('api_key', '')).strip()[:300]
            if provider == 'custom' and (not base_url.startswith('http') or not model):
                return self.reply(400, '{"error":"自定义供应商需要 http 接口地址与模型名"}', 'application/json')
            if not api_key:
                previous = load_butler_settings(self.server.state_dir)
                if previous.get('provider') == provider:
                    api_key = previous.get('api_key', '')
            payload = {'provider': provider, 'model': model, 'base_url': base_url, 'api_key': api_key}
            path = Path(self.server.state_dir) / 'butler-settings.json'
            try:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                    os.write(fd, json.dumps(payload, ensure_ascii=False).encode())
                finally:
                    os.close(fd)
            except OSError as error:
                return self.reply(500, '{"error":"写入失败：' + type(error).__name__ + '"}', 'application/json')
            return self.reply(200, json.dumps({'ok': True, 'label': butler_settings_label(payload), 'has_key': bool(api_key)}, ensure_ascii=False), 'application/json')
        if route.path == '/v1/settings/cost-mode':
            mode = body.get('mode')
            if mode not in COST_MODES:
                return self.reply(400, '{"error":"未知价格模式"}', 'application/json')
            try:
                save_mode(self.server.state_dir, mode)
            except OSError as error:
                return self.reply(500, '{"error":"写入失败：' + type(error).__name__ + '"}', 'application/json')
            return self.reply(200, json.dumps({'ok': True, 'mode': mode}), 'application/json')
        if route.path == '/v1/settings/hotkey':
            key = str(body.get('key', '')).upper()
            flags = {name: bool(body.get(name)) for name in ('ctrl', 'cmd', 'shift', 'alt')}
            if not HOTKEY_RE.match(key) or not (flags['ctrl'] or flags['cmd']):
                return self.reply(400, '{"error":"快捷键需要一个字母/数字，且至少带 ⌃ 或 ⌘"}', 'application/json')
            payload = {'key': key, **flags}
            path = Path(self.server.state_dir) / 'hotkey.json'
            try:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                    os.write(fd, json.dumps(payload).encode())
                finally:
                    os.close(fd)
            except OSError as error:
                return self.reply(500, '{"error":"写入失败：' + type(error).__name__ + '"}', 'application/json')
            return self.reply(200, json.dumps({'ok': True, 'hotkey': payload}), 'application/json')
        if route.path == '/v1/open-app':
            command = OPEN_APPS.get(str(body.get('app', '')))
            if command is None:
                return self.reply(400, '{"error":"未知的 App"}', 'application/json')
            ok = run_open(command)
            return self.reply(200, json.dumps({'ok': ok}, ensure_ascii=False), 'application/json')
        return self.reply(404, '{"error":"Not found"}', 'application/json')


class ConsoleServer(ThreadingHTTPServer):
    app_owner = None

    def __init__(self, *args, **kwargs):
        self.post_lock = threading.Lock()
        self.active_posts = 0
        self.releasing = False
        super().__init__(*args, **kwargs)

    def service_actions(self):
        if self.app_owner is not None and os.getppid() != self.app_owner:
            raise KeyboardInterrupt

    def server_close(self):
        if hasattr(self, 'quotas'): self.quotas.close()
        if hasattr(self, 'wallets'): self.wallets.close()
        super().server_close()


def make_server(port, state_dir, launch_schedules=True):
    server = ConsoleServer(('127.0.0.1', port), Handler)
    server.local_token = secrets.token_urlsafe(32)
    server.state_dir = Path(state_dir)
    server.center = Center(state_dir)
    server.groups = Groups(state_dir,center=server.center)
    server.imports = Imports(state_dir)
    server.todos = Todos(state_dir)
    server.memory = MemoryLibrary()
    server.router = RouterManager()
    server.capabilities = CapabilityRegistry(state_dir)
    # Direct-provider fallback stays off until the user decides how keys may be supplied.
    server.fallback = DirectFallback(server.router, server.capabilities, enabled=False)
    server.schedules = Schedules(server.center,launch=launch_schedules)
    server.schedules.start()
    server.butler = Butler(state_dir, center=server.center)
    # Managed work is claimed and stopped by Protection itself; the external stop resolves the
    # module-global stop_all_local at call time so tests can intercept it. managed= is deliberately
    # not passed here: a plain managed stop would revoke the claims Protection has just written.
    server.protection = Protection(state_dir, server.center, server.groups, server.schedules,
                                   external=lambda: stop_all_local(enabled=True))
    server.quotas = Quotas(state_dir, protection=server.protection)
    server.quotas.start()
    server.wallets = Wallets(state_dir)
    return server


def apply_persistent_token(server, state_dir, fixed_port):
    """Fixed-port servers reuse the stored token across restarts so already-open
    pages survive backend restarts (the whole T4 stale-tab pain). Random-port
    runs keep rotating; the check stays token+Origin gated as before."""
    if not fixed_port:
        return
    token_file = Path(state_dir) / 'console-token'
    try:
        stored = token_file.read_text().strip()
    except OSError:
        stored = ''
    if re.fullmatch(r'[\w-]{20,}', stored or ''):
        server.local_token = stored
        return
    token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(token_file, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, server.local_token.encode())
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', default=os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate'))
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--app-owner', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--require-memory-access', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    state_dir = Path(args.state_dir).expanduser()
    if args.app_owner is not None and os.getppid() != args.app_owner:
        return 1
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state_dir / 'console-backend.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 2
        if args.require_memory_access and MemoryLibrary().access_status() == 'denied':
            return 3
        return serve_console(args, state_dir)


def serve_console(args, state_dir):
    ensure_config(state_dir)
    # 控制台常驻时顺带拉起 Context Gate 服务（用户用 manage.py stop 停掉后不会强拉）。
    try:
        from gate_service import ensure_service
        ensure_service(state_dir)
    except Exception:
        pass
    server = make_server(args.port, state_dir)
    server.app_owner = args.app_owner
    apply_persistent_token(server, state_dir, args.port != 0)
    url = 'http://127.0.0.1:' + str(server.server_port) + '/' + server.local_token + '/'
    connection = state_dir / 'console-connection.json'
    published = {'base_url': url, 'pid': os.getpid()}

    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        write_json(connection, published)
        print(url)
        # 预热总览统计缓存：后端重启后的第一次打开页面不再等全表扫描。
        threading.Thread(target=lambda: snapshot_cached(state_dir, 'all', 'all'), daemon=True).start()
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if json.loads(connection.read_text()) == published:
                connection.unlink()
        except (OSError, ValueError):
            pass
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
