"""Native router management, sharing the console's theme and language tokens."""
CSS = r'''
.router-top,.router-tools,.router-tabs,.router-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.router-top{justify-content:space-between;margin-bottom:16px}.router-top h2{margin:0 0 4px;font-size:18px}.router-top p{margin:0;color:var(--muted)}
.router-scope{display:flex;align-items:center;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:12px;line-height:1.6;margin:-4px 0 12px}.router-scope button{min-height:32px;font-size:12px}
.router-tabs{margin:0 0 20px;gap:24px;border-bottom:1px solid var(--line)}.router-tabs button{padding:12px 0;border:0;border-bottom:2px solid transparent;border-radius:0;background:transparent;font-size:14px;color:var(--muted);box-shadow:none}.router-tabs button.on{border-bottom-color:var(--accent);color:var(--text);font-weight:600}.router-tabs button:hover{color:var(--text)}
.router-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.router-stat{padding:12px 16px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}
.router-stat>span,.router-stat small{display:block;color:var(--muted);font-size:12px}.router-stat b{display:block;font-size:20px;margin:4px 0;font-variant-numeric:tabular-nums;font-weight:600}
.router-state{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.router-badge{font-size:12px;padding:4px 8px;border-radius:6px;background:var(--mutbg);color:var(--muted)}.router-badge.on{background:var(--okbg);color:var(--ok)}
#router-note{min-height:20px;color:var(--muted);margin:8px 0;font-size:13px}#router-note.error{color:var(--bad)}
.router-tools{justify-content:space-between;margin-bottom:16px}.router-tools label{display:flex;align-items:center;gap:8px;white-space:nowrap}.router-tools input{width:min(260px,100%)}
.router-table{width:100%;overflow:auto}.router-table table{width:100%;border-collapse:collapse;font-size:13px}.router-table th{text-align:left;font-size:12px;color:var(--muted);background:var(--chip);font-weight:500}.router-table td,.router-table th{padding:12px 8px;border-bottom:1px solid var(--line);vertical-align:top}.router-table td small{display:block;color:var(--muted);margin-top:4px;overflow-wrap:anywhere}.router-table .number{text-align:right;font-variant-numeric:tabular-nums}.router-table td:first-child{font-weight:500}.router-table button{min-height:32px;font-size:12px;padding:4px 8px}.router-table details{max-width:440px}.router-table pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:320px;overflow:auto}.router-table td:has(>[data-bedrock-enable]),.router-table table:has([data-bedrock-enable]) th:last-child{position:sticky;right:0;background:var(--card);box-shadow:-1px 0 0 var(--line)}
.router-empty{padding:24px 8px;color:var(--muted);line-height:1.7}.router-settings{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}.router-setting-card{padding:16px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}.router-setting-card h3{font-size:14px;margin:0 0 16px}.router-setting-card p{font-size:13px;color:var(--muted);line-height:1.7}.router-setting-card label{display:flex;gap:8px;align-items:center;margin-bottom:16px}.router-setting-card label.router-field{display:block}.router-setting-card input[type=number]{display:block;margin-top:8px;max-width:160px}.router-key{display:flex;gap:8px;flex-wrap:wrap}.router-key input{flex:1;min-width:100px}.router-help{color:var(--muted);font-size:13px;line-height:1.7;overflow-wrap:anywhere}
#router-dialog{width:min(560px,calc(100% - 32px));max-height:85vh;overflow:auto;background:var(--card);color:var(--text);border:1px solid var(--glassline);border-radius:12px;padding:24px;box-shadow:var(--panelshadow)}#router-dialog::backdrop{background:rgba(11,13,16,.6)}#router-dialog h3{font-size:16px;margin:0 0 16px}.router-form{display:grid;gap:16px}.router-form label{display:block;font-size:13px;color:var(--muted)}.router-form input:not([type=checkbox]),.router-form select,.router-form textarea{width:100%;margin-top:8px;min-height:36px}.router-form textarea{min-height:72px}
.router-form label>.dd-select{margin-top:8px}.router-form .router-actions{justify-content:flex-end}.router-form label.check{display:flex;gap:8px;align-items:center;color:var(--text)}.router-form label.check input{margin:0}.router-form-error{color:var(--bad);min-height:20px;font-size:13px}.router-form-error.ok{color:var(--text)}.router-batch-enter{animation:routerBatchIn .16s ease-out}@keyframes routerBatchIn{from{opacity:0;transform:translateY(4px) scale(.99)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.router-batch-enter{animation:none}}.router-key-row{display:grid;gap:12px;padding:16px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}.router-key-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.router-form .router-key-row .router-actions{justify-content:flex-start}.router-form .router-key input{margin-top:0}.router-form .router-key{margin-top:8px}
.router-badge.warn{background:var(--warnbg);color:var(--warn)}.router-badge.bad{background:var(--badbg);color:var(--bad)}#router-caps-table table{min-width:880px}#router-caps-summary{margin:0 0 12px}
#router-page button:disabled{opacity:.5;cursor:default}#router-page button:focus-visible,#router-dialog button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.router-batch-choice{display:flex;gap:8px;flex-wrap:wrap;border:0;padding:0;margin:0}.router-batch-choice legend{font-size:13px;color:var(--muted);margin-bottom:8px}.router-batch-choice label{display:flex;align-items:center;gap:8px;padding:8px 16px;border:1px solid var(--glassline);border-radius:8px;color:var(--text);cursor:pointer;white-space:nowrap}.router-batch-choice label:has(input:checked){background:var(--accentbg);border-color:var(--accent)}.router-form .router-batch-choice input[type=radio]{width:16px;flex:0 0 16px;margin:0;min-height:0}#router-batch-text{min-height:160px;resize:vertical;line-height:1.7}#router-batch-preview{max-height:240px;overflow:auto}.router-form .router-batch-actions{position:sticky;bottom:-24px;padding:16px 0;background:var(--card)}#router-dialog button:disabled{opacity:.5;cursor:default}#router-batch-text[aria-invalid=true]{border-color:var(--bad)}
@media(max-width:1000px){.router-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.router-settings{grid-template-columns:minmax(0,1fr)}}
.router-chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.router-chips button{min-height:32px;font-size:12px}.router-chips button.on{background:var(--accentbg);border-color:var(--accent);color:var(--accent)}.router-bedrock-quick{display:flex;gap:16px;flex-wrap:wrap;margin:8px 0}.router-bedrock-quick label{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--muted)}.router-report{padding:16px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip);margin:12px 0;font-size:13px;line-height:1.8}.router-report b{font-variant-numeric:tabular-nums}.router-report .router-actions{margin-top:8px}
@media(max-width:650px){.router-top{align-items:flex-start}.router-table td,.router-table th{padding:8px}.router-tools label{width:100%}.router-tools input{flex:1;min-width:0}.router-tabs{gap:4px}}

#router-main:not([data-tab=overview]):not([data-tab=logs])>.router-stats,#router-main:not([data-tab=overview]):not([data-tab=logs])>.router-scope{display:none}
.router-stats{gap:0;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}.router-stat{border:0;border-radius:0;background:none}.router-stat+.router-stat{border-left:1px solid var(--glassline)}.router-stat small:empty{display:none}
.bedrock-toolbar{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-bottom:12px}.bedrock-toolbar label{display:grid;gap:8px;flex:1;min-width:180px;font-size:12px;color:var(--muted)}.bedrock-toolbar input{width:100%;min-height:36px}.bedrock-toolbar button{min-height:36px}.bedrock-primary{background:var(--accentbg);border-color:var(--accent);color:var(--accent)}
.bedrock-more{position:relative}.bedrock-more>summary,.bedrock-filters>summary{cursor:pointer;list-style:none}.bedrock-more>summary{border:1px solid var(--glassline);border-radius:8px;padding:8px 12px;font-size:13px}.bedrock-more>summary::-webkit-details-marker,.bedrock-filters>summary::-webkit-details-marker{display:none}.bedrock-more[open]>summary{background:var(--chip)}.bedrock-more-menu{position:absolute;right:0;top:calc(100% + 8px);z-index:4;display:grid;gap:4px;min-width:144px;padding:8px;border:1px solid var(--glassline);border-radius:8px;background:var(--card);box-shadow:var(--panelshadow)}.bedrock-more-menu button{text-align:left;white-space:nowrap}
.bedrock-filters{border:1px solid var(--glassline);border-radius:8px;margin:12px 0}.bedrock-filters>summary{display:flex;gap:8px;align-items:center;padding:12px 16px;font-size:13px}.bedrock-filters>summary:before{content:'›';font-size:16px;color:var(--muted)}.bedrock-filters[open]>summary:before{transform:rotate(90deg)}#bedrock-filter-summary{color:var(--muted);font-size:12px;overflow-wrap:anywhere}.bedrock-filter-body{padding:0 16px 12px}.bedrock-filter-label{font-size:12px;color:var(--muted);margin-top:12px}.bedrock-filter-footer{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0}.bedrock-filter-footer button{min-height:32px;font-size:12px}.bedrock-count{color:var(--muted);font-size:12px}
#bedrock-table table{min-width:760px}#bedrock-table td:first-child{min-width:200px;max-width:250px}#bedrock-table td:nth-child(2){min-width:140px;max-width:190px}#bedrock-table td:nth-child(6){min-width:100px}.bedrock-model-name{font-weight:600}.bedrock-model-detail{margin-top:8px;font-size:12px;font-weight:400;color:var(--muted)}.bedrock-model-detail summary{cursor:pointer}.bedrock-model-detail code{display:block;overflow-wrap:anywhere;margin-top:4px}.bedrock-capability{line-height:1.6}.bedrock-cache summary{white-space:nowrap;cursor:pointer;font-size:12px;color:var(--muted)}.bedrock-cache[open]{min-width:84px}
@media(max-width:1000px){.router-stats{grid-template-columns:repeat(4,minmax(0,1fr))}.router-stat{padding:12px}.router-stat b{font-size:18px}}@media(max-width:650px){.router-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.router-stat:nth-child(3){border-left:0;border-top:1px solid var(--glassline)}.router-stat:nth-child(4){border-top:1px solid var(--glassline)}.bedrock-toolbar label{flex-basis:100%}}

#router-page button,.bedrock-more>summary,.bedrock-filters>summary{transition:transform .14s ease,background-color .16s ease,border-color .16s ease,color .16s ease}
#router-page button:not(:disabled):hover,.bedrock-more>summary:hover,.bedrock-filters>summary:hover{background-color:var(--hl)}
#router-page button:not(:disabled):active,.bedrock-more>summary:active{transform:translateY(1px)}
.bedrock-filters>summary:before{transition:transform .2s ease}
@media(prefers-reduced-motion:reduce){#router-page button,.bedrock-more>summary,.bedrock-filters>summary,.bedrock-filters>summary:before{transition:none!important;transform:none!important}}
.router-quota-panel{margin:12px 0;padding:16px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}
.router-quota-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.router-quota-head h3{margin:0;font-size:15px}
.router-quota-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.router-quota-actions label{display:flex;align-items:center;gap:6px;cursor:pointer}
.router-quota-summary{color:var(--muted);min-height:20px;font-size:13px;margin-bottom:12px}
.router-quota-summary.ok{color:var(--text)}
.router-quota-summary.error{color:var(--bad)}
.router-quota-list{display:grid;gap:8px;margin-top:12px}
.router-quota-provider{border:1px solid var(--glassline);border-radius:8px;background:var(--card);padding:12px}
.router-quota-provider summary{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;cursor:pointer;font-size:13px}
.router-quota-provider summary small{color:var(--muted)}
.router-quota-provider .router-table{margin-top:8px}
.router-badge.quota{font-variant-numeric:tabular-nums}
.router-quota-skip{margin:10px 0 0;font-size:12px;color:var(--muted)}
.router-kiro-toggle{display:inline-flex;align-items:center;gap:6px;margin-top:6px;font-size:12px;color:var(--text);cursor:pointer;font-weight:400}
.router-kiro-toggle input{margin:0}
.router-kiro-box{display:grid;gap:6px;padding:10px 12px;border:1px solid var(--glassline);border-radius:8px;background:var(--chip)}
.router-kiro-box label.check{cursor:pointer;font-weight:500}
.router-kiro-box small{color:var(--muted);font-size:12px;line-height:1.5}
'''
HTML = r'''
<section data-view="router" id="router-page" style="display:none">
<div class="router-top"><div class="router-actions"><button id="router-launch" type="button">启动模型路由</button><button id="router-open" type="button">打开原 App</button></div></div>
<div id="router-note" role="status" aria-live="polite">正在连接模型路由…</div>
<div id="router-main" hidden><div class="router-state"><span id="router-status" class="router-badge"></span><code id="router-address"></code><button id="router-copy-url" type="button">复制地址</button><span style="flex:1"></span><button id="router-start" type="button">启动服务</button><button id="router-stop" type="button">停止服务</button><button id="router-restart" type="button">重启服务</button></div>
<div class="router-stats" id="router-stats"></div>
<div class="router-scope" role="status" aria-live="polite"><span id="router-scope-note"></span><button id="router-show-all" type="button" hidden>查看全部时间</button></div>
<div class="router-tabs" role="tablist" aria-label="模型路由"><button type="button" class="on" data-router-tab="overview" role="tab">总览</button><button type="button" data-router-tab="providers" role="tab">供应商</button><button type="button" data-router-tab="models" role="tab">调用名称</button><button type="button" data-router-tab="capabilities" role="tab">模型状态</button><button type="button" data-router-tab="bedrock" role="tab">模型库</button><button type="button" data-router-tab="routes" role="tab">模型别名</button><button type="button" data-router-tab="logs" role="tab">请求日志</button><button type="button" data-router-tab="settings" role="tab">路由设置</button></div>
<div id="router-content" role="tabpanel"></div></div>
</section>
<dialog id="router-dialog" aria-labelledby="router-form-title"><h3 id="router-form-title"></h3><form id="router-form" class="router-form"></form></dialog>
'''
EN = {
"Token 未提供":"Tokens not provided",
"部分请求未提供 Token":"Some requests did not report tokens",
"模型状态":"Capabilities",
"降级":"Degraded",
"超时":"Timed out",
"已下线":"Retired",
"缺密钥":"Missing key",
"不可用":"Unavailable",
"未知":"Unknown",
"可用":"Available",
"已下线（410）":"Retired (410)",
"限流（429）":"Rate limited (429)",
"密钥无效（401）":"Invalid key (401)",
"无权限（403）":"Forbidden (403)",
"模型不存在（404）":"Model not found (404)",
"请求参数错误":"Bad request",
"连接上游失败":"Upstream connection failed",
"上游错误（5xx）":"Upstream error (5xx)",
"路由不可达":"Router unreachable",
"其他错误":"Other error",
"检查":"probe",
"百万 tokens":"million tokens",
"工具调用":"Tool calls",
"支持":"supported",
"不支持":"not supported",
"成功":"Success",
"未检查":"Not probed",
"成功样本":"Success samples",
"近":"Last",
"天":"days",
"路由端口":"Router port",
"可达":"reachable",
"不可达":"unreachable",
"未检查":"not checked",
"直连备用":"Direct fallback",
"平台 / 模型":"Platform / model",
"耗时 P50 / P95":"Latency P50 / P95",
"错误率":"Error rate",
"最后错误":"Last error",
"价格（输入 / 输出）":"Price (input / output)",
"能力":"Capabilities",
"最近检查":"Last probe",
"只读统计路由器 router.db 的请求记录；主动检查默认关闭，每次检查都会消耗供应商额度。价格只取模型钱包目录中同平台的官方价，未知不推算；工具调用与 Responses 没有实测证据时标为未知。":"Read-only statistics from the router’s router.db request log. Active probes are off by default and every probe consumes provider quota. Prices come only from the wallet catalog for the same platform; unknown prices are not estimated. Tool calls and Responses stay unknown without measured evidence.",
"暂无能力记录。":"No capability records yet.",
"模型路由正常，无需直连备用。":"The router is healthy; no direct fallback needed.",
"直连备用默认关闭；需用户明确启用。":"Direct fallback is off by default and needs explicit opt-in.",
"模型路由 App 未运行，平台密钥只在其钥匙串中，无法安全取用；直连备用不可用。":"The router app is not running and provider keys live only in its Keychain, so they cannot be obtained safely; direct fallback is unavailable.",
"模型路由端口不可用，但路由 App 仍在运行，可经其管理桥取用密钥直连。":"The router port is down but the app is running, so keys can be obtained through its management bridge for a direct call.",
'能力 / 上下文':'Features / context','调用 / 目录状态':'Call path / catalog status','搜索模型':'Search models','更多操作':'More actions','筛选':'Filters','未设置筛选':'No filters applied','清除筛选':'Clear filters','价格 / 百万 Token':'Price / million tokens','目录可用':'Listed available','目录状态':'Catalog status','模型详情':'Model details','缓存价格':'Cache pricing','目录状态不代表账户调用权限；实际访问还取决于供应商账户、地区与模型授权。':'Catalog status does not verify account access; invocation also depends on provider account, region and model permissions.',
'同步到 ZCode':'Sync to ZCode','将所选模型添加或更新到 ZCode，保留已有其他模型。':'Add or update selected models in ZCode, preserving other existing models.','选择模型':'Select models','选择账号':'Select accounts','请选择至少一个模型和一个账号。':'Select at least one model and one account.','没有已启用模型或可同步账号。':'No enabled models or available accounts.','正在同步到 ZCode…':'Syncing to ZCode…','全部账号同步完成':'All accounts synced','部分账号同步失败':'Some accounts failed to sync','同步失败':'Sync failed','已更新':'Updated','无需更新':'Unchanged',
'批量添加':'Batch add','批量添加密钥':'Batch keys','操作方式':'Operation','替换':'Replace','新建':'Create','文本格式':'Text format','纯密钥':'Keys only','纯备注':'Notes only','综合':'Notes and keys','粘贴文本':'Paste text','预览':'Preview','返回密钥列表':'Back to keys','待补密钥':'Key needed','待补密钥，填写后保存':'Enter a key, then save',
'每行一把密钥；空行忽略。':'One key per line; blank lines are ignored.','每行一条备注；空行忽略。':'One note per line; blank lines are ignored.','每两行一组：第一行备注，第二行密钥；空备注可以留空行。':'Two lines per entry: note, then key. An empty note may use a blank line.',
'替换按当前列表从上到下对应，数量必须与已有条目一致。':'Replace follows the current list from top to bottom; the count must match all existing entries.','新建会追加条目；只有备注的条目暂不启用，补入密钥后可使用。':'Create appends entries. Note-only entries stay disabled until a key is added.','请输入要批量处理的文本。':'Paste the text to process.','综合模式必须每两行一组，最后一条缺少密钥。':'Each entry needs two lines; the last entry is missing its key.','备注不能超过 200 个字符。':'Notes cannot exceed 200 characters.','密钥不能为空、包含空白或超过 2000 字节。':'Keys must be nonempty, contain no whitespace, and stay within 2000 bytes.','输入数量必须与已有条目数量一致。':'The input count must match the existing entry count.','未知的批量模式。':'Unknown batch mode.','粘贴文本过长。':'Pasted text is too long.','已有条目发生变化，请返回列表重新核对。':'Existing entries changed. Return to the list and review.','已识别':'Recognized','条':'entries','原备注':'Previous note','保留原备注':'Keep previous note','保留原密钥':'Keep previous key','开始替换':'Replace entries','开始新建':'Create entries','正在保存':'Saving','批量处理完成':'Batch completed','已完成':'Completed','保存失败，已停止。请返回列表核对后再处理剩余条目。':'Saving failed and stopped. Return to the list to review before processing the remaining entries.',
'有未保存的设置，离开后将丢弃。是否继续？':'Discard unsaved settings and leave?','启动模型路由':'Launch model router','模型路由':'Model router','配置供应商和密钥，选择软件实际调用的模型。':'Manage local API, providers and model mappings',
'打开原 App':'Open original app','正在连接模型路由…':'Connecting to model router…','启动服务':'Start server','停止服务':'Stop server','重启服务':'Restart server','复制地址':'Copy address','供应商':'Providers','调用名称':'Model mappings','模型别名':'Virtual routes','请求日志':'Request logs','路由设置':'Router settings',
'路由管理已连接':'Router management connected','模型路由尚未连接，请打开支持控制台集成的 Local Model Router。':'Router management is unavailable. Open the version of Local Model Router with console integration.',
'模型路由连接文件权限无效，请重新打开 Local Model Router。':'Invalid connection file permissions. Reopen Local Model Router.',
'模型路由连接信息无效，请重新打开 Local Model Router。':'Invalid connection information. Reopen Local Model Router.',
'今日请求':'Requests today','今日 Token':'Tokens today','成功 / 失败':'Success / failures','平均延迟':'Average latency','搜索路由内容':'Search router data',
'全部供应商':'All providers','暂未识别供应商':'Unresolved provider','请求数':'Requests','Token 总数':'Total tokens','当前范围：':'Range: ','筛选仅影响用量和请求日志，配置仍显示完整列表。':'Filters apply to usage and request logs; configuration lists stay complete.','当前范围暂无请求；可切换全部时间查看历史。':'No requests in this range. Switch to all time to view history.','查看全部时间':'View all time','当前范围内最近 300 条请求（用量汇总包含全部匹配记录）。':'Most recent 300 requests in this range; usage totals include every matching request.',
'添加供应商':'Add provider','添加模型':'Add model','名称 / 地址':'Name / address','密钥 / 策略':'Keys / strategy','优先级':'Priority','轮流使用':'Round robin','失败后换备用':'Failover only','连接测试':'Test connection','调用名称':'Local model ID','供应商模型名':'Upstream model','编辑供应商':'Edit provider','编辑模型':'Edit model',
'暂无供应商。添加供应商后，即可配置调用名称。':'No providers yet. Add a provider, then configure model mappings.',
'暂无调用名称。先添加供应商，再添加调用名称。':'No model mappings yet. Add a provider, then a local model ID.',
'没有匹配的条目。请修改搜索条件。':'No matching entries. Change the search.',
'供应商 / 实际模型':'Provider / upstream model','已停用':'Disabled','名称':'Name','API 地址':'Base URL','备注':'Note','密钥使用方式':'Key strategy','API 密钥（可选）':'API key (optional)','留空保留已有密钥；填写会更新第一把密钥。':'Leave empty to retain the key; entering a value updates the first key.',
'供应商名称和API 地址必填。':'Provider name and base URL are required.','请填写模型名称、本地 ID、供应商和供应商模型名。':'Enter a display name, local ID, provider and upstream model.',
'选择供应商':'Select provider','是否停止模型路由服务？现有 API 客户端将无法发出新请求。':'Stop the router? API clients will be unable to send new requests.',
'是否重启模型路由服务？现有连接可能中断。':'Restart the router? Existing connections may be interrupted.',
'删除供应商会同时删除其调用名称和密钥配置。是否继续？':'Deleting a provider also deletes its model mappings and key configuration. Continue?',
'是否删除此调用名称？':'Delete this model mapping?','是否清空所有请求日志？此操作不可恢复。':'Clear all request logs? This cannot be undone.',
'正在测试连接…':'Testing connection…','操作已完成':'Operation completed','复制成功':'Copied','复制失败，请手动选中复制。':'Could not copy. Select the text and copy manually.',
'路由服务':'Router server','监听端口':'Listen port','启动 App 时自动启动服务':'Start server when the app opens','关闭原 App 窗口后保持后台运行':'Keep running when the original app window closes','记录调试详情':'Record debug details','保存后端口将在下次启动或重启服务时生效。':'The port applies when the server is next started or restarted.',
'本地 API 密钥':'Local API key','密钥仅在主动显示或复制时读取，不会写入控制台记录。':'The key is read only when you reveal or copy it. It is not stored in console records.',
'显示密钥':'Reveal key','隐藏密钥':'Hide key','复制密钥':'Copy key','重新生成':'Regenerate','重新生成会使旧 API 密钥立即失效。是否继续？':'Regenerating immediately invalidates the old API key. Continue?',
'导出路由配置':'Export router configuration','默认只导出配置，不包含密钥。文件保存到下载文件夹。':'Configuration exports exclude secrets by default. Files are saved to Downloads.',
'包含供应商密钥':'Include provider secrets','导出文件将包含明文供应商密钥。是否继续？':'The export will contain plaintext provider secrets. Continue?',
'导出配置':'Export configuration','已导出到：':'Exported to: ','版本 / 数据位置':'Version / data location','已启用供应商 / 模型':'Enabled providers / models','模型用量':'Usage by model','供应商用量':'Usage by provider','请求数':'Requests','Token 总数':'Total tokens','错误数':'Errors','无真实请求记录。通过本地 API 发送请求后，这里会显示用量。':'No requests yet. Usage appears after requests reach the local API.',
'软件调用左侧名称时，会按右侧顺序选择实际模型。这里只查看已有配置。':'Virtual models are resolved by the existing router engine. This page shows configured routes; editing is not available yet.',
'操作':'Actions','失败时切换下一把密钥':'Switch to the next key on failure','固定使用首选密钥':'Always use the primary key','密钥在供应商列表的「密钥」里查看、添加和更新。':'View, add and update keys under “Keys” in the provider list.','密钥':'Keys','只使用排在第一位的已启用密钥。':'Only the first enabled key is used.','按顺序尝试；前一把失效、限流或供应商出错时自动换下一把。':'Keys are tried in order; the next one is used when a key is rejected, rate limited, or the upstream fails.','首选':'Primary','备注':'Note','例如：主账号 / 备用账号 / 到期日':'e.g. main account / backup / expiry date','已保存。点「显示」查看，或直接输入新密钥后保存':'Saved. Reveal it, or type a new key and save','显示':'Reveal','隐藏':'Hide','设为首选':'Make primary','这个供应商还没有密钥。':'This provider has no keys yet.','添加密钥':'Add key','添加':'Add','关闭':'Close','一键测速':'Test all keys','正在逐把测试…':'Testing each key…','把密钥可用':'keys usable','可用':'OK','密钥无效或已过期':'Invalid or expired','密钥被拒绝':'Rejected','已被限流':'Rate limited','连接上游失败或超时':'Upstream unreachable or timed out','找不到该供应商。':'Provider not found.','请输入密钥。':'Enter a key.','密钥已添加':'Key added','密钥已删除':'Key deleted','已保存':'Saved','再点一次确认删除':'Click again to delete','请确认':'Please confirm','继续':'Continue','已启用':'Enabled','编辑':'Edit','停用':'Disable','启用':'Enable','删除':'Delete',
'路由供应商':'Router providers','模型提供商':'Model providers','全部模型提供商':'All model providers','模型库':'Model catalog','只看最新版本':'Latest versions only','调用 ID':'Call ID','调用方式':'Call path','本区直连':'In-region direct','跨区调用':'Cross-region','文本':'Text','图片':'Image','音频':'Audio','视频':'Video','嵌入':'Embedding','输入':'Input','输出':'Output','流式输出':'Streaming output','分布':'Breakdown','版本阶段':'Lifecycle','全部':'All','可调用':'Callable','Bedrock 模型由 AWS 官方 API 自动发现；启用后才会出现在 Agent 的模型列表里。':'Bedrock models are discovered from official AWS APIs; only enabled ones appear to the Agent.','同步模型':'Sync models','同步价格':'Sync pricing','全部同步':'Sync all','正在同步…':'Syncing…','刷新列表':'Refresh list','还没有接入 Bedrock 供应商。先在「供应商」里把 base_url 指向 bedrock-runtime 端点。':'No Bedrock provider yet. Point a provider base URL at the bedrock-runtime endpoint under Providers.','模型':'Model','能力':'Features','上下文':'Context','输入':'Input','输出':'Output','缓存读':'Cache read','缓存写':'Cache write','推理':'Inference','状态':'Status','原生':'Native','系统 Profile':'System profile','应用 Profile':'Application profile','状态未知':'Unknown','新增':'New','已废弃':'Deprecated','已退市':'Unavailable','受限':'Restricted','当前':'Current','旧版':'Legacy','仅看启用':'Enabled only','仅看新增':'New only','隐藏旧版':'Hide legacy','隐藏已废弃':'Hide deprecated','同步报告':'Sync report','发现':'Discovered','新增':'Added','更新':'Updated','标记退市':'Marked unavailable','来源':'Source','价格条目':'Pricing entries','已写入':'Inserted','未变化':'Unchanged','有官方价格':'With official pricing','缺官方价格':'Missing official pricing','官方价格页':'Official pricing','暂无数据，先点「同步模型」。':'No data yet — run Sync models first.','同步已完成':'Sync finished','同步仍在进行…':'Sync still running…','全部启用会开放当前筛选内的全部模型给 Agent。是否继续？':'Enabling all opens every model in the current filter to the Agent. Continue?','缓存写':'Cache write','缓存读':'Cache read','AWS Bedrock 模型注册表：数据来自 AWS 官方 API 与官方价格文件，缺失信息显示为 —，不做任何推测。':'The AWS Bedrock registry comes from official AWS APIs and pricing files; missing data shows as — and is never guessed.','暂无模型别名配置。':'No virtual routes configured.','按顺序的目标模型':'Ordered target models','清空日志':'Clear logs','时间 / 请求':'Time / request','模型 / 供应商':'Model / provider','状态 / 耗时':'Status / latency','详情':'Details','暂无请求日志。':'No request logs yet.','模型路由返回超出窗口，未发送不完整数据。':'Router response exceeds the window. Incomplete data was not sent.',
'已启用，已同步到 ZCode':'Enabled, synced to ZCode','已停用，已同步到 ZCode':'Disabled, synced to ZCode','已启用，但 ZCode 同步失败':'Enabled, but ZCode sync failed','已停用，但 ZCode 同步失败':'Disabled, but ZCode sync failed',
'一键查额度':'Check quotas','查额度':'Quota','密钥额度汇总':'Key quota summary','包含已停用密钥':'Include disabled keys','重新查询':'Refresh','收起':'Collapse','正在查询已配置供应商的密钥额度…':'Querying configured provider key quotas…','查询额度失败。':'Failed to query quotas.','已配置供应商':'Configured providers','可用启用密钥':'Usable enabled keys','已检查密钥':'Checked keys','USD 可用总额':'Total USD available','余额':'Balance','日额':'Daily','Kiro 点数':'Kiro credits','可用 / 已查密钥':'Usable / checked keys','个已配置':'configured','个跳过':'skipped','不可用免费额度':'Non-spendable free credit','Backboard 免费额':'Backboard free credits','把启用可用':'enabled usable','启用合计':'Enabled total','存活去重':'Unique alive total','个重复账户':'duplicate accounts','# / 备注':'# / Note','剩余额度':'Remaining','耗时':'Latency','默认':'Default','重复账户':'Duplicate account','未配置（不支持查询真实余额）：':'Not configured (real balance unsupported): ','正在逐把查询额度…':'Querying each key quota…','已检查':'Checked','把':'keys','该供应商暂不支持查询密钥额度。':'Quota query is not configured for this provider.','密钥为空':'Secret is empty','余额已耗尽':'Balance exhausted','密钥无效或已停用（401）':'Key invalid or inactive (401)','密钥被拒绝或已停用（403）':'Key rejected or inactive (403)','已被限流（429）':'Rate limited (429)','仅使用基础额度':'Base quota only','不使用赠送额度；基础额度用完后后台标记为暂停并直接跳过，不禁用':'Do not spend bonus credits; when base quota is exhausted, mark paused in the background and skip directly without disabling','基础额度用完后已标记为暂停并直接跳过，不会禁用密钥':'Marked paused and skipped directly after base quota exhaustion without disabling keys','已暂停（基础额度用完）':'Paused (base quota exhausted)','已暂停':'Paused','后台已暂停（基础额度用完）':'Paused in background (base quota exhausted)','把已暂停':'paused','赠送未启用':'bonus unused','基础':'Base','赠送':'Bonus','已开启仅使用基础额度':'Base quota only enabled','已关闭仅使用基础额度':'Base quota only disabled'
}
JS = r'''
let routerQuota=null,routerQuotaLoading=false,routerQuotaIncludeDisabled=false,routerQuotaError='';
let routerData=null,routerTab='overview',routerQuery='',routerLoading=false,routerBusy=false,routerSettingsDirty=false,routerConnected=false,routerRequestSeq=0,routerReloadPending=false;
let routerPeriod='all',routerProvider='all',routerProviderItems=[{v:'all',l:'全部供应商'}];
const routerStrategies={priority:'失败时切换下一把密钥',fixed:'固定使用首选密钥',round_robin:'轮流使用',failover_only:'失败后换备用'},routerStrategyChoices=['priority','fixed'];
function routerNote(text,error=false){$('router-note').textContent=T(text);$('router-note').classList.toggle('error',error);}
function routerEnableNote(on,zs){const base=on?'已停用':'已启用';if(!zs||!(zs.accounts>0))return {text:base,error:false};return zs.ok?{text:base+'，已同步到 ZCode',error:false}:{text:base+'，但 ZCode 同步失败',error:true};}
async function routerCall(command,args={}){const d=await centerApi('router/action',{command,args});return d.result;}
function syncRouterFilters(){
 if(typeof periodItems==='undefined')return;
 const supplied=(routerData?.filters?.providerOptions||[]).map(x=>({v:String(x.value),l:x.value==='__unresolved_provider__'?T('暂未识别供应商'):(x.label||x.value)}));
 routerProviderItems=[{v:'all',l:T('全部供应商')},...supplied.filter(x=>x.v!=='all')];
 if(routerProvider!=='all'&&!routerProviderItems.some(x=>x.v===routerProvider))routerProviderItems.push({v:routerProvider,l:routerProvider});
 ddSync($('dd-router-period'),periodItems,routerPeriod);
 ddSync($('dd-router-provider'),routerProviderItems,routerProvider);
}
function initRouterFilters(){try{const p=localStorage.getItem('cg-router-period');if(['all','today','week','month'].includes(p))routerPeriod=p;const v=localStorage.getItem('cg-router-provider');if(typeof v==='string'&&v.length<=200)routerProvider=v||'all';}catch(e){}}
function setRouterFilters(period=routerPeriod,provider=routerProvider){
 if(period===routerPeriod&&provider===routerProvider)return;
 routerPeriod=period;routerProvider=provider;routerRequestSeq++;routerContentKey='';
 try{localStorage.setItem('cg-router-period',routerPeriod);localStorage.setItem('cg-router-provider',routerProvider);}catch(e){}
 syncRouterFilters();
 if(routerBusy){routerReloadPending=true;return;}
 loadRouter(true);
}
function drainRouterReload(){if(routerReloadPending&&!routerBusy&&!routerLoading){routerReloadPending=false;setTimeout(()=>loadRouter(true),0);}}
async function loadRouter(force=false){
 if(routerLoading){routerReloadPending=true;return null;}if(routerBusy)return null;routerLoading=true;
 const requestSeq=++routerRequestSeq,period=routerPeriod,provider=routerProvider;
 try{const params=new URLSearchParams({period,provider});const d=await centerApi('router?'+params.toString());
  if(requestSeq!==routerRequestSeq||period!==routerPeriod||provider!==routerProvider){routerReloadPending=true;return;}
  routerData=d;$('router-main').hidden=!d.connected;$('router-launch').hidden=d.connected;
  if(!d.connected){routerConnected=false;routerNote(d.message,true);return false;}
  // 仅在刚连上时提示；轮流使用不得覆盖连接测试、导出路径等操作结果。
  if(!routerConnected)routerNote('路由管理已连接');routerConnected=true;renderRouter(force);return true;
 }catch(e){if(requestSeq===routerRequestSeq)routerNote(e.message,true);return false;}finally{routerLoading=false;drainRouterReload();}
}
async function routerRun(command,args={},button=null){
 if(routerBusy)return;routerBusy=true;if(button)button.disabled=true;
 try{const result=await routerCall(command,args);routerNote('操作已完成');routerSettingsDirty=false;return result;}
 catch(e){routerNote(e.message,true);throw e;}
 finally{routerBusy=false;if(button)button.disabled=false;drainRouterReload();}
}

// Animate only deliberate disclosure/tab actions; polling never starts motion.
const routerMotionQuery=matchMedia('(prefers-reduced-motion: reduce)'),routerDisclosureStates=new WeakMap();
let routerTabMotionPending=false;
function routerTabEnter(){
 if(!routerTabMotionPending||!$('router-content').children.length)return;
 routerTabMotionPending=false;
 const content=$('router-content');content.getAnimations().forEach(a=>a.cancel());
 if(!routerMotionQuery.matches)content.animate([{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:180,easing:'ease-out'});
}
function routerDisclosure(details){
 const previous=routerDisclosureStates.get(details),next=previous?!previous.next:!details.open;
 const start=details.getBoundingClientRect().height;
 previous?.animation.cancel();
 const menu=details.classList.contains('bedrock-more'),target=menu?details.querySelector('.bedrock-more-menu'):details;
 const overflow=previous?previous.overflow:details.style.overflow;
 const finish=()=>{if(routerDisclosureStates.get(details)!==state)return;details.open=next;details.style.overflow=overflow;routerDisclosureStates.delete(details);};
 if(routerMotionQuery.matches||!target){details.open=next;details.style.overflow=overflow;routerDisclosureStates.delete(details);return;}
 details.open=next;const end=details.getBoundingClientRect().height;details.open=true;
 if(!menu)details.style.overflow='hidden';
 const frames=menu?[{opacity:next?0:1,transform:next?'translateY(-4px)':'none'},{opacity:next?1:0,transform:next?'none':'translateY(-4px)'}]:[{height:start+'px'},{height:end+'px'}];
 const animation=target.animate(frames,{duration:menu?150:220,easing:next?'cubic-bezier(.2,.75,.25,1)':'ease-in-out'});
 const state={next,animation,overflow};routerDisclosureStates.set(details,state);animation.onfinish=finish;
}
$('router-page').addEventListener('click',e=>{
 const summary=e.target.closest('summary');if(!summary)return;
 const details=summary.parentElement;
 if(!details.matches('.bedrock-filters,.bedrock-more,.bedrock-model-detail,.bedrock-cache'))return;
 e.preventDefault();routerDisclosure(details);
});
routerMotionQuery.addEventListener('change',()=>{if(routerMotionQuery.matches)$('router-page').getAnimations({subtree:true}).forEach(a=>{try{a.finish();}catch(e){a.cancel();}});});

function routerButton(label,action,id){return '<button type="button" data-router-action="'+action+'"'+(id!==undefined?' data-router-id="'+esc(id)+'"':'')+'>'+esc(T(label))+'</button>';}
function routerEmpty(text){return '<p class="router-empty">'+esc(T(text))+'</p>';}
function routerTable(head,rows,id){return '<div class="router-table"><table><thead><tr>'+head.map(h=>'<th>'+esc(T(h))+'</th>').join('')+'</tr></thead><tbody'+(id?' id="'+id+'"':'')+'>'+rows.join('')+'</tbody></table></div>';}
function routerFiltered(rows){const q=routerQuery.toLocaleLowerCase();return rows.filter(r=>!q||JSON.stringify(r).toLocaleLowerCase().includes(q));}
function routerBadge(enabled){return '<span class="router-badge'+(enabled?' on':'')+'">'+esc(T(enabled?'已启用':'已停用'))+'</span>';}
function routerKiroUrl(raw){try{const u=new URL(String(raw||'').trim());return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&!u.search&&!u.hash&&(u.pathname==='/'||u.pathname==='')&&(u.hostname==='q.us-east-1.amazonaws.com'||u.hostname==='q.eu-central-1.amazonaws.com');}catch(e){return false;}}
function routerIsKiro(p){return !!p&&routerKiroUrl(p.baseUrl);}
function routerPausedBadge(count,total,title=''){return count>0?'<span class="router-badge warn"'+(title?' title="'+esc(T(title))+'"':'')+'>'+esc(T('已暂停（基础额度用完）'))+(total!=null?' '+num(count)+'/'+num(total):'')+'</span>':'';}
function routerProviderStatus(p){return '<div class="router-state">'+routerBadge(p.enabled)+routerPausedBadge(p.pausedKeyCount||0,p.enabledKeyCount??p.keyCount,'基础额度用完后已标记为暂停并直接跳过，不会禁用密钥')+'</div>';}
function routerControls(add='',clear=false){return '<div class="router-tools"><label>'+esc(T('搜索路由内容'))+'<input id="router-search" type="search" value="'+esc(routerQuery)+'"></label><div class="router-actions">'+(add==='添加供应商'?routerButton('一键查额度','quota-all'):'')+(add?routerButton(add,add==='添加供应商'?'add-provider':'add-model'):'')+(clear?routerButton('清空日志','clear-logs'):'')+'</div></div>';}
function renderRouter(force=false){
 if(!routerData?.connected)return;const d=routerData,s=d.dashboard.server,t=d.dashboard.usage.today;
 syncRouterFilters();
 $('router-main').dataset.tab=routerTab;
 $('router-status').textContent=T(s.running?'运行中':'已停止');$('router-status').classList.toggle('on',s.running);$('router-address').textContent=s.baseUrl;
 $('router-start').disabled=s.running;$('router-stop').disabled=!s.running;$('router-restart').disabled=!s.running;
 const periods={all:'全部时间',today:'今天',week:'本周',month:'本月'},providerLabel=routerProviderItems.find(x=>x.v===routerProvider)?.l||routerProvider;
 $('router-scope-note').textContent=t.requests===0&&routerPeriod!=='all'?T('当前范围暂无请求；可切换全部时间查看历史。'):T('当前范围：')+T(periods[routerPeriod]||routerPeriod)+' · '+providerLabel+'。'+T('筛选仅影响用量和请求日志，配置仍显示完整列表。');
 $('router-show-all').hidden=routerPeriod==='all'||t.requests>0;$('router-show-all').textContent=T('查看全部时间');
 reconcile($('router-stats'),[['请求数',num(t.requests),T('成功 / 失败')+' '+num(t.success)+' / '+num(t.failures),t.requests,'num'],['Token 总数',t.requests>0&&t.measuredRequests===0?T('Token 未提供'):num(t.totalTokens),num(t.inputTokens)+' → '+num(t.outputTokens)+(t.measuredRequests<t.requests?' · '+T('部分请求未提供 Token'):'')+(typeof t.kiroCredits==='number'?' · '+t.kiroCredits.toFixed(6)+' credits':''),t.totalTokens,t.requests>0&&t.measuredRequests===0?'':'num'],['已启用供应商 / 模型',num(d.dashboard.activeProviders)+' / '+num(d.dashboard.activeModels),''],['平均延迟',num(Math.round(t.avgLatencyMs))+' ms','',Math.round(t.avgLatencyMs),'msu']].map((x,i)=>'<div class="router-stat" data-k="s'+i+'"><span>'+esc(T(x[0]))+'</span><b'+(x[4]?dnA(x[3],x[4]):'')+'>'+(i===2?'<span'+dnA(d.dashboard.activeProviders,'num')+'>'+num(d.dashboard.activeProviders)+'</span> / <span'+dnA(d.dashboard.activeModels,'num')+'>'+num(d.dashboard.activeModels)+'</span>':esc(x[1]))+'</b><small>'+esc(x[2])+'</small></div>').join(''));
 document.querySelectorAll('[data-router-tab]').forEach(b=>{b.classList.toggle('on',b.dataset.routerTab===routerTab);b.setAttribute('aria-selected',b.dataset.routerTab===routerTab?'true':'false');});
 renderRouterContent(force);
 if(routerTab!=='bedrock')routerTabEnter();
}
// 模型状态：只读展示 ContextGate 侧动态能力注册表；轮流使用只做 reconcile，不触发动画。
let routerCaps=null,routerCapsSeq=0;
const routerCapStatus={available:['可用','on'],degraded:['降级','warn'],timeout:['超时','bad'],retired:['已下线','bad'],missing_key:['缺密钥','bad'],unavailable:['不可用','bad'],unknown:['未知','']};
const routerCapKinds={ok:'成功',gone:'已下线（410）',missing_key:'缺密钥',timeout:'超时',rate_limited:'限流（429）',auth:'密钥无效（401）',forbidden:'无权限（403）',not_found:'模型不存在（404）',client_error:'请求参数错误',network:'连接上游失败',upstream_error:'上游错误（5xx）',router_unavailable:'路由不可达',error:'其他错误'};
function routerCapMs(v){return v==null?'—':v>=1000?(v/1000).toFixed(v>=10000?0:1)+' s':Math.round(v)+' ms';}
function routerCapTime(ts){return ts?new Date(ts).toLocaleString(LOCALE()):'—';}
async function loadCapabilities(force=false){
 if(routerTab!=='capabilities')return;
 if(routerCaps&&!$('router-caps-table'))renderCapabilities(true);
 const seq=++routerCapsSeq;
 try{const d=await centerApi('router/capabilities');if(seq!==routerCapsSeq||routerTab!=='capabilities')return;routerCaps=d;renderCapabilities(!$('router-caps-table'));}
 catch(e){if(seq===routerCapsSeq)routerNote(e.message,true);}
}
function routerCapRow(r){
 const st=routerCapStatus[r.status]||[r.status,''],w=r.window||{},e=r.lastError,p=r.price;
 const err=e?esc(T(routerCapKinds[e.kind]||e.kind))+(e.status?' · '+esc(e.status):'')+'<small>'+esc(e.message||'')+'</small><small>'+esc(routerCapTime(e.at))+(e.source==='probe'?' · '+esc(T('检查')):'')+'</small>':'—';
 const price=p?esc(p.input??'—')+' / '+esc(p.output??'—')+'<small>'+esc(p.currency||'')+' / '+esc(T('百万 tokens'))+'</small>':esc(T('未知'));
 const tools=r.toolCalls==='supported'?'支持':r.toolCalls==='unsupported'?'不支持':'未知';
 const probe=r.probe?esc(routerCapTime(r.probe.lastAt))+'<small>'+esc(T(routerCapKinds[r.probe.kind]||r.probe.kind))+' · '+esc(routerCapMs(r.probe.latencyMs))+'</small>':esc(T('未检查'));
 return '<tr><td>'+esc(r.model)+'<small>'+esc(r.platform||'—')+(r.upstreamModel&&r.upstreamModel!==r.model?' · '+esc(r.upstreamModel):'')+'</small></td>'
  +'<td><span class="router-badge '+st[1]+'">'+esc(T(st[0]))+'</span>'+(r.enabled?'':'<small>'+esc(T('已停用'))+'</small>')+'</td>'
  +'<td class="number">'+esc(routerCapMs(w.p50Ms))+' / '+esc(routerCapMs(w.p95Ms))+'<small>'+esc(T('成功样本'))+' '+num(w.latencySamples||0)+'</small></td>'
  +'<td class="number">'+(w.errorRate==null?'—':esc((w.errorRate*100).toFixed(1))+'%')+'<small>'+num(w.failures||0)+' / '+num(w.requests||0)+'</small></td>'
  +'<td>'+err+'</td><td>'+price+'</td><td>'+esc(T('工具调用'))+' '+esc(T(tools))+'<small>Responses '+esc(T(r.responsesApi==='supported'?'支持':'未知'))+'</small></td><td>'+probe+'</td></tr>';
}
function renderCapabilities(force=false){
 const d=routerCaps,content=$('router-content');if(!d||routerTab!=='capabilities')return;
 const order={available:0,degraded:1,timeout:2,missing_key:3,unavailable:4,retired:5,unknown:6};
 const records=routerFiltered(d.records||[]).slice().sort((a,b)=>(b.enabled-a.enabled)||((order[a.status]??9)-(order[b.status]??9))||String(a.platform).localeCompare(String(b.platform))||String(a.model).localeCompare(String(b.model)));
 const c=d.counts||{},router=d.router,fb=d.fallback,down=(c.timeout||0)+(c.missing_key||0)+(c.unavailable||0)+(c.retired||0);
 const summary=esc(T('近'))+' '+esc(d.windowDays)+' '+esc(T('天'))+' · '+esc(T('可用'))+' '+num(c.available||0)+' · '+esc(T('降级'))+' '+num(c.degraded||0)+' · '+esc(T('不可用'))+' '+num(down)+' · '+esc(T('未知'))+' '+num(c.unknown||0)
  +'<br>'+esc(T('路由端口'))+' '+esc(T(router?(router.reachable?'可达':'不可达'):'未检查'))+' · '+esc(T('直连备用'))+' '+esc(T(fb?(fb.available?'可用':'不可用'):'未检查'))+(fb&&fb.message?' · '+esc(T(fb.message)):'')
  +(d.error?'<br><span style="color:var(--bad)">'+esc(T(d.error))+'</span>':'');
 const table=records.length?routerTable(['平台 / 模型','状态','耗时 P50 / P95','错误率','最后错误','价格（输入 / 输出）','能力','最近检查'],records.map(routerCapRow)):routerEmpty((d.records||[]).length?'没有匹配的条目。请修改搜索条件。':'暂无能力记录。');
 if(!force&&$('router-caps-table')&&content.contains($('router-caps-table'))){reconcile($('router-caps-summary'),summary);reconcile($('router-caps-table'),table);return;}
 content.innerHTML=routerControls('',false)+'<p class="router-help">'+esc(T('只读统计路由器 router.db 的请求记录；主动检查默认关闭，每次检查都会消耗供应商额度。价格只取模型钱包目录中同平台的官方价，未知不推算；工具调用与 Responses 没有实测证据时标为未知。'))+'</p><p class="router-help" id="router-caps-summary" role="status">'+summary+'</p><div id="router-caps-table">'+table+'</div>';
 $('router-search').oninput=e=>{routerQuery=e.target.value;renderCapabilities();};
 routerTabEnter();
}
let routerContentKey='';
function routerUsageCell(tokens,measured,credits){
 const label=measured===0?esc(T('Token 未提供')):nsp(tokens,'num',num(tokens));
 return label+(typeof credits==='number'?'<small>'+esc(credits.toFixed(6))+' credits</small>':'');
}
function renderRouterContent(force=false){
 const d=routerData,content=$('router-content');if(!d?.connected)return;
 if(routerTab==='capabilities'){loadCapabilities(force);return;}
 const key=routerTab+'|'+routerQuery+'|'+JSON.stringify(routerTab==='providers'?d.providers:routerTab==='models'?d.models:routerTab==='logs'?d.logs:routerTab==='routes'?d.aliases:routerTab==='settings'?[d.settings,d.info]:d.dashboard.usage);
 // Preserve focused controls, an open log, and a settings draft during polling.
 if(!force&&(key===routerContentKey||content.contains(document.activeElement)||content.querySelector('details[open]')))return;
 if(routerTab==='settings'&&$('router-settings-form')&&!force)return;
 routerContentKey=key;
 if(routerTab==='settings'){
  if(routerSettingsDirty&&$('router-settings-form'))return;
  const s=d.settings;
  content.innerHTML='<div class="router-settings"><form id="router-settings-form" class="router-setting-card"><h3>'+T('路由服务')+'</h3><label class="router-field">'+T('监听端口')+'<input name="port" type="number" min="1024" max="65535" required value="'+s.port+'"></label>'+[['autostartServer','启动 App 时自动启动服务'],['backgroundOnClose','关闭原 App 窗口后保持后台运行'],['debugLogging','记录调试详情']].map(x=>'<label><input name="'+x[0]+'" type="checkbox"'+(s[x[0]]?' checked':'')+'>'+esc(T(x[1]))+'</label>').join('')+'<p>'+T('保存后端口将在下次启动或重启服务时生效。')+'</p><button type="submit">'+T('保存')+'</button></form><div class="router-setting-card"><h3>'+T('本地 API 密钥')+'</h3><p>'+T('密钥仅在主动显示或复制时读取，不会写入控制台记录。')+'</p><div class="router-key"><input id="router-local-key" type="password" readonly aria-label="'+T('本地 API 密钥')+'" value="" autocomplete="off"><button type="button" data-router-action="reveal-key">'+T('显示密钥')+'</button></div><div class="router-actions" style="margin-top:16px">'+routerButton('复制密钥','copy-key')+routerButton('重新生成','regenerate-key')+'</div></div><div class="router-setting-card"><h3>'+T('导出路由配置')+'</h3><p>'+T('默认只导出配置，不包含密钥。文件保存到下载文件夹。')+'</p><label><input id="router-export-secrets" type="checkbox">'+T('包含供应商密钥')+'</label>'+routerButton('导出配置','export')+'</div><div class="router-setting-card"><h3>'+T('版本 / 数据位置')+'</h3><p>'+esc(d.info.version)+'</p><p>'+esc(d.info.dbPath)+'</p><p>'+esc(d.info.keychainService)+'</p></div></div>';
  $('router-settings-form').oninput=()=>routerSettingsDirty=true;
  $('router-settings-form').onsubmit=async e=>{e.preventDefault();const f=e.target;try{await routerRun('update_settings',{port:Number(f.elements.port.value),autostartServer:f.elements.autostartServer.checked,backgroundOnClose:f.elements.backgroundOnClose.checked,debugLogging:f.elements.debugLogging.checked},f.querySelector('button'));routerContentKey='';$('router-content').replaceChildren();await loadRouter(true);}catch(e){}};
  return;
 }
 if(routerTab==='bedrock'){loadBedrock();return;}
 const tables=()=>{
  if(routerTab==='providers'){const rows=routerFiltered(d.providers);return rows.length?routerTable(['名称 / 地址','密钥 / 策略','状态','操作'],rows.map(p=>'<tr><td>'+esc(p.name)+'<small>'+esc(p.baseUrl)+'</small><small>'+esc(p.note)+'</small>'+(routerIsKiro(p)?'<label class="router-kiro-toggle" title="'+esc(T('不使用赠送额度；基础额度用完后后台标记为暂停并直接跳过，不禁用'))+'"><input type="checkbox" data-router-base-only="'+p.id+'"'+(p.baseQuotaOnly?' checked':'')+'><span>'+esc(T('仅使用基础额度'))+'</span></label>':'')+'</td><td>'+num(p.keyCount)+'<small>'+esc(T(routerStrategies[p.keyStrategy]||p.keyStrategy))+'</small></td><td>'+routerProviderStatus(p)+'</td><td><div class="router-actions">'+routerButton('编辑','edit-provider',p.id)+routerButton('密钥','keys-provider',p.id)+(p.quotaSupported?routerButton('查额度','quota-provider',p.id):'')+routerButton(p.enabled?'停用':'启用','toggle-provider',p.id)+routerButton('连接测试','test-provider',p.id)+routerButton('一键测速','speed-provider',p.id)+routerButton('删除','delete-provider',p.id)+'</div></td></tr>')):routerEmpty(d.providers.length?'没有匹配的条目。请修改搜索条件。':'暂无供应商。添加供应商后，即可配置调用名称。');}
  if(routerTab==='models'){const rows=routerFiltered(d.models);return rows.length?routerTable(['调用名称','供应商 / 实际模型','状态','操作'],rows.map(m=>'<tr><td>'+esc(m.modelId)+'<small>'+esc(m.displayName)+'</small></td><td>'+esc(m.providerName)+'<small>'+esc(m.upstreamModel)+'</small></td><td>'+routerBadge(m.enabled&&m.providerEnabled)+'</td><td><div class="router-actions">'+routerButton('编辑','edit-model',m.id)+routerButton(m.enabled?'停用':'启用','toggle-model',m.id)+routerButton('删除','delete-model',m.id)+'</div></td></tr>')):routerEmpty(d.models.length?'没有匹配的条目。请修改搜索条件。':'暂无调用名称。先添加供应商，再添加调用名称。');}
  const rows=routerFiltered(d.logs);return rows.length?routerTable(['时间 / 请求','模型 / 供应商','状态 / 耗时','Token 总数','详情'],rows.map(l=>'<tr><td>'+esc(new Date(l.ts).toLocaleString(LOCALE()))+'<small>'+esc(l.endpoint)+(l.isStream?' · SSE':'')+'</small></td><td>'+esc(l.requestedModel)+'<small>'+esc(l.resolvedModel||'—')+' / '+esc(l.providerName||'—')+'</small>'+(l.fallbackFrom?'<small>'+esc(l.fallbackFrom)+' → '+esc(l.resolvedModel||'—')+'</small>':'')+'</td><td>'+num(l.status)+'<small>'+num(l.latencyMs)+' ms</small></td><td class="number">'+routerUsageCell(l.totalTokens,l.totalTokens==null?0:1,l.kiroCredits)+'</td><td><details><summary>'+T('详情')+'</summary><pre>'+esc(JSON.stringify({input:l.promptTokens,output:l.completionTokens,cached:l.cachedTokens,cacheCreation:l.cacheCreationTokens,kiroCredits:l.kiroCredits,contextUsagePercent:l.contextUsagePercent,error:l.error,debug:l.debug},null,2))+'</pre></details></td></tr>')):routerEmpty(d.logs.length?'没有匹配的条目。请修改搜索条件。':'暂无请求日志。');
 };
 if(['providers','models','logs'].includes(routerTab)){
  const previous=$('router-search'),focused=previous===document.activeElement,start=previous?.selectionStart;
  content.innerHTML=routerControls(routerTab==='providers'?'添加供应商':routerTab==='models'?'添加模型':'',routerTab==='logs')+(routerTab==='providers'?routerQuotaPanelHtml():'')+(routerTab==='logs'?'<p class="router-help">'+T('当前范围内最近 300 条请求（用量汇总包含全部匹配记录）。')+'</p>':'')+tables();
  $('router-search').oninput=e=>{routerQuery=e.target.value;renderRouterContent(true);};
  if(routerTab==='providers'){
   content.querySelectorAll('[data-router-action=quota-all]').forEach(btn=>btn.disabled=routerQuotaLoading);
   const qd=$('router-quota-disabled');if(qd)qd.onchange=e=>{routerQuotaIncludeDisabled=e.target.checked;routerQueryAllQuotas();};
  }
  if(focused){$('router-search').focus();try{$('router-search').setSelectionRange(start,start);}catch(e){}}
  return;
 }
 if(routerTab==='routes'){content.innerHTML='<p class="router-help">'+T('软件调用左侧名称时，会按右侧顺序选择实际模型。这里只查看已有配置。')+'</p>'+(d.aliases.length?routerTable(['调用名称','按顺序的目标模型'],d.aliases.map(a=>'<tr><td>'+esc(a.aliasId)+'</td><td>'+a.targets.map(esc).join(' → ')+'</td></tr>')):routerEmpty('暂无模型别名配置。'));return;}
 const u=d.dashboard.usage,mrows=u.byModel.map(m=>'<tr data-k="'+esc(m.model)+'"><td>'+esc(m.model)+'</td><td class="number">'+nsp(m.requests,'num',num(m.requests))+'</td><td class="number">'+routerUsageCell(m.inputTokens+m.outputTokens,m.measuredRequests,m.kiroCredits)+'</td><td class="number">'+nsp(m.errors,'num',num(m.errors))+'</td></tr>'),prows=u.byProvider.map(p=>'<tr data-k="'+esc(p.provider)+'"><td>'+esc(p.provider)+'</td><td class="number">'+nsp(p.requests,'num',num(p.requests))+'</td><td class="number">'+routerUsageCell(p.tokens,p.measuredRequests,p.kiroCredits)+'</td><td class="number">'+nsp(p.errors,'num',num(p.errors))+'</td></tr>'),um=$('router-um'),up=$('router-up');
 if(um&&up&&content.contains(um)&&content.contains(up)&&mrows.length&&prows.length){reconcile(um,mrows.join(''));reconcile(up,prows.join(''));return;}
 content.innerHTML='<div class="router-settings"><div><h3>'+T('模型用量')+'</h3>'+(u.byModel.length?routerTable(['模型','请求数','Token 总数','错误数'],mrows,'router-um'):routerEmpty('无真实请求记录。通过本地 API 发送请求后，这里会显示用量。'))+'</div><div><h3>'+T('供应商用量')+'</h3>'+(u.byProvider.length?routerTable(['供应商','请求数','Token 总数','错误数'],prows,'router-up'):routerEmpty('无真实请求记录。通过本地 API 发送请求后，这里会显示用量。'))+'</div></div>';
}
function routerQuotaFmt(v,unit){if(v==null||Number.isNaN(Number(v)))return '—';const n=Number(v);return unit==='USD'?'$'+n.toFixed(4):n.toFixed(2)+' '+(unit||'credits');}
function routerQuotaPanelHtml(){
 if(!routerQuota&&!routerQuotaLoading&&!routerQuotaError)return '';
 const hdr='<div class="router-quota-head"><h3>'+esc(T('密钥额度汇总'))+'</h3><div class="router-quota-actions"><label><input type="checkbox" id="router-quota-disabled"'+(routerQuotaIncludeDisabled?' checked':'')+(routerQuotaLoading?' disabled':'')+'>'+esc(T('包含已停用密钥'))+'</label>'+routerButton('重新查询','quota-all')+routerButton('收起','quota-close')+'</div></div>';
 if(routerQuotaLoading)return '<div id="router-quota-panel" class="router-quota-panel">'+hdr+'<div class="router-quota-summary">'+esc(T('正在查询已配置供应商的密钥额度…'))+'</div></div>';
 if(routerQuotaError)return '<div id="router-quota-panel" class="router-quota-panel">'+hdr+'<div class="router-quota-summary error">'+esc(T(routerQuotaError))+'</div></div>';
 const d=routerQuota,t=d.totals;
 const summary=esc(T('已配置供应商'))+' '+num(t.supportedProviders)+' · '+esc(T('可用启用密钥'))+' '+num(t.usableKeys)+' · '+esc(T('已检查密钥'))+' '+num(t.checkedKeys)+' · '+esc(new Date(d.checkedAt).toLocaleTimeString(LOCALE()));
 const kiroBonusNote=(t.extraBonusCredits||0)>0?'credits · '+esc(T('赠送未启用'))+' '+Number(t.extraBonusCredits).toFixed(2):'credits';
 const cards='<div class="router-stats">'
  +'<div class="router-stat"><span>'+esc(T('USD 可用总额'))+'</span><b>$'+Number(t.usdAvailable||0).toFixed(4)+'</b><small>'+esc(T('余额'))+' $'+Number(t.usdBalance||0).toFixed(4)+' · '+esc(T('日额'))+' $'+Number(t.usdDaily||0).toFixed(2)+'</small></div>'
  +'<div class="router-stat"><span>'+esc(T('Kiro 点数'))+'</span><b>'+Number(t.kiroCredits||0).toFixed(2)+'</b><small>'+kiroBonusNote+'</small></div>'
  +'<div class="router-stat"><span>'+esc(T('可用 / 已查密钥'))+'</span><b>'+num(t.usableKeys)+' / '+num(t.checkedKeys)+'</b><small>'+num(t.supportedProviders)+' '+esc(T('个已配置'))+' · '+num(t.unsupportedProviders)+' '+esc(T('个跳过'))+'</small></div>'
  +'<div class="router-stat"><span>'+esc(T('不可用免费额度'))+'</span><b>$'+Number(t.extraFreeUsd||0).toFixed(2)+'</b><small>'+esc(T('Backboard 免费额'))+'</small></div>'
  +'</div>';
 const providers=(d.providers||[]).map(rep=>{
  const meta=esc(T('启用合计'))+' '+esc(routerQuotaFmt(rep.enabledTotal,rep.unit))
   +(rep.allAliveTotal!==rep.enabledTotal?' · '+esc(T('存活去重'))+' '+esc(routerQuotaFmt(rep.allAliveTotal,rep.unit)):'')
   +((rep.extraBonusCredits||0)>0?' · '+esc(T('赠送未启用'))+' '+Number(rep.extraBonusCredits).toFixed(2)+' credits':'')
   +(rep.duplicateAccounts?' · '+num(rep.duplicateAccounts)+' '+esc(T('个重复账户')):'');
  const krows=(rep.keys||[]).map(k=>{
   const badge=!k.ok?'<span class="router-badge bad">✗</span>':k.paused?'<span class="router-badge warn">'+esc(T('已暂停'))+'</span>':(k.remaining||0)<=0?'<span class="router-badge warn">!</span>':'<span class="router-badge on">'+(k.duplicateAccount?'≈':'✓')+'</span>';
   const remTxt=k.remaining!=null?esc(routerQuotaFmt(k.remaining,k.unit))+(k.duplicateAccount?' <small>'+esc(T('重复账户'))+'</small>':''):'—';
   const stateHtml='<div class="router-state">'+routerBadge(k.enabled)+(k.paused?'<span class="router-badge warn">'+esc(T('已暂停（基础额度用完）'))+'</span>':'')+'</div>';
   return '<tr><td>#'+num(k.id)+' '+esc(k.label||T('默认'))+'</td><td>'+stateHtml+'</td><td class="number">'+remTxt+'</td><td>'+badge+' '+esc(T(k.message))+'</td><td class="number">'+(k.latencyMs!=null?num(k.latencyMs)+' ms':'—')+'</td></tr>';
  });
  return '<details class="router-quota-provider"><summary><span class="router-state"><b>'+esc(rep.providerName)+'</b> <span class="router-badge'+(rep.usableCount?' on':'')+'">'+num(rep.usableCount)+'/'+num(rep.enabledChecked)+' '+esc(T('把启用可用'))+'</span>'+(rep.pausedCount>0?' <span class="router-badge warn">'+num(rep.pausedCount)+' '+esc(T('把已暂停'))+'</span>':'')+'</span><small>'+meta+'</small></summary>'+(krows.length?routerTable(['# / 备注','状态','剩余额度','详情','耗时'],krows):routerEmpty('这个供应商还没有密钥。'))+'</details>';
 }).join('');
 const skip=d.unsupportedProviders?.length?'<p class="router-quota-skip">'+esc(T('未配置（不支持查询真实余额）：'))+esc(d.unsupportedProviders.map(x=>x.name).join('、'))+'</p>':'';
 return '<div id="router-quota-panel" class="router-quota-panel">'+hdr+'<div class="router-quota-summary ok">'+summary+'</div>'+cards+'<div class="router-quota-list">'+providers+'</div>'+skip+'</div>';
}
async function routerQueryAllQuotas(){
 if(routerQuotaLoading)return;
 routerQuotaLoading=true;routerQuotaError='';if(routerTab==='providers')renderRouterContent(true);
 try{routerQuota=await routerCall('query_all_quotas',{includeDisabled:routerQuotaIncludeDisabled});}
 catch(err){routerQuotaError=err.message||'查询额度失败。';}
 finally{routerQuotaLoading=false;if(routerTab==='providers')renderRouterContent(true);}
}
// 原生壳不支持浏览器自带的 confirm()，统一用页面内对话框确认。
dialogCancelAnimation($('router-dialog'));
function routerConfirm(text){return new Promise(resolve=>{const d=$('router-dialog');$('router-form-title').textContent=T('请确认');
 $('router-form').innerHTML='<p>'+esc(T(text))+'</p><div class="router-actions"><button type="button" id="router-confirm-no">'+T('取消')+'</button><button type="submit">'+T('继续')+'</button></div>';
 let settled=false;const done=ok=>{if(settled)return;settled=true;d.removeEventListener('close',onClose);dialogClose(d,()=>resolve(ok));};const onClose=()=>{if(!settled){settled=true;resolve(false);}};
 $('router-form').onsubmit=e=>{e.preventDefault();done(true);};$('router-confirm-no').onclick=()=>done(false);
 d.addEventListener('close',onClose,{once:true});dialogOpen(d);});}
// 密钥管理：一个供应商可挂多把密钥；值默认隐藏，仅在点「显示」时向路由器读取。
let routerKeyProvider=0;const routerRevealed=new WeakMap();
async function routerKeys(pid,message=''){
 $('router-form').oninput=null;$('router-form').onchange=null;
 routerKeyProvider=pid;const p=routerData.providers.find(x=>x.id===pid);if(!p)return;
 const keys=await routerCall('list_provider_keys',{providerId:pid}),fixed=p.keyStrategy==='fixed';
 $('router-form-title').textContent=T('密钥')+' · '+p.name;
 $('router-form').innerHTML='<div class="router-actions"><button type="button" id="router-keys-batch-top">'+T('批量添加')+'</button>'+(p.quotaSupported?'<button type="button" id="router-keys-quota-top">'+T('一键查额度')+'</button>':'')+'<button type="button" id="router-keys-speed-top">'+T('一键测速')+'</button></div><div id="router-form-status-top" class="router-form-error" role="status" aria-live="polite">'+esc(T(message))+'</div><p class="router-help">'+esc(T(routerStrategies[p.keyStrategy]||p.keyStrategy))+' · '+T(fixed?'只使用排在第一位的已启用密钥。':'按顺序尝试；前一把失效、限流或供应商出错时自动换下一把。')+'</p>'
  +(routerIsKiro(p)?'<div class="router-kiro-box"><label class="check"><input type="checkbox" id="router-keys-base-only"'+(p.baseQuotaOnly?' checked':'')+'>'+esc(T('仅使用基础额度'))+'</label><small>'+esc(T('不使用赠送额度；基础额度用完后后台标记为暂停并直接跳过，不禁用'))+'</small></div>':'')
  +(keys.length?keys.map((k,i)=>'<div class="router-key-row" data-key="'+k.id+'"><div class="router-key-head"><b>#'+(i+1)+'</b>'+(i===0?'<span class="router-badge on">'+T('首选')+'</span>':'')+routerBadge(k.enabled)+(k.paused?'<span class="router-badge warn paused-tag">'+esc(T('后台已暂停（基础额度用完）'))+'</span>':'')+(routerIsKiro(p)&&k.baseRemaining!=null?'<span class="router-badge quota">'+esc(T('基础'))+' '+Number(k.baseRemaining).toFixed(2)+(k.bonusRemaining!=null&&k.bonusRemaining>0?' · '+esc(T('赠送'))+' '+Number(k.bonusRemaining).toFixed(2):'')+'</span>':'')+'</div>'
   +'<label>'+T('备注')+'<input data-key-note maxlength="200" value="'+esc(k.label)+'" placeholder="'+esc(T('例如：主账号 / 备用账号 / 到期日'))+'"></label>'
   +(k.hasSecret===false?'<span class="router-badge">'+T('待补密钥')+'</span>':'')
   +'<label>'+T('密钥')+'<div class="router-key"><input data-key-value type="password" autocomplete="off" placeholder="'+esc(T(k.hasSecret===false?'待补密钥，填写后保存':'已保存。点「显示」查看，或直接输入新密钥后保存'))+'"><button type="button" data-key-act="reveal"'+(k.hasSecret===false?' disabled':'')+'>'+T('显示')+'</button></div></label>'
   +'<div class="router-actions"><button type="button" data-key-act="save">'+T('保存')+'</button>'+(i?'<button type="button" data-key-act="primary">'+T('设为首选')+'</button>':'')+'<button type="button" data-key-act="toggle">'+T(k.enabled?'停用':'启用')+'</button><button type="button" data-key-act="delete">'+T('删除')+'</button></div></div>').join(''):routerEmpty('这个供应商还没有密钥。'))
  +'<div class="router-key-row"><div class="router-key-head"><b>'+T('添加密钥')+'</b><span style="flex:1"></span><button type="button" id="router-keys-batch">'+T('批量添加')+'</button></div><label>'+T('备注')+'<input id="router-key-new-note" maxlength="200" placeholder="'+esc(T('例如：主账号 / 备用账号 / 到期日'))+'"></label><label>'+T('密钥')+'<input id="router-key-new" type="password" autocomplete="new-password"></label><div class="router-actions"><button type="submit">'+T('添加')+'</button></div></div>'
  +'<div id="router-form-error" class="router-form-error" role="alert">'+esc(T(message))+'</div><div class="router-actions">'+(p.quotaSupported?'<button type="button" id="router-keys-quota">'+T('一键查额度')+'</button>':'')+'<button type="button" id="router-keys-speed">'+T('一键测速')+'</button><button type="button" id="router-form-cancel">'+T('关闭')+'</button></div>';
 $('router-form').dataset.keys=JSON.stringify(keys.map(k=>({id:k.id,enabled:k.enabled})));
 $('router-form-cancel').onclick=()=>dialogClose($('router-dialog'));
 $('router-keys-batch').onclick=()=>routerBatchKeys(pid,keys);
 $('router-keys-batch-top').onclick=()=>routerBatchKeys(pid,keys);
 const kbo=$('router-keys-base-only');
 if(kbo)kbo.onchange=async e=>{const en=e.target.checked;kbo.disabled=true;try{await routerCall('set_provider_base_quota_only',{providerId:pid,enabled:en});await routerKeysDone(pid,en?'已开启仅使用基础额度':'已关闭仅使用基础额度');}catch(err){kbo.checked=!en;if(kbo.isConnected)kbo.disabled=false;setKeysStatus(T(err.message));}};
 const setKeysStatus=(text,ok=false)=>{for(const el of [$('router-form-error'),$('router-form-status-top')]){if(!el)continue;el.classList.toggle('ok',ok);el.textContent=text;}};
 const runQuota=async()=>{const btns=[$('router-keys-quota'),$('router-keys-quota-top')].filter(Boolean);btns.forEach(x=>x.disabled=true);setKeysStatus(T('正在逐把查询额度…'));
  try{const rep=await routerCall('query_provider_quotas',{providerId:pid,includeDisabled:true});
   for(const r of (rep.keys||[])){const row=$('router-form').querySelector('[data-key="'+r.id+'"] .router-key-head');if(!row)continue;
    let ptag=row.querySelector('.paused-tag');
    if(r.paused){if(!ptag){ptag=document.createElement('span');ptag.className='router-badge warn paused-tag';row.appendChild(ptag);}ptag.textContent=T('后台已暂停（基础额度用完）');}else if(ptag){ptag.remove();}
    let tag=row.querySelector('.quota');if(!tag){tag=document.createElement('span');tag.className='router-badge quota';row.appendChild(tag);}
    tag.classList.toggle('on',r.ok&&!r.paused&&(r.remaining||0)>0);tag.classList.toggle('warn',r.ok&&(r.paused||(r.remaining||0)<=0));tag.classList.toggle('bad',!r.ok);
    tag.textContent=(!r.ok?'✗ ':r.paused?'! ':(r.remaining||0)<=0?'! ':r.duplicateAccount?'≈ ':'✓ ')+T(r.message)+(r.duplicateAccount?' · '+T('重复账户'):'')+(r.latencyMs!=null?' · '+r.latencyMs+' ms':'');}
   setKeysStatus(T('启用合计')+' '+routerQuotaFmt(rep.enabledTotal,rep.unit)+(rep.allAliveTotal!==rep.enabledTotal?' · '+T('存活去重')+' '+routerQuotaFmt(rep.allAliveTotal,rep.unit):'')+((rep.extraBonusCredits||0)>0?' · '+T('赠送未启用')+' '+Number(rep.extraBonusCredits).toFixed(2)+' credits':'')+' · '+num(rep.usableCount)+'/'+num(rep.enabledChecked)+' '+T('把启用可用')+(rep.pausedCount>0?' · '+num(rep.pausedCount)+' '+T('把已暂停'):'')+' · '+T('已检查')+' '+num(rep.checkedKeys)+' '+T('把')+(rep.duplicateAccounts?' · '+num(rep.duplicateAccounts)+' '+T('个重复账户'):''),true);
   if(routerIsKiro(p))loadRouter(true).catch(()=>{});
  }catch(x){setKeysStatus(T(x.message));}finally{btns.forEach(x=>{if(x.isConnected)x.disabled=false;});}};
 for(const b of [$('router-keys-quota'),$('router-keys-quota-top')])if(b)b.onclick=runQuota;
 const runSpeed=async()=>{const btns=[$('router-keys-speed'),$('router-keys-speed-top')].filter(Boolean);btns.forEach(x=>x.disabled=true);setKeysStatus(T('正在逐把测试…'));
  try{const rs=await routerCall('test_keys',{providerId:pid});
   for(const r of rs){const row=$('router-form').querySelector('[data-key="'+r.id+'"] .router-key-head');if(!row)continue;let tag=row.querySelector('.speed');if(!tag){tag=document.createElement('span');tag.className='router-badge speed';row.appendChild(tag);}
    tag.classList.toggle('on',r.ok);tag.textContent=(r.ok?'✓ ':'✗ ')+T(r.message)+(r.latencyMs!=null?' · '+r.latencyMs+' ms':'');}
   const good=rs.filter(r=>r.ok).length;setKeysStatus(good+' / '+rs.length+' '+T('把密钥可用'),true);
  }catch(x){setKeysStatus(T(x.message));}finally{btns.forEach(x=>{if(x.isConnected)x.disabled=false;});}};
 for(const b of [$('router-keys-speed'),$('router-keys-speed-top')])if(b)b.onclick=runSpeed;
 $('router-form').onsubmit=async e=>{e.preventDefault();const submit=e.target.querySelector('[type=submit]');if(submit.disabled)return;const secret=$('router-key-new').value.trim();if(!secret){$('router-form-error').textContent=T('请输入密钥。');return;}
  submit.disabled=true;try{await routerCall('upsert_provider_key',{input:{providerId:pid,label:$('router-key-new-note').value,secret}});await routerKeysDone(pid,'密钥已添加');}catch(err){$('router-form-error').textContent=T(err.message);}finally{if(submit.isConnected)submit.disabled=false;}};
 dialogOpen($('router-dialog'));
}
async function routerKeysDone(pid,message){routerLoading=false;await loadRouter(true);await routerKeys(pid,message);}
function routerParseKeys(text,mode,operation,keys){
 if(!['keys','notes','combined'].includes(mode)||!['replace','create'].includes(operation))throw Error('未知的批量模式。');
 if(text.length>1000000)throw Error('粘贴文本过长。');
 let lines=text.replace(/^\uFEFF/,'').split(/\r\n|\n|\r/).map(s=>s.trim());
 while(lines.length&&!lines.at(-1))lines.pop();
 if(mode!=='combined')lines=lines.filter(Boolean);
 if(!lines.length)throw Error('请输入要批量处理的文本。');
 if(mode==='combined'&&lines.length%2)throw Error('综合模式必须每两行一组，最后一条缺少密钥。');
 const entries=[];
 for(let i=0;i<lines.length;i+=mode==='combined'?2:1){
  const entry=mode==='keys'?{secret:lines[i]}:mode==='notes'?{label:lines[i]}:{label:lines[i],secret:lines[i+1]};
  if(entry.label!==undefined&&[...entry.label].length>200)throw Error('备注不能超过 200 个字符。');
  if(entry.secret!==undefined&&(!entry.secret||/\s/.test(entry.secret)||new TextEncoder().encode(entry.secret).length>2000))throw Error('密钥不能为空、包含空白或超过 2000 字节。');
  entries.push(entry);
 }
 if(operation==='replace'&&entries.length!==keys.length)throw Error('输入数量必须与已有条目数量一致。');
 return entries.map((e,i)=>({...e,...(operation==='replace'?{id:keys[i].id}:{})}));
}
function routerBatchConflict(operation,keys,current){
 if(operation!=='replace')return false;
 const sig=rows=>rows.map(k=>[k.id,k.providerId,k.priority,k.label,k.hasSecret]);
 return JSON.stringify(sig(current))!==JSON.stringify(sig(keys));
}
function routerBatchKeys(pid,keys){
 const form=$('router-form'),dialog=$('router-dialog');let saving=false,failed=false;
 $('router-form-title').textContent=T('批量添加密钥')+' · '+routerData.providers.find(p=>p.id===pid).name;
 const choices=(name,title,values)=>'<fieldset class="router-batch-choice"><legend>'+T(title)+'</legend>'+values.map((v,i)=>'<label><input type="radio" name="'+name+'" value="'+v[0]+'"'+((name==='operation'?v[0]==='create':!i)?' checked':'')+'>'+T(v[1])+'</label>').join('')+'</fieldset>';
 form.innerHTML=choices('operation','操作方式',[['replace','替换'],['create','新建']])+choices('mode','文本格式',[['keys','纯密钥'],['notes','纯备注'],['combined','综合']])
  +'<p id="router-batch-help" class="router-help"></p><label>'+T('粘贴文本')+'<textarea id="router-batch-text" autocomplete="off" autocapitalize="off" spellcheck="false" aria-describedby="router-batch-help router-form-error"></textarea></label><div id="router-batch-count" role="status" aria-live="polite"></div><div id="router-batch-preview"></div><div id="router-form-error" class="router-form-error" role="alert"></div><div class="router-actions router-batch-actions"><button type="button" id="router-batch-back">'+T('返回密钥列表')+'</button><button type="submit" id="router-batch-save" disabled>'+T('开始新建')+'</button></div>';
 form.classList.remove('router-batch-enter');void form.offsetWidth;form.classList.add('router-batch-enter');form.addEventListener('animationend',()=>form.classList.remove('router-batch-enter'),{once:true});
 const text=$('router-batch-text'),error=$('router-form-error'),button=$('router-batch-save');
 const update=()=>{
  if(saving||failed)return;
  const mode=form.elements.mode.value,operation=form.elements.operation.value;
  $('router-batch-help').textContent=T({keys:'每行一把密钥；空行忽略。',notes:'每行一条备注；空行忽略。',combined:'每两行一组：第一行备注，第二行密钥；空备注可以留空行。'}[mode])+' '+T(operation==='replace'?'替换按当前列表从上到下对应，数量必须与已有条目一致。':'新建会追加条目；只有备注的条目暂不启用，补入密钥后可使用。');
  button.textContent=T(operation==='replace'?'开始替换':'开始新建');error.textContent='';text.setAttribute('aria-invalid','false');button.disabled=true;$('router-batch-preview').replaceChildren();$('router-batch-count').textContent='';
  if(!text.value.trim())return;
  try{const entries=routerParseKeys(text.value,mode,operation,keys);
   $('router-batch-count').textContent=T('已识别')+' '+entries.length+' '+T('条');
   $('router-batch-preview').innerHTML=routerTable(['预览','原备注','备注','密钥'],entries.map((e,i)=>'<tr><td>#'+(operation==='create'?keys.length+i+1:i+1)+'</td><td>'+esc(operation==='replace'?keys[i].label:'—')+'</td><td>'+esc(e.label===undefined?T('保留原备注'):e.label||'—')+'</td><td>'+T(e.secret===undefined?(operation==='replace'?'保留原密钥':'待补密钥'):'密钥')+(e.secret===undefined?'':' · ••••••••')+'</td></tr>'));button.disabled=false;
  }catch(e){error.textContent=T(e.message);text.setAttribute('aria-invalid','true');}
 };
 form.oninput=update;form.onchange=update;
 const blockCancel=e=>{if(saving)e.preventDefault();};dialog.addEventListener('cancel',blockCancel);
 dialog.addEventListener('close',()=>{if(dialog.open)return;dialog.removeEventListener('cancel',blockCancel);form.replaceChildren();form.oninput=null;form.onchange=null;},{once:true});
 $('router-batch-back').onclick=()=>routerKeys(pid);
 form.onsubmit=async e=>{e.preventDefault();if(saving||failed)return;let done=0,total=0;
  try{const operation=form.elements.operation.value,entries=routerParseKeys(text.value,form.elements.mode.value,operation,keys);total=entries.length;
   saving=true;dialog.dataset.busy='1';routerBusy=true;form.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=true);
   if(operation==='replace'&&routerBatchConflict(operation,keys,await routerCall('list_provider_keys',{providerId:pid})))throw Error('已有条目发生变化，请返回列表重新核对。');
   for(const entry of entries){button.textContent=T('正在保存')+' '+done+' / '+total;await routerCall('upsert_provider_key',{input:{providerId:pid,...entry}});done++;}
   text.value='';routerBusy=false;saving=false;await routerKeysDone(pid,T('批量处理完成')+' · '+done+' / '+total);
  }catch(e){failed=true;error.textContent=T('已完成')+' '+done+' / '+total+'。'+T('保存失败，已停止。请返回列表核对后再处理剩余条目。')+' '+T(e.message);$('router-batch-back').disabled=false;}
  finally{saving=false;delete dialog.dataset.busy;routerBusy=false;}
 };update();text.focus();
}
$('router-form').addEventListener('click',async e=>{
 const b=e.target.closest('[data-key-act]');if(!b)return;const row=b.closest('[data-key]'),id=Number(row.dataset.key),act=b.dataset.keyAct,pid=routerKeyProvider;
 const value=row.querySelector('[data-key-value]'),enabled=JSON.parse($('router-form').dataset.keys).find(k=>k.id===id)?.enabled;
 try{
  if(act==='reveal'){if(value.type==='text'){value.value='';value.type='password';b.textContent=T('显示');}else{value.value=await routerCall('reveal_provider_key',{id});routerRevealed.set(value,value.value);value.type='text';b.textContent=T('隐藏');}return;}
  if(act==='delete'&&!b.dataset.armed){b.dataset.armed='1';b.textContent=T('再点一次确认删除');setTimeout(()=>{if(b.isConnected){delete b.dataset.armed;b.textContent=T('删除');}},4000);return;}
  b.disabled=true;
  if(act==='save')await routerCall('upsert_provider_key',{input:{id,label:row.querySelector('[data-key-note]').value,...(value.value.trim()&&value.value.trim()!==routerRevealed.get(value)?{secret:value.value.trim()}:{})}});
  if(act==='primary')await routerCall('upsert_provider_key',{input:{id,primary:true}});
  if(act==='toggle')await routerCall('upsert_provider_key',{input:{id,enabled:!enabled}});
  if(act==='delete')await routerCall('delete_provider_key',{id});
  await routerKeysDone(pid,act==='delete'?'密钥已删除':'已保存');
 }catch(err){b.disabled=false;$('router-form-error').textContent=T(err.message);}
});
function routerField(name,label,value='',extra=''){return '<label>'+esc(T(label))+'<input name="'+name+'" value="'+esc(value)+'" '+extra+'></label>';}
function routerEdit(kind,id){
 const p=kind==='provider'?(routerData.providers.find(p=>p.id===id)||{enabled:true,keyStrategy:'priority',baseQuotaOnly:false}):(routerData.models.find(p=>p.id===id)||{enabled:true});
 $('router-form-title').textContent=T(kind==='provider'?(id?'编辑供应商':'添加供应商'):(id?'编辑模型':'添加模型'));
 $('router-form').innerHTML=kind==='provider'?routerField('name','名称',p.name||'','required maxlength="200"')+routerField('baseUrl','API 地址',p.baseUrl||'','required type="url"')+routerField('note','备注',p.note||'')+'<label>'+T('密钥使用方式')+'<select name="keyStrategy">'+[...new Set([...routerStrategyChoices,p.keyStrategy])].map(v=>'<option value="'+esc(v)+'"'+(p.keyStrategy===v?' selected':'')+'>'+esc(T(routerStrategies[v]||v))+'</option>').join('')+'</select></label><div id="router-edit-kiro-box" class="router-kiro-box"'+(routerKiroUrl(p.baseUrl||'')?'':' hidden')+'><label class="check"><input name="baseQuotaOnly" type="checkbox"'+(p.baseQuotaOnly?' checked':'')+'>'+esc(T('仅使用基础额度'))+'</label><small>'+esc(T('不使用赠送额度；基础额度用完后后台标记为暂停并直接跳过，不禁用'))+'</small></div>'+(id?'<small class="muted">'+T('密钥在供应商列表的「密钥」里查看、添加和更新。')+'</small>':routerField('apiKey','API 密钥（可选）','','type="password" autocomplete="new-password"')):routerField('displayName','名称',p.displayName||'','required')+routerField('modelId','调用名称',p.modelId||'','required')+'<label>'+T('供应商')+'<select name="providerId" required><option value="">'+T('选择供应商')+'</option>'+routerData.providers.map(x=>'<option value="'+x.id+'"'+(p.providerId===x.id?' selected':'')+'>'+esc(x.name)+'</option>').join('')+'</select></label>'+routerField('upstreamModel','供应商模型名',p.upstreamModel||'','required');
 $('router-form').innerHTML+='<label class="check"><input name="enabled" type="checkbox"'+(p.enabled?' checked':'')+'>'+T('启用')+'</label><div id="router-form-error" class="router-form-error" role="alert"></div><div class="router-actions"><button type="button" id="router-form-cancel">'+T('取消')+'</button><button type="submit">'+T('保存')+'</button></div>';
 if(kind==='provider'){const bu=$('router-form').elements.baseUrl,kb=$('router-edit-kiro-box');if(bu&&kb)bu.addEventListener('input',()=>{kb.hidden=!routerKiroUrl(bu.value);});}
 $('router-form-cancel').onclick=()=>dialogClose($('router-dialog'));
 $('router-form').onsubmit=async e=>{e.preventDefault();const f=e.target,input=Object.fromEntries(new FormData(f));if(id)input.id=id;input.enabled=f.elements.enabled.checked;if(kind==='provider'){if(routerKiroUrl(input.baseUrl))input.baseQuotaOnly=!!f.elements.baseQuotaOnly?.checked;else delete input.baseQuotaOnly;}if(kind==='model')input.providerId=Number(input.providerId);
  try{await routerRun('upsert_'+kind,{input},f.querySelector('[type=submit]'));dialogClose($('router-dialog'));await loadRouter(true);}catch(err){$('router-form-error').textContent=T(err.message);}
 };
 dialogOpen($('router-dialog'));
}
async function routerCopy(text){try{await navigator.clipboard.writeText(text);}catch(err){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();const ok=document.execCommand('copy');ta.remove();if(!ok)throw new Error(T('复制失败，请手动选中复制。'));}routerNote('复制成功');}
$('router-dialog').addEventListener('close',()=>{if($('router-dialog').open)return;$('router-form').replaceChildren();$('router-form').oninput=null;$('router-form').onchange=null;});
$('router-launch').onclick=async e=>{try{await centerApi('router/action',{command:'launch_app'});routerNote('正在连接模型路由…');setTimeout(loadRouter,1500);}catch(err){routerNote(err.message,true);}};
$('router-open').onclick=async e=>{try{await centerApi('router/action',{command:'open_app'});routerNote('操作已完成');setTimeout(loadRouter,1500);}catch(err){routerNote(err.message,true);}};

$('router-copy-url').onclick=()=>routerCopy(routerData.dashboard.server.baseUrl).catch(e=>routerNote(e.message,true));
for(const cmd of ['start','stop','restart'])$('router-'+cmd).onclick=async e=>{if(cmd==='stop'&&!await routerConfirm('是否停止模型路由服务？现有 API 客户端将无法发出新请求。'))return;if(cmd==='restart'&&!await routerConfirm('是否重启模型路由服务？现有连接可能中断。'))return;try{await routerRun(cmd+'_server',{},e.target);await loadRouter(true);}catch(e){}};
$('router-page').addEventListener('click',async e=>{
 const tab=e.target.closest('[data-router-tab]');if(tab){if(tab.dataset.routerTab===routerTab)return;if(routerSettingsDirty&&!await routerConfirm('有未保存的设置，离开后将丢弃。是否继续？'))return;routerTab=tab.dataset.routerTab;routerTabMotionPending=true;routerQuery='';routerSettingsDirty=false;routerContentKey='';$('router-content').replaceChildren();renderRouter();return;}
 const b=e.target.closest('[data-router-action]');if(!b||routerBusy)return;const action=b.dataset.routerAction,id=Number(b.dataset.routerId);
 try{
  if(action==='add-provider'||action==='edit-provider'){routerEdit('provider',id||null);return;}
  if(action==='keys-provider'){await routerKeys(id);return;}
  if(action==='add-model'||action==='edit-model'){routerEdit('model',id||null);return;}
  if(action==='delete-provider'){if(!await routerConfirm('删除供应商会同时删除其调用名称和密钥配置。是否继续？'))return;await routerRun('delete_provider',{id},b);}
  if(action==='delete-model'){if(!await routerConfirm('是否删除此调用名称？'))return;await routerRun('delete_model',{id},b);}
  if(action==='toggle-provider'){const p=routerData.providers.find(p=>p.id===id);await routerRun('upsert_provider',{input:{id:p.id,name:p.name,baseUrl:p.baseUrl,note:p.note,keyStrategy:p.keyStrategy,enabled:!p.enabled,...(routerIsKiro(p)?{baseQuotaOnly:!!p.baseQuotaOnly}:{})}},b);}
  if(action==='toggle-model'){const m=routerData.models.find(m=>m.id===id);await routerRun('upsert_model',{input:{id:m.id,displayName:m.displayName,modelId:m.modelId,providerId:m.providerId,upstreamModel:m.upstreamModel,enabled:!m.enabled}},b);}
  if(action==='quota-all'){await routerQueryAllQuotas();return;}
  if(action==='quota-close'){routerQuota=null;routerQuotaError='';if(routerTab==='providers')renderRouterContent(true);return;}
  if(action==='quota-provider'){await routerKeys(id);$('router-keys-quota')?.click();return;}
  if(action==='speed-provider'){await routerKeys(id);$('router-keys-speed').click();return;}
  if(action==='test-provider'){routerNote('正在测试连接…');const r=await routerRun('test_provider_connection',{id},b);routerNote(r.message+' · '+num(r.latencyMs)+' ms',!r.ok);return;}
  if(action==='clear-logs'){if(!await routerConfirm('是否清空所有请求日志？此操作不可恢复。'))return;await routerRun('clear_logs',{},b);}
  if(action==='reveal-key'){const input=$('router-local-key');if(input.value){input.value='';input.type='password';b.textContent=T('显示密钥');}else{input.value=await routerCall('get_local_api_key');input.type='text';b.textContent=T('隐藏密钥');}return;}
  if(action==='copy-key'){await routerCopy(await routerCall('get_local_api_key'));return;}
  if(action==='regenerate-key'){if(!await routerConfirm('重新生成会使旧 API 密钥立即失效。是否继续？'))return;await routerRun('regenerate_local_api_key',{},b);const key=$('router-local-key');if(key){key.value='';key.type='password';}const reveal=$('router-content').querySelector('[data-router-action=reveal-key]');if(reveal)reveal.textContent=T('显示密钥');}
  if(action==='export'){const includeSecrets=$('router-export-secrets').checked;if(includeSecrets&&!await routerConfirm('导出文件将包含明文供应商密钥。是否继续？'))return;const r=await routerRun('export_config',{includeSecrets},b);routerNote(T('已导出到：')+r.path);return;}
  await loadRouter(true);
 }catch(err){routerNote(err.message,true);}
});
$('router-page').addEventListener('change',async e=>{
 const cb=e.target.closest('[data-router-base-only]');if(!cb)return;
 const pid=Number(cb.dataset.routerBaseOnly),enabled=cb.checked;cb.disabled=true;
 try{await routerRun('set_provider_base_quota_only',{providerId:pid,enabled},cb);routerNote(T(enabled?'已开启仅使用基础额度':'已关闭仅使用基础额度'));await loadRouter(true);}
 catch(err){cb.checked=!enabled;routerNote(err.message,true);}
 finally{if(cb.isConnected)cb.disabled=false;}
});
// 模型库：AWS Bedrock 注册表（官方同步 + 管理员启停）。
let routerBedrock=null,routerBedrockSeq=0,routerBedrockBusy=false,routerBedrockReports=[],routerBedrockShellFor='';
const routerBedrockFilters={q:'',providers:new Set(),modelProviders:new Set(),lifecycle:'all',availability:'all',enabledOnly:false,newOnly:false,hideLegacy:false,hideDeprecated:false,latestOnly:false};
function bedrockPrice(m,bucket){const p=m.prices||{};const x=p[bucket];return x&&typeof x.price==='number'?'$'+x.price.toFixed(2):'—';}
function bedrockHumanMods(m){
 const map={TEXT:T('文本'),IMAGE:T('图片'),AUDIO:T('音频'),VIDEO:T('视频'),EMBEDDING:T('嵌入')},out=[];
 for(const [field,label] of [['inputModalities','输入'],['outputModalities','输出']]){
  const mods=(JSON.parse(m[field]||'[]')||[]).map(x=>map[x]).filter(Boolean);
  if(mods.length)out.push(T(label)+'·'+mods.join('/'));
 }
 if(m.streaming)out.push(T('流式输出'));
 return out.join(' · ')||'—';
}
function bedrockCmpVer(a,b){const A=String(a||'0').split('.').map(Number),B=String(b||'0').split('.').map(Number);for(let i=0;i<Math.max(A.length,B.length);i++){const x=A[i]||0,y=B[i]||0;if(x!==y)return x-y;}return 0;}
function bedrockLatestOnly(rows){
 const fam=new Map();
 rows.forEach(m=>{const name=m.displayName||m.modelId||'';const vm=name.match(/\d+(?:\.\d+)+/g);const ver=vm?vm[vm.length-1]:'0';
  const famKey=name.replace(/\s*\d+(?:\.\d+)+\s*$/,'').trim().toLowerCase()||name.toLowerCase();
  if(!fam.has(famKey))fam.set(famKey,[]);fam.get(famKey).push({m:m,ver:ver});});
 const out=[];fam.forEach(arr=>{arr.sort((a,b)=>bedrockCmpVer(b.ver,a.ver));out.push(arr[0].m);});
 return out;
}
function bedrockFiltered(rows){
 const f=routerBedrockFilters,q=f.q.toLocaleLowerCase();
 let list=rows.filter(m=>{
  if(f.providers.size&&!f.providers.has(m.routerProvider||'—'))return false;
  if(f.modelProviders.size&&!f.modelProviders.has(m.providerName||'—'))return false;
  if(f.lifecycle!=='all'&&(m.lifecycleStatus||'').toUpperCase()!==f.lifecycle)return false;
  if(f.availability!=='all'&&(m.availabilityStatus||'UNKNOWN')!==f.availability)return false;
  if(f.enabledOnly&&!m.enabled)return false;
  if(f.newOnly&&!m.isNew)return false;
  if(f.hideLegacy&&(m.lifecycleStatus||'').toUpperCase()==='LEGACY')return false;
  if(f.hideDeprecated&&m.availabilityStatus==='UNAVAILABLE')return false;
  if(q&&![m.displayName,m.modelId,m.inferenceProfileId,m.providerName].some(x=>(x||'').toLocaleLowerCase().includes(q)))return false;
  return true;});
 if(f.latestOnly)list=bedrockLatestOnly(list);
 return list;
}
async function loadBedrock(force=false){
 if(routerTab!=='bedrock'||!routerData?.connected||(routerBedrockBusy&&!force))return;
 const seq=++routerBedrockSeq;
 try{const d=await routerCall('list_bedrock_models',{input:{providerId:0}});
  if(seq!==routerBedrockSeq||routerTab!=='bedrock')return;
  routerBedrock=d;renderBedrock(force);
 }catch(e){if(seq===routerBedrockSeq)routerNote(e.message,true);}
}
function bedrockReportHtml(items){
 return items.map(({kind,last})=>{
  if(!last)return '';
  if(last.error)return '<div class="router-report"><b>'+esc(T('同步报告'))+'（'+T(kind==='models'?'同步模型':'同步价格')+'）</b><br><span style="color:var(--bad)">'+esc(last.error)+'</span></div>';
  if(kind==='models'){
   const by=Object.entries(last.byProvider||{}).map(([k,c])=>esc(k)+' <b>'+c+'</b>').join(' · ');
   const errs=(last.errors||[]).map(e=>esc(e.provider+': '+e.error)).join('<br>');
   return '<div class="router-report"><b>'+esc(T('同步报告'))+'（'+T('同步模型')+'）</b><br>'
    +T('发现')+' <b>'+num(last.discovered)+'</b> · '+T('新增')+' <b>'+num(last.added)+'</b> · '+T('更新')+' <b>'+num(last.updated)+'</b> · '+T('标记退市')+' <b>'+num(last.markedUnavailable)+'</b><br>'
    +(by?by+'<br>':'')+(errs?'<span style="color:var(--warn)">'+errs+'</span><br>':'')
    +'<a href="https://aws.amazon.com/bedrock/pricing/" target="_blank" rel="noopener">'+esc(T('官方价格页'))+' ↗</a></div>';
  }
  const errs=(last.errors||[]).map(e=>esc(JSON.stringify(e))).join('<br>');
  return '<div class="router-report"><b>'+esc(T('同步报告'))+'（'+T('同步价格')+'）</b><br>'
   +T('价格条目')+' <b>'+num(last.pricingEntries)+'</b> · '+T('已写入')+' <b>'+num(last.inserted)+'</b> · '+T('未变化')+' <b>'+num(last.unchanged)+'</b><br>'
   +T('有官方价格')+' <b>'+num(last.modelsWithPricing)+'</b> · '+T('缺官方价格')+' <b>'+num(last.modelsWithoutPricing)+'</b> · '
   +'<a href="https://aws.amazon.com/bedrock/pricing/" target="_blank" rel="noopener">'+esc(T('官方价格页'))+' ↗</a>'+(errs?'<br><span style="color:var(--warn)">'+errs+'</span>':'')+'</div>';
 }).join('');
}
function renderBedrock(force=false){
 const content=$('router-content'),d=routerBedrock;if(!d)return;
 const f=routerBedrockFilters,shellKey='bedrock';
 if(force||!content.querySelector('#bedrock-shell')||routerBedrockShellFor!==shellKey){
  routerBedrockShellFor=shellKey;
  content.innerHTML='<div id="bedrock-shell">'
   +'<div class="bedrock-toolbar"><label>'+esc(T('搜索模型'))+'<input id="bedrock-search" type="search" value="'+esc(f.q)+'"></label><button class="bedrock-primary" type="button" data-bedrock-act="bedrock-sync-all">'+esc(T('全部同步'))+'</button><button type="button" data-bedrock-act="bedrock-zcode">'+esc(T('同步到 ZCode'))+'</button><details class="bedrock-more"><summary>'+esc(T('更多操作'))+' ▾</summary><div class="bedrock-more-menu">'+[['同步模型','bedrock-sync-models'],['同步价格','bedrock-sync-pricing'],['刷新列表','bedrock-refresh']].map(([label,act])=>'<button type="button" data-bedrock-act="'+act+'">'+esc(T(label))+'</button>').join('')+'</div></details></div>'
   +'<p class="router-help">'+esc(T('Bedrock 模型由 AWS 官方 API 自动发现；启用后才会出现在 Agent 的模型列表里。'))+'</p>'
   +'<details class="bedrock-filters"><summary>'+T('筛选')+' <span id="bedrock-filter-summary"></span></summary><div class="bedrock-filter-body"><div class="bedrock-filter-label">'+T('路由供应商')+'</div><div class="router-chips" id="bedrock-chips" role="group" aria-label="'+esc(T('路由供应商'))+'"></div>'
   +'<div class="bedrock-filter-label">'+T('模型提供商')+'</div><div class="router-chips" id="bedrock-model-chips" role="group" aria-label="'+esc(T('模型提供商'))+'"></div>'
   +'<div class="router-bedrock-quick">'
   +'<label>'+T('版本阶段')+' <select id="bedrock-lifecycle"><option value="all">'+T('全部')+'</option>'+['ACTIVE','LEGACY'].map(v=>'<option value="'+v+'"'+(f.lifecycle===v?' selected':'')+'>'+T(v==='ACTIVE'?'当前':'旧版')+'</option>').join('')+'</select></label>'
   +'<label>'+T('目录状态')+' <select id="bedrock-availability"><option value="all">'+T('全部')+'</option>'+['AVAILABLE','UNKNOWN','UNAVAILABLE'].map(v=>'<option value="'+v+'"'+(f.availability===v?' selected':'')+'>'+T({AVAILABLE:'目录可用',UNKNOWN:'状态未知',UNAVAILABLE:'已退市'}[v]))+'</option></select></label>'
   +'<label><input type="checkbox" id="bedrock-enabled-only"'+(f.enabledOnly?' checked':'')+'>'+T('仅看启用')+'</label>'
   +'<label><input type="checkbox" id="bedrock-new-only"'+(f.newOnly?' checked':'')+'>'+T('仅看新增')+'</label>'
   +'<label><input type="checkbox" id="bedrock-hide-legacy"'+(f.hideLegacy?' checked':'')+'>'+T('隐藏旧版')+'</label>'
   +'<label><input type="checkbox" id="bedrock-hide-deprecated"'+(f.hideDeprecated?' checked':'')+'>'+T('隐藏已废弃')+'</label>'
   +'<label><input type="checkbox" id="bedrock-latest-only"'+(f.latestOnly?' checked':'')+'>'+T('只看最新版本')+'</label></div></div></details><div class="bedrock-filter-footer"><span id="bedrock-count" class="bedrock-count" role="status" aria-live="polite"></span><button type="button" id="bedrock-clear-filters" hidden>'+T('清除筛选')+'</button></div>'
   +'<div id="bedrock-report"></div>'
   +'<div id="bedrock-table"></div>'
   +'<p class="router-help">'+esc(T('AWS Bedrock 模型注册表：数据来自 AWS 官方 API 与官方价格文件，缺失信息显示为 —，不做任何推测。'))+'</p></div>';
  $('bedrock-clear-filters').onclick=()=>{f.q='';f.providers.clear();f.modelProviders.clear();f.lifecycle='all';f.availability='all';for(const k of ['enabledOnly','newOnly','hideLegacy','hideDeprecated','latestOnly'])f[k]=false;renderBedrock(true);$('bedrock-search').focus();};
  const search=$('bedrock-search');
  search.oninput=e=>{if(e.isComposing)return;f.q=e.target.value;updateBedrock();};
  search.oncompositionend=e=>{f.q=e.target.value;updateBedrock();};
  $('bedrock-lifecycle').onchange=e=>{f.lifecycle=e.target.value;updateBedrock();};
  $('bedrock-availability').onchange=e=>{f.availability=e.target.value;updateBedrock();};
  $('bedrock-enabled-only').onchange=e=>{f.enabledOnly=e.target.checked;updateBedrock();};
  $('bedrock-new-only').onchange=e=>{f.newOnly=e.target.checked;updateBedrock();};
  $('bedrock-hide-legacy').onchange=e=>{f.hideLegacy=e.target.checked;updateBedrock();};
  $('bedrock-hide-deprecated').onchange=e=>{f.hideDeprecated=e.target.checked;updateBedrock();};
  $('bedrock-latest-only').onchange=e=>{f.latestOnly=e.target.checked;updateBedrock();};
 }
 updateBedrock();
 routerTabEnter();
}
function updateBedrock(){
 const d=routerBedrock;if(!d)return;
 const f=routerBedrockFilters;
 // 两组多选独立组合；空集合表示全部，点击「全部」清除该组筛选。
 for(const [field,selected,target,attr,label] of [
  ['routerProvider',f.providers,'bedrock-chips','data-bedrock-chip','全部供应商'],
  ['providerName',f.modelProviders,'bedrock-model-chips','data-bedrock-model-chip','全部模型提供商']]){
  const counts=new Map();d.models.forEach(m=>{const k=m[field]||'—';counts.set(k,(counts.get(k)||0)+1);});
  const names=[...counts.keys()].sort(),allSelected=selected.size===0||names.every(n=>selected.has(n));
  const chips=[{k:'__all__',l:T(label)+' ('+d.models.length+')',on:allSelected}]
   .concat(names.map(n=>({k:n,l:n+' ('+counts.get(n)+')',on:selected.has(n)})));
  $(target).innerHTML=chips.map(c=>'<button type="button" '+attr+'="'+esc(c.k)+'" aria-pressed="'+c.on+'"'+(c.on?' class="on"':'')+'>'+esc(c.l)+'</button>').join('');
 }
 $('bedrock-report').innerHTML=bedrockReportHtml(routerBedrockReports);
 const conditions=[...f.providers,...f.modelProviders];
 if(f.lifecycle!=='all')conditions.push(T(f.lifecycle==='ACTIVE'?'当前':'旧版'));
 if(f.availability!=='all')conditions.push(T({AVAILABLE:'目录可用',UNKNOWN:'状态未知',UNAVAILABLE:'已退市'}[f.availability]));
 for(const [k,label] of [['enabledOnly','仅看启用'],['newOnly','仅看新增'],['hideLegacy','隐藏旧版'],['hideDeprecated','隐藏已废弃'],['latestOnly','只看最新版本']])if(f[k])conditions.push(T(label));
 $('bedrock-filter-summary').textContent=conditions.join(' · ')||T('未设置筛选');
 $('bedrock-clear-filters').hidden=!conditions.length&&!f.q;
 let rows=bedrockFiltered(d.models);
 $('bedrock-count').textContent=T('显示')+' '+rows.length+' / '+d.models.length+' '+T('条');
 const counts={};rows.forEach(m=>{const k=m.providerName||'Unknown';counts[k]=(counts[k]||0)+1;});
 const table=rows.length?routerTable(
  ['模型','能力 / 上下文','输入','输出','缓存价格','调用 / 目录状态','启用'],
  rows.map(m=>{
   const scope=m.inferenceProfileId?(m.inferenceProfileType==='APPLICATION'?T('应用 Profile'):T('跨区调用')):T('本区直连');
   const statusParts=[];
   if(m.availabilityStatus==='UNAVAILABLE')statusParts.push('<span class="router-badge">'+esc(T('已退市'))+'</span>');
   else if(m.availabilityStatus==='UNKNOWN')statusParts.push('<span class="router-badge">'+esc(T('状态未知'))+'</span>');
   else statusParts.push('<span class="router-badge on">'+esc(T('目录可用'))+'</span>');
   if((m.lifecycleStatus||'').toUpperCase()==='LEGACY')statusParts.push('<span class="router-badge">'+esc(T('旧版'))+'</span>');
   if((m.lifecycleStatus||'').toUpperCase()==='DEPRECATED')statusParts.push('<span class="router-badge">'+esc(T('已废弃'))+'</span>');
   if(m.isNew)statusParts.push('<span class="router-badge on">'+esc(T('新增'))+'</span>');
   return '<tr><td><span class="bedrock-model-name">'+esc(m.displayName||m.modelId)+'</span><small>'+esc(m.providerName||m.routerProvider||'—')+' · '+esc(m.routerProvider||'—')+'</small><details class="bedrock-model-detail"><summary>'+T('模型详情')+'</summary><code>'+esc(m.modelId)+'</code>'+(m.inferenceProfileId?'<small>'+esc(T('调用 ID'))+'</small><code>'+esc(m.inferenceProfileId)+'</code>':'')+'</details></td>'
    +'<td class="bedrock-capability">'+esc(bedrockHumanMods(m))+'<small>'+T('上下文')+' '+(m.contextWindow!=null?num(m.contextWindow):'—')+'</small></td>'
    +'<td class="number">'+bedrockPrice(m,'input')+'</td><td class="number">'+bedrockPrice(m,'output')+'</td>'
    +'<td class="number"><details class="bedrock-cache"><summary>'+T('详情')+'</summary><small>'+T('缓存读')+' '+bedrockPrice(m,'cacheRead')+'</small><small>'+T('缓存写')+' '+bedrockPrice(m,'cacheWrite')+'</small></details></td>'
    +'<td>'+esc(scope)+'<small>'+statusParts.join(' ')+'</small></td>'
    +'<td><button type="button" data-bedrock-enable data-id="'+m.id+'" data-on="'+(m.enabled?'1':'0')+'">'+esc(T(m.enabled?'停用':'启用'))+'</button></td></tr>';
  })
 ):routerEmpty(d.models.length?'没有匹配的条目。请修改搜索条件。':'暂无数据，先点「同步模型」。');
 $('bedrock-table').innerHTML='<p class="router-help">'+T('价格 / 百万 Token')+' · '+T('目录状态不代表账户调用权限；实际访问还取决于供应商账户、地区与模型授权。')+'</p>'+table;
}
async function bedrockRunSync(kinds){
 const done=[];
 for(const kind of kinds){
  const cmd=kind==='models'?'bedrock_sync_models':'bedrock_sync_pricing';
  const r=await routerCall(cmd,{input:{providerId:0}});
  if(r&&r.started===false){routerNote(r.message);continue;}
  routerNote('正在同步…');
  for(let i=0;i<400;i++){
   await new Promise(r2=>setTimeout(r2,1500));
   const st=await routerCall('bedrock_sync_status',{input:{providerId:0}});
   if(!(kind==='models'?st.modelsRunning:st.pricingRunning))break;
  }
  const st=await routerCall('bedrock_sync_status',{input:{providerId:0}});
  const last=kind==='models'?st.lastModels:st.lastPricing;
  if(last)done.push({kind:kind,last:last});
  await loadBedrock(true);
 }
 if(done.length){routerBedrockReports=done;routerNote('同步已完成');updateBedrock();}
}
async function routerZcodeSync(){
 const d=await centerApi('router/zcode'),form=$('router-form'),dialog=$('router-dialog');let saving=false;
 form.oninput=null;form.onchange=null;form.onsubmit=null;dialog.dataset.busy='0';
 $('router-form-title').textContent=T('同步到 ZCode');
 form.innerHTML='<p class="router-help">'+esc(T('将所选模型添加或更新到 ZCode，保留已有其他模型。'))+'</p>'
  +[['选择模型','models',d.models||[]],['选择账号','accounts',d.accounts||[]]].map(([label,group,items])=>'<fieldset style="border:1px solid var(--glassline);border-radius:8px;padding:12px;max-height:240px;overflow:auto"><legend>'+esc(T(label))+'</legend>'+items.map(x=>'<label class="check"><input type="checkbox" data-zcode-group="'+group+'" value="'+esc(x.id)+'" checked>'+esc(x.name||x.label||x.id)+'</label>').join('')+'</fieldset>').join('')
  +'<div id="router-zcode-result" role="status" aria-live="polite"></div><div class="router-actions"><button type="button" id="router-zcode-close">'+T('关闭')+'</button><button type="submit"'+(!(d.models||[]).length||!(d.accounts||[]).length?' disabled':'')+'>'+T('同步到 ZCode')+'</button></div>';
 const result=$('router-zcode-result'),close=$('router-zcode-close');
 if(!(d.models||[]).length||!(d.accounts||[]).length)result.textContent=T('没有已启用模型或可同步账号。');
 close.onclick=()=>{if(!saving)dialogClose(dialog);};
 form.onsubmit=async e=>{e.preventDefault();if(saving)return;
  const selected=group=>[...form.querySelectorAll('[data-zcode-group="'+group+'"]:checked')].map(x=>x.value);
  const model_ids=selected('models'),account_ids=selected('accounts');
  if(!model_ids.length||!account_ids.length){result.textContent=T('请选择至少一个模型和一个账号。');return;}
  saving=true;dialog.dataset.busy='1';[...form.elements].forEach(x=>x.disabled=true);result.textContent=T('正在同步到 ZCode…');
  try{const r=await centerApi('router/zcode/sync',{model_ids,account_ids}),rs=r.results||[];
   const complete=rs.length===account_ids.length&&rs.every(x=>x.ok);
   result.innerHTML='<p>'+esc(T(complete?'全部账号同步完成':'部分账号同步失败'))+'</p>'+rs.map(x=>{const a=(d.accounts||[]).find(a=>a.id===x.accountId);return '<p>'+esc(a?.label||x.accountId)+' · '+esc(T(x.ok?(x.changed?'已更新':'无需更新'):'同步失败'))+(x.message?' · '+esc(x.message):'')+'</p>';}).join('');
  }catch(err){result.textContent=T('同步失败')+' · '+err.message;}
  finally{saving=false;dialog.dataset.busy='0';[...form.elements].forEach(x=>x.disabled=false);}
 };
 dialogOpen(dialog);
}
$('router-page').addEventListener('click',async e=>{
 const chip=e.target.closest('[data-bedrock-chip],[data-bedrock-model-chip]');
 if(chip){const model=chip.hasAttribute('data-bedrock-model-chip'),k=model?chip.dataset.bedrockModelChip:chip.dataset.bedrockChip;
  const selected=model?routerBedrockFilters.modelProviders:routerBedrockFilters.providers;
  if(k==='__all__')selected.clear();
  else{if(selected.has(k))selected.delete(k);else selected.add(k);}
  updateBedrock();return;}
 const en=e.target.closest('[data-bedrock-enable]');
 if(en&&!en.disabled&&!routerBedrockBusy){const id=Number(en.dataset.id),on=en.dataset.on==='1';en.disabled=true;routerBedrockBusy=true;
  try{const d=await centerApi('router/action',{command:'set_bedrock_model_enabled',args:{input:{id:id,enabled:!on}}});const note=routerEnableNote(on,d.zcodeSync);routerNote(note.text,note.error);await loadBedrock(true);}
  catch(err){routerNote(err.message,true);}
  finally{routerBedrockBusy=false;if(en.isConnected)en.disabled=false;}return;}
 const act=e.target.closest('[data-bedrock-act]');
 if(!act||routerBedrockBusy)return;
 const kind=act.dataset.bedrockAct;act.disabled=true;routerBedrockBusy=true;
 try{
  if(kind==='bedrock-zcode'){await routerZcodeSync();return;}
  if(kind==='bedrock-refresh'){await loadBedrock(true);return;}
  if(kind==='bedrock-sync-models'){await bedrockRunSync(['models']);return;}
  if(kind==='bedrock-sync-pricing'){await bedrockRunSync(['pricing']);return;}
  if(kind==='bedrock-sync-all'){await bedrockRunSync(['models','pricing']);return;}
 }catch(err){routerNote(err.message,true);}
 finally{routerBedrockBusy=false;if(act.isConnected)act.disabled=false;}
});
'''
