# -*- coding: utf-8 -*-
"""Model wallet page: cost calculator, model catalog, wallet ledger and simulation.

Ported from the accepted standalone Model Wallet Console prototype. Local simulation only:
no real model call, no provider billing, no real wallet deduction. Styles use the console's
theme tokens; everything is scoped to #mw-root, #mw-modal, #mw-toast or .mw-* classes.
"""

CSS = r'''
#mw-root{min-width:0;overflow-wrap:anywhere}
#mw-root .mw-heading{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:12px;margin:0 0 16px}
#mw-root .mw-heading h3,#mw-root .mw-panel h3,#mw-modal h3{margin:0 0 4px;font-size:16px;font-weight:650;letter-spacing:-.01em}
#mw-root .mw-panel h3{font-size:14px;font-weight:600;margin:0 0 12px;letter-spacing:0}
#mw-root .mw-sub,#mw-modal .mw-sub{margin:0;color:var(--muted);font-size:13px;line-height:1.6}
#mw-root .mw-actions,#mw-modal .mw-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
#mw-root .mw-center{justify-content:center}
#mw-root .mw-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 16px}
#mw-root .mw-tab-count{margin-left:4px;color:var(--muted);font-variant-numeric:tabular-nums}
#mw-root .mw-tabs button[aria-current=page] .mw-tab-count{color:var(--accent)}
#mw-root .mw-panel{margin-bottom:16px}
#mw-root .mw-grid{display:grid;gap:16px;margin-bottom:16px}
#mw-root .mw-grid>*{min-width:0}
#mw-root .mw-two{grid-template-columns:repeat(2,minmax(0,1fr))}
#mw-root .mw-three{grid-template-columns:repeat(3,minmax(0,1fr))}
#mw-root .mw-four{grid-template-columns:repeat(4,minmax(0,1fr))}
#mw-root .mw-calc{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:16px;align-items:start}
#mw-root .mw-calc>*{min-width:0}
#mw-root .mw-metric{border:1px solid var(--glassline);border-radius:12px;padding:16px;background:var(--cardT);box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow);min-width:0}
#mw-root .mw-mlabel{color:var(--muted);font-size:12px;line-height:1.6}
#mw-root .mw-mvalue{font-size:24px;font-weight:650;letter-spacing:-.01em;line-height:1.25;margin:8px 0;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#mw-root .mw-mnote{color:var(--muted);font-size:12px;line-height:1.5}
#mw-root .mw-kv,#mw-modal .mw-kv{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
#mw-root .mw-kv:last-child,#mw-modal .mw-kv:last-child{border-bottom:0}
#mw-root .mw-kv>span,#mw-modal .mw-kv>span{color:var(--muted);flex:none}
#mw-root .mw-kv>strong,#mw-modal .mw-kv>strong{font-weight:500;text-align:right;min-width:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
#mw-root .mw-na{color:var(--muted)}
#mw-root .mw-note,#mw-modal .mw-note{color:var(--muted);font-size:12px;line-height:1.6;margin:8px 0;overflow-wrap:anywhere}
#mw-root .mw-end{float:right;color:var(--text);font-weight:500;font-variant-numeric:tabular-nums}
#mw-root .mw-balance{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums;margin:4px 0 0;overflow-wrap:anywhere}
#mw-root .mw-avail{color:var(--muted);font-size:12px;margin:0 0 12px}
#mw-root .mw-callout,#mw-modal .mw-callout{margin:12px 0;padding:10px 14px;border-radius:8px;border:1px solid var(--line);background:var(--chip);font-size:13px;line-height:1.6;overflow-wrap:anywhere}
#mw-root .mw-callout.warn,#mw-modal .mw-callout.warn{background:var(--warnbg);color:var(--warn);border-color:var(--warnbg)}
#mw-root .mw-callout.error,#mw-modal .mw-callout.error{background:var(--badbg);color:var(--bad);border-color:var(--badbg)}
#mw-root .mw-form,#mw-modal .mw-form{display:grid;gap:16px}
#mw-root .mw-form-grid,#mw-modal .mw-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px}
#mw-root .mw-form-grid>*,#mw-modal .mw-form-grid>*{min-width:0}
#mw-root .mw-span2,#mw-modal .mw-span2{grid-column:1/-1}
#mw-root .mw-field,#mw-modal .mw-field{display:grid;gap:6px;min-width:0;font-size:13px}
#mw-root .mw-field>label,#mw-modal .mw-field>label{color:var(--muted);font-size:12px}
#mw-root .mw-field input:not([type=checkbox]):not([type=radio]),#mw-root .mw-field select,#mw-root .mw-field textarea,#mw-modal .mw-field input:not([type=checkbox]):not([type=radio]),#mw-modal .mw-field select,#mw-modal .mw-field textarea{width:100%;min-width:0;min-height:36px;box-sizing:border-box}
#mw-root .mw-field textarea,#mw-modal .mw-field textarea{min-height:72px;resize:vertical;padding:8px 10px}
#mw-root .mw-field .dd-select,#mw-modal .mw-field .dd-select{display:block;width:100%}
#mw-root .mw-field .dd-select>.dd-btn,#mw-modal .mw-field .dd-select>.dd-btn{width:100%}
#mw-root .mw-row,#mw-modal .mw-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
#mw-root .mw-between{justify-content:space-between}
#mw-root .mw-check,#mw-modal .mw-check{display:inline-flex;align-items:center;gap:6px;color:var(--text);font-size:13px;user-select:none}
#mw-root .mw-check input,#mw-modal .mw-check input{margin:0;accent-color:var(--accent)}
#mw-root .mw-presets,#mw-modal .mw-presets{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
#mw-root .mw-presets button,#mw-modal .mw-presets button{min-height:32px;padding:4px 10px;border-radius:999px;font-size:12px;background:var(--chip);border-color:var(--glassline);color:var(--muted)}
#mw-root .mw-presets button:hover,#mw-modal .mw-presets button:hover{color:var(--text);border-color:var(--line2)}
#mw-root .mw-presets button[aria-pressed=true],#mw-modal .mw-presets button[aria-pressed=true]{background:var(--accentbg);border-color:var(--accent);color:var(--accent);font-weight:600}
#mw-root .mw-seg,#mw-modal .mw-seg{display:inline-flex;flex-wrap:wrap;gap:4px;padding:4px;border:1px solid var(--glassline);border-radius:999px;background:var(--chipbg);max-width:100%}
#mw-root .mw-seg button,#mw-modal .mw-seg button{min-height:32px;padding:0 12px;border:0;border-radius:999px;background:transparent;color:var(--muted);font:inherit;font-size:13px;box-shadow:none;transition:background-color .16s ease,color .16s ease}
#mw-root .mw-seg button:hover,#mw-modal .mw-seg button:hover{color:var(--text);background:var(--rowhover)}
#mw-root .mw-seg button:active,#mw-modal .mw-seg button:active{transform:scale(.98)}
#mw-root .mw-seg button[aria-pressed=true],#mw-modal .mw-seg button[aria-pressed=true]{background:var(--accentbg);color:var(--accent);font-weight:600;box-shadow:inset 0 0 0 1px var(--accent)}
#mw-root .mw-seg button:disabled,#mw-modal .mw-seg button:disabled{opacity:.45;cursor:not-allowed}
#mw-root .mw-small,#mw-modal .mw-small{min-height:32px;padding:4px 10px;font-size:12px;border-radius:7px}
#mw-root .mw-primary,#mw-modal .mw-primary{background:var(--accent);border-color:transparent;color:var(--onaccent);font-weight:600}
#mw-root .mw-danger,#mw-modal .mw-danger{background:var(--badbg);border-color:transparent;color:var(--bad);font-weight:600}
#mw-root .mw-ghost,#mw-modal .mw-ghost{background:transparent;border-color:transparent;color:var(--muted)}
#mw-root .mw-ghost:hover,#mw-modal .mw-ghost:hover{color:var(--text);background:var(--rowhover)}
#mw-root .mw-table{overflow-x:auto;margin:0 -2px;padding:0 2px;max-width:100%}
#mw-root .mw-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
#mw-root .mw-mcard{border:1px solid var(--glassline);border-radius:12px;padding:16px;background:var(--cardT);min-width:0;box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow);transition:border-color .12s ease,box-shadow .12s ease}
#mw-root .mw-mcard:hover{border-color:var(--line2);box-shadow:var(--lift)}
#mw-root .mw-prices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:12px 0;font-size:12px;color:var(--muted)}
#mw-root .mw-prices b{display:block;color:var(--text);font-weight:600;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
#mw-root .mw-name{font-weight:600;font-size:14px;background:transparent;border:0;padding:0;text-align:left;color:var(--text);min-height:0}
#mw-root .mw-name:hover{color:var(--accent);border:0}
#mw-root .mw-name-sm{display:block;font-weight:600;overflow-wrap:anywhere}
#mw-root .mw-pick-model{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;text-align:left;min-height:44px}
#mw-root .mw-model-id{display:block;color:var(--muted);font-size:12px;font-weight:400;overflow-wrap:anywhere}
#mw-root .mw-bulk{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 12px;margin:0 0 12px;border-radius:8px;background:var(--accentbg);color:var(--accent);font-size:13px}
#mw-root .mw-filters{display:grid;gap:8px;margin:0 0 12px}
#mw-root .mw-filters select,#mw-root .mw-filters input{min-width:0}
#mw-root .mw-search{flex:1 1 220px;min-width:0}
#mw-root .mw-foot{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:center;margin-top:12px;color:var(--muted);font-size:12px}
#mw-root .mw-hero{padding:4px 0 12px;border-bottom:1px solid var(--line);margin-bottom:12px}
#mw-root .mw-hv{font-size:28px;font-weight:650;letter-spacing:-.01em;font-variant-numeric:tabular-nums;margin:8px 0 4px;overflow-wrap:anywhere}
#mw-root .mw-step{padding:12px 0;border-top:1px solid var(--line)}
#mw-root .mw-step h4{margin:0 0 8px;font-size:13px;font-weight:600}
#mw-root .mw-empty{padding:24px 8px;color:var(--muted);text-align:center;line-height:1.7}
#mw-root .mw-empty h4{margin:0 0 6px;color:var(--text);font-size:14px}
#mw-root .mw-empty p{margin:0}
#mw-root .mw-empty .mw-actions{margin-top:16px}
#mw-root .mw-cmp-list{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
#mw-root .mw-tools{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;margin-bottom:12px}
#mw-root .mw-tools>*{min-width:0}
#mw-root .mw-tools select,#mw-root .mw-tools input{min-width:0}
#mw-root .mw-wallet-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
#mw-root .mw-wallet-head h3{margin:0;overflow-wrap:anywhere}
#mw-root .mw-wallet-actions{margin-top:16px}
#mw-modal .modal-panel{max-width:min(760px,100%);background:var(--card)}
#mw-modal .mw-modal-foot{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;padding:12px;border-top:1px solid var(--line)}
#mw-modal .mw-modal-foot[hidden]{display:none}
#mw-modal .mw-picker-list{display:grid;gap:8px;max-height:min(52vh,420px);overflow:auto;padding-right:2px}
#mw-modal .mw-pick-row{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;background:var(--card2)}
#mw-modal .mw-pick{flex:1 1 auto;min-width:0;text-align:left;border:0;background:transparent;padding:4px 0;color:var(--text);min-height:0}
#mw-modal .mw-pick-meta{color:var(--muted);font-size:12px;display:block;overflow-wrap:anywhere}
#mw-modal .mw-modal-body{font-size:13px}
#mw-modal .mw-modal-body h3{font-size:14px}
#mw-toast{display:none;margin:12px 0 0;padding:10px 14px;border-radius:8px;border:1px solid var(--line2);background:var(--card2);color:var(--text);font-size:13px;align-items:center;gap:8px;flex-wrap:wrap}
#mw-toast.show{display:flex}
#mw-toast.error{color:var(--bad);border-color:var(--badbg);background:var(--badbg)}
#mw-root :focus-visible,#mw-modal :focus-visible,#mw-toast :focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#mw-root .mw-field input[type=range]{-webkit-appearance:none;appearance:none;min-height:32px;height:32px;padding:0;margin:0;border:0;box-shadow:none;background:transparent;cursor:pointer;--mw-progress:0%}
#mw-root input[type=range]::-webkit-slider-runnable-track{height:8px;border-radius:999px;background:linear-gradient(to right,var(--accent) 0 var(--mw-progress),var(--line2) var(--mw-progress) 100%)}
#mw-root input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;margin-top:-6px;border-radius:50%;border:2px solid var(--accent);background:var(--card2);box-shadow:0 2px 6px var(--glassline)}
#mw-root input[type=range]::-moz-range-track{height:8px;border-radius:999px;background:var(--line2)}
#mw-root input[type=range]::-moz-range-progress{height:8px;border-radius:999px;background:var(--accent)}
#mw-root input[type=range]::-moz-range-thumb{width:16px;height:16px;border-radius:50%;border:2px solid var(--accent);background:var(--card2)}
#mw-root input[type=range]:hover{filter:brightness(1.08)}
#mw-root input[type=range]:active{cursor:grabbing}
#mw-root input[type=range]:disabled{opacity:.45;cursor:not-allowed}
#mw-root .mw-tabs{gap:24px;border-bottom:1px solid var(--line);margin-bottom:20px}
#mw-root .mw-tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;box-shadow:none;padding:12px 0;color:var(--muted);font-size:14px;font-weight:500}
#mw-root .mw-tabs button:hover{color:var(--text);background:transparent}
#mw-root .mw-tabs button[aria-current=page]{border-bottom-color:var(--accent);color:var(--text);font-weight:600}
#mw-root .mw-tabs button:active{opacity:.7}
#mw-root .mw-panel{border:0;border-radius:0;background:transparent;box-shadow:none;padding:0;margin-bottom:20px}
#mw-root .mw-empty{padding:16px 0;text-align:left;font-size:13px}
#mw-root .mw-empty h4{font-size:13px;font-weight:500}
#mw-root .mw-empty .mw-actions{justify-content:flex-start;margin-top:8px}
#mw-root .mw-model-toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-bottom:16px}
#mw-root .mw-model-toolbar>div{flex:0 1 160px;min-width:0}
#mw-root .mw-model-toolbar .mw-search{display:grid;gap:6px;flex:1 1 240px;min-width:0;font-size:12px;color:var(--muted)}
#mw-root .mw-model-toolbar input{width:100%;box-sizing:border-box}
#mw-root .mw-wallet-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;border-bottom:1px solid var(--line);padding-bottom:16px;margin-bottom:20px}
#mw-root .mw-wallet-summary .mw-metric{padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
#mw-root .mw-wallet-summary .mw-mvalue{font-size:22px;margin:4px 0}
#mw-root .mw-wallet-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin-bottom:20px}
#mw-root .mw-wallet-item{border-bottom:1px solid var(--line);padding-bottom:16px}
#mw-root .mw-wallet-item .mw-wallet-actions{margin-top:8px}
#mw-root .mw-ledger{background:transparent;border:0;border-top:1px solid var(--line);box-shadow:none;border-radius:0;padding:16px 0}
#mw-root .mw-ledger h3{font-size:14px;margin:0 0 12px}
#mw-root .mw-inline-empty{font-size:13px;color:var(--muted);margin:12px 0 20px}
#mw-root .mw-settings-list{max-width:760px;display:grid;gap:20px}
#mw-root .mw-settings-list>.mw-panel{border-bottom:1px solid var(--line);padding-bottom:20px;margin:0}
@media (max-width:55em){#mw-root .mw-wallet-summary{grid-template-columns:repeat(2,minmax(0,1fr))}#mw-root .mw-wallet-list{grid-template-columns:minmax(0,1fr)}}
@media (max-width:74em){#mw-root .mw-four{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:55em){#mw-root .mw-three{grid-template-columns:repeat(2,minmax(0,1fr))}#mw-root .mw-calc{grid-template-columns:minmax(0,1fr)}}
@media (max-width:38em){
 #mw-root .mw-two,#mw-root .mw-three,#mw-root .mw-four,#mw-root .mw-form-grid,#mw-modal .mw-form-grid,#mw-root .mw-prices{grid-template-columns:minmax(0,1fr)}
 #mw-root .mw-cards{grid-template-columns:minmax(0,1fr)}
 #mw-root .mw-heading{flex-direction:column}
 #mw-root .mw-tools>*{flex:1 1 100%}
 #mw-modal .modal-panel{max-height:calc(100dvh - 24px)}
}
@media (pointer:coarse){#mw-root button,#mw-root select,#mw-root input:not([type=checkbox]):not([type=radio]),#mw-modal button,#mw-modal select,#mw-modal input:not([type=checkbox]):not([type=radio]){min-height:44px}}
@keyframes mw-view-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
#mw-root [role=tabpanel].mw-view-in{animation:mw-view-in .22s ease}
@media (prefers-reduced-motion:reduce){#mw-root *,#mw-modal *,#mw-toast{transition:none!important;animation:none!important}}
'''

HTML = r'''
<div class="pagehead" data-view="wallet"><h2>模型钱包</h2><p>比较价格和计算预算。余额与交易由你手工登记，不会实际扣款。</p></div>
<section data-view="wallet"><div id="mw-root"><div class="mw-empty"><p>正在读取本地数据…</p></div></div><p id="mw-toast" role="status" aria-live="polite"></p></section>
<dialog id="mw-modal" class="modal-backdrop" aria-labelledby="mw-modal-title"><div class="modal-panel"><div class="modal-head"><span id="mw-modal-title"></span><button type="button" data-mw-close aria-label="关闭">×</button></div><div class="modal-body mw-modal-body" id="mw-modal-body" tabindex="0"></div><div class="mw-modal-foot" id="mw-modal-foot" hidden></div></div></dialog>
'''

JS = r'''
(function(){
'use strict';
/* 模型钱包：原型 Model Wallet Console 的界面迁入 Context Gate 控制台。
   原型的全部名字（$、api、toast、state、render…）都留在本 IIFE 内；对控制台只暴露 loadWallet。 */
const qs=s=>document.querySelector(s);
const qsa=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc=encodeURIComponent;
const decRe=/^-?\d+(\.\d+)?$/,posRe=/^\d+(\.\d+)?$/,intRe=/^\d+$/;
const nz=v=>{const s=String(v??'').trim();return s===''?null:s};
const csv=v=>String(v??'').split(',').map(x=>x.trim()).filter(Boolean);
const newId=p=>`${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
const ageDays=v=>{const t=Date.parse(v);return Number.isFinite(t)?(Date.now()-t)/86400000:null};
const daysUntil=v=>{const t=Date.parse(v);return Number.isFinite(t)?Math.ceil((t-Date.now())/86400000):null};
const ts=v=>esc(String(v||'').replace('T',' ').slice(0,19)||'—');
const date=v=>v?esc(String(v).slice(0,10)):T('未验证');
const NA=()=>'<span class="mw-na">N/A</span>';
const btn=(text,action,cls='')=>`<button type="button" class="${cls}" data-mw-action="${action}">${text}</button>`;
const heading=(title,sub,actions='')=>`<div class="mw-heading"><div><h3>${title}</h3><p class="mw-sub">${sub}</p></div><div class="mw-actions">${actions}</div></div>`;
const panel=(title,body,action='')=>`<section class="mw-panel"><div class="mw-row mw-between"><h3>${title}</h3>${action}</div>${body}</section>`;
const kv=(label,value)=>`<div class="mw-kv"><span>${label}</span><strong>${value}</strong></div>`;
const empty=(title,note,action='')=>`<div class="mw-empty"><h4>${title}</h4><p>${note}</p>${action?`<div class="mw-actions mw-center">${action}</div>`:''}</div>`;
const field=(label,name,value,type='text',extra='')=>`<div class="mw-field"><label for="mw-f-${name}">${label}</label><input id="mw-f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
const select=(label,name,options)=>`<div class="mw-field"><label for="mw-f-${name}">${label}</label><select id="mw-f-${name}" name="${name}">${options}</select></div>`;
const option=(v,label,selected)=>`<option value="${esc(v)}"${v===selected?' selected':''}>${esc(label??v)}</option>`;
const seg=(items,attr,active,disabled=false)=>`<div class="mw-seg" role="group">${items.map(([v,l])=>`<button type="button" ${attr}="${esc(v)}" aria-pressed="${String(v===active)}"${disabled?' disabled':''}>${esc(l)}</button>`).join('')}</div>`;
const metric=(label,value,note)=>`<div class="mw-metric"><div class="mw-mlabel">${label}</div><div class="mw-mvalue">${value}</div><div class="mw-mnote">${note}</div></div>`;
const cats=m=>Array.isArray(m.category)?m.category:Array.isArray(m.categories)?m.categories:[m.category].filter(Boolean);
const providers=()=>[...new Set(state.models.map(m=>m.apiProvider).filter(Boolean))].sort();
const modelName=m=>m?.displayName||m?.name||m?.id||T('选择模型');
const currentModel=()=>state.transient||state.models.find(m=>m.id===state.modelId);
const statusLabel=k=>({CURRENT:T('现行'),NEW:T('新发布'),PREVIEW:T('预览'),PREVIOUS:T('上一代'),LEGACY:T('旧版'),DEPRECATED:T('弃用'),RETIRED:T('已退役'),UNKNOWN:T('未知')})[k]||k;
const categoryLabel=k=>({Text:T('文本'),Coding:T('编程'),Reasoning:T('推理'),Fast:T('快速'),Budget:T('经济'),Multimodal:T('多模态'),Translation:T('翻译'),Image:T('图像'),Audio:T('音频'),Custom:T('自定义')})[k]||k;
const presetLabel=k=>({Chat:T('聊天'),'Coding Agent':T('编程 Agent'),'Long-context Coding':T('长上下文编程'),Reasoning:T('推理'),'Document Analysis':T('文档分析'),Translation:T('翻译'),'Batch Processing':T('批量处理')})[k]||k;
const badges=m=>cats(m).slice(0,3).map(x=>`<span class="tag">${esc(categoryLabel(x))}</span>`).join('');
const count=v=>`<span title="${esc(v??T('未知'))}" tabindex="0">${compact(v)}</span>`;
const compact=v=>{if(v===null||v===undefined||v==='')return 'N/A';const n=Number(v);if(!Number.isFinite(n))return esc(v);return new Intl.NumberFormat('en-US',{notation:state.settings.numberFormat==='full'?'standard':'compact',maximumFractionDigits:3}).format(n)};
const money=(v,c='USD')=>{if(v===null||v===undefined||v==='')return NA();const str=String(v),prefix={USD:'$',CAD:'CA$',CNY:'¥'}[c]||c+' ';if(!/^[-+]?\d+(\.\d+)?$/.test(str))return NA();const [a,b='']=str.split('.');return esc(prefix)+esc(a.replace(/\B(?=(\d{3})+(?!\d))/g,','))+(b?'.'+esc(b.slice(0,6).replace(/0+$/,'')||'00'):'.00')};
const walletOf=id=>state.wallets.find(w=>w.id===id);
const walletName=id=>esc(walletOf(id)?.name||id||'—');
const walletCurrency=id=>walletOf(id)?.currency||'USD';
const modelLabel=id=>{const m=state.models.find(x=>x.id===id);return esc(m?modelName(m):(id||'—'))};
const safeLink=(url,label)=>{try{const u=new URL(url);return u.protocol==='https:'||u.protocol==='http:'?`<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`:NA()}catch{return NA()}};
const sel=(id,label,opts)=>`<select id="mw-${id}" aria-label="${esc(label)}">${opts}</select>`;
const expiryText=v=>{if(!v)return T('无到期日');const d=daysUntil(v);const tag=d===null?'':d<0?T(' · 已过期'):d<=30?` · ${d} ${T('天后到期')}`:'';return `${esc(String(v).slice(0,10))}${tag}`};
const sourceBadge=s=>{const meta={LIVE_API:['LIVE_API','success',T('官方实时')],ESTIMATED:['ESTIMATED','warning',T('估算')],MANUAL:['MANUAL','',T('手工记录')]}[s];return meta?`<span class="tag ${meta[1]}" title="${esc(T('余额来源'))}">${meta[0]} · ${meta[2]}</span>`:`<span class="tag" title="${esc(T('余额来源'))}">${esc(s||'UNKNOWN')} · ${esc(T('未知来源'))}</span>`};
const ledgerTypes=['RESERVATION','RELEASE','USAGE','CREDIT','ADJUSTMENT','REFUND'];
const ledgerLabel=k=>({RESERVATION:T('预留'),RELEASE:T('释放'),USAGE:T('用量扣款'),CREDIT:T('入账'),ADJUSTMENT:T('余额调整'),REFUND:T('退款')})[k]||k;
const tabDefs=()=>[['dashboard',T('总览')],['calculator',T('成本计算')],['models',T('模型目录')],['compare',T('模型对比')],['wallets',T('钱包')],['usage',T('用量账本')],['contextgate',T('路由模拟')],['custom',T('自定义模型')],['settings',T('设置')]];
const presets={Chat:[60,40,25],'Coding Agent':[85,15,90],'Long-context Coding':[90,10,95],Reasoning:[50,50,50],'Document Analysis':[95,5,90],Translation:[50,50,0],'Batch Processing':[80,20,75]};
const routeStrategies=()=>[['CHEAPEST_FIRST',T('最低成本优先')],['QUALITY_FIRST',T('质量优先（需用户提供评分）')],['EXPIRING_CREDITS_FIRST',T('到期额度优先')],['WALLET_BALANCE_AWARE',T('余额感知')],['BALANCED',T('均衡')]];
const resetMeta=()=>({builtins:[T('恢复内置模型目录'),T('重新导入随包附带的已验证目录，保留钱包与账本。')],models:[T('重置模型设置'),T('清除隐藏、启用、收藏与价格覆盖；自定义模型保留。')],calculator:[T('重置计算器设置'),T('恢复默认预算、比例、Cache、显示与手工汇率设置。')],all:[T('重置本地数据'),T('删除钱包、账本、用量、预留、审计与自定义模型，不可撤销。')]});

/* ---------- 状态 ---------- */
const calcDefaults={budget:'100',currency:'USD',input:80,output:20,cache:90,totalTokens:'1000000',averageInputTokens:'60000',averageOutputTokens:'8000',uncached:10,read:90,write:0,promptTokens:'60000'};
const state={models:[],wallets:[],settings:{},dashboard:{},catalogVersion:'',catalogUpdatedAt:'',selected:new Set(),compare:new Set(),compareResults:[],recent:[],page:'calculator',mode:'money',cacheMode:'basic',view:'table',
  filters:{search:'',custom:false,providers:[],category:'',capability:'',status:'active',price:'',context:'',sort:'name',hidden:false,favorite:false},
  calc:JSON.parse(JSON.stringify(calcDefaults)),modelId:'',result:null,transient:null,
  ctx:{modelId:'',walletId:'',requestId:'',input:'60000',output:'8000',cache:'90',actualInput:'60000',actualOutput:'8000',actualCacheRead:'54000',refundAmount:''},
  sim:null,routeResult:null,usageRows:null,usageError:'',usageLoading:false,usageFilter:{wallet:'',type:'',record:'ledger'}};
let modalKind='',loaded=false,toastTimer=0,pickerTab='all',pickerSearch='';

/* ---------- 接口：控制台只有 GET 与 POST；原型的 PATCH 走 POST ?_method=PATCH。路径令牌由相对地址自动带上。 */
async function api(path,method='GET',data,keepalive=false){
  const isPatch=method==='PATCH';
  const url='v1/wallet/'+path+(isPatch?'?_method=PATCH':'');
  const init=method==='GET'?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data===undefined?{}:data)};
  if(keepalive)init.keepalive=true;
  const r=await fetch(url,init);
  if(r.status===403&&typeof showReconnect==='function'){showReconnect(T('服务已重启，连接令牌已更新，本次操作没有生效。'));throw Error(T('服务已重启，请按横幅提示重开控制台'))}
  let out;try{out=await r.json()}catch{throw Error(T('服务端未返回 JSON，请确认应用已启动'))}
  if(!r.ok||out.error){const e=out.error;throw Error(typeof e==='object'&&e!==null?`${e.code?e.code+' · ':''}${e.message||T('操作失败')}`:(typeof e==='string'?e:(out.message||('HTTP '+r.status))))}
  return out;
}
function toast(message,error=false,undo){const el=qs('#mw-toast');if(!el)return;clearTimeout(toastTimer);el.className='show'+(error?' error':'');el.textContent=String(message);if(undo){const b=document.createElement('button');b.type='button';b.className='mw-small';b.textContent=T('撤销');b.onclick=undo;el.append(' ',b)}toastTimer=setTimeout(()=>{el.className=''},undo?10000:5000)}
async function run(fn){try{return await fn()}catch(e){toast(e.message,true)}}
async function reload(){
  const b=await api('bootstrap');
  Object.assign(state,{models:b.models||[],wallets:b.wallets||[],settings:b.settings||{},dashboard:b.dashboard||{},catalogVersion:b.catalogVersion,catalogUpdatedAt:b.catalogUpdatedAt});
  state.recent=state.settings.recentModels||[];
  if(!state.modelId)state.modelId=state.models.find(m=>m.enabled&&!m.hidden&&m.inputPrice!=null&&m.outputPrice!=null)?.id||state.models[0]?.id||'';
}

/* ---------- 渲染骨架 ---------- */
function tabsHtml(){
  const group=['models','custom','compare'].includes(state.page)?'models':['dashboard','wallets','usage','contextgate'].includes(state.page)?'wallets':state.page;
  return `<nav class="mw-tabs" aria-label="${esc(T('模型钱包子页面'))}">${[['calculator',T('成本计算')],['models',T('模型库')],['wallets',T('钱包与账本')],['settings',T('设置')]].map(([k,l])=>`<button type="button" aria-current="${group===k?'page':'false'}" data-mw-tab="${k}">${esc(l)}</button>`).join('')}</nav>`;
}
const renderers={dashboard:()=>dashboard(),calculator:()=>calculator(),models:()=>models(false),compare:()=>compare(),wallets:()=>wallets(),usage:()=>wallets(),contextgate:()=>contextgate(),custom:()=>models(true),settings:()=>settings()};
function render(){const root=qs('#mw-root');if(!root)return;root.innerHTML=tabsHtml()+`<div role="tabpanel">${renderers[state.page]()}</div>`}
function rerender(){const a=document.activeElement;const id=a&&a.id;const pos=a&&typeof a.selectionStart==='number'?a.selectionStart:null;render();if(id){const el=document.getElementById(id);if(el){el.focus();if(pos!=null){try{el.setSelectionRange(pos,pos)}catch{}}}}}
function go(p){readCalc();readCtx();queueDraft(true);if(p==='usage')p='wallets';state.page=p;render();const panel=qs('#mw-root [role=tabpanel]');if(panel){panel.classList.remove('mw-view-in');void panel.offsetWidth;panel.classList.add('mw-view-in')}if(p==='usage'||p==='wallets')loadUsage()}
async function patchModel(id,body,msg){try{await api('models/'+enc(id),'PATCH',body);await reload();if(modalKind==='picker')renderPicker();render();if(msg)toast(msg)}catch(e){render();toast(e.message,true)}}

/* ---------- 总览 ---------- */
function dashboard(){
  const d=state.dashboard,p=d.periods||{},g=d.groups||{},w=state.wallets;
  return heading(T('成本与额度总览'),T('目录、预算与账务统一管理。当前环境不会发送真实模型请求。'),`<button type="button" class="mw-small" data-mw-nav="wallets">${T('返回钱包与账本')}</button>`)
  +`<div class="mw-grid mw-four">`
  +metric(T('可用额度 · USD'),money(d.totalWalletBalanceUSD),`${w.length} ${T('个本地钱包')}${d.walletsMissingExchangeRate?.length?' · '+T('含未配置汇率钱包'):''}`)
  +metric(T('今日支出'),money(p.today?.cost),`${p.today?.requests||0} ${d.simulationIncluded?T('次模拟结算'):T('次结算')}`)
  +metric(T('今日 Tokens'),count(p.today?.tokens),T('仅来自本地用量账本'))
  +metric(T('预计可用天数'),d.estimatedDaysRemaining?compact(d.estimatedDaysRemaining)+' '+T('天'):'—',T('按近 30 天日均消耗估算'))
  +`</div><div class="mw-grid mw-two">`
  +panel(T('支出概览'),kv(T('近 7 天'),money(p['7d']?.cost))+kv(T('近 30 天'),money(p['30d']?.cost))+kv(T('缓存节省'),money(d.cacheSavings))+`<p class="mw-note">${d.simulationIncluded?T('含用户主动创建的模拟用量；不等于供应商账单。'):T('尚未产生消费。创建钱包后可主动执行一笔模拟预留与结算。')}</p>`)
  +panel(T('目录状态'),kv(T('模型条目'),state.models.length)+kv(T('API 服务商数'),providers().length)+kv(T('已启用'),state.models.filter(m=>m.enabled&&!m.hidden).length)+kv(T('价格未确认'),state.models.filter(m=>m.inputPrice==null||m.outputPrice==null).length)+kv(T('目录版本'),esc(state.catalogVersion||'unknown')),btn(T('管理模型 →'),'nav-models','mw-small'))
  +`</div><div class="mw-grid mw-three">`
  +[['modelId',T('常用模型')],['provider',T('常用服务商')],['agentId',T('常用 AI 助手')]].map(([k,title])=>panel(T(title),(g[k]||[]).slice(0,5).map(x=>kv(esc(k==='modelId'?modelName(state.models.find(m=>m.id===x.id)):x.id),money(x.cost))).join('')||empty(T('暂无用量'),T('完成一笔模拟结算后，按模型和服务商统计将在这里显示。')))).join('')
  +`</div>`
  +panel(T('即将到期额度'),(d.creditsExpiringSoon||[]).map(x=>kv(esc(x.name),money(x.availableBalance,x.currency)+' · '+date(x.expiresAt))).join('')||`<p class="mw-sub">${T('没有已登记的即将到期额度。')}</p>`);
}

/* ---------- 成本计算 ---------- */
function calculator(){
  const c=state.calc,m=currentModel(),cache=m?.supportsCache!==false;
  const modes=[['money',T('预算 → Tokens')],['tokens',T('Tokens → 成本')],['requests',T('请求数')]];
  return heading(T('成本计算器'),T('按统一价格规则计算。结果为估算，不代表实际账单。'),btn(Date.now()<copiedUntil?T('已复制'):T('复制计算摘要'),'share','mw-small')+resetButton())
  +`<p id="mw-draft-status" class="mw-note" role="status"${draftError?'':' hidden'}>${esc(draftError)}</p><div class="mw-calc"><section class="mw-panel"><div class="mw-row">${seg(modes,'data-mw-mode',state.mode)}</div>`
  +`<form id="mw-calc-form" class="mw-form" data-mw-form="calc" style="margin-top:16px">`
  +`<div class="mw-field"><span class="mw-sub">${T('模型与 API 接口')}</span><button type="button" class="mw-pick-model" data-mw-action="picker"><span><span class="mw-name-sm">${esc(modelName(m))}</span><span class="mw-model-id">${esc(m?.apiProvider||'Registry')} · ${esc(m?.id||'')}${state.transient?' · '+esc(T('本次临时模型')):''}</span></span><span aria-hidden="true">⌄</span></button>`
  +(m?.priceConditions?`<div class="mw-callout warn">${esc(typeof m.priceConditions==='string'?m.priceConditions:JSON.stringify(m.priceConditions))}</div>`:'')
  +`<small class="mw-note">${T('输入')} ${money(m?.inputPrice)} / ${T('输出')} ${money(m?.outputPrice)} · USD / 1M · ${date(m?.priceLastVerifiedAt)}</small></div>`
  +`<div class="mw-form-grid">${state.mode==='tokens'?field(T('总 Tokens'),'totalTokens',c.totalTokens,'number','min="0" step="any"'):field(T('预算'),'budget',c.budget,'number','min="0" step="any"')}${select(T('显示货币'),'currency',['USD','CAD','CNY'].map(x=>option(x,x,c.currency)).join(''))}</div>`
  +`<hr>`
  +(state.mode==='requests'
    ?`<div class="mw-form-grid">${field(T('平均 Input / Request'),'averageInputTokens',c.averageInputTokens,'number','min="0"')}${field(T('平均 Output / Request'),'averageOutputTokens',c.averageOutputTokens,'number','min="0"')}</div>`
    :`<div class="mw-field"><label>${T('输入 / 输出比例')} <strong class="mw-end"><span id="mw-ratio-label">${esc(c.input)}% / ${esc(c.output)}%</span></strong></label><input aria-label="${esc(T('输入占比'))}" id="mw-input-range" type="range" min="0" max="100" style="--mw-progress:${esc(c.input)}%" value="${esc(c.input)}"><div class="mw-form-grid">${field(T('输入 %'),'input',c.input,'number','min="0" max="100"')}${field(T('输出 %'),'output',c.output,'number','min="0" max="100"')}</div></div>`)
  +`<div class="mw-field"><label for="mw-usage-preset">${T('使用预设')} <span class="tag">${T('估算预设')}</span></label><select id="mw-usage-preset"><option value="">${T('自定义比例')}</option>${Object.keys(presets).map(x=>option(x,presetLabel(x))).join('')}</select></div>`
  +`<div class="mw-row mw-between"><span class="mw-sub">${T('输入缓存')}</span>${seg([['basic',T('基础')],['advanced',T('高级')]],'data-mw-cache-mode',state.cacheMode,!cache)}</div>`
  +(state.cacheMode==='advanced'&&cache
    ?`<div class="mw-form-grid">${field(T('未缓存输入 %'),'uncached',c.uncached,'number','min="0" max="100"')}${field(T('缓存读取 %'),'read',c.read,'number','min="0" max="100"')}${field(T('缓存写入 %'),'write',c.write,'number','min="0" max="100"')}</div><p class="mw-note">${T('三项总计须为 100%，未知 cache-write 价格会阻止对应计费。')}</p>`
    :`<div class="mw-field"><label for="mw-cache-range">${T('缓存命中率')} <b class="mw-end" id="mw-cache-label">${cache?esc(c.cache):0}%</b></label><input id="mw-cache-range" aria-label="${esc(T('缓存命中率'))}" type="range" min="0" max="100" style="--mw-progress:${cache?esc(c.cache):0}%" value="${cache?esc(c.cache):0}"${!cache?' disabled':''}>${field(T('缓存命中率 %'),'cache',cache?c.cache:0,'number',`min="0" max="100"${!cache?' disabled':''}`)}${!cache?`<small class="mw-note">${T('该模型明确不支持 Cache。')}</small>`:''}</div>`)
  +field(T('单次提示 Tokens · 价格区间'),'promptTokens',c.promptTokens,'number','min="0"')
  +`<p class="mw-note">${T('总预算 Tokens 是累计量；单次 Prompt 决定长上下文价格条件。非 token 计费模型请查看详情中的计费单位。')}</p>`
  +`<div class="mw-field"><label for="mw-wallet-budget">${T('使用钱包可用额度')}</label><select id="mw-wallet-budget"><option value="">${T('手动预算')}</option>${state.wallets.map(w=>option(w.id,`${w.name} · ${w.currency} ${w.availableBalance}`)).join('')}</select></div>`
  +`<button class="mw-primary" type="submit">${state.mode==='money'?T('计算可用 Tokens →'):state.mode==='tokens'?T('计算预估成本 →'):T('计算可运行请求数 →')}</button>`
  +`</form></section><div id="mw-calc-result">${resultView(state.result)}</div></div>`;
}
function resultView(r){
  if(!r)return panel(T('计算结果'),empty(T('估算你的下一次工作负载'),T('选择模型、设置预算与使用比例，然后计算。')+'<br>'+T('未知价格将显示明确错误，绝不会当作免费。')));
  const token=state.mode!=='tokens',hero=state.mode==='requests'?count(r.estimatedRequests)+' '+T('次'):token?count(r.totalTokens)+' Tokens':money(r.displayCost??r.totalCost,r.currency);
  return `<section class="mw-panel"><div class="mw-hero"><span class="tag prepared">${T('估算')}</span><div class="mw-hv">${hero}</div><p class="mw-sub">${esc(modelName(currentModel()))} · ${esc(r.provider)}</p></div>`
  +kv(T('预算'),money(r.budget,r.currency))+kv(T('每百万 tokens 的估算费用 · 美元'),money(r.effectiveCostPerMillion))+kv(T('总 Tokens'),count(r.totalTokens))+kv(T('输入 / 输出'),count(r.inputTokens)+' / '+count(r.outputTokens))+kv(T('未缓存输入'),count(r.uncachedInputTokens))+kv(T('缓存读取 / 写入'),count(r.cacheReadTokens)+' / '+count(r.cacheWriteTokens))
  +`<h3 style="margin-top:16px">${T('费用明细 · 美元')}</h3>`+kv(T('未缓存输入'),money(r.inputCost))+kv(T('输出'),money(r.outputCost))+kv(T('缓存读取 + 写入'),money(r.cacheCost))+kv(T('无 Cache 成本'),money(r.costWithoutCache))+kv(T('当前成本'),money(r.costWithCache))+kv(T('缓存节省'),money(r.cacheSavings)+' '+(r.savingsPercent!=null?'('+compact(r.savingsPercent)+'%)':''))+(r.costPerRequest!=null?kv(T('每次请求成本'),money(r.costPerRequest)):'')
  +`<details style="margin-top:16px"><summary>${T('价格版本与完整数字')}</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details><p class="mw-note">${T('按美元计算，再按所设汇率显示。')} ${T('价格版本')} ${esc(r.priceVersion||'unknown')}</p></section>`;
}
/* ---------- 计算器草稿：复用本地 settings，不保存钱包与账本 ---------- */
let draftReady=false,draftTimer=0,draftPending=null,draftSaving=null,draftInFlight=null,draftSuspended=false,draftCleared=false,draftRevision=0,draftSaved='',draftError='',calcRevision=0,calcRequest=0,copiedUntil=0,copyTimer=0;
const plain=v=>v&&typeof v==='object'&&!Array.isArray(v);
function calculatorDefaults(){const d={...calcDefaults},s=state.settings;d.currency=s.defaultCurrency||d.currency;d.budget=String(s.defaultBudget??d.budget);d.input=String(Number(s.defaultInputRatio??.8)*100);d.output=String(Number(s.defaultOutputRatio??.2)*100);d.cache=String(Number(s.defaultCacheRatio??.9)*100);d.read=d.cache;d.uncached=String(100-Number(d.cache));return d}
function defaultModel(){return state.models.find(m=>m.enabled&&!m.hidden&&['CURRENT','NEW','PREVIEW'].includes(String(m.status).toUpperCase())&&m.inputPrice!=null&&m.outputPrice!=null)?.id||''}
function calculatorDirty(){
  const defaults=calculatorDefaults();
  const equal=(a,b)=>String(a)===String(b)||(String(a).trim()!==''&&String(b).trim()!==''&&Number.isFinite(Number(a))&&Number(a)===Number(b));
  return Object.keys(defaults).some(k=>!equal(state.calc[k],defaults[k]))||state.mode!=='money'||state.cacheMode!=='basic'||state.modelId!==defaultModel()||Boolean(state.transient||state.result);
}
function resetButton(){const dirty=calculatorDirty();return `<button type="button" class="mw-small ${dirty?'mw-primary':'mw-ghost'}" data-mw-action="calc-reset"${dirty?'':' disabled'}>${T('重置计算器')}</button>`}
function updateResetButton(){const button=qs('#mw-root [data-mw-action=calc-reset]');if(!button)return;const dirty=calculatorDirty();button.className='mw-small '+(dirty?'mw-primary':'mw-ghost');button.disabled=!dirty}
function blendedPrice(m){const d=calculatorDefaults();const num=v=>v==null||v===''||!/^-?\d+(\.\d+)?$/.test(String(v))?null:Number(v);const ov=(m.priceOverride&&typeof m.priceOverride==='object')?m.priceOverride:{};const inp=num(ov.inputPrice)??num(m.inputPrice),out=num(ov.outputPrice)??num(m.outputPrice);if(inp==null||out==null)return null;const caR=Number(d.cache)/100,rdR=Number(d.read)/100,wrR=Number(d.write)/100,rd=num(ov.cacheReadPrice)??num(m.cacheReadPrice),wr=num(ov.cacheWritePrice)??num(m.cacheWritePrice);const inputEff=m.supportsCache===false?inp:caR*((rd==null?inp:rd)*rdR+(wr==null?inp:wr)*wrR)+(1-caR)*inp;return Number(d.input)/100*inputEff+Number(d.output)/100*out}
function introLine(m){const cs=(cats(m)||[]).map(categoryLabel);return [m.apiProvider,m.creator,statusLabel(m.status||'UNKNOWN'),cs.join(' / '),T('上下文')+' '+(m.contextWindow??T('未知'))].filter(Boolean).join(' · ')}
function calculatorDraft(){return JSON.parse(JSON.stringify({version:1,calc:state.calc,mode:state.mode,cacheMode:state.cacheMode,modelId:state.modelId,transient:state.transient,result:state.result}))}
function restoreDraft(){
  if(draftReady)return;
  const d=state.settings.calculatorDraft;
  draftRevision=Number.isSafeInteger(state.settings.calculatorDraftRevision)?state.settings.calculatorDraftRevision:0;
  state.calc=calculatorDefaults();state.modelId=defaultModel();
  if(plain(d)&&d.version===1&&plain(d.calc)){
    for(const k of Object.keys(calcDefaults))if(typeof d.calc[k]==='string'||typeof d.calc[k]==='number')state.calc[k]=String(d.calc[k]);
    if(['money','tokens','requests'].includes(d.mode))state.mode=d.mode;
    if(['basic','advanced'].includes(d.cacheMode))state.cacheMode=d.cacheMode;
    if(typeof d.modelId==='string'&&state.models.some(m=>m.id===d.modelId))state.modelId=d.modelId;
    if(plain(d.transient)){
      state.transient={};for(const k of ['id','name','displayName','creator','apiProvider','currency','inputPrice','outputPrice','cacheReadPrice','cacheWritePrice','contextWindow','supportsCache','supportsCoding','supportsReasoning','supportsTools','supportsVision','category','isCustom','status','notes'])if(k in d.transient)state.transient[k]=d.transient[k];
    }
    if(plain(d.result))state.result=d.result;
  }
  draftReady=true;draftCleared=!plain(d);draftSaved=JSON.stringify(calculatorDraft());
}
function draftStatus(message){draftError=message;const el=qs('#mw-draft-status');if(el){el.textContent=message;el.hidden=!message}if(message)toast(message,true)}
function draftPayload(value){draftRevision=Math.max(Date.now(),draftRevision+1);return {calculatorDraft:value,calculatorDraftRevision:draftRevision}}
function queueDraft(immediate=false){
  if(!draftReady||draftSuspended)return Promise.resolve(true);
  const value=calculatorDraft(),json=JSON.stringify(value);
  if(draftPending?.json===json||(!draftPending&&draftInFlight?.json===json))return immediate?flushDraft():Promise.resolve(true);
  clearTimeout(draftTimer);
  if(json===draftSaved&&!draftPending&&!draftSaving)return Promise.resolve(true);
  draftCleared=false;draftPending={payload:draftPayload(value),json};
  if(immediate)return flushDraft();
  draftTimer=setTimeout(()=>flushDraft(),500);return Promise.resolve(true);
}
async function flushDraft(){
  clearTimeout(draftTimer);
  if(draftSaving){await draftSaving;return draftPending?flushDraft():!draftError}
  draftSaving=(async()=>{
    while(draftPending){
      const next=draftPending;draftPending=null;draftInFlight=next;
      try{const settings=await api('settings','PATCH',next.payload,true);draftRevision=Math.max(draftRevision,Number(settings.calculatorDraftRevision)||0);draftSaved=next.json;draftStatus('')}
      catch(e){if(!draftPending)draftPending=next;draftStatus(T('计算器草稿未保存，请重试或保持页面打开。')+' '+e.message);return false}
      finally{draftInFlight=null}
    }
    return true;
  })();
  try{return await draftSaving}finally{draftSaving=null}
}
function calcChanged(){draftCleared=false;calcRevision++;updateResetButton();queueDraft()}
async function resetCalculator(announce=true){
  draftCleared=true;calcRevision++;calcRequest++;clearTimeout(draftTimer);
  state.calc=calculatorDefaults();state.mode='money';state.cacheMode='basic';state.modelId=defaultModel();state.transient=null;state.result=null;
  const json=JSON.stringify(calculatorDraft());draftPending={payload:draftPayload(null),json};render();
  if(await flushDraft()&&announce)toast(T('计算器已重置'));
}
function pageDraft(){
  if(!draftReady||draftSuspended)return;
  readCalc();const value=calculatorDraft(),json=JSON.stringify(value);
  if(json===draftSaved&&!draftPending&&!draftSaving)return;
  // A higher revision makes this final keepalive safe even while an older save is in flight.
  const next={payload:draftPayload(draftCleared?null:value),json};draftPending=next;clearTimeout(draftTimer);
  api('settings','PATCH',next.payload,true).then(settings=>{draftRevision=Math.max(draftRevision,Number(settings.calculatorDraftRevision)||0);if(draftPending===next)draftPending=null;draftSaved=next.json;draftStatus('')}).catch(e=>draftStatus(T('计算器草稿未保存，请重试或保持页面打开。')+' '+e.message));
}
function calcPayload(){const c=state.calc;return {mode:state.mode,modelId:state.modelId,...(state.transient?{customModel:state.transient}:{}),budget:c.budget,currency:c.currency,totalTokens:c.totalTokens,inputRatio:String(Number(c.input)/100),outputRatio:String(Number(c.output)/100),cacheRatio:String(Number(c.cache)/100),averageInputTokens:c.averageInputTokens,averageOutputTokens:c.averageOutputTokens,cacheMode:state.cacheMode,uncachedRatio:String(Number(c.uncached)/100),cacheReadRatio:String(Number(c.read)/100),cacheWriteRatio:String(Number(c.write)/100),promptTokens:c.promptTokens};}
function readCalc(){const f=qs('#mw-calc-form');if(!f)return;for(const k of Object.keys(state.calc)){const input=f.elements.namedItem(k);if(input)state.calc[k]=input.value}}
async function calculate(){
  readCalc();queueDraft(true);const revision=calcRevision,request=++calcRequest,out=qs('#mw-calc-result');
  if(out)out.innerHTML=panel(T('计算结果'),`<p class="mw-sub">${T('正在计算预估成本…')}</p>`);
  try{const result=await api('calculate','POST',calcPayload());if(revision!==calcRevision||request!==calcRequest)return;state.result=result;state.recent=[state.modelId,...state.recent.filter(x=>x!==state.modelId)].slice(0,10);if(qs('#mw-calc-result'))qs('#mw-calc-result').innerHTML=resultView(state.result);updateResetButton();queueDraft(true)}
  catch(e){if(revision!==calcRevision||request!==calcRequest)return;state.result=null;if(qs('#mw-calc-result'))qs('#mw-calc-result').innerHTML=panel(T('无法计算'),`<div class="mw-callout error">${esc(e.message)}</div><p class="mw-note">${T('确认模型计费类型、Cache 价格及汇率设置后重试。')}</p>`);toast(e.message,true);updateResetButton();queueDraft(true)}
}

function calcFieldChanged(t){readCalc();if(t.name==='input')state.calc.output=String(100-Number(state.calc.input||0));if(t.name==='output')state.calc.input=String(100-Number(state.calc.output||0));syncCalcDom();calcChanged()}
function syncCalcDom(){
  const f=qs('#mw-calc-form');if(!f)return;const c=state.calc;
  const setVal=(n,v)=>{const el=f.elements.namedItem(n);if(el&&el!==document.activeElement)el.value=v};
  setVal('input',c.input);setVal('output',c.output);setVal('cache',c.cache);
  const r=qs('#mw-input-range');if(r&&r!==document.activeElement)r.value=c.input;
  const rr=qs('#mw-cache-range');if(rr&&rr!==document.activeElement)rr.value=c.cache;
  if(r)r.style.setProperty('--mw-progress',c.input+'%');if(rr)rr.style.setProperty('--mw-progress',c.cache+'%');
  const rl=qs('#mw-ratio-label');if(rl)rl.textContent=`${c.input}% / ${c.output}%`;
  const cl=qs('#mw-cache-label');if(cl)cl.textContent=`${c.cache}%`;
}
async function catalogUpdate(){const r=await api('catalog/update','POST');await reload();render();toast(T('目录已更新：')+(r.catalogVersion||'unknown'))}
async function shareCalc(){
  readCalc();
  const m=currentModel(),c=state.calc;
  const text=`${T('模型：')}${modelName(m)}（${m?.id||T('未选择')}）；${T('预算')} ${c.budget} ${c.currency}；${T('输入/输出')} ${c.input}%/${c.output}%；${T('缓存命中')} ${c.cache}%。${T('本地估算，不代表实际账单。')}`;
  try{await navigator.clipboard.writeText(text);copiedUntil=Date.now()+2000;clearTimeout(copyTimer);const button=qs('#mw-root [data-mw-action=share]');if(button)button.textContent=T('已复制');copyTimer=setTimeout(()=>{copiedUntil=0;const b=qs('#mw-root [data-mw-action=share]');if(b)b.textContent=T('复制计算摘要')},2000);toast(T('计算摘要已复制'))}
  catch{copiedUntil=0;clearTimeout(copyTimer);const b=qs('#mw-root [data-mw-action=share]');if(b)b.textContent=T('复制计算摘要');showModal(T('复制计算摘要'),`<textarea readonly rows="4" aria-label="${esc(T('计算摘要'))}" style="width:100%">${esc(text)}</textarea>`)}
}

/* ---------- 弹窗（控制台 dialogOpen / dialogClose 动效） ---------- */
function showModal(title,body,foot=''){const m=qs('#mw-modal');qs('#mw-modal-title').innerHTML=title;qs('#mw-modal-body').innerHTML=body;const f=qs('#mw-modal-foot');f.innerHTML=foot;f.hidden=!foot;if(!m.open){if(typeof dialogOpen==='function')dialogOpen(m);else m.showModal()}}
function closeModal(){const m=qs('#mw-modal');if(m.open){if(typeof dialogClose==='function')dialogClose(m);else m.close()}modalKind=''}

/* ---------- 模型目录 ---------- */
const filterIds={'mw-category-filter':'category','mw-capability-filter':'capability','mw-status-filter':'status','mw-price-filter':'price','mw-context-filter':'context','mw-model-sort':'sort'};
function filtered(custom=false){
  const f=state.filters;let rows=state.models.filter(m=>(!custom&&!state.filters.custom)||m.isCustom);
  rows=rows.filter(m=>{const p=m.inputPrice==null?null:Number(m.inputPrice);return (!f.search||[m.name,m.displayName,m.id,m.apiProvider,m.creator,m.family].join(' ').toLowerCase().includes(f.search.toLowerCase()))&&(!f.providers.length||f.providers.includes(m.apiProvider))&&(!f.category||cats(m).includes(f.category))&&(!f.capability||m[f.capability]===true)&&(!f.status||f.status==='all'||(f.status==='active'?['CURRENT','NEW','PREVIEW'].includes(String(m.status).toUpperCase())||m.isCustom:String(m.status).toUpperCase()===f.status))&&(!f.price||(f.price==='unknown'?p===null:f.price==='cache'?m.supportsCache===true:f.price==='free'?p===0:p!==null&&p<Number(f.price)))&&(!f.context||Number(m.contextWindow)>=Number(f.context))&&(f.hidden||!m.hidden)&&(!f.favorite||m.favorite)});
  const sorts={name:m=>modelName(m).toLowerCase(),provider:m=>m.apiProvider||'',creator:m=>m.creator||'',input:m=>m.inputPrice==null?Infinity:Number(m.inputPrice),output:m=>m.outputPrice==null?Infinity:Number(m.outputPrice),context:m=>-Number(m.contextWindow||0),cache:m=>m.cacheReadPrice==null?Infinity:Number(m.cacheReadPrice),verified:m=>-(Date.parse(m.priceLastVerifiedAt)||0),newest:m=>-(Date.parse(m.releaseDate)||0)};
  const key=sorts[f.sort]||sorts.name;
  return rows.sort((a,b)=>{const ka=key(a),kb=key(b);if(typeof ka==='string')return ka.localeCompare(kb);return ka===kb?0:ka<kb?-1:1});
}
function modelCard(m){
  return `<article class="mw-mcard"><div class="mw-row mw-between"><label class="mw-check"><input type="checkbox" aria-label="${esc(T('选择'))} ${esc(modelName(m))}" data-mw-select="${esc(m.id)}"${state.selected.has(m.id)?' checked':''}>${T('选择')}</label><span class="tag ${m.enabled?'success':''}">${m.enabled?T('启用'):T('禁用')}</span><button type="button" class="mw-small mw-ghost" data-mw-favorite="${esc(m.id)}" aria-label="${esc(T('收藏'))}">${m.favorite?'★':'☆'}</button></div><button type="button" class="mw-name" data-mw-detail="${esc(m.id)}">${esc(modelName(m))}</button><span class="mw-model-id">${esc(m.apiProvider)} · ${esc(m.creator)}</span><div class="mw-row" style="margin-top:12px">${badges(m)}</div><div class="mw-prices"><span>${T('输入')}<b>${money(m.inputPrice)}</b></span><span>${T('输出')}<b>${money(m.outputPrice)}</b></span><span>${T('上下文')}<b>${count(m.contextWindow)}</b></span></div><p class="mw-note">${esc(statusLabel(m.status||'UNKNOWN'))} · ${date(m.priceLastVerifiedAt)}${m.priceConditions?' · '+esc(T('条件价格')):''}</p></article>`;
}
function modelTable(rows){
  const all=rows.length&&rows.every(m=>state.selected.has(m.id));
  return `<div class="mw-table"><table><thead><tr><th><input id="mw-select-all" aria-label="${esc(T('选择全部筛选结果'))}" type="checkbox"${all?' checked':''}></th><th>${T('模型')}</th><th>${T('服务商')}</th><th class="num">${T('输入 / 输出价格')}</th><th class="num">${T('上下文')}</th><th>${T('操作')}</th></tr></thead><tbody>${rows.map(m=>`<tr class="${state.selected.has(m.id)?'selected':''}"><td><input aria-label="${esc(T('选择'))} ${esc(modelName(m))}" type="checkbox" data-mw-select="${esc(m.id)}"${state.selected.has(m.id)?' checked':''}></td><td><button type="button" class="mw-name" data-mw-detail="${esc(m.id)}">${esc(modelName(m))}</button><span class="mw-model-id">${esc(m.creator)} · ${esc(statusLabel(m.status||'UNKNOWN'))}${!m.enabled?' · '+esc(T('禁用')):''}${m.hidden?' · '+esc(T('已隐藏')):''}</span></td><td>${esc(m.apiProvider)}</td><td class="num">${money(m.inputPrice)} / ${money(m.outputPrice)}</td><td class="num">${count(m.contextWindow)}</td><td><div class="mw-row"><button type="button" class="mw-small" data-mw-use-model="${esc(m.id)}">${T('计算')}</button><button type="button" class="mw-small mw-ghost" aria-label="${esc(T('收藏模型'))}" data-mw-favorite="${esc(m.id)}">${m.favorite?'★':'☆'}</button></div></td></tr>`).join('')}</tbody></table></div>`;
}
function models(custom=false){
  const f=state.filters,rows=filtered(custom),categories=[...new Set(state.models.flatMap(cats))].sort();
  const filterCount=[f.capability,f.status!=='active'?f.status:'',f.price,f.context,f.hidden,f.favorite,f.custom].filter(Boolean).length;
  return heading(T('模型库'),T('选择模型计算成本；勾选多个模型可对比。价格单位：USD / 1M Tokens。'),btn(T('新增模型'),'new-model','mw-small'))
  +`<section class="mw-panel"><div class="mw-model-toolbar"><label class="mw-search"><span>${T('搜索')}</span><input id="mw-model-search" aria-label="${esc(T('搜索模型'))}" placeholder="${esc(T('搜索名称、模型 ID、开发者…'))}" value="${esc(f.search)}"></label>`
  +`<div class="mw-field"><label for="mw-provider-filter">${T('服务商')}</label>${sel('provider-filter',T('服务商'),option('',T('所有服务商'),f.providers.length===1?f.providers[0]:'')+providers().map(x=>option(x,x,f.providers.length===1?f.providers[0]:'' )).join(''))}</div>`
  +`<div class="mw-field"><label for="mw-category-filter">${T('用途')}</label>${sel('category-filter',T('用途'),option('',T('所有类别'),f.category)+categories.map(x=>option(x,categoryLabel(x),f.category)).join(''))}</div>`
  +`<div class="mw-field"><label for="mw-model-sort">${T('排序')}</label>${sel('model-sort',T('排序'),[['name',T('名称')],['input',T('最低输入价格')],['output',T('最低输出价格')],['context',T('最大上下文')],['newest',T('最新发布')]].map(([k,v])=>option(k,v,f.sort)).join(''))}</div>`
  +`<button type="button" class="mw-small ${f.favorite?'mw-primary':'mw-ghost'}" data-mw-action="toggle-favorite-filter" aria-pressed="${f.favorite}">${f.favorite?'★':'☆'} ${T('仅收藏')}</button>`+btn(T('筛选')+(filterCount?' ('+filterCount+')':''),'model-filters','mw-small')+(filterCount?btn(T('清除筛选'),'clear-filters','mw-small mw-ghost'):'')+`</div><div id="mw-model-results">${modelResults(rows)}</div></section>`;
}
function modelResults(rows){
  return (state.selected.size?`<div class="mw-bulk"><span>${T('已选择')} ${state.selected.size} ${T('个模型')}</span><select id="mw-bulk-action" aria-label="${esc(T('批量操作'))}">${[['enable',T('启用')],['disable',T('禁用')],['hide',T('隐藏')],['unhide',T('恢复')],['favorite',T('收藏')],['unfavorite',T('取消收藏')],['delete',T('删除（隐藏，可撤销）')]].map(([k,v])=>option(k,v)).join('')}</select>${btn(T('应用'),'apply-bulk','mw-small')}${btn(T('对比'),'compare-selection','mw-small')}${btn(T('取消选择'),'clear-selection','mw-small mw-ghost')}</div>`:'')
  +(rows.length
    ?(state.view==='table'?modelTable(rows):`<div class="mw-cards">${rows.map(modelCard).join('')}</div>`)
    :empty(T('没有匹配模型'),T('尝试调整服务商、状态或价格筛选。'),btn(T('清除筛选'),'clear-filters','mw-small')))
  +`<div class="mw-foot"><span>${rows.length} ${T('个匹配')} · ${state.models.filter(m=>m.hidden).length} ${T('个隐藏')}</span><button type="button" class="mw-small" data-mw-action="select-filtered">${T('选择全部筛选结果')}</button></div>`;
}
function updateModelResults(){const box=qs('#mw-model-results');if(box)box.innerHTML=modelResults(filtered(state.page==='custom'))}
function picker(){
  pickerTab='all';pickerSearch='';modalKind='picker';
  showModal(T('选择模型 · API 接口'),`<div class="mw-row" style="margin-bottom:12px">${seg([['all',T('全部')],['favorites',T('收藏')],['recent',T('最近')],['custom',T('自定义')]],'data-mw-picker-tab','all')}</div><div class="mw-form-grid" style="margin-bottom:12px"><input id="mw-picker-search" aria-label="${esc(T('搜索模型'))}" placeholder="${esc(T('搜索模型、服务商、开发者'))}"><select id="mw-picker-provider" aria-label="${esc(T('服务商'))}">${option('',T('所有服务商'))+providers().map(x=>option(x)).join('')}</select></div><div class="mw-picker-list" id="mw-picker-results"></div>`);
  renderPicker();
}
function renderPicker(){
  const provider=qs('#mw-picker-provider')?.value;
  let rows=state.models.filter(m=>!m.hidden&&!['DEPRECATED','RETIRED'].includes(String(m.status).toUpperCase())&&(!provider||m.apiProvider===provider)&&(!pickerSearch||[modelName(m),m.apiProvider,m.creator,m.id].join(' ').toLowerCase().includes(pickerSearch.toLowerCase())));
  if(pickerTab==='favorites')rows=rows.filter(m=>m.favorite);
  if(pickerTab==='recent')rows=state.recent.map(id=>rows.find(m=>m.id===id)).filter(Boolean);
  if(pickerTab==='custom')rows=rows.filter(m=>m.isCustom);
  const box=qs('#mw-picker-results');if(!box)return;
  box.innerHTML=rows.map(m=>`<div class="mw-pick-row"><button type="button" class="mw-pick" data-mw-pick="${esc(m.id)}"><span class="mw-name-sm">${esc(modelName(m))}</span><span class="mw-pick-meta">${esc(m.apiProvider)} · ${esc(m.creator)} · ${count(m.contextWindow)} ${T('上下文')}</span></button><div style="text-align:right"><span class="mw-note">${T('输入 / 输出')}</span><p class="mw-note" style="margin:4px 0">${money(m.inputPrice)} / ${money(m.outputPrice)}</p></div><button type="button" class="mw-small mw-ghost" data-mw-favorite="${esc(m.id)}" aria-label="${esc(T('收藏'))}">${m.favorite?'★':'☆'}</button></div>`).join('')||empty(T('没有匹配条目'),T('在模型目录收藏模型，或换一个筛选。'));
}
async function detail(id){
  const response=await api('models/'+enc(id));const m=response.model||response;
  showModal(esc(modelName(m)),`<div class="mw-row">${badges(m)}<span class="tag ${m.enabled?'success':''}">${m.enabled?T('启用'):T('禁用')}</span><span class="tag">${esc(statusLabel(m.status||'UNKNOWN'))}</span></div><div class="mw-form-grid" style="margin-top:16px"><div>${kv(T('模型 ID'),esc(m.id))}${kv(T('开发者'),esc(m.creator))}${kv(T('API 服务商'),esc(m.apiProvider))}${kv(T('系列 / 版本'),esc(m.family)+' / '+esc(m.version))}${kv(T('发布日期'),date(m.releaseDate))}${kv(T('上下文'),count(m.contextWindow))}${kv(T('最大输入 / 输出'),count(m.maxInputTokens)+' / '+count(m.maxOutputTokens))}${kv(T('用途'),(cats(m)||[]).map(categoryLabel).join(' · ')||T('未知'))}</div><div>${kv(T('输入 · USD / 1M'),money(m.inputPrice))}${kv(T('输出 · USD / 1M'),money(m.outputPrice))}${kv(T('综合参考价 · 每百万 Tokens'),(()=>{const b=blendedPrice(m);return b==null?NA():money(b.toFixed(4))})())}${kv(T('缓存读取 / 写入'),money(m.cacheReadPrice)+' / '+money(m.cacheWritePrice))}${kv(T('计费单位'),esc(m.pricingUnit||'Unknown'))}${kv(T('最后验证'),date(m.priceLastVerifiedAt))}${kv(T('价格来源'),safeLink(m.officialPricingUrl,T('官方定价来源')))}${kv(T('模型文档'),safeLink(m.officialModelUrl,T('官方模型文档')))}</div></div><div style="margin-top:16px"><span class="mw-sub">${T('简短介绍')}</span><p class="mw-note">${esc(m.intro||m.description||introLine(m))}</p><p class="mw-note">${T('按系统默认比例估算')}：${T('输入')} ${calculatorDefaults().input}% · ${T('输出')} ${calculatorDefaults().output}% · ${T('缓存读')} ${calculatorDefaults().read}% · ${T('缓存写')} ${calculatorDefaults().write}%</p></div>${m.notes?`<div class="mw-callout warn" style="margin-top:12px"><b>${T('计费备注')}</b> ${esc(m.notes)}</div>`:''}${m.priceOverride&&Object.keys(m.priceOverride).length?`<div class="mw-callout warn" style="margin-top:12px"><b>${T('你的价格覆盖')}</b> ${Object.entries(m.priceOverride).map(([k,v])=>esc(k)+' '+money(v)).join(' · ')}</div>`:''}${m.priceConditions?`<div class="mw-callout warn">${T('适用条件：')}${esc(typeof m.priceConditions==='string'?m.priceConditions:JSON.stringify(m.priceConditions))}</div>`:''}<details style="margin-top:16px"><summary>${T('技术详情与完整字段')}</summary><h3>${T('接口 / 其他计费')}</h3><pre>${esc(JSON.stringify({endpoints:response.endpoints||m.endpoints||[],prices:response.prices||m.prices||{},priceHistory:response.priceHistory||m.priceHistory||[]},null,2))}</pre><h3>${T('完整模型资料')}</h3><pre>${esc(JSON.stringify(m,null,2))}</pre></details>`,
  `<button type="button" data-mw-override="${esc(id)}">${T('自定义价格覆盖')}</button><button type="button" data-mw-duplicate="${esc(id)}">${T('复制为自定义模型')}</button><button type="button" class="mw-primary" data-mw-use-model="${esc(id)}">${T('在计算器使用')}</button>`);
}
function customModel(m={}){
  modalKind='custom';
  showModal(m.id?T('编辑自定义模型'):T('新建自定义模型'),`<form id="mw-custom-form" data-mw-form="custom" class="mw-form-grid">${field(T('模型名称'),'name',m.displayName||m.name||'','text','required')}${field(T('开发者'),'creator',m.creator||'Custom')}${field(T('API 服务商'),'apiProvider',m.apiProvider||'Custom','text','required')}${select(T('币种'),'currency',['USD','CAD','CNY'].map(x=>option(x,x,m.currency||'USD')).join(''))}${field(T('输入 / 1M'),'inputPrice',m.inputPrice??'','number','min="0" step="any"')}${field(T('输出 / 1M'),'outputPrice',m.outputPrice??'','number','min="0" step="any"')}${field(T('缓存读取 / 1M'),'cacheReadPrice',m.cacheReadPrice??'','number','min="0" step="any"')}${field(T('缓存写入 / 1M'),'cacheWritePrice',m.cacheWritePrice??'','number','min="0" step="any"')}${field(T('上下文窗口'),'contextWindow',m.contextWindow??'','number','min="0"')}<div class="mw-field mw-span2"><span class="mw-sub">${T('能力')}</span><div class="mw-row">${[['supportsCache',T('缓存')],['supportsCoding',T('编程')],['supportsReasoning',T('推理')],['supportsTools',T('工具')],['supportsVision',T('视觉')]].map(([k,v])=>`<label class="mw-check"><input type="checkbox" name="${k}"${m[k]?' checked':''}>${v}</label>`).join('')}</div></div><div class="mw-field mw-span2"><label for="mw-f-notes">${T('备注')}</label><textarea id="mw-f-notes" name="notes">${esc(m.notes||'')}</textarea></div></form><p class="mw-note">${T('留空的价格保存为 Unknown，不会当作 $0。自定义价格仅表示你的配置。')}</p>`,
  `<button type="button" data-mw-custom-save="transient">${T('仅本次计算')}</button><button type="button" data-mw-custom-save="calculate">${T('保存并计算')}</button><button type="button" class="mw-primary" data-mw-custom-save="save">${T('保存')}</button>`);
}
async function saveCustom(mode){
  const f=qs('#mw-custom-form');if(!f)return;if(!f.reportValidity())return;
  const d=Object.fromEntries(new FormData(f));
  for(const k of ['inputPrice','outputPrice','cacheReadPrice','cacheWritePrice','contextWindow'])if(d[k]===''||d[k]===undefined)d[k]=null;
  for(const k of ['supportsCache','supportsCoding','supportsReasoning','supportsTools','supportsVision'])d[k]=f.elements[k].checked;
  d.displayName=d.name;d.category=['Custom'];d.isCustom=true;d.status='CURRENT';
  if(mode==='transient'){state.transient=d;state.result=null;calcRevision++;closeModal();go('calculator');toast(T('临时模型仅用于本次计算'));return}
  const m=await api('models','POST',d);await reload();closeModal();
  if(mode==='calculate'){state.modelId=(m.model||m).id;state.transient=null;state.result=null;calcRevision++;go('calculator');return}
  render();toast(T('自定义模型已保存'));
}
function priceOverride(id){
  const m=state.models.find(x=>x.id===id);modalKind='override';
  showModal(T('本地价格覆盖'),`<form id="mw-override-form" data-mw-form="override" class="mw-form"><p class="mw-note">${T('覆盖只修改账户配置，官方目录与历史账单保持原价格版本。')}</p><div class="mw-form-grid">${['inputPrice','outputPrice','cacheReadPrice','cacheWritePrice'].map(k=>field(T({inputPrice:'输入价格',outputPrice:'输出价格',cacheReadPrice:'缓存读取价格',cacheWritePrice:'缓存写入价格'}[k]),k,m?.priceOverride?.[k]??m?.[k]??'','number','min="0" step="any"')).join('')}</div></form>`,
  `<button type="button" data-mw-official-price="${esc(id)}">${T('使用官方价格')}</button><button type="button" class="mw-primary" data-mw-save-override="${esc(id)}">${T('保存覆盖')}</button>`);
}
async function saveOverride(id){
  const f=qs('#mw-override-form');if(!f)return;const o={};
  for(const k of ['inputPrice','outputPrice','cacheReadPrice','cacheWritePrice']){const v=String(f.elements[k]?.value??'').trim();if(v==='')continue;if(!posRe.test(v))throw Error(`${k} ${T('必须为非负数字')}`);o[k]=v}
  await api('models/'+enc(id),'PATCH',{priceOverride:Object.keys(o).length?o:null});
  closeModal();await reload();render();toast(T('价格覆盖已保存'));
}
async function officialPrice(id){await api('models/'+enc(id),'PATCH',{priceOverride:null});closeModal();await reload();render();toast(T('已恢复官方价格'))}
async function duplicateModel(id){await api('models/'+enc(id)+'/duplicate','POST',{});closeModal();await reload();toast(T('已复制为自定义模型'));go('custom')}
function useModel(id){readCalc();state.modelId=id;state.transient=null;state.result=null;calcRevision++;closeModal();go('calculator')}
function modelFilters(){
  const f=state.filters;modalKind='filters';
  showModal(T('筛选模型'),`<form id="mw-model-filter-form" class="mw-form-grid" data-mw-form="model-filters">`
  +select(T('能力'),'capability',option('',T('所有能力'),f.capability)+[['supportsReasoning',T('推理')],['supportsCoding',T('编程')],['supportsVision',T('视觉')],['supportsTools',T('工具调用')],['supportsImageOutput',T('图像')],['supportsAudioOutput',T('音频')],['supportsVideoOutput',T('视频')],['supportsEmbedding',T('嵌入')],['supportsStreaming',T('流式')],['isOpenWeight',T('开放权重')]].map(([k,v])=>option(k,v,f.capability)).join(''))
  +select(T('版本状态'),'status',option('active',T('活跃版本'),f.status)+option('all',T('所有状态'),f.status)+['CURRENT','NEW','PREVIEW','PREVIOUS','LEGACY','DEPRECATED','RETIRED','UNKNOWN'].map(x=>option(x,statusLabel(x),f.status)).join(''))
  +select(T('输入价格'),'price',[['',T('所有输入价格')],['0.1','< $0.10'],['0.5','< $0.50'],['1','< $1'],['5','< $5'],['20','< $20'],['cache',T('支持缓存')],['free',T('免费')],['unknown',T('未知价格')]].map(([k,v])=>option(k,v,f.price)).join(''))
  +select(T('上下文'),'context',[['',T('所有上下文')],['32000','32K+'],['128000','128K+'],['256000','256K+'],['1000000','1M+'],['2000000','2M+']].map(([k,v])=>option(k,v,f.context)).join(''))
  +`<div class="mw-row mw-span2">${[['hidden',T('显示隐藏')],['favorite',T('仅收藏')],['custom',T('仅自定义模型')]].map(([k,v])=>`<label class="mw-check"><input name="${k}" type="checkbox"${f[k]?' checked':''}>${v}</label>`).join('')}</div></form>`,`${btn(T('清除筛选'),'clear-modal-filters','mw-small')}<button type="button" data-mw-close>${T('取消')}</button><button type="submit" class="mw-primary" form="mw-model-filter-form">${T('应用筛选')}</button>`);
}
function applyModelFilters(form){const d=new FormData(form);for(const k of ['capability','status','price','context'])state.filters[k]=String(d.get(k)||'');for(const k of ['hidden','favorite','custom'])state.filters[k]=d.has(k);closeModal();render()}
function providerFilter(){
  const picked=new Set(state.filters.providers);modalKind='provider';
  showModal(T('按服务商筛选'),`<div class="mw-picker-list">${providers().map(p=>`<label class="mw-check"><input type="checkbox" data-mw-provider-check="${esc(p)}"${picked.has(p)?' checked':''}>${esc(p)}</label>`).join('')||`<p class="mw-note">${T('暂无 Provider。')}</p>`}</div>`,
  `<button type="button" data-mw-action="provider-clear">${T('清空')}</button><button type="button" class="mw-primary" data-mw-action="provider-apply">${T('应用筛选')}</button>`);
}
function applyProviderFilter(clear){const picked=clear?[]:qsa('#mw-modal [data-mw-provider-check]:checked').map(x=>x.getAttribute('data-mw-provider-check'));state.filters.providers=picked;closeModal();render()}
function compareSelection(){
  const ids=[...state.selected];
  if(!ids.length){toast(T('请先勾选模型'),true);return}
  const next=new Set([...state.compare,...ids]);
  if(next.size>10){toast(T('对比最多 10 个模型，请减少选择'),true);return}
  state.compare=next;state.selected.clear();go('compare');
}
async function bulk(action){const r=await api('models/bulk','POST',{ids:[...state.selected],action});await reload();state.selected.clear();render();toast(T('批量操作已完成'),false,r.undoId?()=>run(async()=>{await api('models/undo','POST',{undoId:r.undoId});await reload();render();toast(T('已撤销'))}):null)}

/* ---------- 模型对比 ---------- */
function compare(){
  return heading(T('模型对比'),T('相同预算、比例与 Cache 条件。未知价格保留明确错误。'),btn(T('返回模型库'),'nav-models','mw-small'))
  +panel(T('统一工作负载'),`<form id="mw-compare-form" class="mw-form" data-mw-form="compare"><div class="mw-form-grid">${field(T('预算'),'cmp-budget',state.calc.budget,'number','min="0" step="any"')}${select(T('货币'),'cmp-currency',['USD','CAD','CNY'].map(x=>option(x,x,state.calc.currency)).join(''))}${field(T('输入 %'),'cmp-input',state.calc.input,'number','min="0" max="100"')}${field(T('缓存 %'),'cmp-cache',state.calc.cache,'number','min="0" max="100"')}</div><div class="mw-cmp-list">${[...state.compare].map(id=>`<button type="button" class="mw-small" data-mw-remove-compare="${esc(id)}">${esc(modelName(state.models.find(m=>m.id===id)))} ×</button>`).join('')||`<p class="mw-note">${T('在模型目录中勾选 2–10 个模型，再点击「加入对比」。')}</p>`}</div><button class="mw-primary" type="submit"${state.compare.size<2?' disabled':''}>${T('对比')} ${state.compare.size} ${T('个模型 →')}</button></form>`)
  +`<div id="mw-compare-result">${empty(T('同一工作负载，一次比较'),T('选择至少两个模型。结果包含 Tokens、有效价格、Cache Savings 与 Context。'))}</div>`;
}
async function compareRun(){
  const f=qs('#mw-compare-form');if(!f)return;if(!f.reportValidity())return;
  const inPct=Number(f.elements['cmp-input'].value);
  const payload={...calcPayload(),mode:'money',modelIds:[...state.compare],budget:f.elements['cmp-budget'].value,currency:f.elements['cmp-currency'].value,inputRatio:String(inPct/100),outputRatio:String((100-inPct)/100),cacheRatio:String(Number(f.elements['cmp-cache'].value)/100)};
  delete payload.customModel;
  const r=await api('compare','POST',payload);
  state.compareResults=r.results||[];
  const out=qs('#mw-compare-result');if(!out)return;
  out.innerHTML=panel(T('对比结果 · 估算'),`<div class="mw-row" style="margin-bottom:12px"><label class="mw-sub" for="mw-compare-sort">${T('排序')}</label><select id="mw-compare-sort" aria-label="${esc(T('排序'))}">${[['tokens',T('Tokens 最多')],['cost',T('有效成本最低')],['context',T('上下文最大')],['savings',T('缓存节省最多')]].map(([k,v])=>option(k,v)).join('')}</select></div><div id="mw-compare-table"></div>`);
  renderCompareTable('tokens');
}
function renderCompareTable(sort){
  const rows=[...(state.compareResults||[])];
  const key=r=>sort==='tokens'?-Number(r.totalTokens||0):sort==='context'?-Number(state.models.find(m=>m.id===r.modelId)?.contextWindow||0):sort==='savings'?-Number(r.cacheSavings||0):Number(r.effectiveCostPerMillion??Infinity);
  rows.sort((a,b)=>{const ka=key(a),kb=key(b);return ka===kb?0:ka<kb?-1:1});
  const box=qs('#mw-compare-table');if(!box)return;
  box.innerHTML=`<div class="mw-table"><table><thead><tr><th>${T('模型')}</th><th>${T('服务商')}</th><th class="num">Tokens</th><th class="num">${T('每百万成本 · USD')}</th><th class="num">${T('输入 / 输出')}</th><th class="num">${T('缓存节省')}</th><th class="num">${T('上下文')}</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(modelName(state.models.find(m=>m.id===r.modelId)))}</td><td>${esc(r.provider||'—')}</td>${r.error?`<td colspan="5" class="mw-na">${esc(typeof r.error==='object'?r.error.message||JSON.stringify(r.error):r.error)}</td>`:`<td class="num">${count(r.totalTokens)}</td><td class="num">${money(r.effectiveCostPerMillion)}</td><td class="num">${money(r.inputCost)} / ${money(r.outputCost)}</td><td class="num">${money(r.cacheSavings)}</td><td class="num">${count(state.models.find(m=>m.id===r.modelId)?.contextWindow)}</td>`}</tr>`).join('')}</tbody></table></div>`;
}

/* ---------- 钱包 ---------- */
function wallets(){
  const d=state.dashboard,p=d.periods||{};
  return heading(T('钱包与账本'),T('手工登记额度并查看本地账本。'),btn(T('+ 新建钱包'),'new-wallet','mw-small')+btn(T('路由模拟'),'nav-sim','mw-small'))
  +`<div class="mw-wallet-summary">${metric(T('可用额度 · USD'),money(d.totalWalletBalanceUSD),`${state.wallets.length} ${T('个本地钱包')}`)}${metric(T('今日支出'),money(p.today?.cost),`${p.today?.requests||0} ${T('次结算')}`)}${metric(T('今日 Tokens'),count(p.today?.tokens),T('仅来自本地用量账本'))}${metric(T('预计可用天数'),d.estimatedDaysRemaining?compact(d.estimatedDaysRemaining)+' '+T('天'):'—',T('按近 30 天日均消耗估算'))}</div>`
  +(state.wallets.length?`<div class="mw-wallet-list">${state.wallets.map(walletCard).join('')}</div>`:`<p class="mw-inline-empty">${T('还没有钱包，点击新建钱包登记额度。')}</p>`)
  +usage()+`<div class="mw-actions"><button type="button" class="mw-small mw-ghost" data-mw-nav="dashboard">${T('额度与支出明细')}</button></div>`;
}
function walletCard(w){
  const cum=(state.dashboard?.groups?.walletId||[]).find(g=>g.id===w.id)?.cost;
  const recent=state.usageRows?String(state.usageRows.usage.filter(u=>u.walletId===w.id&&ageDays(u.createdAt)!==null&&ageDays(u.createdAt)<=30).length):T('加载中');
  const low=w.lowBalanceThreshold!=null&&Number(w.availableBalance)<Number(w.lowBalanceThreshold);
  const debt=Number(w.debt||0)>0;
  return `<section class="mw-panel mw-wallet-item"><div class="mw-wallet-head"><h3>${esc(w.name)}</h3>${sourceBadge(w.balanceSource)}</div><p class="mw-sub">${esc(w.provider)} · ${esc(w.currency)} · ${T('优先级')} ${esc(w.priority)} · ${w.type==='MANUAL'?T('手工钱包'):T('连接型钱包（未接入）')} · ${esc(w.connectionStatus||'UNCONNECTED')}</p>`
  +`<div class="mw-balance">${money(w.availableBalance,w.currency)}</div><div class="mw-avail">${T('可用余额（已扣除预留）')}</div>`
  +kv(T('当前余额'),money(w.currentBalance,w.currency))+kv(T('预留中'),money(w.reservedBalance,w.currency))+kv(T('初始额度'),money(w.initialCredit,w.currency))+kv(T('到期'),expiryText(w.expiresAt))+kv(T('最近 30 天请求'),recent)+kv(T('累计成本 · USD'),cum!=null?money(cum,'USD'):NA())+kv(T('最后同步'),w.lastSyncedAt?date(w.lastSyncedAt):T('从未同步'))
  +(low?`<div class="mw-callout warn">${T('余额低于提醒阈值')}</div>`:'')+(debt?`<div class="mw-callout error">${T('透支')} ${money(w.debt,w.currency)}</div>`:'')
  +`<div class="mw-actions mw-wallet-actions"><button type="button" class="mw-small" data-mw-wallet-edit="${esc(w.id)}">${T('编辑')}</button><button type="button" class="mw-small" data-mw-wallet-adjust="${esc(w.id)}">${T('余额调整')}</button><button type="button" class="mw-small" data-mw-wallet-calc="${esc(w.id)}">${T('带入计算器 →')}</button><button type="button" class="mw-small mw-ghost" data-mw-wallet-sync="${esc(w.id)}">${T('尝试同步')}</button></div></section>`;
}
function walletForm(w){
  const edit=Boolean(w),lim=w?.limits||{};
  const dateV=w?.expiresAt?String(w.expiresAt).slice(0,10):'';
  const limitField=(label,name)=>field(label,name,lim[name]??'','text','pattern="[0-9]+(\\.[0-9]+)?" inputmode="decimal"');
  modalKind='wallet';
  const body=`<form id="mw-wallet-form" data-mw-form="wallet" data-mw-wallet-id="${esc(w?.id||'')}" class="mw-form"><div class="mw-form-grid">`
  +field(T('钱包名称'),'name',w?.name||'','text','required maxlength="80"')
  +field(T('服务商'),'provider',w?.provider||'Custom','text','required maxlength="60"')
  +(edit?`<div class="mw-field"><label>${T('币种')}</label><input value="${esc(w.currency)}" disabled></div>`:select(T('币种'),'currency',['USD','CAD','CNY'].map(x=>option(x,x,'USD')).join('')))
  +(edit?'':field(T('初始额度'),'initialCredit','','text','required pattern="[0-9]+(\\.[0-9]+)?" inputmode="decimal"'))
  +(edit?'':field(T('当前余额（留空则等于初始额度）'),'currentBalance','','text','pattern="[0-9]+(\\.[0-9]+)?" inputmode="decimal"'))
  +field(T('到期日（留空=无到期）'),'expiresAt',dateV,'date')
  +field(T('优先级（数字越小越先用）'),'priority',w?.priority??1,'number','min="0" step="1" required')
  +field(T('低余额提醒阈值（同币种，留空保持原值）'),'lowBalanceThreshold',w?.lowBalanceThreshold??'10','text','pattern="[0-9]+(\\.[0-9]+)?" inputmode="decimal"')
  +field(T('可用 Provider（逗号分隔，留空=按映射）'),'eligibleProviders',(w?.eligibleProviders||[]).join(', '))
  +field(T('可用模型 ID（逗号分隔，留空=不限）'),'eligibleModels',(w?.eligibleModels||[]).join(', '))
  +limitField(T('单次上限（钱包币种）'),'perRequest')+limitField(T('日上限'),'daily')+limitField(T('周上限'),'weekly')+limitField(T('月上限'),'monthly')
  +`<div class="mw-field mw-span2"><label for="mw-f-notes">${T('备注')}</label><textarea id="mw-f-notes" name="notes">${esc(w?.notes||'')}</textarea></div>`
  +`</div>${edit?`<p class="mw-note">${T('余额请用「余额调整」修改；币种与初始额度创建后不可改。')}</p>`:`<p class="mw-note">${T('手工登记不会连接 Provider，余额来源标记为 MANUAL。')}</p>`}</form>`;
  showModal(edit?`${T('编辑钱包')} · ${esc(w.name)}`:T('新建手工钱包'),body,`<button type="button" data-mw-close>${T('取消')}</button><button class="mw-primary" type="submit" form="mw-wallet-form">${T('保存')}</button>`);
}
async function saveWallet(f){
  if(!f.reportValidity())return;
  const d=Object.fromEntries(new FormData(f));
  const id=f.getAttribute('data-mw-wallet-id');
  const limits={};
  for(const k of ['perRequest','daily','weekly','monthly']){const v=nz(d[k]);if(v!==null){if(!posRe.test(v))throw Error(`${k} ${T('上限必须为非负数字')}`);limits[k]=v}}
  const body={name:String(d.name).trim(),provider:String(d.provider).trim(),priority:Number(d.priority||1),expiresAt:nz(d.expiresAt),notes:String(d.notes||''),eligibleProviders:csv(d.eligibleProviders),eligibleModels:csv(d.eligibleModels),limits};
  const lt=nz(d.lowBalanceThreshold);
  if(lt!==null){if(!posRe.test(lt))throw Error(T('低余额阈值必须为非负数字'));body.lowBalanceThreshold=lt}
  if(id){
    await api('wallets/'+enc(id),'PATCH',body);
  }else{
    const init=nz(d.initialCredit);
    if(init===null||!posRe.test(init))throw Error(T('初始额度必须为非负数字'));
    const cur=nz(d.currentBalance);
    if(cur!==null&&!posRe.test(cur))throw Error(T('当前余额必须为非负数字'));
    await api('wallets','POST',{...body,type:'MANUAL',currency:d.currency,initialCredit:init,...(cur!==null?{currentBalance:cur}:{})});
  }
  closeModal();await reload();render();toast(id?T('钱包已更新'):T('钱包已创建'));
}
function adjustForm(id){
  const w=walletOf(id);if(!w)throw Error(T('钱包不存在，请刷新页面'));
  modalKind='adjust';
  showModal(`${T('余额调整')} · ${esc(w.name)}`,`<form id="mw-adjust-form" data-mw-form="adjust" data-mw-wallet-id="${esc(id)}" class="mw-form">${kv(T('当前余额'),money(w.currentBalance,w.currency))}${kv(T('预留中'),money(w.reservedBalance,w.currency))}${kv(T('可用余额'),money(w.availableBalance,w.currency))}<div class="mw-field" style="margin-top:16px"><label for="mw-f-amount">${T('调整金额（正数增加，负数减少）')}（${esc(w.currency)}）</label><input id="mw-f-amount" name="amount" type="text" required pattern="-?[0-9]+(\\.[0-9]+)?" inputmode="decimal" autocomplete="off"></div>${field(T('原因（必填，写入账本）'),'reason','','text','required maxlength="200"')}<p class="mw-note">${T('调整会生成 ADJUSTMENT 账本记录。调整后可用余额不得低于预留金额。')}</p></form>`,
  `<button type="button" data-mw-close>${T('取消')}</button><button class="mw-primary" type="submit" form="mw-adjust-form">${T('提交调整')}</button>`);
}
async function adjustWallet(f){
  if(!f.reportValidity())return;
  const d=Object.fromEntries(new FormData(f));
  const amount=String(d.amount??'').trim();
  if(!decRe.test(amount))throw Error(T('调整金额格式不正确'));
  const reason=String(d.reason??'').trim();
  if(!reason)throw Error(T('请填写调整原因'));
  await api('wallets/'+enc(f.getAttribute('data-mw-wallet-id'))+'/adjust','POST',{amount,reason});
  closeModal();await reload();await loadUsage();render();toast(T('余额已调整'));
}
async function syncWallet(id){const r=await api('wallets/'+enc(id)+'/sync','POST');await reload();render();toast(`${r.status==='UNSUPPORTED'?T('未接入官方余额来源'):r.status}${r.reason?'：'+r.reason:''}`)}
function useWalletInCalc(id){const w=walletOf(id);if(!w)return;readCalc();state.calc.budget=String(w.availableBalance);state.calc.currency=w.currency;state.result=null;calcRevision++;go('calculator')}

/* ---------- 用量与账本 ---------- */
async function loadUsage(){
  state.usageLoading=true;state.usageError='';
  try{
    const [u,l,r]=await Promise.all([api('usage'),api('ledger'),api('reservations')]);
    state.usageRows={usage:u.usage||[],ledger:l.transactions||[],reservations:r.reservations||[]};
  }catch(e){state.usageError=e.message}
  finally{state.usageLoading=false}
  if(state.page==='usage'||state.page==='wallets')render();
}
function usage(){
  const head='';
  if(state.usageError)return head+panel(T('加载失败'),`<div class="mw-callout error">${esc(state.usageError)}</div>${btn(T('重试'),'usage-refresh','mw-small')}`);
  const R=state.usageRows;
  if(!R)return head+panel(T('账本'),`<p class="mw-sub">${T('正在读取账本…')}</p>`);
  const f=state.usageFilter;
  const inW=r=>!f.wallet||r.walletId===f.wallet;
  const ledger=R.ledger.filter(r=>inW(r)&&(!f.type||r.type===f.type));
  const usageList=R.usage.filter(inW);
  const resv=R.reservations.filter(inW);
  const tools=`<div class="mw-tools">${sel('record-kind',T('记录类型'),[['ledger',T('账本流水')],['usage',T('用量记录')],['reservations',T('预留记录')]].map(([k,v])=>option(k,v,f.record)).join(''))}${sel('usage-wallet',T('按钱包筛选'),option('',T('所有钱包'),f.wallet)+state.wallets.map(w=>option(w.id,w.name,f.wallet)).join(''))}${f.record==='ledger'?sel('usage-type',T('按账本类型筛选（仅作用于账本流水）'),option('',T('所有账本类型'),f.type)+ledgerTypes.map(t=>option(t,ledgerLabel(t),f.type)).join('')):''}</div>`;
  const ledgerTable=ledger.length
    ?`<div class="mw-table"><table><thead><tr><th>${T('时间')}</th><th>${T('类型')}</th><th>${T('钱包')}</th><th>${T('模型')}</th><th>${T('请求')}</th><th class="num">${T('金额')}</th><th class="num">${T('变动前')}</th><th class="num">${T('变动后')}</th></tr></thead><tbody>${ledger.map(r=>`<tr><td>${ts(r.createdAt)}</td><td><span class="tag">${esc(ledgerLabel(r.type))}</span></td><td>${walletName(r.walletId)}</td><td>${r.modelId?modelLabel(r.modelId):'—'}</td><td>${esc(r.requestId||'—')}</td><td class="num">${money(r.amount,r.currency)}</td><td class="num">${money(r.balanceBefore,r.currency)}</td><td class="num">${money(r.balanceAfter,r.currency)}</td></tr>`).join('')}</tbody></table></div>`
    :empty(T('暂无账本流水'),T('登记或调整钱包额度后，记录会显示在这里。'));
  const usageTable=usageList.length
    ?`<div class="mw-table"><table><thead><tr><th>${T('时间')}</th><th>${T('请求')}</th><th>${T('模型')}</th><th>${T('服务商')}</th><th>${T('钱包')}</th><th class="num">${T('输入')}</th><th class="num">${T('输出')}</th><th class="num">${T('缓存读取')}</th><th class="num">${T('成本 · USD')}</th><th class="num">${T('扣款')}</th><th>${T('类型')}</th><th class="num">${T('缓存节省 · USD')}</th></tr></thead><tbody>${usageList.map(u=>`<tr><td>${ts(u.createdAt)}</td><td>${esc(u.requestId||'—')}</td><td>${modelLabel(u.modelId)}</td><td>${esc(u.provider||'—')}</td><td>${walletName(u.walletId)}</td><td class="num">${count(u.inputTokens)}</td><td class="num">${count(u.outputTokens)}</td><td class="num">${count(u.cacheReadTokens)}</td><td class="num">${money(u.actualCost,'USD')}</td><td class="num">${money(u.chargedAmount,u.currency||walletCurrency(u.walletId))}</td><td><span class="tag ${u.kind==='SIMULATED'?'pending':''}">${esc(u.kind||'—')}</span></td><td class="num">${money(u.cacheSavings,'USD')}</td></tr>`).join('')}</tbody></table></div>`
    :empty(T('暂无用量记录'),T('完成模拟结算后，用量会显示在这里。'));
  const resvTable=resv.length
    ?`<div class="mw-table"><table><thead><tr><th>${T('请求')}</th><th>${T('钱包')}</th><th>${T('状态')}</th><th>${T('模型')}</th><th class="num">${T('预留')}</th><th>${T('创建')}</th></tr></thead><tbody>${resv.map(r=>`<tr><td>${esc(r.requestId||'—')}</td><td>${walletName(r.walletId)}</td><td><span class="tag">${esc(r.state||'—')}</span></td><td>${modelLabel(r.modelId)}</td><td class="num">${money(r.reservedAmount,r.currency)}</td><td>${ts(r.createdAt)}</td></tr>`).join('')}</tbody></table></div>`
    :empty(T('暂无预留记录'),T('预留只降低可用余额，不改变账面余额；释放或结算后状态会更新。'));
  const record={ledger:ledgerTable,usage:usageTable,reservations:resvTable}[f.record]||ledgerTable;return `<section class="mw-ledger"><div class="mw-row mw-between"><h3>${T('账本')}</h3>${btn(T('刷新'),'usage-refresh','mw-small')}</div>${tools}${record}</section>`;
}

/* ---------- 路由模拟（独立模拟） ---------- */
function ctxDefaults(){const c=state.ctx;if(!c.requestId)c.requestId=newId('sim');if(!c.modelId||!state.models.some(m=>m.id===c.modelId))c.modelId=state.modelId||state.models.find(m=>m.enabled&&!m.hidden)?.id||''}
function readCtx(){const f=qs('#mw-ctx-form');if(!f)return;const d=new FormData(f);for(const k of ['modelId','walletId','requestId','input','output','cache','actualInput','actualOutput','actualCacheRead','refundAmount']){if(d.has(k))state.ctx[k]=String(d.get(k)??'')}}
function simBody(){const c=state.ctx;return {requestId:c.requestId.trim(),modelId:c.modelId,...(c.walletId?{walletId:c.walletId}:{}),estimatedInputTokens:String(c.input),estimatedOutputTokens:String(c.output),estimatedCacheRatio:String(Number(c.cache||0)/100),simulated:true}}
function usageBody(){const c=state.ctx;const u={inputTokens:String(c.actualInput),outputTokens:String(c.actualOutput)};if(nz(c.actualCacheRead)!==null)u.cacheReadTokens=String(c.actualCacheRead);return u}
function newSimId(){readCtx();state.ctx.requestId=newId('sim');state.sim=null;render()}
async function simStep(step){
  readCtx();
  const c=state.ctx;
  const titles={check:T('1 预算检查'),reserve:T('2 预留'),settle:T('3 模拟结算（含 Usage）'),'settle-missing':T('3 模拟缺失 Usage'),release:T('4a 释放预留'),refund:T('4b 退款')};
  if(!titles[step])throw Error(T('未知模拟步骤'));
  if(!c.modelId)throw Error(T('请选择模型'));
  if(!c.requestId.trim())throw Error(T('请填写 requestId'));
  if(!state.sim||state.sim.requestId!==c.requestId.trim())state.sim={requestId:c.requestId.trim(),steps:[]};
  const S=state.sim;
  const seq=S.steps.filter(x=>x.step===step).length+1;
  let data;
  try{
    if(step==='check')data=await api('wallets/check-budget','POST',simBody());
    else if(step==='reserve')data=await api('wallets/reserve','POST',simBody());
    else if(step==='settle'){
      for(const k of ['actualInput','actualOutput','actualCacheRead']){if(k==='actualCacheRead'&&nz(c[k])===null)continue;if(!intRe.test(String(c[k])))throw Error(T('实际 Tokens 必须为非负整数'))}
      data=await api('wallets/settle','POST',{requestId:c.requestId.trim(),usage:usageBody(),simulated:true});
    }
    else if(step==='settle-missing')data=await api('wallets/settle','POST',{requestId:c.requestId.trim(),simulated:true});
    else if(step==='release')data=await api('wallets/release','POST',{requestId:c.requestId.trim(),reason:'模拟：请求中止'});
    else if(step==='refund')data=await api('wallets/refund','POST',{requestId:c.requestId.trim(),refundId:`refund-${c.requestId.trim()}-${seq}`,...(nz(c.refundAmount)!==null?{amount:nz(c.refundAmount)}:{})});
    S.steps.push({step,title:titles[step],ok:true,data});
  }catch(err){
    S.steps.push({step,title:titles[step],ok:false,error:err.message});
    toast(err.message,true);
  }
  await reload();await loadUsage();render();
}
function stepView(s){
  if(!s.ok)return `<div class="mw-step"><div class="mw-callout error"><strong>${esc(s.title)} ${T('失败')}</strong>：${esc(s.error)}</div></div>`;
  const d=s.data||{};
  let rows='';
  if(s.step==='check'){
    rows=d.allowed
      ?kv(T('结果'),'<span class="tag success">ALLOWED</span>')+kv(T('钱包'),walletName(d.walletId))+kv(T('预计成本 · USD'),money(d.estimatedCost,'USD'))+kv(T('将预留'),money(d.reservedAmount,d.currency))+kv(T('服务商'),esc(d.provider||'—'))+kv(T('模型'),modelLabel(d.modelId))+kv(T('价格版本'),esc(d.priceVersion||'—'))+(d.lowBalance?`<div class="mw-callout warn">${T('预留后将低于提醒阈值')}</div>`:'')
      :kv(T('结果'),'<span class="tag failed">DENIED</span>')+kv(T('原因'),esc(d.reason||'—'))+kv(T('预计成本 · USD'),money(d.estimatedCost,'USD'))+(d.rejected?.length?`<details style="margin-top:12px"><summary>${T('被拒绝的钱包')} (${d.rejected.length})</summary><pre>${esc(JSON.stringify(d.rejected,null,2))}</pre></details>`:'');
  }else if(s.step==='reserve'){
    rows=kv(T('状态'),esc(d.state||'—'))+kv(T('钱包'),walletName(d.walletId))+kv(T('预留金额'),money(d.reservedAmount,d.currency))+kv(T('汇率（币种 / 1 USD）'),esc(d.exchangeRate||'—'));
  }else if(s.step==='settle'||s.step==='settle-missing'){
    if(d.state==='USAGE_UNKNOWN')rows=kv(T('状态'),'<span class="tag pending">USAGE_UNKNOWN</span>')+`<div class="mw-callout warn">${T('未结算：没有 Usage，预留保留待对账，不按预估费用扣款。')}</div>`;
    else rows=kv(T('状态'),esc(d.state||'—'))+kv(T('类型'),'<span class="tag pending">SIMULATED</span>')+kv(T('实际成本 · USD'),money(d.actualCost,'USD'))+kv(T('扣款'),money(d.chargedAmount,d.currency))+kv(T('缓存节省 · USD'),money(d.cacheSavings,'USD'))+kv(T('输入 / 输出'),`${count(d.inputTokens)} / ${count(d.outputTokens)}`);
  }else if(s.step==='release'){
    rows=kv(T('状态'),esc(d.state||'—'))+kv(T('释放金额'),money(d.reservedAmount,d.currency));
  }else if(s.step==='refund'){
    rows=kv(T('类型'),esc(d.type||'—'))+kv(T('退款金额'),money(d.amount,d.currency))+kv(T('余额（之后）'),money(d.balanceAfter,d.currency));
  }
  return `<div class="mw-step"><h4>${esc(s.title)} · ${T('成功')}</h4>${rows}<details style="margin-top:12px"><summary>${T('原始响应')}</summary><pre>${esc(JSON.stringify(d,null,2))}</pre></details></div>`;
}
function simResultView(){
  const S=state.sim;
  if(!S||!S.steps.length)return panel(T('模拟结果'),empty(T('尚未执行'),T('按 1 → 2 → 3 → 4 的顺序执行，也可以只运行其中一步。结果显示预算、预留、结算与释放的金额和钱包状态。')));
  return panel(`${T('模拟结果')} · SIMULATION`,`<p class="mw-note">requestId：<code>${esc(S.requestId)}</code> · ${T('仅本地账本模拟，不调用外部模型')}</p>${S.steps.map(stepView).join('<hr>')}`);
}
function routeView(){
  const R=state.routeResult;
  if(!R)return empty(T('尚未运行路由'),T('选择策略后运行。将列出每个启用模型的预算检查结果与被拒绝原因，不会预留额度。'));
  const cands=R.candidates||[],rej=R.rejected||[];
  return `<div class="mw-callout">${T('选中：')}${R.selected?`${modelLabel(R.selected.modelId)} · ${walletName(R.selected.walletId)}`:T('无可用候选')}</div>`
  +(cands.length?`<div class="mw-table"><table><thead><tr><th>${T('模型')}</th><th>${T('钱包')}</th><th class="num">${T('预计成本 · USD')}</th><th class="num">${T('预留')}</th><th class="num">${T('质量分')}</th></tr></thead><tbody>${cands.map(q=>`<tr><td>${modelLabel(q.modelId)}</td><td>${walletName(q.walletId)}</td><td class="num">${money(q.estimatedCost,'USD')}</td><td class="num">${money(q.reservedAmount,q.currency)}</td><td class="num">${esc(q.quality??'—')}</td></tr>`).join('')}</tbody></table></div>`:'')
  +(rej.length?`<details style="margin-top:12px"><summary>${T('被拒绝的候选')} (${rej.length})</summary><pre>${esc(JSON.stringify(rej,null,2))}</pre></details>`:'');
}
async function runRoute(){
  readCtx();
  const c=state.ctx;
  const strategy=qs('#mw-f-strategy')?.value||'CHEAPEST_FIRST';
  if(!intRe.test(String(c.input))||!intRe.test(String(c.output)))throw Error(T('预估 Tokens 必须为非负整数'));
  state.routeResult=await api('route','POST',{strategy,estimatedInputTokens:String(c.input),estimatedOutputTokens:String(c.output),estimatedCacheRatio:String(Number(c.cache||0)/100),simulated:true});
  render();
}
function contextgate(){
  ctxDefaults();
  const c=state.ctx;
  const enabled=state.models.filter(m=>m.enabled&&!m.hidden);
  const modelOpts=enabled.map(m=>option(m.id,`${modelName(m)} · ${m.apiProvider||''}`,c.modelId)).join('')||option('',T('没有可用模型'));
  const walletOpts=option('',T('自动选择（按钱包策略）'),c.walletId)+state.wallets.map(w=>option(w.id,`${w.name} · ${w.currency} ${w.availableBalance}`,c.walletId)).join('');
  const sb=(k,l)=>`<button type="button" data-mw-sim="${k}">${l}</button>`;
  return heading(T('路由模拟'),T('独立模拟：未接入真实 ContextGate，不调用外部模型，不产生真实账单。'),`<button type="button" class="mw-small" data-mw-nav="wallets">${T('返回钱包与账本')}</button>`)
  +`<div class="mw-callout warn"><strong>${T('独立模拟环境')}</strong>：${T('这里的路由与账务只在本机数据库中模拟，未接入真实 ContextGate，不会调用任何外部模型或 Provider。模拟记录标记为 SIMULATED。')}</div>`
  +`<div class="mw-calc"><section class="mw-panel"><form id="mw-ctx-form" data-mw-form="ctx" class="mw-form"><div class="mw-form-grid">${select(T('模型'),'modelId',modelOpts)}${select(T('钱包'),'walletId',walletOpts)}</div>`
  +`<div class="mw-form-grid">${field(T('requestId（同一 ID 参数必须一致）'),'requestId',c.requestId,'text','required maxlength="120" autocomplete="off"')}<div class="mw-field" style="align-self:end"><button type="button" class="mw-small" data-mw-sim="new-id">${T('生成新 requestId')}</button></div></div>`
  +`<div class="mw-form-grid">${field(T('预估输入 Tokens'),'input',c.input,'number','min="0" step="1" required')}${field(T('预估输出 Tokens'),'output',c.output,'number','min="0" step="1" required')}${field(T('预估缓存命中率 %'),'cache',c.cache,'number','min="0" max="100" step="any"')}</div>`
  +`<hr><h3>${T('本次用量（整数 tokens）')}</h3>`
  +`<div class="mw-form-grid">${field(T('实际输入 Tokens'),'actualInput',c.actualInput,'number','min="0" step="1"')}${field(T('实际输出 Tokens'),'actualOutput',c.actualOutput,'number','min="0" step="1"')}${field(T('实际缓存读取 Tokens（可留空）'),'actualCacheRead',c.actualCacheRead,'number','min="0" step="1"')}${field(T('退款金额（留空=全额剩余 · 钱包币种）'),'refundAmount',c.refundAmount,'text','pattern="[0-9]+(\\.[0-9]+)?" inputmode="decimal"')}</div>`
  +`<hr><div class="mw-presets" style="margin-top:0">${sb('check',T('1 预算检查'))}${sb('reserve',T('2 预留'))}${sb('settle',T('3 模拟结算（带 Usage）'))}${sb('settle-missing',T('3′ 模拟缺失 Usage'))}${sb('release',T('4a 释放预留'))}${sb('refund',T('4b 退款'))}</div>`
  +`<p class="mw-note">${T('步骤 3′ 演示「无 Usage 不按预估结算」：预留保持不变。')}</p></form></section><div id="mw-sim-result">${simResultView()}</div></div>`
  +panel(T('路由预览（只读，不预留）'),`<form id="mw-route-form" data-mw-form="route" class="mw-tools" style="margin-bottom:12px">${select(T('路由策略'),'strategy',routeStrategies().map(([v,l])=>option(v,l,'CHEAPEST_FIRST')).join(''))}<button type="submit" class="mw-small">${T('运行路由模拟')}</button></form><div id="mw-route-result">${routeView()}</div>`);
}

/* ---------- 设置 ---------- */
function settings(){
  const s=state.settings,r=s.exchangeRates||{},g=s.costGuard||{},al=s.alerts||{};
  const display=panel(T('显示'),`<form data-mw-form="appearance" class="mw-form"><div class="mw-form-grid">${select(T('数字格式'),'numberFormat',[['compact',T('紧凑（1.2K）')],['full',T('完整数字')]].map(([v,l])=>option(v,l,s.numberFormat||'compact')).join(''))}</div><div class="mw-actions"><button class="mw-primary" type="submit">${T('保存显示')}</button></div></form>`);
  const moneyDefaults=panel(T('默认计算参数'),`<form data-mw-form="money" class="mw-form"><div class="mw-form-grid">${select(T('默认货币'),'defaultCurrency',['USD','CAD','CNY'].map(x=>option(x,x,s.defaultCurrency||'USD')).join(''))}${field(T('默认预算'),'defaultBudget',s.defaultBudget??'100','number','min="0" step="any" required')}${field(T('默认输入占比（0–1）'),'defaultInputRatio',s.defaultInputRatio??'0.8','number','min="0" max="1" step="any" required')}${field(T('默认输出占比（0–1）'),'defaultOutputRatio',s.defaultOutputRatio??'0.2','number','min="0" max="1" step="any" required')}${field(T('默认缓存命中率（0–1）'),'defaultCacheRatio',s.defaultCacheRatio??'0.9','number','min="0" max="1" step="any" required')}</div><p class="mw-note">${T('输入与输出占比之和必须为 1。')}</p><div class="mw-actions"><button class="mw-primary" type="submit">${T('保存计算参数')}</button></div></form>`);
  const rates=panel(T('汇率（手工填写）'),`<form data-mw-form="rates" class="mw-form"><div class="mw-form-grid">${field(T('CAD：1 USD 等于多少 CAD'),'CAD',r.CAD??'','number','min="0" step="any"')}${field(T('CNY：1 USD 等于多少 CNY'),'CNY',r.CNY??'','number','min="0" step="any"')}</div><p class="mw-note">${T('自动汇率来源：')}${esc(s.exchangeRateSource||'UNAVAILABLE')}${s.exchangeRateUpdatedAt?`，${T('更新于')} ${date(s.exchangeRateUpdatedAt)}`:''}。${T('留空表示未配置，依赖该币种的计算会明确报错，不会按 0 计算。')}</p><div class="mw-actions"><button class="mw-primary" type="submit">${T('保存汇率')}</button></div></form>`);
  const guard=panel(T('成本保护'),`<form data-mw-form="guard" class="mw-form"><div class="mw-form-grid">${select(T('超过阈值时'),'mode',[['BLOCK',T('阻断请求')],['REQUIRE_APPROVAL',T('需人工批准')]].map(([v,l])=>option(v,l,g.mode||'BLOCK')).join(''))}${field(T('单次请求成本阈值 · USD（留空=关闭）'),'threshold',g.threshold??'','number','min="0" step="any"')}</div><div class="mw-actions"><button class="mw-primary" type="submit">${T('保存成本保护')}</button></div></form>`);
  const walletDefaults=panel(T('钱包默认与提醒'),`<form data-mw-form="walletDefaults" class="mw-form"><div class="mw-form-grid">${select(T('钱包选择策略'),'walletStrategy',[['MANUAL_PRIORITY',T('手工优先级')],['SOONEST_EXPIRY_FIRST',T('最快到期优先')],['USE_EXPIRING_CREDITS_FIRST',T('即将过期额度优先')],['HIGHEST_BALANCE_FIRST',T('余额最多优先')]].map(([v,l])=>option(v,l,s.walletStrategy||'MANUAL_PRIORITY')).join(''))}${select(T('后端失败模式'),'failMode',[['FAIL_CLOSED',T('失败关闭（默认）')],['FAIL_OPEN',T('失败开放')]].map(([v,l])=>option(v,l,s.failMode||'FAIL_CLOSED')).join(''))}${field(T('即将到期提醒天数'),'creditsExpiringDays',al.creditsExpiringDays??30,'number','min="1" step="1" required')}</div><div class="mw-actions"><button class="mw-primary" type="submit">${T('保存钱包默认')}</button></div></form>`);
  const data=panel(T('导入 / 导出 / 模型目录'),`<div class="mw-two"><div><h3>${T('导出')}</h3><p class="mw-note">${T('导出自定义模型、收藏与隐藏设置、钱包配置（不含余额）、设置、用量与账本。文件只保存在你的本机，请妥善保管。')}</p><button type="button" data-mw-action="settings-export">${T('导出 JSON')}</button></div><div><h3>${T('导入')}</h3><div class="mw-field"><label for="mw-import-file">${T('选择 JSON 文件（不超过 2 MB）')}</label><input id="mw-import-file" type="file" accept="application/json,.json"></div><p class="mw-note">${T('导入不会还原钱包余额或账本；余额需重新手工登记。')}</p><button type="button" data-mw-action="settings-import">${T('导入 JSON')}</button></div></div><hr><h3>${T('模型目录')}</h3><p class="mw-note">${T('当前目录版本')} ${esc(state.catalogVersion||'unknown')}。${T('只导入随包附带的已验证目录，不接受任意 URL。')}</p><button type="button" data-mw-action="catalog-update">${T('更新目录')}</button>`);
  const meta=resetMeta();
  const resetPanel=panel(T('清除记录（需要输入 RESET 确认）'),`<div class="mw-two">${Object.keys(meta).map(k=>`<div class="mw-field"><button type="button" class="mw-danger" data-mw-reset="${k}">${esc(meta[k][0])}</button><p class="mw-note">${esc(meta[k][1])}</p></div>`).join('')}</div>`);
  return heading(T('设置'),T('本地偏好、计算默认值、手工汇率与数据管理。所有修改仅作用于本机模拟。'))
  +`<div class="mw-settings-list">${display}${moneyDefaults}${rates}${guard}${walletDefaults}${data}</div>`+resetPanel;
}
async function saveSettings(kind,f){
  if(!f.reportValidity())return;
  const d=Object.fromEntries(new FormData(f));
  let p;
  if(kind==='appearance')p={numberFormat:d.numberFormat};
  else if(kind==='money')p={defaultCurrency:d.defaultCurrency,defaultBudget:String(d.defaultBudget).trim(),defaultInputRatio:String(d.defaultInputRatio).trim(),defaultOutputRatio:String(d.defaultOutputRatio).trim(),defaultCacheRatio:String(d.defaultCacheRatio).trim()};
  else if(kind==='rates')p={exchangeRates:{USD:'1',CAD:nz(d.CAD),CNY:nz(d.CNY)}};
  else if(kind==='guard')p={costGuard:{mode:d.mode,threshold:nz(d.threshold)}};
  else if(kind==='walletDefaults')p={walletStrategy:d.walletStrategy,failMode:d.failMode,alerts:{...(state.settings.alerts||{}),creditsExpiringDays:Number(d.creditsExpiringDays)}};
  else throw Error(T('未知设置分组'));
  await api('settings','PATCH',p);
  await reload();render();toast(T('设置已保存'));
}
async function exportConfig(){
  const data=await api('export');
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download=`model-wallet-export-${new Date().toISOString().slice(0,10)}.json`;
  document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast(T('配置已导出（含本地账本，请妥善保管）'));
}
async function importConfig(){
  const file=qs('#mw-import-file')?.files?.[0];
  if(!file)throw Error(T('请先选择 JSON 文件'));
  if(file.size>2000000)throw Error(T('文件超过 2 MB 上限'));
  let data;
  try{data=JSON.parse(await file.text())}catch{throw Error(T('JSON 解析失败'))}
  const r=await api('import','POST',data);
  await reload();render();toast(r.reason||T('导入完成'));
}
function resetConfirm(target){
  const meta=resetMeta()[target];if(!meta)return;
  modalKind='reset';
  showModal(`${T('确认')}：${esc(meta[0])}`,`<div class="mw-callout error">${esc(meta[1])}</div><form id="mw-reset-form" data-mw-form="reset" data-mw-target="${esc(target)}" class="mw-form"><div class="mw-field"><label for="mw-f-confirmation">${T('输入 RESET 以确认')}</label><input id="mw-f-confirmation" name="confirmation" autocomplete="off" required aria-describedby="mw-reset-note"></div><p id="mw-reset-note" class="mw-note">${T('为安全起见，所有重置都需要二次确认。')}</p></form>`,
  `<button type="button" data-mw-close>${T('取消')}</button><button type="submit" form="mw-reset-form" class="mw-danger" id="mw-reset-submit" disabled>${T('确认重置')}</button>`);
}
async function resetSubmit(f){
  const target=f.getAttribute('data-mw-target');
  const d=Object.fromEntries(new FormData(f));
  if(String(d.confirmation??'').trim()!=='RESET')throw Error(T('请输入 RESET 以确认'));
  const resetsCalc=target==='calculator'||target==='all';
  if(resetsCalc){draftSuspended=true;calcRevision++;calcRequest++;clearTimeout(draftTimer);draftPending=null;if(draftSaving)await draftSaving;draftPending=null}
  try{
    const revision=resetsCalc?draftPayload(null).calculatorDraftRevision:undefined;
    await api('reset','POST',{confirmation:'RESET',target,...(resetsCalc?{calculatorDraftRevision:revision}:{})});
    closeModal();
    Object.assign(state,{modelId:'',transient:null,result:null,sim:null,routeResult:null,usageRows:null});state.selected.clear();state.compare.clear();
    await reload();
    if(resetsCalc){draftRevision=Math.max(draftRevision,Number(state.settings.calculatorDraftRevision)||0);draftSuspended=false;await resetCalculator(false)}else render();
    toast(`${resetMeta()[target][0]} ${T('已完成')}`);
  }finally{draftSuspended=false}

}

/* ---------- 事件委托（绑在 #mw-root 与 #mw-modal 上） ---------- */
const formHandlers={
  'model-filters':applyModelFilters,
  wallet:saveWallet,
  adjust:adjustWallet,
  custom:()=>saveCustom('save'),
  ctx:()=>simStep('check'),
  route:()=>runRoute(),
  appearance:f=>saveSettings('appearance',f),
  money:f=>saveSettings('money',f),
  rates:f=>saveSettings('rates',f),
  guard:f=>saveSettings('guard',f),
  walletDefaults:f=>saveSettings('walletDefaults',f),
  reset:f=>resetSubmit(f)
};
function doAction(name){
  switch(name){
    case 'refresh':return run(async()=>{await reload();render();toast(T('已刷新'))});
    case 'retry':return loadWallet();
    case 'new-wallet':return walletForm();
    case 'nav-models':return go('models');
    case 'nav-sim':return go('contextgate');
    case 'share':return run(shareCalc);
    case 'calc-reset':return run(resetCalculator);
    case 'picker':readCalc();return picker();
    case 'new-model':return customModel();
    case 'catalog-update':return run(catalogUpdate);
    case 'provider-filter':return providerFilter();
    case 'model-filters':return modelFilters();
    case 'apply-bulk':return run(()=>bulk(qs('#mw-bulk-action')?.value||'enable'));
    case 'clear-modal-filters':Object.assign(state.filters,{capability:'',status:'active',price:'',context:'',hidden:false,favorite:false,custom:false});closeModal();return render();
    case 'provider-apply':return applyProviderFilter(false);
    case 'provider-clear':return applyProviderFilter(true);
    case 'clear-filters':Object.assign(state.filters,{custom:false,search:'',providers:[],category:'',capability:'',status:'active',price:'',context:'',hidden:false,favorite:false});return render();
    case 'toggle-favorite-filter':state.filters.favorite=!state.filters.favorite;return render();
    case 'select-filtered':filtered(state.page==='custom').forEach(m=>state.selected.add(m.id));return render();
    case 'clear-selection':state.selected.clear();return render();
    case 'compare-selection':return compareSelection();
    case 'usage-refresh':return run(async()=>{await loadUsage();toast(T('账本已刷新'))});
    case 'settings-export':return run(exportConfig);
    case 'settings-import':return run(importConfig);
  }
}
const clickRules=[
  ['[data-mw-close]',()=>closeModal()],
  ['[data-mw-nav]',el=>go(el.getAttribute('data-mw-nav'))],
  ['[data-mw-action]',el=>doAction(el.getAttribute('data-mw-action'))],
  ['[data-mw-mode]',el=>{readCalc();state.mode=el.getAttribute('data-mw-mode');state.result=null;calcChanged();render()}],
  ['[data-mw-budget]',el=>{readCalc();state.calc.budget=el.getAttribute('data-mw-budget');render()}],
  ['[data-mw-ratio]',el=>{readCalc();const x=Number(el.getAttribute('data-mw-ratio'));state.calc.input=String(x);state.calc.output=String(100-x);render()}],
  ['[data-mw-cache-mode]',el=>{readCalc();state.cacheMode=el.getAttribute('data-mw-cache-mode');calcChanged();render()}],
  ['[data-mw-cache]',el=>{readCalc();state.calc.cache=el.getAttribute('data-mw-cache');render()}],
  ['[data-mw-view-kind]',el=>{state.view=el.getAttribute('data-mw-view-kind');render()}],
  ['[data-mw-bulk]',el=>run(()=>bulk(el.getAttribute('data-mw-bulk')))],
  ['[data-mw-favorite]',el=>{const id=el.getAttribute('data-mw-favorite');const m=state.models.find(x=>x.id===id);if(m)run(()=>patchModel(id,{favorite:!m.favorite},m.favorite?T('已取消收藏'):T('已收藏')))}],
  ['[data-mw-detail]',el=>run(()=>detail(el.getAttribute('data-mw-detail')))],
  ['[data-mw-pick]',el=>useModel(el.getAttribute('data-mw-pick'))],
  ['[data-mw-use-model]',el=>useModel(el.getAttribute('data-mw-use-model'))],
  ['[data-mw-picker-tab]',el=>{pickerTab=el.getAttribute('data-mw-picker-tab');qsa('#mw-modal [data-mw-picker-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b===el)));renderPicker()}],
  ['[data-mw-override]',el=>{priceOverride(el.getAttribute('data-mw-override'))}],
  ['[data-mw-official-price]',el=>run(()=>officialPrice(el.getAttribute('data-mw-official-price')))],
  ['[data-mw-save-override]',el=>run(()=>saveOverride(el.getAttribute('data-mw-save-override')))],
  ['[data-mw-duplicate]',el=>run(()=>duplicateModel(el.getAttribute('data-mw-duplicate')))],
  ['[data-mw-remove-compare]',el=>{state.compare.delete(el.getAttribute('data-mw-remove-compare'));render()}],
  ['[data-mw-custom-save]',el=>run(()=>saveCustom(el.getAttribute('data-mw-custom-save')))],
  ['[data-mw-wallet-edit]',el=>{const w=walletOf(el.getAttribute('data-mw-wallet-edit'));if(w)walletForm(w)}],
  ['[data-mw-wallet-adjust]',el=>run(()=>adjustForm(el.getAttribute('data-mw-wallet-adjust')))],
  ['[data-mw-wallet-calc]',el=>useWalletInCalc(el.getAttribute('data-mw-wallet-calc'))],
  ['[data-mw-wallet-sync]',el=>run(()=>syncWallet(el.getAttribute('data-mw-wallet-sync')))],
  ['[data-mw-sim]',el=>{const k=el.getAttribute('data-mw-sim');return k==='new-id'?newSimId():run(()=>simStep(k))}],
  ['[data-mw-reset]',el=>resetConfirm(el.getAttribute('data-mw-reset'))]
];
function onClick(e){
  const t=e.target;
  if(!(t instanceof Element))return;
  const tab=t.closest('[data-mw-tab]');
  if(tab){e.preventDefault();go(tab.getAttribute('data-mw-tab'));return}
  for(const [selector,fn] of clickRules){
    const el=t.closest(selector);
    if(el){e.preventDefault();return fn(el)}
  }
}
function onChange(e){
  const t=e.target,id=t.id;
  if(t.form?.dataset.mwForm&&!['calc','ctx'].includes(t.form.dataset.mwForm))t.form.dataset.mwDirty='1';
  if(t.hasAttribute('data-mw-select')){const v=t.getAttribute('data-mw-select');t.checked?state.selected.add(v):state.selected.delete(v);return render()}
  if(t.hasAttribute('data-mw-enable'))return patchModel(t.getAttribute('data-mw-enable'),{enabled:t.checked},t.checked?T('已启用'):T('已禁用'));
  if(id==='mw-select-all'){filtered(state.page==='custom').forEach(m=>t.checked?state.selected.add(m.id):state.selected.delete(m.id));return render()}
  if(id==='mw-provider-filter'){state.filters.providers=t.value?[t.value]:[];return updateModelResults()}
  if(id==='mw-show-hidden'){state.filters.hidden=t.checked;return updateModelResults()}
  if(id==='mw-only-favorite'){state.filters.favorite=t.checked;return updateModelResults()}
  if(filterIds[id]){state.filters[filterIds[id]]=t.value;return updateModelResults()}
  if(id==='mw-usage-wallet'){state.usageFilter.wallet=t.value;return render()}
  if(id==='mw-record-kind'){state.usageFilter.record=t.value;return render()}
  if(id==='mw-usage-type'){state.usageFilter.type=t.value;return render()}
  if(id==='mw-wallet-budget'){readCalc();const w=walletOf(t.value);if(w){state.calc.budget=String(w.availableBalance);state.calc.currency=w.currency;state.result=null}calcChanged();queueDraft(true);return render()}
  if(id==='mw-usage-preset'){readCalc();const p=presets[t.value];if(p){state.calc.input=String(p[0]);state.calc.output=String(p[1]);state.calc.cache=String(p[2])}calcChanged();return render()}
  if(id==='mw-compare-sort')return renderCompareTable(t.value);
  if(id==='mw-picker-provider')return renderPicker();
  if(t.form&&t.form.id==='mw-calc-form')return calcFieldChanged(t);
}
function onInput(e){
  const t=e.target,id=t.id;
  if(t.form?.dataset.mwForm&&!['calc','ctx'].includes(t.form.dataset.mwForm))t.form.dataset.mwDirty='1';
  if(id==='mw-model-search'){if(e.isComposing||composing.has(t))return;state.filters.search=t.value;return updateModelResults()}
  if(id==='mw-picker-search'){if(e.isComposing||composing.has(t))return;pickerSearch=t.value;return renderPicker()}
  if(id==='mw-input-range'){state.calc.input=String(t.value);state.calc.output=String(100-Number(t.value));syncCalcDom();return calcChanged()}
  if(id==='mw-cache-range'){state.calc.cache=String(t.value);syncCalcDom();return calcChanged()}
  if(t.name==='confirmation'&&t.form&&t.form.id==='mw-reset-form'){const b=qs('#mw-reset-submit');if(b)b.disabled=t.value.trim()!=='RESET';return}
  if(t.form&&t.form.id==='mw-calc-form'&&t.type!=='range'&&t.name){if(e.isComposing||composing.has(t))return;return calcFieldChanged(t)}
}
function onSubmit(e){
  const f=e.target;
  if(!(f instanceof HTMLFormElement))return;
  e.preventDefault();
  if(f.id==='mw-calc-form')return run(calculate);
  if(f.id==='mw-compare-form'){if(state.compare.size<2){toast(T('请至少选择 2 个模型'),true);return}return run(compareRun)}
  const h=formHandlers[f.getAttribute('data-mw-form')];
  if(h)return run(async()=>{await h(f);f.dataset.mwDirty='0'});
}
const composing=new WeakSet();
function onCompositionStart(e){composing.add(e.target)}
function onCompositionEnd(e){composing.delete(e.target);onInput(e)}
let eventsBound=false;
function bind(){
  if(eventsBound)return;eventsBound=true;
  const root=qs('#mw-root'),modal=qs('#mw-modal');
  for(const el of [root,modal]){el.addEventListener('click',onClick);el.addEventListener('change',onChange);el.addEventListener('input',onInput);el.addEventListener('compositionstart',onCompositionStart);el.addEventListener('compositionend',onCompositionEnd);el.addEventListener('submit',onSubmit)}
  root.addEventListener('focusout',e=>{if(e.target.form?.id==='mw-calc-form'){readCalc();queueDraft(true)}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){readCalc();queueDraft(true)}});
  window.addEventListener('pagehide',pageDraft);
  modal.addEventListener('close',()=>{modalKind=''});
  modal.addEventListener('cancel',e=>{e.preventDefault();closeModal()});
  modal.addEventListener('click',ev=>{if(ev.target===modal)closeModal()});
}

/* ---------- 入口：控制台切到「模型钱包」视图时调用 ---------- */
let walletRenderedSnapshot='',walletLoading=false;
async function loadWallet(options={}){
  bind();
  const root=qs('#mw-root');if(!root)return false;
  if(walletLoading)return null;
  const editing=()=>qs('#mw-modal')?.open||!!root.querySelector('form[data-mw-dirty="1"],.dd.open')||(root.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select,[contenteditable=true]'));
  if(loaded&&editing())return null;
  if(!loaded)root.innerHTML=`<div class="mw-empty"><p>${T('正在读取本地数据…')}</p></div>`;
  if(loaded){readCalc();readCtx()}
  const revision=calcRevision;
  const fingerprint=()=>JSON.stringify([state.models,state.wallets,state.settings,state.dashboard]);
  walletLoading=true;
  try{
    await reload();
    if(loaded&&(editing()||revision!==calcRevision))return null;
    if(!loaded)restoreDraft();
    if(!loaded||!options.automatic||walletRenderedSnapshot!==fingerprint()){render();walletRenderedSnapshot=fingerprint();}
    loaded=true;return true;
  }catch(e){
    if(loaded)toast(T('更新失败：')+e.message,true);
    else root.innerHTML=panel(T('无法读取本地数据'),`<div class="mw-callout error">${esc(e.message)}</div><p class="mw-note">${T('请确认控制台服务正在本机运行，然后重试。')}</p><div class="mw-actions">${btn(T('重试'),'retry','mw-primary mw-small')}</div>`);
    return false;
  }finally{walletLoading=false;}
}
window.loadWallet=loadWallet;
})();
'''

EN = {
 "模型钱包": "Model Wallet",
 "比较价格和计算预算。余额与交易由你手工登记，不会实际扣款。": "Cost calculation, model price catalog and wallet ledger. Local simulation only: no real calls or deductions.",
 "正在读取本地数据…": "Loading local data…",
 " · 已过期": " · expired",
 "+ 新建钱包": "+ New wallet",
 "1 预算检查": "1 Budget check",
 "2 预留": "2 Reserve",
 "3 模拟结算（含 Usage）": "3 Simulated settle (with usage)",
 "3 模拟结算（带 Usage）": "3 Simulated settle (with usage)",
 "3 模拟缺失 Usage": "3 Simulated settle (no usage)",
 "3′ 模拟缺失 Usage": "3′ Simulated settle (no usage)",
 "4a 释放预留": "4a Release reserve",
 "4b 退款": "4b Refund",
 "CAD：1 USD 等于多少 CAD": "How many CAD equal 1 USD",
 "CNY：1 USD 等于多少 CNY": "How many CNY equal 1 USD",
 "Cache 命中": "Cache hit",
 "Cache 命中率": "Cache hit rate",
 "Cache 节省 · USD": "Cache savings · USD",
 "Cache 节省最多": "Best cache savings",
 "Cache 读": "Cache read",
 "Context 最大": "Largest context",
 "Input / Output 比例": "Input / output ratio",
 "Input 与 Output 占比之和必须为 1。": "Input and output shares must sum to 1.",
 "JSON 解析失败": "JSON parse failed",
 "Registry 状态": "Registry status",
 "Registry、预算与账务统一管理。当前环境不会发送真实模型请求。": "Registry, budgets and ledgers in one place. This environment never sends real model requests.",
 "Tokens 最多": "Most tokens",
 "requestId（同一 ID 参数必须一致）": "requestId (same ID, same parameters required)",
 "三项总计须为 100%，未知 cache-write 价格会阻止对应计费。": "The three shares must total 100%. An unknown cache-write price blocks the charge.",
 "上限必须为非负数字": "limit must be a non-negative number",
 "个 Registry 条目 · Creator 与 API Provider 独立 · USD / 1M token 价格": " Registry entries · Creator and API Provider are independent · USD per 1M tokens",
 "个匹配": "matches",
 "个本地钱包": "local wallets",
 "个模型": "models",
 "个模型 →": "models →",
 "个钱包 30 天内到期": "wallet(s) expiring within 30 days",
 "个隐藏": "hidden",
 "临时模型仅用于本次计算": "Temporary model used for this calculation only",
 "为安全起见，所有重置都需要二次确认。": "For safety, every reset needs a second confirmation.",
 "仅收藏": "Favorites only",
 "简短介绍": "Intro",
 "综合参考价 · 每百万 Tokens": "Blended price · per 1M tokens",
 "按系统默认比例估算": "Estimated at system default ratios",
 "缓存读": "cache read",
 "缓存写": "cache write",
 "计费备注": "Billing notes",
 "你的价格覆盖": "Your price override",
 "仅本地账本模拟，不调用外部模型": "Local ledger simulation only; no external model is called",
 "仅本次计算": "Calculate only",
 "仅来自本地 Usage Ledger": "From the local usage ledger only",
 "今日 Tokens": "Tokens today",
 "今日支出": "Spend today",
 "从未同步": "Never synced",
 "从目录添加": "Add from catalog",
 "价格未确认": "Price unconfirmed",
 "价格来源": "Price source",
 "价格版本": "Price version",
 "价格版本与完整数字": "Price version and full numbers",
 "价格覆盖已保存": "Price override saved",
 "优先级": "Priority",
 "优先级（数字越小越先用）": "Priority (lower number is used first)",
 "估算": "Estimate",
 "估算你的下一次工作负载": "Estimate your next workload",
 "低余额提醒阈值（同币种，留空保持原值）": "Low-balance alert threshold (same currency; blank keeps current)",
 "低余额阈值必须为非负数字": "Low-balance threshold must be a non-negative number",
 "余额低于提醒阈值": "Balance is below the alert threshold",
 "余额已调整": "Balance adjusted",
 "余额感知": "Balance-aware",
 "余额最多优先": "Highest balance first",
 "余额来源": "Balance source",
 "余额请用「余额调整」修改；币种与初始额度创建后不可改。": "Change the balance with “Balance adjustment”. Currency and initial credit cannot be changed after creation.",
 "余额调整": "Balance adjustment",
 "余额（之后）": "Balance (after)",
 "使用官方价格": "Use official price",
 "使用钱包可用额度": "Use wallet available balance",
 "使用预设": "Preset",
 "保存": "Save",
 "保存 Cost Guard": "Save Cost Guard",
 "保存并计算": "Save & calculate",
 "保存显示": "Save display",
 "保存汇率": "Save rates",
 "保存覆盖": "Save override",
 "保存计算参数": "Save calculation defaults",
 "保存钱包默认": "Save wallet defaults",
 "入账": "Credit",
 "全部": "All",
 "全部能力与 Registry 字段": "All capabilities and Registry fields",
 "创建": "Created",
 "初始额度": "Initial credit",
 "初始额度 Initial Credit": "Initial credit",
 "初始额度必须为非负数字": "Initial credit must be a non-negative number",
 "删除钱包、账本、用量、预留、审计与自定义模型，不可撤销。": "Deletes wallets, ledgers, usage, reservations, audit and custom models. Cannot be undone.",
 "删除（隐藏，可撤销）": "Delete (hide, undoable)",
 "到期": "Expires",
 "到期日（留空=无到期）": "Expiry date (blank = none)",
 "到期额度优先": "Expiring credits first",
 "刷新": "Refresh",
 "加入对比": "Add to compare",
 "加载中": "Loading",
 "加载失败": "Load failed",
 "单次 Prompt Tokens · 价格区间": "Single prompt tokens · price tier",
 "单次上限 Per request（钱包币种）": "Per-request limit (wallet currency)",
 "单次请求成本阈值 · USD（留空=关闭）": "Per-request cost threshold · USD (blank = off)",
 "卡片": "Cards",
 "即将到期提醒天数": "Days before expiry to alert",
 "即将到期额度": "Expiring credits",
 "即将过期额度优先": "Expiring credits first",
 "原因": "Reason",
 "原因（必填，写入账本）": "Reason (required, written to the ledger)",
 "原始响应": "Raw response",
 "去路由模拟 →": "Go to routing simulation →",
 "取消": "Cancel",
 "取消收藏": "Unfavorite",
 "取消选择": "Clear selection",
 "变动前": "Before",
 "变动后": "After",
 "只导入随包附带的已验证目录，不接受任意 URL。": "Imports only the verified catalog bundled with the app. Arbitrary URLs are not accepted.",
 "可用 Provider（逗号分隔，留空=按映射）": "Eligible providers (comma-separated; blank = by mapping)",
 "可用余额": "Available balance",
 "可用余额（已扣除预留）": "Available balance (after reservations)",
 "可用模型 ID（逗号分隔，留空=不限）": "Eligible model IDs (comma-separated; blank = any)",
 "可用额度 · USD": "Available credit · USD",
 "同一工作负载，一次比较": "Same workload, compared at once",
 "后端失败模式": "Backend failure mode",
 "含未配置汇率钱包": "includes wallets without an FX rate",
 "含用户主动创建的模拟用量；不等于供应商账单。": "Includes simulated usage you created. Not an official provider bill.",
 "启用": "Enabled",
 "周上限 Weekly": "Weekly limit",
 "在 Calculator 使用": "Use in calculator",
 "在「路由模拟」完成一次预留与结算，或在钱包中做一次余额调整后，流水会出现在这里。": "Run one reservation and settlement in “Routing simulation”, or adjust a wallet balance; entries appear here.",
 "在同一 Pricing Engine 中计算。ESTIMATE 结果不代表实际账单。": "Calculated in the same Pricing Engine. ESTIMATE results are not an actual bill.",
 "在模型目录中勾选 2–10 个模型，再点击「加入对比」。": "Select 2–10 models in the catalog, then click “Add to compare”.",
 "在模型目录收藏模型，或换一个筛选。": "Favorite models in the catalog, or change the filter.",
 "均衡": "Balanced",
 "备注 Notes": "Notes",
 "复制计算摘要": "Copy calculation summary",
 "天": "days",
 "天后到期": "days to expiry",
 "失败": "failed",
 "失败关闭（默认）": "Fail closed (default)",
 "失败开放": "Fail open",
 "完成一笔模拟结算后，按模型和服务商统计将在这里显示。": "Attribution stats appear here after one simulated settlement.",
 "完整数字": "Full numbers",
 "官方定价来源": "Official pricing source",
 "官方实时": "Live official",
 "官方模型文档": "Official model docs",
 "实际 Cache Read Tokens（可留空）": "Actual cache read tokens (optional)",
 "实际 Input Tokens": "Actual input tokens",
 "实际 Output Tokens": "Actual output tokens",
 "实际 Tokens 必须为非负整数": "Actual tokens must be non-negative integers",
 "实际 Usage（用于结算，整数 Tokens）": "Actual usage (for settlement, integer tokens)",
 "实际成本 · USD": "Actual cost · USD",
 "对比": "Compare",
 "对比最多 10 个模型，请减少选择": "Compare at most 10 models. Reduce the selection.",
 "对比结果 · ESTIMATE": "Comparison · ESTIMATE",
 "导入": "Import",
 "导入 / 导出 / 模型目录": "Import / export / model catalog",
 "导入 JSON": "Import JSON",
 "导入不会还原钱包余额或账本；余额需重新手工登记。": "Import does not restore wallet balances or ledgers. Re-enter balances manually.",
 "导入完成": "Import complete",
 "导出": "Export",
 "导出 JSON": "Export JSON",
 "导出自定义模型、收藏与隐藏设置、钱包配置（不含余额）、设置、用量与账本。文件只保存在你的本机，请妥善保管。": "Exports custom models, favorite and hidden settings, wallet config (no balances), settings, usage and ledgers. The file stays on this machine; keep it safe.",
 "将预留": "To reserve",
 "尚未产生消费。创建钱包后可主动执行一笔模拟预留与结算。": "No spend yet. After creating a wallet you can run one simulated reservation and settlement.",
 "尚未执行": "Not run yet",
 "尚未运行路由": "Routing not run yet",
 "尝试同步": "Try sync",
 "尝试调整 Provider、状态或价格筛选。": "Try adjusting the provider, status or price filter.",
 "已刷新": "Refreshed",
 "已取消收藏": "Unfavorited",
 "已启用": "Enabled",
 "已复制为自定义模型": "Duplicated as a custom model",
 "已完成": "completed",
 "已恢复官方价格": "Restored official price",
 "已撤销": "Undone",
 "已收藏": "Favorited",
 "已禁用": "Disabled",
 "已选择": "Selected",
 "已隐藏": "Hidden",
 "币种 Currency": "Currency",
 "带入计算器 →": "Use in calculator →",
 "平均 Input / Request": "Average input / request",
 "平均 Output / Request": "Average output / request",
 "应用筛选": "Apply filter",
 "当前余额": "Current balance",
 "当前余额必须为非负数字": "Current balance must be a non-negative number",
 "当前余额（留空则等于初始额度）": "Current balance (blank = initial credit)",
 "当前成本": "Current cost",
 "当前目录版本": "Current catalog version",
 "必须为非负数字": "must be a non-negative number",
 "总占比始终为 100%。": "The total share is always 100%.",
 "总览": "Overview",
 "总预算 Tokens 是累计量；单次 Prompt 决定长上下文价格条件。非 token 计费模型请查看详情中的计费单位。": "Total budget tokens are cumulative. The single prompt size sets long-context price tiers. For non-token billing, see the billing unit in details.",
 "恢复": "Restore",
 "恢复内置模型目录": "Restore built-in model catalog",
 "恢复默认预算、比例、Cache、显示与手工汇率设置。": "Restore default budget, ratios, cache, display and manual FX settings.",
 "成功": "succeeded",
 "成本 · USD": "Cost · USD",
 "成本与额度总览": "Cost and credit overview",
 "费用明细 · 美元": "Cost breakdown · USD",
 "成本计算": "Cost calculator",
 "成本计算器": "Cost calculator",
 "所有 Context": "All contexts",
 "所有 Provider": "All providers",
 "所有状态": "All statuses",
 "所有类别": "All categories",
 "所有能力": "All capabilities",
 "所有账本类型": "All ledger types",
 "所有输入价格": "All input prices",
 "所有钱包": "All wallets",
 "手动预算": "Manual budget",
 "手工优先级": "Manual priority",
 "手工登记不会连接 Provider，余额来源标记为 MANUAL。": "Manual entries do not connect to a provider. The balance source is marked MANUAL.",
 "手工记录": "Manual",
 "手工钱包": "Manual wallet",
 "手工钱包的余额由你维护，标记为 MANUAL 或 ESTIMATED，不代表 Provider 官方余额；本页不发起真实请求。": "Balances are maintained by you and marked MANUAL or ESTIMATED. They are not official provider balances. This page sends no real requests.",
 "扣款": "Charged",
 "批量操作已完成": "Bulk action complete",
 "按 1 → 2 → 3 → 4 的顺序执行，也可以只运行其中一步。结果显示预算、预留、结算与释放的金额和钱包状态。": "Run in order 1 → 2 → 3 → 4, or run a single step. Results show budget, reserve, settle and release amounts and wallet state.",
 "按 Provider 筛选": "Filter by provider",
 "按账本类型筛选（仅作用于账本流水）": "Filter by ledger type (ledger entries only)",
 "按近 30 天日均消耗估算": "Estimated from average daily use over the last 30 days",
 "按钱包筛选": "Filter by wallet",
 "排序": "Sort",
 "提交调整": "Submit adjustment",
 "搜索名称、Model ID、Creator…": "Search name, model ID, creator…",
 "搜索模型": "Search models",
 "搜索模型、Provider、Creator": "Search models, provider, creator",
 "撤销": "Undo",
 "操作失败": "Action failed",
 "支出概览": "Spend overview",
 "收藏": "Favorite",
 "收藏模型": "Favorite model",
 "数字格式 Number Format": "Number format",
 "文件超过 2 MB 上限": "File exceeds the 2 MB limit",
 "新建手工钱包": "New manual wallet",
 "新建自定义模型": "New custom model",
 "无 Cache 成本": "Cost without cache",
 "无到期日": "No expiry",
 "无可用候选": "No available candidate",
 "无法计算": "Cannot calculate",
 "无法读取本地数据": "Cannot read local data",
 "日上限 Daily": "Daily limit",
 "时间": "Time",
 "显示": "Display",
 "显示货币": "Display currency",
 "显示隐藏": "Show hidden",
 "暂无 Provider。": "No providers.",
 "暂无用量": "No usage",
 "暂无用量记录": "No usage records",
 "暂无账本流水": "No ledger entries",
 "暂无预留记录": "No reservations",
 "更新于": "updated",
 "更新目录": "Update catalog",
 "最低成本优先": "Cheapest first",
 "最后同步": "Last synced",
 "最快到期优先": "Soonest expiry first",
 "最近": "Recent",
 "最近 30 天请求": "Requests, last 30 days",
 "月上限 Monthly": "Monthly limit",
 "有价格适用条件": "Has conditional pricing",
 "有效成本最低": "Lowest effective cost",
 "服务已重启，请按横幅提示重开控制台": "The service restarted. Reopen the console as the banner says.",
 "服务已重启，连接令牌已更新，本次操作没有生效。": "The service restarted and the connection token changed. This action did not take effect.",
 "服务端未返回 JSON，请确认应用已启动": "The server did not return JSON. Check that the app is running.",
 "未接入官方余额来源": "No official balance source connected",
 "未知": "Unknown",
 "未知价格": "Unknown price",
 "未知价格将显示明确错误，绝不会当作免费。": "Unknown prices show a clear error and are never treated as free.",
 "未知来源": "Unknown source",
 "未知模拟步骤": "Unknown simulation step",
 "未知设置分组": "Unknown settings group",
 "未结算：没有 Usage，预留保留待对账，不按预估费用扣款。": "Not settled: no usage. The reservation is kept for reconciliation and is not charged at the estimate.",
 "未选择": "not selected",
 "未验证": "Not verified",
 "本地价格覆盖": "Local price override",
 "本地估算，不代表实际账单。": "Local estimate, not an actual bill.",
 "本地偏好、计算默认值、手工汇率与数据管理。所有修改仅作用于本机模拟。": "Local preferences, calculation defaults, manual FX and data management. All changes apply only to this local simulation.",
 "本次临时模型": "temporary model for this calculation",
 "条件价格": "Conditional price",
 "模型": "Model",
 "模型 Model": "Model",
 "模型与 API Endpoint": "Model and API endpoint",
 "模型名称 Model Name": "Model name",
 "模型对比": "Model comparison",
 "模型文档": "Model docs",
 "模型条目": "Registry entries",
 "模型目录": "Model catalog",
 "模型详情": "Model details",
 "模型钱包子页面": "Model wallet sub-pages",
 "模型：": "Model: ",
 "模拟结果": "Simulation result",
 "次": "requests",
 "次模拟结算": "simulated settlements",
 "次结算": "settlements",
 "正在读取账本…": "Reading the ledger…",
 "正在调用统一 Pricing Engine…": "Calling the unified Pricing Engine…",
 "步骤 3′ 演示「无 Usage 不按预估结算」：预留保持不变。": "Step 3′ shows “no usage, no estimate-based settlement”. The reservation stays unchanged.",
 "比值": "Ratio",
 "汇率（币种 / 1 USD）": "FX rate (currency per 1 USD)",
 "汇率（手工填写）": "FX rates (manual)",
 "没有匹配条目": "No matching entries",
 "没有匹配模型": "No matching models",
 "没有可用模型": "No models available",
 "没有已登记的即将到期额度。": "No registered credits expiring soon.",
 "清空": "Clear",
 "清除筛选": "Clear filters",
 "清除隐藏、启用、收藏与价格覆盖；自定义模型保留。": "Clears hidden, enabled, favorite and price-override settings. Custom models are kept.",
 "点击「+ 新建钱包」登记一笔额度：Provider、初始额度、币种与到期日。手工登记的余额会标记为 MANUAL，不会被当作实时余额。": "Click “+ New wallet” to register a credit: provider, initial credit, currency and expiry. Manual balances are marked MANUAL and never treated as live balances.",
 "版本状态": "Version status",
 "状态": "Status",
 "独立模拟环境": "Standalone simulation",
 "独立模拟：未接入真实 ContextGate，不调用外部模型，不产生真实账单。": "Standalone simulation: not connected to a real ContextGate. No external model is called and no real bill is produced.",
 "生成新 requestId": "New requestId",
 "用量与账本": "Usage and ledger",
 "用量扣款": "Usage charge",
 "用量记录": "Usage records",
 "用量账本": "Usage ledger",
 "用量账本 ↗": "Usage ledger ↗",
 "留空的价格保存为 Unknown，不会当作 $0。自定义价格仅表示你的配置。": "Blank prices are saved as Unknown, never as $0. Custom prices only reflect your configuration.",
 "留空表示未配置，依赖该币种的计算会明确报错，不会按 0 计算。": "Blank means not configured. Calculations that depend on that currency show a clear error instead of using 0.",
 "目录已更新：": "Catalog updated: ",
 "目录版本": "Catalog version",
 "相同预算、比例与 Cache 条件。未知价格保留明确错误。": "Same budget, ratio and cache conditions. Unknown prices keep a clear error.",
 "确认": "Confirm",
 "确认模型计费类型、Cache 价格及汇率设置后重试。": "Check the billing type, cache prices and FX settings, then retry.",
 "确认重置": "Confirm reset",
 "禁用": "Disabled",
 "管理模型 →": "Manage models →",
 "类别": "Category",
 "类型": "Type",
 "紧凑（1.2K）": "Compact (1.2K)",
 "累计成本 · USD": "Cumulative cost · USD",
 "结果": "Result",
 "结算成功后会记录实际 Usage 与成本。缺失 Usage 的请求不会被按预估结算。": "Actual usage and cost are recorded after a successful settlement. Requests missing usage are not settled at the estimate.",
 "按美元计算，再按所设汇率显示。": "Exact USD settlement. Display conversion is done by the backend FX rate.",
 "统一工作负载": "Shared workload",
 "缓存 Cache": "Cache",
 "编辑": "Edit",
 "编辑自定义模型": "Edit custom model",
 "编辑钱包": "Edit wallet",
 "能力": "Capabilities",
 "能力 Capabilities": "Capabilities",
 "自动汇率来源：": "Automatic FX source: ",
 "自动选择（按钱包策略）": "Auto-select (by wallet strategy)",
 "自定义": "Custom",
 "自定义价格覆盖": "Custom price override",
 "自定义模型": "Custom models",
 "自定义模型已保存": "Custom model saved",
 "自定义比例": "Custom ratio",
 "表格": "Table",
 "被拒绝的候选": "Rejected candidates",
 "被拒绝的钱包": "Rejected wallets",
 "覆盖只修改账户配置，官方目录与历史账单保持原价格版本。": "Overrides only change account settings. The official catalog and historical bills keep the original price version.",
 "计算可用 Tokens →": "Calculate usable tokens →",
 "计算可运行请求数 →": "Calculate runnable requests →",
 "计算摘要": "Calculation summary",
 "计算摘要已复制": "Calculation summary copied",
 "计算结果": "Result",
 "计算预估成本 →": "Calculate estimated cost →",
 "计费单位": "Billing unit",
 "设置": "Settings",
 "设置已保存": "Settings saved",
 "该模型明确不支持 Cache。": "This model explicitly does not support cache.",
 "请先勾选模型": "Select models first",
 "请先选择 JSON 文件": "Choose a JSON file first",
 "请填写 requestId": "Enter a requestId",
 "请填写调整原因": "Enter an adjustment reason",
 "请求": "Request",
 "请确认控制台服务正在本机运行，然后重试。": "Make sure the console service is running on this machine, then retry.",
 "请至少选择 2 个模型": "Select at least 2 models",
 "请输入 RESET 以确认": "Type RESET to confirm",
 "请选择模型": "Choose a model",
 "调整会生成 ADJUSTMENT 账本记录。调整后可用余额不得低于预留金额。": "The adjustment creates an ADJUSTMENT ledger entry. Available balance after adjustment must not fall below reserved amounts.",
 "调整金额格式不正确": "Invalid adjustment amount format",
 "调整金额（正数增加，负数减少）": "Adjustment amount (positive adds, negative subtracts)",
 "账本": "Ledger",
 "账本已刷新": "Ledger refreshed",
 "账本流水": "Ledger entries",
 "账本流水、预留与用量记录，均来自本地模拟（钱包操作与路由模拟页产生）。不是 Provider 官方账单。": "Ledger entries, reservations and usage records all come from the local simulation (wallet actions and routing simulation). Not an official provider bill.",
 "货币": "Currency",
 "质量优先（需用户提供评分）": "Quality first (requires user-provided scores)",
 "质量分": "Quality score",
 "超过阈值时": "When threshold is exceeded",
 "路由模拟": "Routing simulation",
 "路由模拟 ↗": "Routing simulation ↗",
 "路由策略 Strategy": "Routing strategy",
 "路由预览（只读，不预留）": "Routing preview (read-only, no reservation)",
 "输入 Cache": "Input cache",
 "输入 RESET 以确认": "Type RESET to confirm",
 "输入/输出": "Input/output",
 "输入价格": "Input price",
 "输入占比": "Input share",
 "运行路由模拟": "Run routing simulation",
 "近 30 天": "Last 30 days",
 "近 7 天": "Last 7 days",
 "还没有钱包": "No wallets yet",
 "这里的路由与账务只在本机数据库中模拟，未接入真实 ContextGate，不会调用任何外部模型或 Provider。模拟记录标记为 SIMULATED。": "Routing and accounting are simulated only in the local database. Not connected to a real ContextGate. No external model or provider is called. Records are marked SIMULATED.",
 "连接型钱包（未接入）": "Connected wallet (not connected)",
 "退款": "Refund",
 "退款金额": "Refund amount",
 "退款金额（留空=全额剩余 · 钱包币种）": "Refund amount (blank = full remainder, wallet currency)",
 "适用条件：": "Conditions: ",
 "选中：": "Selected: ",
 "选择": "Select",
 "选择 JSON 文件（不超过 2 MB）": "Choose a JSON file (max 2 MB)",
 "选择全部筛选结果": "Select all filtered results",
 "选择模型": "Select model",
 "选择模型 · API Endpoint": "Select model · API endpoint",
 "选择模型、设置预算与使用比例，然后计算。": "Choose a model, set the budget and usage ratio, then calculate.",
 "选择策略后运行。将列出每个启用模型的预算检查结果与被拒绝原因，不会预留额度。": "Choose a strategy and run it. Lists each enabled model's budget check and rejection reason. No credit is reserved.",
 "选择至少两个模型。结果包含 Tokens、有效价格、Cache Savings 与 Context。": "Select at least two models. Results include tokens, effective price, cache savings and context.",
 "透支": "Overdrawn",
 "配置已导出（含本地账本，请妥善保管）": "Config exported (includes local ledger; keep it safe)",
 "释放": "Release",
 "释放金额": "Released amount",
 "重新导入随包附带的已验证目录，保留钱包与账本。": "Re-import the verified catalog bundled with the app. Wallets and ledgers are kept.",
 "重置本地数据": "Reset local data",
 "重置模型设置": "Reset model settings",
 "重置计算器设置": "Reset calculator settings",
 "清除记录（需要输入 RESET 确认）": "Reset (destructive; type RESET to confirm)",
 "重试": "Retry",
 "金额": "Amount",
 "钱包": "Wallet",
 "钱包 Wallet": "Wallet",
 "钱包不存在，请刷新页面": "Wallet not found. Refresh the page.",
 "钱包名称 Name": "Wallet name",
 "钱包已创建": "Wallet created",
 "钱包已更新": "Wallet updated",
 "钱包选择策略": "Wallet selection strategy",
 "钱包额度": "Wallet credits",
 "钱包默认与提醒": "Wallet defaults and alerts",
 "阻断请求": "Block request",
 "隐藏": "Hide",
 "需人工批准": "Requires manual approval",
 "预估 Cache 命中率 %": "Estimated cache hit rate %",
 "预估 Input Tokens": "Estimated input tokens",
 "预估 Output Tokens": "Estimated output tokens",
 "预估 Tokens 必须为非负整数": "Estimated tokens must be non-negative integers",
 "预留": "Reserved",
 "预留中": "Reserved",
 "预留只降低可用余额，不改变账面余额；释放或结算后状态会更新。": "A reservation lowers the available balance but not the book balance. Status updates after release or settlement.",
 "预留后将低于提醒阈值": "Will be below the alert threshold after reservation",
 "预留记录": "Reservations",
 "预留金额": "Reserved amount",
 "预算": "Budget",
 "预算 Budget": "Budget",
 "预计可用天数": "Estimated days remaining",
 "预计成本 · USD": "Estimated cost · USD",
 "默认 Cache 命中率（0–1）": "Default cache hit rate (0–1)",
 "默认 Input 占比（0–1）": "Default input share (0–1)",
 "默认 Output 占比（0–1）": "Default output share (0–1)",
 "默认计算参数": "Calculation defaults",
 "默认货币": "Default currency",
 "默认预算": "Default budget",
}

# Additional UI labels use the console language; model/provider data stay unchanged.
EN.update({
 "缓存节省": "Cache Savings",
 "常用模型": "Top Models",
 "常用服务商": "Top Providers",
 "常用 AI 助手": "Top agents",
 "总 Tokens": "Total Tokens",
 "输入 %": "Input %",
 "输出 %": "Output %",
 "缓存 %": "Cache %",
 "基础": "Basic",
 "高级": "Advanced",
 "每百万 tokens 的估算费用 · 美元": "Effective Cost / 1M · USD",
 "输入 / 输出": "Input / Output",
 "未缓存输入": "Uncached Input",
 "缓存读取 / 写入": "Cache Read / Write",
 "输出": "Output",
 "缓存读取 + 写入": "Cache Read + Write",
 "每次请求成本": "Cost / Request",
 "服务商": "Provider",
 "API 服务商": "API Provider",
 "开发者": "Creator",
 "模型 ID": "Model ID",
 "系列 / 版本": "Family / Version",
 "发布日期": "Release Date",
 "上下文": "Context",
 "最大输入 / 输出": "Max Input / Output",
 "输入 · USD / 1M": "Input · USD / 1M",
 "输出 · USD / 1M": "Output · USD / 1M",
 "最后验证": "Last Verified",
 "输入 / 1M": "Input / 1M",
 "输出 / 1M": "Output / 1M",
 "缓存读取 / 1M": "Cache Read / 1M",
 "缓存写入 / 1M": "Cache Write / 1M",
 "上下文窗口": "Context Window",
 "成本保护": "Cost Guard",
 "+ 自定义模型": "+ Custom Model",
 "推理": "Reasoning",
 "编程": "Coding",
 "视觉": "Vision",
 "工具调用": "Tool Calling",
 "图像": "Image",
 "音频": "Audio",
 "视频": "Video",
 "嵌入": "Embedding",
 "流式": "Streaming",
 "开放权重": "Open Weight",
 "活跃版本": "Active generations",
 "支持缓存": "Has Cache",
 "免费": "Free",
 "名称": "Name",
 "最新发布": "Newest",
 "最低输入价格": "Cheapest Input",
 "最低输出价格": "Cheapest Output",
 "最大上下文": "Largest Context",
 "最低缓存价格": "Best Cache Price",
 "最近验证": "Recently Verified",
 "工具": "Tools",
 "聊天": "Chat",
 "编程 Agent": "Coding Agent",
 "长上下文编程": "Long-context Coding",
 "文档分析": "Document Analysis",
 "翻译": "Translation",
 "批量处理": "Batch Processing",
 "输入": "Input",
 "已验证": "Verified",
 "模型 / 开发者": "Model / Creator",
 "模型": "Model",
 "每百万成本 · USD": "Cost / 1M USD",
 "接口 / 其他计费": "Endpoints / Other Pricing",
 "复制为自定义模型": "Duplicate as Custom",
 "估算预设": "Estimated preset",
 "预算 → Tokens": "Money → Tokens",
 "Tokens → 成本": "Tokens → Money",
 "请求数": "Requests",
 "预算": "Budget",
 "输入缓存": "Input cache",
 "输入 / 输出比例": "Input / output ratio",
 "缓存命中率": "Cache hit rate",
 "未缓存输入 %": "Uncached Input %",
 "缓存读取 %": "Cache Read %",
 "缓存写入 %": "Cache Write %",
 "模型与 API 接口": "Model and API endpoint",
 "钱包名称": "Wallet name",
 "币种": "Currency",
 "初始额度": "Initial credit",
 "单次上限（钱包币种）": "Per-request limit (wallet currency)",
 "日上限": "Daily limit",
 "周上限": "Weekly limit",
 "月上限": "Monthly limit",
 "备注": "Notes",
 "模型名称": "Model name",
 "能力": "Capabilities",
 "缓存": "Cache",
 "钱包": "Wallet",
 "路由策略": "Routing strategy",
 "数字格式": "Number format",
 "仅来自本地用量账本": "From the local usage ledger only",
 "目录状态": "Catalog status",
 "API 服务商数": "API providers",
 "目录、预算与账务统一管理。当前环境不会发送真实模型请求。": "Manage the catalog, budget and accounting together. This environment sends no real model requests.",
 "更多": "More",
 "更多筛选与排序": "More filters and sorting"
})

EN.update({
 "上下文": "Context",
 "所有上下文": "All contexts",
 "所有服务商": "All providers",
 "搜索名称、模型 ID、开发者…": "Search name, model ID, creator…",
 "搜索模型、服务商、开发者": "Search models, provider, creator",
 "按服务商筛选": "Filter by provider",
 "尝试调整服务商、状态或价格筛选。": "Try adjusting the provider, status or price filter.",
 "选择模型 · API 接口": "Select model · API endpoint",
 "在计算器使用": "Use in calculator",
 "完整模型资料": "All capabilities and Registry fields",
 "个目录条目 · 开发者与 API 服务商独立 · USD / 1M token 价格": " Registry entries · Creator and API Provider are independent · USD per 1M tokens",
 "默认输入占比（0–1）": "Default input share (0–1)",
 "默认输出占比（0–1）": "Default output share (0–1)",
 "默认缓存命中率（0–1）": "Default cache hit rate (0–1)",
 "输入与输出占比之和必须为 1。": "Input and output shares must sum to 1.",
 "缓存命中": "Cache hit",
 "缓存读取": "Cache read",
 "缓存节省 · USD": "Cache savings · USD",
 "缓存节省最多": "Best cache savings",
 "上下文最大": "Largest context",
 "保存成本保护": "Save Cost Guard",
 "单次提示 Tokens · 价格区间": "Single prompt tokens · price tier",
 "本次用量（整数 tokens）": "Actual usage (for settlement, integer tokens)",
 "预估输入 Tokens": "Estimated input tokens",
 "预估输出 Tokens": "Estimated output tokens",
 "预估缓存命中率 %": "Estimated cache hit rate %",
 "实际输入 Tokens": "Actual input tokens",
 "实际输出 Tokens": "Actual output tokens",
 "实际缓存读取 Tokens（可留空）": "Actual cache read tokens (optional)",
 "现行": "Current",
 "新发布": "New",
 "预览": "Preview",
 "上一代": "Previous generation",
 "旧版": "Legacy",
 "弃用": "Deprecated",
 "已退役": "Retired",
 "文本": "Text",
 "快速": "Fast",
 "经济": "Budget",
 "多模态": "Multimodal",
 "输出价格": "Output price",
 "缓存读取价格": "Cache read price",
 "缓存写入价格": "Cache write price"
})

EN.update({
 "技术详情与完整字段": "Technical details and full fields",
 "按统一价格规则计算。结果为估算，不代表实际账单。": "Calculated with shared pricing rules. Estimates are not actual bills.",
 "正在计算预估成本…": "Calculating estimated cost…",
 "对比结果 · 估算": "Comparison · Estimate"
})

EN.update({
 "模型库": "Model library",
 "钱包与账本": "Wallet and ledger",
 "预算预设": "Budget preset",
 "自定义预算": "Custom budget",
 "缓存命中率 %": "Cache hit rate %",
 "输入 / 输出价格": "Input / output price",
 "操作": "Actions",
 "计算": "Calculate",
 "选择模型计算成本；勾选多个模型可对比。价格单位：USD / 1M Tokens。": "Choose a model to calculate cost; select several to compare. Prices: USD / 1M tokens.",
 "新增模型": "Add model",
 "搜索": "Search",
 "用途": "Use case",
 "筛选": "Filter",
 "批量操作": "Bulk action",
 "应用": "Apply",
 "筛选模型": "Filter models",
 "仅自定义模型": "Custom models only",
 "返回模型库": "Back to model library",
 "返回钱包与账本": "Back to wallet and ledger",
 "记录类型": "Record type",
 "手工登记额度并查看本地账本。": "Register credits manually and view the local ledger.",
 "还没有钱包，点击新建钱包登记额度。": "No wallets yet. Add a wallet to register credits.",
 "额度与支出明细": "Credit and spend details",
 "登记或调整钱包额度后，记录会显示在这里。": "Entries appear after registering or adjusting wallet credits.",
 "完成模拟结算后，用量会显示在这里。": "Usage appears after a simulated settlement."
})

EN.update({
 "更新失败：": "Update failed: ",
 "已复制": "Copied",
 "重置计算器": "Reset calculator",
 "计算器已重置": "Calculator reset",
 "计算器草稿未保存，请重试或保持页面打开。": "Calculator draft was not saved. Retry or keep this page open."
})
