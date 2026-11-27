"""Obsidian Prism (黑曜棱镜): default console style.

Neutral obsidian surfaces, a cobalt accent and a thin four-stop prism line used
only as a signature (brand mark, active nav, overlays). Surfaces are solid:
no backdrop blur on persistent chrome and no animated or fixed backgrounds.
"""

CSS = r'''
/* ===== 黑曜棱镜 · tokens ===== */
:root[data-style=prism]{--p1:#4C8DF6;--p2:#9B72CB;--p3:#D96570;--p4:#F2B84B;--prism:linear-gradient(90deg,var(--p1),var(--p2) 38%,var(--p3) 70%,var(--p4));--prism-v:linear-gradient(180deg,var(--p1),var(--p2) 55%,var(--p3));--r-sm:8px;--r-md:10px;--r-lg:12px;--ease:cubic-bezier(.2,0,0,1);--ease-out:cubic-bezier(.16,1,.3,1)}
:root[data-style=prism][data-theme=dark]{color-scheme:dark;--bg:#0E0E11;--sidebg:#09090B;--card:#151519;--card2:#1C1C21;--cardT:#151519;--field:#0F0F12;--chip:rgba(255,255,255,.035);--chipbg:#1C1C21;--line:rgba(255,255,255,.07);--line2:rgba(255,255,255,.13);--glassline:rgba(255,255,255,.085);--text:#F2F2F5;--muted:#A2A2AF;--accent:#7EA9F7;--accent2:#5B89D6;--onaccent:#08101F;--accentbg:rgba(126,169,247,.13);--rowhover:rgba(255,255,255,.04);--ok:#4CC38A;--okbg:rgba(76,195,138,.13);--bad:#F2685F;--badbg:rgba(242,104,95,.13);--warn:#F2B84B;--warnbg:rgba(242,184,75,.13);--mutbg:rgba(255,255,255,.06);--tipbg:#202027;--tiptext:#F2F2F5;--prebg:#09090B;--pretext:#E4E4EA;--hl:rgba(255,255,255,.06);--shadow:0 6px 18px -6px rgba(0,0,0,.6);--cardshadow:0 1px 2px rgba(0,0,0,.35),0 10px 28px -16px rgba(0,0,0,.8);--panelshadow:inset 0 1px 0 rgba(255,255,255,.07),0 0 0 .5px rgba(0,0,0,.5),0 24px 60px -12px rgba(0,0,0,.75);--lift:0 14px 36px -14px rgba(0,0,0,.8);--glassbg:#18181D;--g1:transparent;--g2:transparent;--g3:transparent;--refreshshadow:none;--sel-fill:color-mix(in srgb,#7EA9F7 15%,#18181D);--sel-glow:0 4px 16px -6px rgba(76,141,246,.55),0 2px 12px -6px rgba(217,101,112,.35);--bar-glow:0 0 12px rgba(76,141,246,.45);--cost:#7EA9F7;--costbg:rgba(126,169,247,.13);--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%238F8F9C' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
:root[data-style=prism][data-theme=warm]{color-scheme:light;--bg:#F4F6FA;--sidebg:#ECF0F6;--card:#FFFFFF;--card2:#F1F4F9;--cardT:#FFFFFF;--field:#F7F9FC;--chip:#F4F6FA;--chipbg:#EEF2F8;--line:rgba(15,23,42,.08);--line2:rgba(15,23,42,.15);--glassline:rgba(15,23,42,.11);--text:#0F172A;--muted:#56637A;--accent:#1D4ED8;--accent2:#1E40AF;--onaccent:#FFFFFF;--accentbg:rgba(37,99,235,.09);--rowhover:rgba(15,23,42,.035);--ok:#15803D;--okbg:rgba(21,128,61,.1);--bad:#C81E1E;--badbg:rgba(220,38,38,.09);--warn:#A1460A;--warnbg:rgba(217,119,6,.12);--mutbg:rgba(15,23,42,.06);--tipbg:#0F172A;--tiptext:#F8FAFC;--prebg:#0F172A;--pretext:#E2E8F0;--hl:rgba(255,255,255,.9);--shadow:0 4px 14px rgba(15,23,42,.08);--cardshadow:0 1px 2px rgba(15,23,42,.05),0 8px 24px -14px rgba(30,58,138,.14);--panelshadow:0 0 0 1px rgba(15,23,42,.06),0 2px 6px rgba(15,23,42,.06),0 24px 52px -14px rgba(30,58,138,.22);--lift:0 12px 30px -12px rgba(30,58,138,.22);--glassbg:#FFFFFF;--g1:transparent;--g2:transparent;--g3:transparent;--refreshshadow:none;--sel-fill:color-mix(in srgb,#2563EB 8%,#FFFFFF);--sel-glow:0 4px 14px -6px rgba(37,99,235,.35),0 2px 10px -6px rgba(217,101,112,.25);--bar-glow:0 0 10px rgba(37,99,235,.3);--cost:#1D4ED8;--costbg:rgba(37,99,235,.09);--chev:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%2364748B' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}

/* ===== base ===== */
:root[data-style=prism] body{font-family:"SF Pro Text",-apple-system,BlinkMacSystemFont,Inter,"Segoe UI Variable","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);background-image:radial-gradient(1100px 420px at 62% -120px,rgba(76,141,246,.07),transparent 70%)}
:root[data-style=prism][data-theme=warm] body{background-image:radial-gradient(1100px 420px at 62% -120px,rgba(37,99,235,.06),transparent 70%)}
:root[data-style=prism] ::selection{background:color-mix(in srgb,var(--accent) 28%,transparent)}
:root[data-style=prism] :is(code,pre,kbd,code.file){font-family:"SF Mono","JetBrains Mono",ui-monospace,Menlo,monospace}
:root[data-style=prism] :focus-visible{outline:2px solid color-mix(in srgb,var(--accent) 75%,transparent);outline-offset:2px}

/* Solid chrome: blur only on transient overlays, never on persistent surfaces. */
:root[data-style=prism] :is(#sidenav,header select,header button,header .chk,.dd-menu,.modal-panel,.group-compose .group-menu,.tour-card,body.todo-mini #todo-page){backdrop-filter:none;-webkit-backdrop-filter:none}

/* ===== sidebar ===== */
:root[data-style=prism] #sidenav{background:var(--sidebg);border-right:1px solid var(--line)}
:root[data-style=prism] #sidenav .brand{display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;letter-spacing:-.015em}
:root[data-style=prism] #sidenav .brand::before{content:"";display:block;flex:none;width:16px;height:16px;border-radius:3px;transform:rotate(45deg) scale(.86);background:conic-gradient(from 210deg,var(--p1),var(--p2),var(--p3),var(--p4),var(--p1));box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 14px -2px rgba(76,141,246,.55)}
:root[data-style=prism] body.sidemini #sidenav .brand{justify-content:center;padding:4px 0 16px}
:root[data-style=prism] .nav-group-label{font-size:11px;font-weight:550;letter-spacing:.03em;color:color-mix(in srgb,var(--muted) 78%,transparent)}
:root[data-style=prism] #sidenav .nav-item{position:relative;min-height:36px;border-radius:var(--r-sm);color:var(--muted);transition:background-color .14s var(--ease),color .14s var(--ease)}
:root[data-style=prism] #sidenav .nav-item:hover{color:var(--text);background:var(--rowhover)}
:root[data-style=prism] #sidenav .nav-item.on,:root[data-style=prism] #sidenav .nav-item.is-current-section{color:var(--text);font-weight:550;background:var(--card2);box-shadow:inset 0 1px 0 var(--hl),0 0 0 1px var(--line)}
:root[data-style=prism] #sidenav .nav-item.is-current-section:not(.on){background:transparent;box-shadow:none;font-weight:500}
:root[data-style=prism][data-theme=warm] #sidenav .nav-item.on{background:#FFFFFF;box-shadow:0 0 0 1px var(--line2),0 1px 2px rgba(15,23,42,.06)}
:root[data-style=prism] #sidenav .nav-item.on svg{color:var(--accent)}
:root[data-style=prism] #sidenav .nav-item.on::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:0 3px 3px 0;background:linear-gradient(180deg,var(--p1),var(--p2) 55%,var(--p3))}
:root[data-style=prism] .nav-footer{border-top-color:var(--line)}
:root[data-style=prism] .nav-sub{border-left-color:var(--line2)}

/* ===== header & toolbar ===== */
:root[data-style=prism] .console-header h1{font-size:22px;font-weight:600;letter-spacing:-.025em}
:root[data-style=prism] .global-actions :is(button,.iconbtn),:root[data-style=prism] .refresh-control #refresh{border-radius:var(--r-sm);background:var(--card);border:1px solid var(--line2);box-shadow:inset 0 1px 0 var(--hl);color:var(--text)}
:root[data-style=prism] .global-actions :is(button,.iconbtn):hover,:root[data-style=prism] .refresh-control #refresh:hover{background:var(--card2);border-color:var(--line2)}
:root[data-style=prism] .page-toolbar{border-bottom-color:var(--line)}
:root[data-style=prism] .dd-btn{background-color:var(--card);border-color:var(--line2);box-shadow:inset 0 1px 0 var(--hl)}
:root[data-style=prism] .dd-btn:hover{background-color:var(--card2)}
:root[data-style=prism] .dd-btn.filtering{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,transparent)}

/* ===== fields ===== */
:where(:root[data-style=prism]) :is(input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]),textarea){background-color:var(--field);border-color:var(--line2)}
:where(:root[data-style=prism]) :is(input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select):focus{outline:none;border-color:color-mix(in srgb,var(--accent) 70%,transparent);box-shadow:0 0 0 3px var(--accentbg)}
:root[data-style=prism] :is(input[type=checkbox],input[type=radio],input[type=range]){accent-color:var(--accent)}
:root[data-style=prism] #git-page .git-search{background:var(--field);border-color:var(--line2);border-radius:var(--r-sm)}

/* ===== surfaces ===== */
:root[data-style=prism] :is(section,.card,.tile,.wb-item,.scard,.group-pane,.quota-log-row){background-image:none}
:root[data-style=prism] .tile{box-shadow:inset 0 1px 0 var(--hl)}
:root[data-style=prism] section:not([data-view=group]){background-color:var(--card);border:1px solid var(--glassline);border-radius:var(--r-lg);box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow)}
:root[data-style=prism] section h2{font-size:14px;font-weight:600;letter-spacing:-.01em}
:root[data-style=prism] .h2-meta{font-weight:400}
:root[data-style=prism] .card{position:relative;background-color:var(--card);border-color:var(--glassline);border-radius:var(--r-lg);box-shadow:inset 0 1px 0 var(--hl),var(--cardshadow)}
:root[data-style=prism] .grid>.card::before{content:"";position:absolute;left:22px;right:22px;top:0;height:3px;border-radius:0 0 3px 3px;background:var(--prism);box-shadow:var(--bar-glow);opacity:0;transform:scaleX(.55);transition:opacity .2s var(--ease),transform .32s var(--ease);pointer-events:none}
:root[data-style=prism] .grid>.card:hover::before{opacity:1;transform:none}
:root[data-style=prism] .grid>.card:hover{border-color:var(--line2)}
:root[data-style=prism] .card .k{font-weight:500}
:root[data-style=prism] .card .v{font-size:30px;font-weight:600;letter-spacing:-.03em}
:root[data-style=prism] .tile{border-radius:var(--r-md)}
:root[data-style=prism] .card.memory-topic{background:var(--card2);box-shadow:none;border-radius:var(--r-md)}
:root[data-style=prism] .tile:hover{border-color:color-mix(in srgb,var(--accent) 40%,transparent)}
:root[data-style=prism] :is(.ux-advanced,.theme-family){background:var(--card);border-color:var(--glassline)}
:root[data-style=prism] pre{border-radius:var(--r-sm)}

/* ===== tables ===== */
:root[data-style=prism] th{font-weight:550;letter-spacing:.01em;border-bottom-color:var(--line2)}
:root[data-style=prism] td{border-bottom-color:var(--line)}

/* ===== segmented / chips / tags ===== */
:root[data-style=prism] .charts button{background:transparent;border-color:var(--line2);box-shadow:none}
:root[data-style=prism] .charts button.on{background:var(--accentbg);border-color:color-mix(in srgb,var(--accent) 55%,transparent);color:var(--accent)}
:root[data-style=prism] :is(.modetog,.quota-seg){background:var(--field);border-color:var(--line2)}
:root[data-style=prism] .tag{font-weight:500}

/* ===== primary actions ===== */
:root[data-style=prism] :is(#center-form #center-submit,.ask-row .ask-ok,#butler-submit){background:var(--accent);color:var(--onaccent);border-color:transparent;box-shadow:inset 0 1px 0 rgba(255,255,255,.25),0 1px 2px rgba(0,0,0,.25)}
:root[data-style=prism] :is(#center-form #center-submit,.ask-row .ask-ok,#butler-submit):hover{background:color-mix(in srgb,var(--accent) 88%,#fff)}

/* ===== overlays ===== */
:root[data-style=prism] .dd-menu{background:var(--glassbg);border-color:var(--line2);border-radius:var(--r-md);box-shadow:var(--panelshadow)}
:root[data-style=prism] .dd-it{border-radius:6px}
:root[data-style=prism] .modal-panel{position:relative;background:var(--glassbg);border-color:var(--line2);border-radius:14px;box-shadow:var(--panelshadow)}
:root[data-style=prism] .modal-panel::before{content:"";position:absolute;left:28px;right:28px;top:0;height:3px;border-radius:0 0 3px 3px;background:var(--prism);box-shadow:var(--bar-glow);pointer-events:none}
:root[data-style=prism] .modal-backdrop{background:rgba(4,4,7,.62);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)}
:root[data-style=prism][data-theme=warm] .modal-backdrop{background:rgba(15,23,42,.3)}
:root[data-style=prism] .tour-card{background:var(--glassbg);box-shadow:var(--panelshadow)}
:root[data-style=prism] #charttip{border-radius:6px;box-shadow:var(--shadow)}

/* ===== 棱镜选中态 · prism selection system ===== */
/* 1) Pills & segmented controls: prism gradient ring + soft glow. */
:root[data-style=prism] :is(.quota-seg button,#mw-root .mw-seg button,#mw-modal .mw-seg button,.memory-presentation button){border:1px solid transparent}
:root[data-style=prism] :is(.charts button.on,.quota-seg button[aria-pressed=true],.router-chips button.on,#mw-root .mw-presets button[aria-pressed=true],#mw-modal .mw-presets button[aria-pressed=true],#mw-root .mw-seg button[aria-pressed=true],#mw-modal .mw-seg button[aria-pressed=true],#todo-page .todo-bar button[aria-pressed=true],.memory-presentation button[aria-pressed=true],.router-batch-choice label:has(input:checked),.tour-lang-btn.on,.theme-choice-row button[aria-pressed=true]){border:1px solid transparent;background:linear-gradient(var(--sel-fill),var(--sel-fill)) padding-box,var(--prism) border-box;box-shadow:var(--sel-glow);color:var(--text);font-weight:600}
:root[data-style=prism] .modetog .mt-thumb{border:1px solid transparent;background:linear-gradient(var(--sel-fill),var(--sel-fill)) padding-box,var(--prism) border-box;box-shadow:var(--sel-glow)}
:root[data-style=prism] :is(.modetog[data-mode=cost] [data-m=cost],.modetog[data-mode=usage] [data-m=usage],.modetog[data-pos] span.on){color:var(--text)}
/* 2) Tabs: 3px prism bar under the current tab. */
:root[data-style=prism] :is(.router-tabs button.on,#mw-root .mw-tabs button[aria-current=page]){position:relative;border-bottom-color:transparent;color:var(--text)}
:root[data-style=prism] :is(.router-tabs button.on,#mw-root .mw-tabs button[aria-current=page])::after{content:"";position:absolute;left:10px;right:10px;bottom:-1px;height:3px;border-radius:3px 3px 0 0;background:var(--prism);box-shadow:var(--bar-glow);pointer-events:none}
/* 3) Lists & menus: vertical prism bar, same as the sidebar. */
:root[data-style=prism] :is(.dd-it.on,.group-member.on,.group-channel.on,.memory-list button.on,#import-list button[aria-pressed=true]){position:relative;color:var(--text);background:var(--sel-fill);border-color:var(--line2)}
:root[data-style=prism] :is(.dd-it.on,.group-member.on,.group-channel.on,.memory-list button.on,#import-list button[aria-pressed=true])::before{content:"";position:absolute;left:0;top:8px;bottom:8px;width:3px;border-radius:0 3px 3px 0;background:var(--prism-v);box-shadow:var(--bar-glow);pointer-events:none}
:root[data-style=prism] #sidenav .nav-item.on::before{box-shadow:var(--bar-glow);background:var(--prism-v)}
/* Hover highlights. */
:where(:root[data-style=prism]) :is(button,select,.dd-btn):not(:disabled):hover{border-color:color-mix(in srgb,var(--accent) 50%,var(--line2))}
:root[data-style=prism] #sidenav .nav-item:hover svg{color:var(--accent)}
:root[data-style=prism] tbody tr:hover>td:first-child{box-shadow:inset 3px 0 0 color-mix(in srgb,var(--accent) 80%,transparent)}
:root[data-style=prism] :is(#center-form #center-submit,.ask-row .ask-ok,#butler-submit):not(:disabled):hover{box-shadow:0 0 0 3px var(--accentbg),0 6px 18px -6px color-mix(in srgb,var(--accent) 70%,transparent)}

/* ===== 微动效 · micro-motion (transform/opacity only; reduced-motion turns it all off) ===== */
@keyframes cgRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes cgPop{0%{transform:scale(.94)}55%{transform:scale(1.035)}100%{transform:none}}
@keyframes cgBarY{from{opacity:0;transform:scaleY(.1)}to{opacity:1;transform:none}}
@keyframes cgBarX{from{opacity:0;transform:scaleX(.1)}to{opacity:1;transform:none}}
@keyframes cgModal{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}
@keyframes cgItem{from{opacity:0;transform:translateX(-4px)}to{opacity:1;transform:none}}
/* KPI cards cascade in whenever their view is shown (display:none -> grid restarts CSS animations). */
:root[data-style=prism] main .grid>.card{animation:cgRise .46s var(--ease-out) backwards;transition:transform .22s var(--ease-out),border-color .2s var(--ease),box-shadow .2s var(--ease)}
:root[data-style=prism] main .grid>.card:nth-child(2){animation-delay:.05s}
:root[data-style=prism] main .grid>.card:nth-child(3){animation-delay:.1s}
:root[data-style=prism] main .grid>.card:nth-child(n+4){animation-delay:.15s}
:root[data-style=prism] main .grid>.card:hover{transform:translateY(-2px);box-shadow:inset 0 1px 0 var(--hl),var(--lift)}
:root[data-style=prism] main section .tile{transition:transform .22s var(--ease-out),background-color .16s var(--ease)}
:root[data-style=prism] main section .tile:hover{transform:translateY(-2px)}
/* Selection indicators grow in from their anchor when the state is applied. */
:root[data-style=prism] #sidenav .nav-item.on::before,:root[data-style=prism] :is(.dd-it.on,.group-member.on,.group-channel.on,.memory-list button.on,#import-list button[aria-pressed=true])::before{animation:cgBarY .34s var(--ease-out)}
:root[data-style=prism] :is(.router-tabs button.on,#mw-root .mw-tabs button[aria-current=page])::after{animation:cgBarX .34s var(--ease-out)}
:root[data-style=prism] :is(.charts button.on,.quota-seg button[aria-pressed=true],.router-chips button.on,#mw-root .mw-presets button[aria-pressed=true],#mw-modal .mw-presets button[aria-pressed=true],#mw-root .mw-seg button[aria-pressed=true],#mw-modal .mw-seg button[aria-pressed=true],#todo-page .todo-bar button[aria-pressed=true],.memory-presentation button[aria-pressed=true],.tour-lang-btn.on,.theme-choice-row button[aria-pressed=true]){animation:cgPop .34s var(--ease-out)}
/* Click on a pill: the prism ring draws itself around the button once, then stays. */
@property --cg-sweep{syntax:'<angle>';inherits:false;initial-value:360deg}
@keyframes cgDraw{from{--cg-sweep:0deg}to{--cg-sweep:360deg}}
:root[data-style=prism] :is(.charts button.on,.quota-seg button[aria-pressed=true],.router-chips button.on,#mw-root .mw-presets button[aria-pressed=true],#mw-modal .mw-presets button[aria-pressed=true],#mw-root .mw-seg button[aria-pressed=true],#mw-modal .mw-seg button[aria-pressed=true],#todo-page .todo-bar button[aria-pressed=true],.memory-presentation button[aria-pressed=true]){position:relative;background:var(--sel-fill) padding-box}
:root[data-style=prism] :is(.charts button.on,.quota-seg button[aria-pressed=true],.router-chips button.on,#mw-root .mw-presets button[aria-pressed=true],#mw-modal .mw-presets button[aria-pressed=true],#mw-root .mw-seg button[aria-pressed=true],#mw-modal .mw-seg button[aria-pressed=true],#todo-page .todo-bar button[aria-pressed=true],.memory-presentation button[aria-pressed=true])::after{content:"";position:absolute;inset:-1px;border-radius:999px;padding:1.5px;background:conic-gradient(from 180deg,#4C8DF6,#9B72CB,#D96570,#F2B84B,#4C8DF6);-webkit-mask:conic-gradient(from 180deg,#000 var(--cg-sweep),transparent 0),linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:source-in,xor;mask:conic-gradient(from 180deg,#000 var(--cg-sweep),transparent 0),linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:intersect,exclude;animation:cgDraw .6s cubic-bezier(.4,0,.2,1) backwards;pointer-events:none}

/* Two-option segmented (.quota-seg, e.g. 按付费设置/按官方标价): one prism thumb slides between options, like 计费/用量. */
:root[data-style=prism] .quota-seg{position:relative}
:root[data-style=prism] .quota-seg::before{content:"";position:absolute;top:50%;height:26px;margin-top:-13px;left:4px;width:calc(50% - 6px);border-radius:999px;border:1px solid transparent;background:linear-gradient(var(--sel-fill),var(--sel-fill)) padding-box,var(--prism) border-box;box-shadow:var(--sel-glow);transition:transform .28s cubic-bezier(.2,.8,.2,1),opacity .2s;pointer-events:none}
:root[data-style=prism] .quota-seg:has(>button:nth-of-type(2)[aria-pressed=true])::before{transform:translateX(calc(100% + 4px))}
:root[data-style=prism] .quota-seg:not(:has(>button[aria-pressed=true]))::before{opacity:0}
:root[data-style=prism] :is(#cost-mode,.quota-seg).quota-seg>button{position:relative;z-index:1;min-height:26px;height:26px;padding:0 14px;font-size:13px;border:0;transition:color .28s ease;background:transparent;box-shadow:none;animation:none}
:root[data-style=prism] :is(#cost-mode,.quota-seg).quota-seg>button[aria-pressed=true]{background:transparent;box-shadow:none;animation:none;color:var(--text)}
:root[data-style=prism] :is(#cost-mode,.quota-seg).quota-seg>button[type]::after,:root[data-style=prism] :is(#cost-mode,.quota-seg).quota-seg>button[aria-pressed]::after{content:none;display:none}

/* Press feedback, icon nudge, overlays. */
:where(:root[data-style=prism]) button:not(:disabled):active{transform:scale(.97)}
:root[data-style=prism] #sidenav .nav-item svg{transition:transform .22s var(--ease-out),color .14s var(--ease)}
:root[data-style=prism] #sidenav .nav-item:hover svg{transform:translateX(2px)}
:root[data-style=prism] .modal-panel{animation:cgModal .28s var(--ease-out)}
:root[data-style=prism] .dd.open .dd-it{animation:cgItem .24s var(--ease-out) backwards}
:root[data-style=prism] .dd.open .dd-it:nth-child(2){animation-delay:.02s}
:root[data-style=prism] .dd.open .dd-it:nth-child(3){animation-delay:.04s}
:root[data-style=prism] .dd.open .dd-it:nth-child(n+4){animation-delay:.06s}
:root[data-style=prism] .wb-chev{transition:transform .26s var(--ease-out)}
::view-transition-old(root),::view-transition-new(root){animation-duration:.32s;animation-timing-function:cubic-bezier(.2,0,0,1)}
@media (prefers-reduced-motion:reduce){::view-transition-old(root),::view-transition-new(root){animation:none}}

/* ===== theme picker swatch ===== */
:root .theme-choice-row button[data-theme-style=prism]::before{box-shadow:0 1px 3px #00000012}
:root .theme-choice-row button[data-theme-style=prism][data-theme-mode=dark]::before{background:linear-gradient(90deg,#09090B 0 23%,transparent 23%),linear-gradient(90deg,#4C8DF6,#9B72CB,#D96570,#F2B84B) 0 0/100% 2px no-repeat,linear-gradient(#5B89D6,#5B89D6) 36% 28%/36% 3px no-repeat,linear-gradient(#2A2A31,#2A2A31) 55% 56%/58% 3px no-repeat,linear-gradient(#2A2A31,#2A2A31) 55% 73%/58% 3px no-repeat,#151519}
:root .theme-choice-row button[data-theme-style=prism][data-theme-mode=warm]::before{background:linear-gradient(90deg,#E8EEF6 0 23%,transparent 23%),linear-gradient(90deg,#4C8DF6,#9B72CB,#D96570,#F2B84B) 0 0/100% 2px no-repeat,linear-gradient(#2563EB,#2563EB) 36% 28%/36% 3px no-repeat,linear-gradient(#E1E9F4,#E1E9F4) 55% 56%/58% 3px no-repeat,linear-gradient(#E1E9F4,#E1E9F4) 55% 73%/58% 3px no-repeat,#FFF}
:root .theme-presets:has(> :nth-child(3)){max-width:none;grid-template-columns:repeat(3,minmax(0,1fr))}
@media(max-width:62em){:root .theme-presets:has(> :nth-child(3)){grid-template-columns:1fr}}

/* ===== shared layout fixes (all styles) ===== */
#mw-calc-form hr{grid-column:1/-1;width:100%;height:0;border:0;border-top:1px solid var(--line);margin:4px 0}
@media(min-width:38.001em){#workbench .wb-name{flex:0 0 auto;max-width:32%}}
.propbar:not(:has(> i:not([hidden]))){display:none}
/* Ranked bar rows slide by var(--dy)*100% of their OWN height: a wrapped row breaks the stack. */
.brow>*{white-space:nowrap;min-width:0}
.brow .breq{overflow:hidden;text-overflow:ellipsis}
@media(min-width:38.001em){#plat-viz .brow{grid-template-columns:150px minmax(24px,1fr) 84px 120px}}
:root[data-style=prism] #refresh-note:empty{display:none}

/* ===== narrow layout: horizontal nav ===== */
@media(max-width:55em){
 :root[data-style=prism] #sidenav{background:var(--sidebg);border-right:0;border-bottom:1px solid var(--line)}
 :root[data-style=prism] #sidenav .nav-item.on::before{left:12px;right:12px;top:auto;bottom:-5px;width:auto;height:2px;border-radius:2px;background:var(--prism)}
}
'''
