#!/usr/bin/env python3
"""Read-only numeric dashboard; never exposes local or provider credentials."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.request

import prices
from console_memory import project_rows

# Gate acceptance runs record provider-style platform names; they are the same
# daily-driver channels (Claude Code CLI via the gate, Codex CLI via the gate).
PLATFORM_ALIAS={'anthropic':'claude','openai':'codex'}


DEEPAI_ACCESS=('codex','cursor','direct')


def display_platform(row):
    source=row.get('platform') or ''
    if source=='deepai':
        access=row.get('provider_id') if row.get('provider_id') in DEEPAI_ACCESS else 'direct'
        row['client_platform']=access
        row['platform']='deepai'
        return row
    model=str(row.get('model') or '').lower()
    local_in_claude=source in ('claude','anthropic') and model.startswith(('nemotron-', 'nvidia/', 'qwen', 'deepseek', 'moonshotai/', 'muse-'))
    zcode_model=source=='zcode' and bool(model)
    if source=='router' or row.get('provider_id')=='local-model-router' or local_in_claude or zcode_model:
        row.setdefault('client_platform',source)
        if zcode_model and row.get('provider_id')!='local-model-router':
            # Group the user's custom providers together without declaring a
            # previously paid ZCode model to be free or changing its bill basis.
            row.setdefault('pricing_platform', 'zcode')
        row['platform']='router'
    else:
        row['platform']=PLATFORM_ALIAS.get(source,source)
    if source=='antigravity' and model:
        canonical=re.sub(r'(?:-(?:thinking|low|mid|medium|high|xhigh|max))+$','',model)
        if canonical!=model:
            row.setdefault('original_model',row['model'])
            row['reasoning_effort']=model[len(canonical)+1:]
            row['model']=canonical
    return row


def public_rows(rows):
    """Strip per-row price memo keys (`_rule`/`_cost`) before rows reach the API payload."""
    return [{k:v for k,v in r.items() if not k.startswith('_')} for r in rows]


def number_sum(rows, name):
    return sum(row.get(name) or 0 for row in rows)


def row_latency(row):
    """Upstream duration: gate timings when present, else the imported wall clock."""
    value=row.get('total_ms')
    return value if value is not None else row.get('duration_ms')


def row_speed(row):
    """(output tokens, ms) of a sent, successful, timed request that reported output; else None."""
    if not row.get('sent') or row.get('exit_code')!=0:return None
    output=row.get('actual_output') or 0;duration=row_latency(row) or 0
    return (output,duration) if output>0 and duration>0 else None


def speed_stats(pairs):
    """Output tokens/s over (output, ms) pairs; end-to-end time includes waiting for the first token."""
    if not pairs:return {'output_tps':None,'tps_requests':0,'tps_median':None,'tps_p10':None,'tps_p90':None}
    speeds=sorted(output*1000/duration for output,duration in pairs);last=len(speeds)-1
    return {'output_tps':round(sum(p[0] for p in pairs)*1000/sum(p[1] for p in pairs),1),'tps_requests':len(speeds),
            **{name:round(speeds[round(q*last)],1) for name,q in (('tps_median',.5),('tps_p10',.1),('tps_p90',.9))}}


def summarize(rows):
    # A ledger is visited for the total and each platform. Accumulate once per
    # group instead of allocating three subsets and scanning every metric again.
    requests=measured=failed=pending=prepared=blocked=timed=0
    before=after=input_tokens=output_tokens=cached=jev=latency=0;speeds=[]
    for r in rows:
        sent=r['sent'];ready=r.get('ready')
        blocked+=not ready
        prepared+=not sent and ready
        jev+=(r.get('jev_actual_input') or 0)+(r.get('jev_actual_output') or 0)
        if not sent:continue
        requests+=1
        code=r.get('exit_code');failed+=code not in (None,0);pending+=code is None
        before+=r.get('before_est') or 0;after+=r.get('after_est') or 0
        actual_input=r.get('actual_input')
        if actual_input is not None:
            measured+=1;input_tokens+=actual_input
            output_tokens+=r.get('actual_output') or 0;cached+=r.get('cached') or 0
        duration=row_latency(r) if code==0 else None
        if duration is not None:timed+=1;latency+=duration
        if speed:=row_speed(r):speeds.append(speed)
    return {'requests':requests,'measured_requests':measured,
            'failed_requests':failed,'pending_requests':pending,
            'prepared_requests':prepared,'blocked_requests':blocked,
            'input_tokens':input_tokens,'output_tokens':output_tokens,
            'cached_tokens':cached,'jev_tokens':jev,
            'actual_tokens':input_tokens+output_tokens+jev,'estimated_before':before,'estimated_after':after,
            'estimated_saved':before-after,
            'estimated_reduction_pct':round(100*(before-after)/before,2) if before else None,
            'mean_ms':round(latency/timed,2) if timed else None,'timed_requests':timed,**speed_stats(speeds)}


def service_status(state):
    if (state/'disabled').exists():return 'stopped'
    if not (state/'connection.json').exists():return 'offline'
    try:
        settings=json.loads((state/'connection.json').read_text())
        port=settings.get('port')
        if isinstance(port,bool) or not isinstance(port,int) or not 0<port<65536:return 'offline'
        token=(state/'access-token').read_text().strip()
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/health',headers={'Authorization':'Bearer '+token})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=.5) as response:
            return 'online' if json.load(response).get('service')=='context-gate' else 'offline'
    except (OSError,ValueError,KeyError):return 'offline'


def safe_log(state, name):
    path=state/name
    if not path.is_file():return '暂无记录'
    with path.open('rb') as file:
        file.seek(max(0,path.stat().st_size-30000))
        text=file.read(30000).decode('utf-8',errors='replace')
    return redact_text(text)


def redact_text(text):
    # The generated logs contain numeric metrics and operational exceptions.
    # Still hide credentials if an external program accidentally appends one.
    text=re.sub(r'(?i)(authorization[\s:=]+(?:bearer\s+)?|(?:api[_-]?key|access[_-]?token)["\s:=]+)[^\s,}\"]+',r'\1[REDACTED]',text)
    text=re.sub(r'\b(?:sk-[\w-]{16,}|apik[\w-]{20,})\b','[REDACTED]',text)
    text=re.sub(r'(http://127\.0\.0\.1:\d+/)[\w-]{25,}',r'\1[REDACTED]',text)
    return text


AGENT_INDEX = Path.home() / 'AI记忆/项目/索引.md'


def handoff_overview(index_path=AGENT_INDEX, limit=200):
    """Latest handoff entry per project from the shared agent index.

    Read-only convenience for the workbench view; every excerpt goes through
    the same redaction as the logs. Projects without a readable HANDOFF.md
    are skipped instead of guessed.
    """
    rows=[]
    index=Path(index_path)
    if not index.is_file():return rows
    try:
        lines=index.read_text(errors='replace').splitlines()
    except OSError:
        return rows
    for line in lines:
        stripped=line.strip()
        if not stripped.startswith('|'):continue
        cells=[c.strip() for c in stripped.strip('|').split('|')]
        if len(cells)<3:continue
        name=cells[0]
        if not name or name=='项目' or set(name)<=set(':-— '):continue
        # 路径单元格是 `~/...`（尾注）形态：剥掉反引号与括号尾注再解析。
        root_text=cells[2].replace('`','').split('（')[0].split('；')[0].strip()
        if not root_text.startswith(('~','/')):continue
        root=Path(root_text.replace('~',str(Path.home()),1))
        memory_text=cells[3] if len(cells)>3 else ''
        candidates=[root/'memory/HANDOFF.md', root/'HANDOFF.md']
        mention=re.search(r'([\w./~\-]+HANDOFF\.md)',memory_text)
        if mention:
            hinted=Path(mention.group(1).replace('~',str(Path.home()),1))
            candidates.insert(0,hinted if hinted.is_absolute() else root/hinted)
        handoff=next((p for p in candidates if p.is_file()),None)
        if handoff is None:continue
        try:
            text=handoff.read_text(errors='replace')
        except OSError:
            continue
        block='';heading=''
        for chunk in text.split('\n## '):
            if chunk.startswith('[[') or not chunk.strip():continue
            first=chunk.splitlines()[0].lstrip('#').strip()
            if first.startswith('['):
                block=chunk;heading=first;break
        if not block:continue
        block=redact_text(block)
        def field(label):
            m=re.search(r'\*\*'+label+r'\*\*：(.*)',block)
            return m.group(1).strip() if m else ''
        rows.append({'project':name,'status':cells[1][:80],'handoff':str(handoff),
                     'updated':heading,'done':field('做了什么')[:limit],
                     'state_text':field('当前状态')[:limit],'next':field('下一步')[:limit],
                     'doing':'doing' in block.lower()})
        if len(rows)>=40:break
    return rows


AUDIT_ENTRIES=(
    ('~/.zshrc','shell 配置（Anthropic key）',True),
    ('~/.claude/settings.json','Claude Code 设置（env 指向哨兵）',True),
    ('~/.zcode/v2/config.json','ZCode App 供应商配置（含 apiKey）',True),
    ('~/.codex/auth.json','Codex CLI 凭据',True),
    ('access-token','Gate 服务令牌',False),
    ('connection.json','Gate 连接信息',False),
    ('console-connection.json','控制台连接信息（URL 即凭据）',False),
    ('zcode-watch.py','ZCode 哨兵脚本',False),
    ('zcode-watch-connection.json','ZCode 哨兵连接信息',False),
    ('watch-claude.py','Claude 哨兵脚本',False),
    ('watch-claude-connection.json','Claude 哨兵连接信息',False),
    ('prices.json','价格表',False),
    ('usage-import.py','日志导入器',False),
)


def credential_audit(state):
    """Existence/permission/pointer audit for credential-bearing files.

    Reports booleans, octal modes and bare hosts only — never file contents.
    """
    state=Path(state)
    rows=[]
    for raw,label,inspect_content in AUDIT_ENTRIES:
        path=(Path(raw) if raw.startswith('~') else state/raw).expanduser()
        row={'file':raw,'label':label,'exists':path.is_file(),
             'mode':None,'has_key':None,'target':None,'warn':None}
        if row['exists']:
            mode=path.stat().st_mode & 0o777
            row['mode']=format(mode,'03o')
            if mode & 0o077:
                row['warn']='权限过宽'
            if inspect_content:
                try:
                    text=path.read_text(errors='replace')
                    data=json.loads(text) if path.suffix=='.json' else None
                except (OSError,ValueError):
                    data=None;text=''
                if raw.endswith('settings.json'):
                    env=(data or {}).get('env') or {}
                    base=str(env.get('ANTHROPIC_BASE_URL') or '')
                    row['target']='哨兵(本机)' if base.startswith('http://127.0.0.1') else ('直连' if base else '未配置')
                    row['has_key']=any('TOKEN' in k or 'KEY' in k for k in env) or bool((data or {}).get('apiKeyHelper'))
                elif raw.endswith('config.json'):
                    blob=json.dumps(data or {}).lower()
                    row['has_key']='apikey' in blob
                    row['target']='含本机地址' if '127.0.0.1' in blob else '直连'
                elif raw.endswith('auth.json'):
                    blob=json.dumps(data or {}).lower()
                    row['has_key']=bool(data) and ('token' in blob or 'key' in blob)
                else:
                    row['has_key']=bool(re.search(r'sk-ant|sk-|apik[\w-]{20,}|ANTHROPIC_API_KEY|OPENAI_API_KEY',text))
            elif raw in ('access-token','console-connection.json','zcode-watch-connection.json','watch-claude-connection.json'):
                row['has_key']=True
        elif not raw.startswith('~'):
            row['warn']='缺失'
        rows.append(row)
    return rows


def group_costs(rows, rules, mode=prices.MODE_ACTUAL):
    """Money sums for sent rows. Unpriced models are counted, never guessed."""
    out={'cost_before_usd':0.0,'cost_after_est_usd':0.0,'cost_actual_usd':0.0,'unpriced_requests':0,'unpriced_tokens':0,
         'free_tokens':0,'free_requests':0,'local_router_tokens':0,'local_router_requests':0}
    for r in (x for x in rows if x['sent']):
        platform=r.get('platform')
        pricing_platform=r.get('pricing_platform',platform)
        rule=r['_rule'] if '_rule' in r else prices.price_for(r.get('model'),rules,platform=pricing_platform,mode=mode)
        measured=r.get('actual_input') is not None
        tokens=(r.get('actual_input') or 0)+(r.get('actual_output') or 0) if measured else 0
        if rule is not None and rule['input']==0 and rule['output']==0:
            out['free_requests']+=1
            out['free_tokens']+=tokens
        if platform=='router':
            out['local_router_requests']+=1
            out['local_router_tokens']+=tokens
        if rule is None:
            # A row with no model is pre-tracking legacy data, not a model without a price.
            if r.get('model'):
                out['unpriced_requests']+=1
                out['unpriced_tokens']+=tokens
            continue
        out['cost_before_usd']+=(r.get('before_est') or 0)/1e6*rule['input']
        out['cost_after_est_usd']+=(r.get('after_est') or 0)/1e6*rule['input']
        if measured:
            cost=r['_cost'] if '_cost' in r else prices.row_cost(r.get('model'),r.get('actual_input'),r.get('actual_output'),r.get('cached'),rules,cache_creation=r.get('cache_creation'),platform=pricing_platform,rule=rule,at=r.get('at'))
            out['cost_actual_usd']+=cost or 0
    for key in ('cost_before_usd','cost_after_est_usd','cost_actual_usd'):
        out[key]=round(out[key],6)
    return out


def model_rows(rows, rules, mode=prices.MODE_ACTUAL):
    # Legacy rows with no model get no bucket: the card would be an unpriced "unknown model".
    sent=[r for r in rows if r['sent'] and r.get('model')]
    buckets={};grouped={}
    for r in sent:
        # DeepAI Code keeps one platform total, but Codex / Cursor / direct
        # calls stay in separate model cards so the bill shows which is which.
        access=r.get('client_platform') if r.get('platform')=='deepai' else None
        key=(r['platform'], r.get('model'), access)
        grouped.setdefault(key,[]).append(r)
        b=buckets.setdefault(key,{'platform':r['platform'],'model':key[1],
                                  'requests':0,'measured_requests':0,
                                  'before_est':0,'after_est':0,'actual_input':0,'actual_output':0,'cached':0})
        b['requests']+=1
        b['before_est']+=r.get('before_est') or 0
        b['after_est']+=r.get('after_est') or 0
        if r.get('actual_input') is not None:
            b['measured_requests']+=1
            b['actual_input']+=r.get('actual_input') or 0
            b['actual_output']+=r.get('actual_output') or 0
            b['cached']+=r.get('cached') or 0
    result=[]
    for key,b in sorted(buckets.items(),key=lambda kv:(kv[0][0],kv[0][1] is not None,str(kv[0][1]))):
        b['saved_estimated']=b['before_est']-b['after_est']
        b.update(group_costs(grouped[key],rules,mode))
        b.update(speed_stats([speed for speed in map(row_speed,grouped[key]) if speed]))
        resolved=[r.get('_rule') if '_rule' in r else prices.price_for(r.get('model'),rules,platform=r.get('pricing_platform',r['platform']),mode=mode) for r in grouped[key]]
        b['priced']=all(rule is not None for rule in resolved)
        # Free means priced at $0 (NVIDIA free keys, local deploys, :free tiers),
        # not merely unknown pricing.
        b['free']=all(prices.is_free(rule) for rule in resolved)
        # Keep the public reference visible: an open model's host price is not
        # a manufacturer price, and neither is a receipt for this route.
        b['price_sources']=[]
        if mode==prices.MODE_OFFICIAL:
            for rule in resolved:
                if rule is None or not rule.get('source'):continue
                source={name:rule[name] for name in ('source','source_name','price_basis','verified_at','price_note','input','output','cache_read','cache_write') if name in rule}
                if source not in b['price_sources']:b['price_sources'].append(source)
        b['sources']=sorted({r.get('client_platform',r['platform']) for r in grouped[key]})
        b['original_models']=sorted({r.get('original_model',r['model']) for r in grouped[key]})
        result.append(b)
    return result


def ab_by_platform(comparisons):
    tokens={};pairs={};baseline={}
    for c in comparisons:
        name=c['platform']
        baseline[name]=baseline.get(name,0)+(c['baseline_input'] or 0)
        tokens[name]=tokens.get(name,0)+(c['baseline_input'] or 0)-(c['filtered_input'] or 0)
        pairs[name]=pairs.get(name,0)+1
    return tokens,pairs,baseline


def savings_money(rows, saved_tokens, rules, mode=prices.MODE_ACTUAL):
    """A/B input savings valued at the platform's realized average input rate.

    Only measured, priced rows feed the rate; free platforms rate $0, and a
    platform without measured rows returns None instead of a guess.
    """
    if not saved_tokens:
        return 0.0
    input_cost=0.0;input_tokens=0
    for r in (x for x in rows if x.get('actual_input') is not None):
        rule=r['_rule'] if '_rule' in r else prices.price_for(r.get('model'),rules,platform=r.get('platform'),mode=mode)
        if rule is None:continue
        cost=r['_cost'] if '_cost' in r else prices.row_cost(r.get('model'),r.get('actual_input'),r.get('actual_output'),r.get('cached'),rules,cache_creation=r.get('cache_creation'),platform=r.get('platform'),rule=rule)
        if cost is None:continue
        input_tokens+=r.get('actual_input') or 0
        input_cost+=cost-(r.get('actual_output') or 0)/1e6*rule['output']
    if input_tokens<=0:
        return None
    return round(saved_tokens*(input_cost/input_tokens),6)


def _stream_events(path, max_bytes=262144, max_events=120, with_raw=False):
    """Compact summaries of a dispatched session's stream-json tail: one entry
    per assistant turn / tool result / final result. Only the tail is parsed so
    a multi-hour task cannot bloat the snapshot; indices are tail-relative."""
    try:
        size = path.stat().st_size
        with open(path, 'rb') as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            raw = f.read().decode('utf-8', errors='replace')
    except OSError:
        return []
    lines = raw.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]  # first line of the tail is likely partial
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get('type')
        if kind == 'assistant':
            parts = []
            for block in (d.get('message') or {}).get('content') or []:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'tool_use':
                    inp = block.get('input') or {}
                    brief = inp.get('command') or inp.get('file_path') or inp.get('pattern') or inp.get('prompt') or ''
                    parts.append('工具 ' + str(block.get('name', '')) + ('：' + str(brief)[:70] if brief else ''))
                elif block.get('type') == 'text':
                    txt = str(block.get('text', '')).strip()
                    if txt:
                        parts.append(txt[:70])
            entry = {'k': 'AI', 's': ' ｜ '.join(parts)[:160] or '(空轮)'}
        elif kind == 'user':
            entry = None
            for block in (d.get('message') or {}).get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    c = block.get('content')
                    txt = ''
                    if isinstance(c, list):
                        txt = ' '.join(str(x.get('text', '')) for x in c if isinstance(x, dict))
                    elif isinstance(c, str):
                        txt = c
                    entry = {'k': '结果', 's': txt.replace('\n', ' ')[:110]}
                    break
            if entry is None:
                continue
        elif kind == 'result':
            entry = {'k': '完成', 's': (str(d.get('result') or '')[:110]) + ('（出错）' if d.get('is_error') else '')}
        elif kind == 'item.completed':
            # Newer Codex CLI stream shape: lifecycle events carry an `item`
            # with a subtype; without this branch every step of a task run by
            # the new CLI showed as "no per-turn records".
            item = d.get('item') or {}
            sub = item.get('type')
            if sub == 'agent_message':
                txt = str(item.get('text', '')).strip()
                entry = {'k': 'AI', 's': txt[:160] or '(空轮)'}
            elif sub == 'command_execution':
                entry = {'k': 'AI', 's': ('工具 command：' + str(item.get('command', '')))[:160]}
            elif sub == 'file_change':
                paths = ', '.join(str(c.get('path', '')) for c in item.get('changes') or [] if isinstance(c, dict))
                entry = {'k': 'AI', 's': ('工具 file：' + paths)[:160]}
            elif sub == 'error':
                entry = {'k': '错误', 's': str(item.get('message', ''))[:110]}
            else:
                continue
        elif kind == 'turn.completed':
            usage = d.get('usage') or {}
            brief = '输入 ' + str(usage.get('input_tokens', '–')) + ' · 输出 ' + str(usage.get('output_tokens', '–'))
            entry = {'k': '完成', 's': brief[:110]}
        elif kind == 'turn.failed':
            message = str(((d.get('error') or {}).get('message')) or '')[:110]
            entry = {'k': '失败', 's': message or '(无错误信息)'}
        elif kind == 'error':
            entry = {'k': '错误', 's': str(d.get('message', ''))[:110]}
        else:
            continue
        if with_raw:
            entry['raw'] = line[:16000]
        events.append(entry)
    return events[-max_events:]


def gate_stream_event(state, task_id, index):
    """One raw stream event for the console's detail modal (token-gated GET)."""
    if not re.fullmatch(r'[0-9a-fA-F-]{8,64}', str(task_id)):
        return None
    try:
        i = int(index)
    except (ValueError, TypeError):
        return None
    if i < 0:
        return None
    events = _stream_events(Path(state) / 'gate-tasks' / (str(task_id) + '.stream.jsonl'), with_raw=True)
    if i >= len(events):
        return None
    return events[i]


def request_detail(state, rid):
    """One ledger turn plus its saved timing / provably-linked log sources.

    Exact-id lookup only: unknown or malformed ids are errors, never a guess
    from timestamps. Imported ids may be uuids, hashes or anything else, so the
    id is only length- and control-character-checked. The log layer stays
    honest: a gate-tasks registry named by this id is quoted (the dispatch
    row's id falls back to the task id), anything else means "no saved log".
    """
    state=Path(state)
    rid=str(rid or '')
    if not 0<len(rid)<=200 or any(ord(c)<32 for c in rid):
        raise ValueError('bad id')
    db=state/'tokens.sqlite3'
    if not db.exists():raise KeyError('unknown-id')
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=2) as c:
        c.row_factory=sqlite3.Row
        c.execute('BEGIN')
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'turns' not in tables:raise KeyError('unknown-id')
        row=c.execute('SELECT * FROM turns WHERE id=?',(rid,)).fetchone()
        if row is None:raise KeyError('unknown-id')
        request=dict(row)
        timing=None
        if 'request_timings' in tables:
            found=c.execute('SELECT * FROM request_timings WHERE id=?',(rid,)).fetchone()
            if found is not None:
                timing={k:v for k,v in dict(found).items() if k!='id'}
    display_platform(request)
    ready=request.get('ready')
    request['status']='blocked' if not ready else 'prepared' if not request['sent'] else 'pending' if request.get('exit_code') is None else 'success' if request['exit_code']==0 else 'failed'
    if request.get('before_est') is None and request.get('after_est') is None:
        request['saved_estimated']=None
    else:
        request['saved_estimated']=(request.get('before_est') or 0)-(request.get('after_est') or 0)
    logs=[];notice=''
    registry=state/'gate-tasks'/(rid+'.json')
    if registry.is_file():
        try:meta=json.loads(registry.read_text())
        except (OSError,ValueError):meta=None
        if isinstance(meta,dict):
            has_stream=(state/'gate-tasks'/(rid+'.stream.jsonl')).is_file()
            logs.append({'source':'gate-tasks/'+rid,
                         'summary':'该记录是一次 Gate 派发任务（注册表以本 id 命名）：任务目标、状态与逐轮网关事件见「压缩任务」视图；'
                                   '完整执行日志 sidecar '+('存在，同样在「压缩任务」视图逐行查看。' if has_stream else '不存在。'),
                         'request':str(meta.get('request') or ''),
                         'status':meta.get('status')})
    if not logs:
        notice='这条记录只有用量/耗时数据，未保存可关联的原始执行日志。'
    return {'id':rid,'request':request,'timing':timing,'logs':logs,'notice':notice}


def gate_tasks(state, limit=200):
    """Dispatched compression tasks from gate_run's registry, running first.

    Returns the whole registry (not just the last 24 hours): the console
    filters by category/time client-side, so it needs started_at/ended_at on
    every task regardless of age."""
    folder = Path(state) / 'gate-tasks'
    if not folder.is_dir():
        return []
    items = []
    for path in folder.glob('*.json'):
        try:
            t = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(t, dict) or not t.get('task_id'):
            continue
        pid = t.get('pid')
        alive = False
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except PermissionError:
                alive = True
            except OSError:
                alive = False
        status = t.get('status') if t.get('status') in ('running', 'done', 'failed', 'incomplete', 'declined') else 'running'
        if status == 'running':
            status = 'running' if alive else 'interrupted'
        t['display_status'] = status
        if t.get('pack_archive') and not Path(t.get('output') or '').is_file():
            t['output'] = t['pack_archive']
        task_id = t['task_id']
        if isinstance(task_id, str) and re.fullmatch(r'[0-9a-fA-F-]{8,64}', task_id):
            t['stream'] = _stream_events(folder / (task_id + '.stream.jsonl'))
        else:
            t['stream'] = []
        # registry stores up to 100K chars; cap what one stats payload carries
        if len(t.get('request') or '') > 20000:
            t['request'] = t['request'][:20000]
        items.append(t)
    items.sort(key=lambda t: (t['display_status'] != 'running', -(t.get('started_at') or 0)))
    return items[:limit]


def external_outcomes(state, limit=200):
    """Gate-dispatched task outputs for the library's external entry.

    Only files named by the gate-tasks registry (output/pack_archive) are
    listed; the console never reads a path the registry itself didn't record.
    """
    folder = Path(state) / 'gate-tasks'
    if not folder.is_dir():
        return []
    rows = []
    for path in folder.glob('*.json'):
        try:
            t = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(t, dict) or not t.get('task_id'):
            continue
        out = t.get('output') or t.get('pack_archive') or ''
        if not out or not Path(out).is_file():
            continue
        rows.append({'task_id': t['task_id'], 'root': t.get('root') or '',
                     'platform': t.get('platform') or '', 'goal': str(t.get('request') or '')[:200],
                     'status': t.get('status') or 'running', 'file': out,
                     'started_at': t.get('started_at') or 0, 'ended_at': t.get('ended_at'),
                     'source': 'external'})
    rows.sort(key=lambda r: -r['started_at'])
    return rows[:limit]


def merge_workbench_roots(memory_rows, state, tasks_view=None):
    """工作台数据源合并：共享 Memory OS 进度 + 本机登记项目（projects.json 与 gate 注册表根目录），
    按根目录去重。本机登记的条目标 source='本机登记'，供前端在副标题里分开计数。"""
    known = {r.get('root') for r in memory_rows if r.get('root')}
    extra = []

    def add(root):
        if not root or root in known:
            return
        known.add(root)
        extra.append({'project': Path(root).name, 'root': root, 'status': '本机登记项目',
                      'handoff': '', 'updated': '', 'done': '', 'doing': False,
                      'source': '本机登记',
                      'state_text': '本机已登记，共享 Memory OS 暂无该项目进度', 'next': ''})

    try:
        for root in json.loads((Path(state) / 'projects.json').read_text()):
            if isinstance(root, str):
                add(root)
    except (OSError, ValueError):
        pass
    for task in (tasks_view or []):
        add(task.get('root'))
    return list(memory_rows) + extra


def backboard_billing(state, platform, since, day_end, model, mode):
    """Load verified bill totals and the local rows replaced by those totals."""
    if platform not in ('all', 'router'):
        return []
    try:
        data = json.loads((state / 'backboard-billing.json').read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    bills = []
    seen = set()
    for bill in data:
        if not isinstance(bill, dict) or bill.get('model') != 'backboard/claude-opus-5-5':
            continue
        if model is not None and model != bill['model']:
            continue
        try:
            date = datetime.date.fromisoformat(bill['date'])
            start = datetime.datetime.combine(date, datetime.time.min).timestamp()
            amount = bill['usd']
            requests = bill['requests']
            tokens = bill['tokens']
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
        if start < since or (day_end is not None and start >= day_end):
            continue
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
            continue
        if any(type(n) is not int or n < 0 for n in (requests, tokens)):
            continue
        inputs = bill.get('input_tokens')
        outputs = bill.get('output_tokens')
        cached = bill.get('cached_tokens')
        creation = bill.get('cache_creation_tokens')
        covered_ids = bill.get('covered_ids')
        if any(type(n) is not int or n < 0 for n in (inputs, outputs, cached, creation)):
            continue
        if inputs + outputs != tokens or cached + creation > inputs:
            continue
        if not isinstance(covered_ids, list) or any(not isinstance(rid, str) for rid in covered_ids):
            continue
        identity = (date.isoformat(), bill['model'])
        if identity in seen:
            continue
        seen.add(identity)
        cost = amount if mode == prices.MODE_ACTUAL else prices.row_cost(
            bill['model'], inputs, outputs, cached, state_dir=state,
            cache_creation=creation, platform='router', mode=mode, at=start)
        bills.append({'date':date.isoformat(), 'model':bill['model'], 'usd':amount,
                      'requests':requests, 'tokens':tokens, 'input_tokens':inputs,
                      'output_tokens':outputs, 'cached_tokens':cached, 'cost':cost,
                      'covered_ids':set(covered_ids)})
    return sorted(bills, key=lambda bill: bill['date'], reverse=True)


def merge_backboard_totals(total, rows, bills, mode, model_totals=False):
    """Replace covered estimates with verified totals, including missing cache usage."""
    if not bills:
        return total
    by_id = {row['id']:row for row in rows}
    input_key = 'actual_input' if model_totals else 'input_tokens'
    output_key = 'actual_output' if model_totals else 'output_tokens'
    cache_key = 'cached' if model_totals else 'cached_tokens'
    for bill in bills:
        covered = [by_id[rid] for rid in bill['covered_ids'] if rid in by_id]
        inputs = bill['input_tokens'] - number_sum(covered, 'actual_input')
        outputs = bill['output_tokens'] - number_sum(covered, 'actual_output')
        cached = bill['cached_tokens'] - number_sum(covered, 'cached')
        total[input_key] += inputs
        total[output_key] += outputs
        total[cache_key] += cached
        if 'actual_tokens' in total:
            total['actual_tokens'] += inputs + outputs
        total['local_router_tokens'] += inputs + outputs
        covered_costs = group_costs(covered, {}, mode)
        total['cost_actual_usd'] += (bill['cost'] or 0) - covered_costs['cost_actual_usd']
        total['free_requests'] -= covered_costs['free_requests']
        total['free_tokens'] -= covered_costs['free_tokens']
        total['unpriced_requests'] -= covered_costs['unpriced_requests']
        total['unpriced_tokens'] -= covered_costs['unpriced_tokens']
        if mode == prices.MODE_ACTUAL:
            total['provider_billed_usd'] = total.get('provider_billed_usd', 0) + bill['usd']
        if model_totals:
            total['free'] = bill['cost'] == 0
            total['priced'] = bill['cost'] is not None
    total['cost_actual_usd'] = round(total['cost_actual_usd'], 6)
    total['provider_billed_usd'] = round(total.get('provider_billed_usd', 0), 6)
    return total


def snapshot(state, period='all', platform='all', now=None, health=True, model=None, day=None, cost_mode=None):
    state=Path(state);now=time.time() if now is None else now
    # Every money figure in one payload uses the same mode (persisted toggle
    # unless the caller pins one).
    mode=prices.load_mode(state) if cost_mode is None else prices.normalize_mode(cost_mode)
    if period not in ('all','today','week','month'):raise ValueError('Unknown period')
    today=datetime.datetime.fromtimestamp(now).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
    since={'all':0,'today':today,'week':now-7*86400,'month':now-30*86400}[period]
    # Day drill-down (?day=) scopes the whole snapshot to that day (or month):
    # the only consumer is the chart-click modal, which reads day_recent/day_total.
    # Filtering in SQL keeps the 40k+ row ledger from being fully scanned here.
    day_start=day_end=None
    if day:
        if not re.fullmatch(r'\d{4}-\d{2}(-\d{2})?',day):raise ValueError('Unknown day')
        fmt='%Y-%m' if len(day)==7 else '%Y-%m-%d'
        datetime.datetime.strptime(day,fmt)  # range check; ValueError → route 400
        if len(day)==7:
            y,m=int(day[:4]),int(day[5:7])
            day_start=datetime.datetime(y,m,1).timestamp()
            day_end=datetime.datetime(y+1,1,1).timestamp() if m==12 else datetime.datetime(y,m+1,1).timestamp()
        else:
            d=datetime.date(int(day[:4]),int(day[5:7]),int(day[8:10]))
            nxt=d+datetime.timedelta(days=1)
            day_start=datetime.datetime(d.year,d.month,d.day).timestamp()
            day_end=datetime.datetime(nxt.year,nxt.month,nxt.day).timestamp()
    rows=[];comparisons=[]
    db=state/'tokens.sqlite3'
    if db.exists():
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=2) as c:
            c.row_factory=sqlite3.Row
            c.execute('BEGIN')
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'turns' in tables:
                # 'generic' is the pack endpoint's legacy default label; never reported.
                where="platform<>'generic'";params=[]
                if day_start is not None:
                    where+=' AND at>=? AND at<?';params=[day_start,day_end]
                rows=[dict(r) for r in c.execute('SELECT * FROM turns WHERE '+where+' ORDER BY at DESC',params)]
                timing={r['id']:dict(r) for r in c.execute('SELECT * FROM request_timings')} if 'request_timings' in tables else {}
                for r in rows:
                    if 'ready' not in r:r['ready']=r['sent']
                    r.update({k:v for k,v in timing.get(r['id'],{}).items() if k!='id'})
            if 'comparisons' in tables:
                comparisons=[dict(r) for r in c.execute('SELECT * FROM comparisons')]
    for r in rows: display_platform(r)
    rules=prices.load_rules(state,mode)
    rules={name:prices.price_for(name,rules,mode=mode) for name in {str(r.get('model') or '').lower() for r in rows}}
    for r in rows:
        if 'model' not in r:r['model']=None
        r['status']='blocked' if not r.get('ready') else 'prepared' if not r['sent'] else 'pending' if r.get('exit_code') is None else 'success' if r['exit_code']==0 else 'failed'
        speed=row_speed(r);r['output_tps']=round(speed[0]*1000/speed[1],1) if speed else None
        # Imported rows carry no pack estimates (nothing went through the gate);
        # show those columns as unknown instead of a fake 0.
        if r.get('before_est') is None and r.get('after_est') is None:
            r['saved_estimated']=None
        else:
            r['saved_estimated']=(r.get('before_est') or 0)-(r.get('after_est') or 0)
        # Price each row once; summary/platform/model/series aggregations reuse
        # the stashed rule and cost instead of rescanning prices per subset.
        if r['sent']:
            rule=prices.price_for(r.get('model'),rules,platform=r.get('pricing_platform',r.get('platform')),mode=mode)
            r['_rule']=rule
            if r.get('actual_input') is not None:
                r['_cost']=prices.row_cost(r.get('model'),r.get('actual_input'),r.get('actual_output'),r.get('cached'),rules,cache_creation=r.get('cache_creation'),platform=r.get('pricing_platform',r.get('platform')),rule=rule,mode=mode,at=r.get('at'))
    platforms=sorted({r['platform'] for r in rows})
    if platform!='all':rows=[r for r in rows if r['platform']==platform]
    # Day rows were selected in SQL above; day_recent is still computed before
    # the period filter so the modal ignores the header period like the chart.
    day_recent=None;day_total=None
    if day:
        day_total=len(rows)
        day_recent=public_rows(rows[:300])
    # The daily series ignores the header period filter on purpose: the chart
    # section has its own windows (7天/本月/本年/总计) and a stray 今天
    # filter must not collapse it to a single point again.
    chart_rows = {row['id']:row for row in rows}
    series={}
    for r in (x for x in rows if x['sent']):
        sday=datetime.datetime.fromtimestamp(r['at']).date().isoformat()
        bucket=series.setdefault(sday,{'tokens':0,'cost':0.0,'cached':0,'input':0})
        bucket['tokens']+=(r.get('actual_input') or 0)+(r.get('actual_output') or 0)
        if r.get('actual_input') is not None:
            bucket['input']+=r.get('actual_input') or 0
            bucket['cached']+=min(r.get('cached') or 0,r.get('actual_input') or 0)
            cost=r.get('_cost')
            if cost:bucket['cost']+=cost
    if period!='all':rows=[r for r in rows if r['at']>=since]
    display_names={r['platform'] for r in rows}
    comparisons=[{**c, 'platform':'router' if c['platform']=='zcode' and 'zcode' not in display_names and 'router' in display_names else c['platform']} for c in comparisons]
    ab_tokens,ab_pairs,ab_baseline=ab_by_platform(comparisons)
    groups=[];platform_rows={}
    for r in rows:platform_rows.setdefault(r['platform'],[]).append(r)
    for name,subset in sorted(platform_rows.items()):
        saved=ab_tokens.get(name,0);base=ab_baseline.get(name,0)
        groups.append({'platform':name,**summarize(subset),**group_costs(subset,rules,mode),
                       'ab_saved_tokens':saved,'ab_pairs':ab_pairs.get(name,0),
                       'ab_reduction_pct':round(100*saved/base,2) if base else None,
                       'ab_saved_usd':savings_money(subset,saved,rules,mode) if ab_pairs.get(name) else None})
    before=number_sum(comparisons,'baseline_input');after=number_sum(comparisons,'filtered_input')
    if model is not None:
        # Dedicated per-model detail: the latest rows of this one model, not
        # whatever happens to survive in the shared recent window.
        rows=[r for r in rows if r.get('model')==model]
        recent=public_rows(rows[:500]);memory=None;workbench=None;audit=None;tasks_view=None
    elif day:
        recent=public_rows(rows[:300]);memory=None;workbench=None;audit=None;tasks_view=None
    else:
        recent=public_rows(rows[:300])
        memory=project_rows()
        tasks_view=gate_tasks(state)
        workbench=merge_workbench_roots(memory['rows'],state,tasks_view)
        audit=credential_audit(state)
    bills = backboard_billing(state, platform, max(since, day_start or 0), day_end, model, mode)
    all_bills = backboard_billing(state, platform, day_start or 0, day_end, None, mode)
    summary = {**summarize(rows), **group_costs(rows, rules, mode)}
    summary = merge_backboard_totals(summary, rows, bills, mode)
    models = model_rows(rows, rules, mode)
    group_bills = backboard_billing(state, platform, max(since, day_start or 0), day_end, None, mode)
    router = next((group for group in groups if group['platform'] == 'router'), None)
    if group_bills and router is None:
        router = {'platform':'router', **summarize([]), **group_costs([], rules, mode),
                  'ab_saved_tokens':0, 'ab_pairs':0, 'ab_reduction_pct':None, 'ab_saved_usd':None}
        groups.append(router)
        if 'router' not in platforms:
            platforms.append('router')
    if router is not None:
        merge_backboard_totals(router, platform_rows.get('router', []), group_bills, mode)
    for name in {bill['model'] for bill in bills}:
        model_bills = [bill for bill in bills if bill['model'] == name]
        item = next((item for item in models if item['platform'] == 'router' and item['model'] == name), None)
        if item is None:
            item = {'platform':'router', 'model':name, 'requests':0, 'measured_requests':0,
                    'before_est':0, 'after_est':0, 'actual_input':0, 'actual_output':0,
                    'cached':0, 'sources':['router'], 'price_sources':[], 'original_models':[name],
                    **group_costs([], rules, mode), **speed_stats([])}
            models.append(item)
        merge_backboard_totals(item, rows, model_bills, mode, model_totals=True)
    # The chart has its own date range, independent of the header period.
    # Include covered rows outside that period when replacing its daily sums.
    for bill in all_bills:
        bucket = series.setdefault(bill['date'], {'tokens':0, 'cost':0.0, 'cached':0, 'input':0})
        covered = [chart_rows[rid] for rid in bill['covered_ids'] if rid in chart_rows]
        bucket['tokens'] += bill['tokens'] - number_sum(covered, 'actual_input') - number_sum(covered, 'actual_output')
        bucket['input'] += bill['input_tokens'] - number_sum(covered, 'actual_input')
        bucket['cached'] += bill['cached_tokens'] - number_sum(covered, 'cached')
        bucket['cost'] += (bill['cost'] or 0) - sum(row.get('_cost') or 0 for row in covered)
    return {'updated_at':now,'service':service_status(state) if health else 'offline',
            'state_dir':str(state),'period':period,'platform':platform,'platforms':platforms,
            'cost_mode':mode,
            'summary':summary,
            'by_platform':groups,'by_model':models,
            'unpriced_models':sorted({r['model'] for r in rows if r['sent'] and r.get('model') and r.get('_rule') is None}),
            'prices_file':str(prices.config_path(state)),
            'recent':recent,'day_recent':day_recent,'day_total':day_total,
            'series':[{'day':sday,'tokens':b['tokens'],'cost':round(b['cost'],4),
                       'cached':b['cached'],'input':b['input'],
                       'hitrate':round(100*b['cached']/b['input'],2) if b['input'] else None} for sday,b in sorted(series.items())],
            'workbench':workbench,
    'workbench_error':memory['error'] if memory else None,'audit':audit,'gate_tasks':tasks_view,
            'global_ab':{'pairs':len(comparisons),'before':before,'after':after,'saved':before-after,
                         'reduction_pct':round(100*(before-after)/before,2) if before else None},
            'logs':{'service':safe_log(state,'service.log'),'metrics':safe_log(state,'metrics.jsonl')}}


SNAPSHOT_TTL=30.0
SNAPSHOT_PROBE_SKIP=2.0
_snapshot_cache_lock=threading.Lock()
_snapshot_cache={}
_snapshot_inflight={}

def _file_stamp(path):
    try:
        st=Path(path).stat()
        return (st.st_mtime_ns,st.st_size)
    except OSError:
        return None

def _stats_version(state):
    """Cheap fingerprint of the inputs snapshot() reads. Equal versions ⇒ equal
    output (inputs too costly to probe are bounded by SNAPSHOT_TTL instead)."""
    try:
        state=Path(state);parts=[]
        db=state/'tokens.sqlite3'
        if db.exists():
            with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=2) as c:
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('turns','comparisons','request_timings'):
                    if table in tables:
                        parts.append((table,*c.execute('SELECT COUNT(*),IFNULL(MAX(rowid),0) FROM '+table).fetchone()))
        folder=state/'gate-tasks'
        if folder.is_dir():
            # Task-status writes accompany every real transition; externally
            # killed pids are caught by the SNAPSHOT_TTL backstop instead.
            for path in sorted(folder.glob('*')):
                stamp=_file_stamp(path)
                if stamp:parts.append(('gate-tasks/'+path.name,*stamp))
        for name in ('service.log','metrics.jsonl','connection.json','access-token','disabled','backboard-billing.json'):
            parts.append((name,_file_stamp(state/name)))
        parts.append(('prices',_file_stamp(prices.config_path(state))))
        return tuple(parts)
    except sqlite3.Error:
        return ('probe-error',time.time())

def snapshot_cached(state, period='all', platform='all', model=None, day=None):
    """snapshot() behind a data-version cache with stale-while-revalidate. The
    console polls every five seconds from several clients. Both the version
    probe and recompute run off the request path once a value is cached. Cold
    requests for the same filters share one computation."""
    # The cost mode is part of the key: after a toggle the other mode's cached
    # snapshot must never be served stale-while-revalidate.
    mode=prices.load_mode(state)
    key=(str(state),period,platform,model,day,datetime.datetime.now().strftime('%Y-%m-%d'),mode)
    now=time.monotonic()
    with _snapshot_cache_lock:
        entry=_snapshot_cache.get(key)
        if entry is not None:
            if now-entry.get('checked',entry['at'])>=SNAPSHOT_PROBE_SKIP and not entry.get('running'):
                entry['running']=True
                threading.Thread(target=_snapshot_recompute,args=(state,period,platform,model,day,key,mode),daemon=True).start()
            return entry['data']
        flight=_snapshot_inflight.get(key)
        owner=flight is None
        if owner:
            flight={'done':threading.Event()};_snapshot_inflight[key]=flight
    if not owner:
        flight['done'].wait()
        if 'error' in flight:raise flight['error']
        return flight['data']
    try:
        version=_stats_version(state)
        data=snapshot(state,period,platform,model=model,day=day,cost_mode=mode)
        with _snapshot_cache_lock:
            _snapshot_cache[key]={'version':version,'data':data,'at':time.monotonic()}
            if len(_snapshot_cache)>16:
                oldest=min(_snapshot_cache,key=lambda k:_snapshot_cache[k]['at'])
                del _snapshot_cache[oldest]
        flight['data']=data
        return data
    except BaseException as error:
        flight['error']=error
        raise
    finally:
        with _snapshot_cache_lock:
            _snapshot_inflight.pop(key,None)
            flight['done'].set()

def _snapshot_recompute(state, period, platform, model, day, key, mode=None):
    try:
        version=_stats_version(state)
        with _snapshot_cache_lock:
            entry=_snapshot_cache.get(key)
            if entry is not None and version==entry['version'] and time.monotonic()-entry['at']<SNAPSHOT_TTL:
                entry.update(checked=time.monotonic(),running=False)
                return
        data=snapshot(state,period,platform,model=model,day=day,cost_mode=mode)
    except Exception:
        with _snapshot_cache_lock:
            entry=_snapshot_cache.get(key)
            if entry is not None:entry.update(checked=time.monotonic(),running=False)
        return
    with _snapshot_cache_lock:
        _snapshot_cache[key]={'version':version,'data':data,'at':time.monotonic()}
        if len(_snapshot_cache)>16:
            oldest=min(_snapshot_cache,key=lambda k:_snapshot_cache[k]['at'])
            del _snapshot_cache[oldest]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state-dir',default=os.environ.get('CONTEXT_GATE_STATE','~/.local/state/context-gate'))
    parser.add_argument('--period',default='all',choices=['all','today','week','month'])
    parser.add_argument('--platform',default='all')
    args=parser.parse_args()
    try:print(json.dumps(snapshot(Path(args.state_dir).expanduser(),args.period,args.platform),ensure_ascii=False))
    except (OSError,sqlite3.Error,ValueError) as error:
        print(json.dumps({'error':'读取统计失败：'+type(error).__name__},ensure_ascii=False));return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
