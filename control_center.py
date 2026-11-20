"""Persistent local task worker and bounded agent tools. Standard library only."""
import argparse
import base64
import contextlib
import difflib
import fcntl
import hashlib
import json
import math
import os
import pwd
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import urllib.request

from console_search import public, search
from context_gate import SECRET_NAMES
from gate_run import command as gate_command

PROJECT=Path(__file__).resolve().parent
# launchd→壳→后端 链路会丢 USER/LOGNAME；claude CLI 没有 USER 会把已登录误报成未登录，导致「打开原生 App」反复弹登录。
def ensure_user_env(env=os.environ):
    if not env.get('USER'):
        try: env['USER']=pwd.getpwuid(os.getuid()).pw_name
        except KeyError: return env
    if not env.get('LOGNAME'): env['LOGNAME']=env['USER']
    return env
ensure_user_env()
STATE=Path(os.environ.get('CONTEXT_GATE_STATE','~/.local/state/context-gate')).expanduser()
EXCLUDE={'.git','node_modules','venv','.venv','__pycache__','work','.openai'}
TERMINAL={'pending_review','accepted','failed','stopped','interrupted','validation_failed'}
CHECKS={'tests':['python3','-m','unittest','discover','-s','tests','-q'],
        'git_status':['git','status','--short']}
# 2026-10-07：Codex models_cache.json + https://learn.chatgpt.com/docs/models；
# Claude https://code.claude.com/docs/en/model-config#adjust-effort-level。
# ultra / ultracode 是原生客户端的协作模式，不是 API 的 reasoning.effort。
MODEL_CATALOG={'codex':['gpt-6.1-sol','gpt-6-astra','gpt-6-sol','gpt-6-luna','gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna','gpt-5.5'],
               'claude':['sonnet','haiku','opus','fable'],'zcode':['zcode']}
REASONING_BASE=('low','medium','high','xhigh','max')
MODEL_EFFORTS={'codex':{m:REASONING_BASE+('ultra',) for m in ('gpt-6.1-sol','gpt-6-astra','gpt-6-sol','gpt-5.6-sol','gpt-5.6-terra')},
               'claude':{m:REASONING_BASE+('ultracode',) for m in ('sonnet','opus','fable')},
               'zcode':{'zcode':('native',)}}
MODEL_EFFORTS['codex'].update({'gpt-6-luna':REASONING_BASE,'gpt-5.6-luna':REASONING_BASE,'gpt-5.5':REASONING_BASE[:-1]})
MODEL_EFFORTS['claude']['haiku']=('native',)
REASONING_ALIAS={'light':'low','mid':'medium'}

def reasoning_tiers(platform,model):
    if not isinstance(platform,str) or not isinstance(model,str):return ()
    return MODEL_EFFORTS.get(platform,{}).get(model,())

def claude_effort_args(effort):
    return ['--settings',json.dumps({'ultracode':effort=='ultracode'})]+([] if effort=='native' else ['--effort',effort])
CLAUDE_LOGIN_HINT='命令行版 Claude 还没登录（App 的登录和它互不相通）。已自动弹出登录窗口，完成一次授权后重发即可。'
RESUME_NOTE='额度保护已解除。请在当前会话继续原任务未完成工作，先核对已有修改，不重复已完成步骤。'
_login_cache={'at':0.0,'state':None}
_login_pop={'at':0.0}

def claude_login_state(max_age=120):
    """Cheap factual login probe for the claude CLI; cached to stay off the hot path.

    Probe failures (slow CLI, bad output) return {'unknown': True} instead of a
    verdict — callers must fail open and let the real command report its own error.
    """
    now=time.time()
    if _login_cache['state'] is not None and now-_login_cache['at']<max_age:return _login_cache['state']
    try:
        result=subprocess.run(['claude','auth','status'],capture_output=True,text=True,timeout=30)
        try:state=json.loads(result.stdout)
        except ValueError:state={'unknown':True}
    except (OSError,subprocess.SubprocessError):state={'installed':False,'unknown':True}
    _login_cache.update(at=now,state=state)
    return state

def open_claude_login():
    """Pop a visible Terminal window running `claude auth login`; at most one per 2 minutes."""
    if time.time()-_login_pop['at']<120:return
    _login_pop['at']=time.time()
    try:
        subprocess.Popen(['/usr/bin/osascript','-e','tell application "Terminal" to do script "claude auth login"'],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError:pass


def identity(data):
    return {'platform':{'codex':'gpt'}.get(data.get('platform'),data.get('platform','unknown')),
            'session_id':data.get('session_id') or data.get('id') or data.get('task_id') or 'unavailable',
            'session_kind':'native' if data.get('session_id') else 'control_center',
            'model':data.get('actual_model') or data.get('model') or data.get('provider') or 'unavailable',
            'model_verified':bool(data.get('actual_model')),
            'reasoning':data.get('reasoning','unavailable')}


def audit(state,operation,data,**fields):
    path=Path(state)/'operations.jsonl'
    with path.open('a') as out:
        fcntl.flock(out,fcntl.LOCK_EX)
        os.chmod(path,0o600)
        out.write(json.dumps(public({'time':time.time(),'operation':operation,**identity(data),**fields}),ensure_ascii=False)+'\n')


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def digest(path):
    if not path.exists():return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def usage_counts(u,platform):
    if not isinstance(u,dict) or not any(k in u for k in ('input_tokens','output_tokens')):return None
    fields=('input_tokens','output_tokens','cached_input_tokens','cache_read_input_tokens','cache_creation_input_tokens','cache_write_input_tokens')
    if any(type(u[k]) is not int or u[k]<0 for k in fields if k in u):return None
    def count(name):
        n=u.get(name,0);return n if type(n) is int and n>=0 else 0
    cached=count('cache_read_input_tokens') if platform=='claude' else count('cached_input_tokens')
    written=count('cache_creation_input_tokens') if platform=='claude' else count('cache_write_input_tokens')
    inputs=count('input_tokens')+(cached+written if platform=='claude' else 0)
    return {'input_tokens':inputs,'output_tokens':count('output_tokens'),'cached_input_tokens':cached,'cache_write_input_tokens':written}

def usage_summary(values,cost=None,final=False,source='native_event',scope='task'):
    if not values:return None
    result={k:sum(v[k] for v in values) for k in ('input_tokens','output_tokens','cached_input_tokens','cache_write_input_tokens')}
    amount=cost if type(cost) in (int,float) and math.isfinite(cost) and cost>=0 else None
    result.update(total_tokens=result['input_tokens']+result['output_tokens'],reported_usd=amount,final=final,source=source,scope=scope)
    return result


def image_mime(raw):
    return ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
            'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
            'image/gif' if raw.startswith((b'GIF87a',b'GIF89a')) else
            'image/webp' if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP' else None)


def json_objects(text):
    """Yield JSON objects from a stream that may be pretty-printed (zcode events
    span multiple lines) or line-delimited; garbage between objects is skipped."""
    decoder=json.JSONDecoder();i=0;n=len(text)
    while i<n:
        while i<n and text[i] not in '{[':i+=1
        if i>=n:break
        try:event,end=decoder.raw_decode(text,i)
        except ValueError:i+=1;continue
        yield event;i=end


def preview_artifact(root,item,relative,offset=0):
    file=root/relative
    if not file.resolve().is_relative_to(root.resolve()):raise ValueError('成果路径越界')
    if type(offset) is not int or offset<0:raise ValueError('翻页位置无效')
    with file.open('rb') as stream:raw=stream.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('文字预览每份最多8MB，未截断内容')
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('成果已变化')
    mime=image_mime(raw)
    if mime:
        if len(raw)>2_000_000:raise ValueError('图片预览每份最多2MB')
        if offset:raise ValueError('图片无需翻页')
        return {'path':relative,'kind':'image','data_url':'data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii'),
                'offset':0,'next_offset':None,'sha256':item['sha256']}
    try:content=raw.decode('utf-8')
    except UnicodeError:raise ValueError('此成果为二进制文件，暂不支持文字预览') from None
    if '\x00' in content:raise ValueError('此成果不是文字文件')
    if offset>len(content):raise ValueError('翻页位置超出内容')
    return {'path':relative,'kind':'text','content':public(content[offset:offset+32000]),'offset':offset,'total':len(content),
            'next_offset':offset+32000 if len(content)>offset+32000 else None,'sha256':item['sha256']}

def failure_category(data):
    """Classify a task failure from recorded evidence only; unknown stays unknown.

    Categories name the fact (which error signature was recorded), never the
    inferred root cause beyond it — the console shows the raw error alongside.
    """
    if not isinstance(data,dict):return None
    status=data.get('status');error=str(data.get('error') or '')
    if status in ('starting','running'):return '仍在执行，暂无失败事实'
    if status=='validation_failed':return '验证未通过（项目检查失败），执行本身已完成'
    if status=='stopped':return '已被手动停止'
    if status=='pending_review' and not error:return None
    low=error.lower()
    if not error and status=='failed':return '进程退出非零，无错误原文'
    if 'not supported' in low or 'unsupported' in low:return '当前登录不支持所选模型'
    if any(k in low for k in ('401','403','unauthorized','login','logged in','认证','登录','apikey','api key')):return '登录/凭据被拒'
    if any(k in low for k in ('quota','credit','billing','usage limit','insufficient','rate limit','额度','限流')):return '额度或限流'
    if any(k in low for k in ('timeout','timed out','connection','refused','unreachable','network','getaddrinfo')):return '网络或本地服务连接'
    if error:return '执行报错（见错误原文）'
    return None


class Center:
    _before_commit=None  # test seam only
    def __init__(self,state=STATE,roots=None):
        self.state=Path(state).resolve()
        if roots is None:
            try:stored=json.loads((self.state/'projects.json').read_text())
            except (OSError,ValueError):stored=[]
            roots=[PROJECT]+[p for p in stored if isinstance(p,str)]
        self.roots=[Path(p).resolve() for p in roots]
        self.folder=self.state/'center-tasks'
        self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        self._usage_cache={}

    def add_root(self,body):
        """Let the owner authorize one more project folder; persisted, never guessed."""
        raw=str(body.get('path') or '').strip()
        path=Path(os.path.expanduser(raw)).resolve() if raw.startswith(('~','/')) else None
        if path is None or not path.is_dir():raise ValueError('请填写一个真实存在的文件夹完整路径（访达里右键文件夹→按住 option→「拷贝…为路径名称」）')
        home=Path.home().resolve()
        if path!=home and not path.is_relative_to(home):raise ValueError('为了安全，只能添加你用户目录里的文件夹')
        if any(SECRET_NAMES.search(x) for x in path.parts):raise ValueError('路径里有敏感字样（密钥/凭据等），不允许添加')
        if path in self.roots:return {'roots':[str(p) for p in self.roots],'added':False}
        if len(self.roots)>=50:raise ValueError('项目太多了，先清理不用的再加')
        self.roots.append(path)
        write_json(self.state/'projects.json',[str(p) for p in self.roots if p!=PROJECT])
        audit(self.state,'add_project_folder',{'platform':'local','session_id':'local','model':'local'},path=str(path))
        return {'roots':[str(p) for p in self.roots],'added':True}

    def pick_root(self,body=None):
        """Owner picks a folder in the system dialog; the result passes the add_root checks."""
        try:
            done=subprocess.run(['/usr/bin/osascript','-e','tell me to activate','-e','POSIX path of (choose folder with prompt "选择项目文件夹")'],
                capture_output=True,text=True,timeout=300)
        except subprocess.TimeoutExpired:raise ValueError('选择文件夹超时，请重试')
        if done.returncode:
            if '-128' in done.stderr:return {'roots':[str(p) for p in self.roots],'cancelled':True}
            raise ValueError('没能打开文件夹选择框，请重试或稍后再试')
        data=self.add_root({'path':done.stdout.strip()})
        data['path']=str(Path(done.stdout.strip()).resolve())
        return data

    def usage_settings(self,body=None):
        path=self.state/'usage-alert.json'
        if body is None:return json.loads(path.read_text()) if path.exists() else {'enabled':True,'threshold':100000}
        threshold=body.get('threshold');enabled=body.get('enabled')
        if type(threshold) is not int or not 1000<=threshold<=100000000 or type(enabled) is not bool:raise ValueError('提醒门槛需为1000至100000000的整数')
        settings={'enabled':enabled,'threshold':threshold};write_json(path,settings);return settings

    def usage(self,data):
        path=self.path(data['task_id']).parent/'events.jsonl'
        if not path.exists():return None
        stat=path.stat();key=(str(path),stat.st_mtime_ns,stat.st_size,data['platform'])
        if key in self._usage_cache:return self._usage_cache[key]
        totals=[];messages={};cost=None;final=False
        with path.open(errors='replace') as log:text=log.read()
        if data['platform']=='zcode':events=list(json_objects(text))
        else:
            events=[]
            for line in text.splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if isinstance(event,dict):events.append(event)
        for event in events:
            if not isinstance(event,dict):continue
            if data['platform']=='codex' and event.get('type')=='turn.completed':
                u=usage_counts(event.get('usage'),data['platform'])
                if u is not None:totals=[u];final=True
            if data['platform']=='zcode':
                # zcode 事件是多行 JSON 且字段是驼峰：response 为答复文本，
                # usage 为该轮供应商实测（取最后一次作为整任务总量）。
                u=event.get('usage')
                if isinstance(u,dict) and isinstance(u.get('inputTokens'),int) and isinstance(u.get('outputTokens'),int):
                    totals=[{'input_tokens':u['inputTokens'],'output_tokens':u['outputTokens'],
                             'cached_input_tokens':u.get('cacheReadTokens') or 0,
                             'cache_write_input_tokens':u.get('cacheWriteTokens') or 0}];final=True
            if data['platform']=='claude':
                message=event.get('message')
                if event.get('type')=='assistant' and isinstance(message,dict) and isinstance(message.get('id'),str):
                    u=usage_counts(message.get('usage'),data['platform'])
                    if u is not None:messages[message['id']]=u
                if event.get('type')=='result':
                    u=usage_counts(event.get('usage'),data['platform'])
                    if u is not None:totals=[u];final=True
                    amount=event.get('total_cost_usd')
                    if type(amount) in (int,float) and math.isfinite(amount) and amount>=0:cost=amount
        values=totals or list(messages.values())
        result=usage_summary(values,cost,final,'native_task_log','native_thread_total' if data['platform']=='codex' else 'task')
        # Keep only the latest snapshot per log; never persist or print raw model events.
        for old in list(self._usage_cache):
            if old[0]==str(path):del self._usage_cache[old]
        self._usage_cache[key]=result
        return result

    def root(self,value):
        path=Path(value).resolve()
        if path not in self.roots:raise ValueError('项目未授权')
        return path

    def templates(self):
        path=self.state/'task-templates.json'
        return json.loads(path.read_text()) if path.exists() else []

    def save_template(self,body):
        name=body.get('name');goal=body.get('goal');acceptance=body.get('acceptance','')
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('常用任务名称需为1至80字')
        if not isinstance(goal,str) or not 1<=len(goal.strip())<=12000:raise ValueError('请先填写任务目标')
        if not isinstance(acceptance,str) or len(acceptance)>4000:raise ValueError('验收条件最多4000字')
        if body.get('platform') not in ('codex','claude','zcode'):raise ValueError('执行平台无效')
        root=str(self.root(body.get('root','')))
        item={'id':str(uuid.uuid4()),'name':name.strip(),'root':root,'platform':body['platform'],
              'goal':goal.strip(),'acceptance':acceptance,'checks':['tests'] if body.get('tests') is True else []}
        with (self.state/'task-templates.lock').open('a') as lock:
            os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
            rows=self.templates()
            if len(rows)>=100:raise ValueError('最多保存100个常用任务，请先移除不需要的任务')
            write_json(self.state/'task-templates.json',rows+[item])
        return item

    def delete_template(self,body):
        with (self.state/'task-templates.lock').open('a') as lock:
            os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
            rows=self.templates();remaining=[x for x in rows if x['id']!=body.get('id')]
            if len(rows)==len(remaining):raise ValueError('常用任务不存在')
            write_json(self.state/'task-templates.json',remaining)
        return {'ok':True}

    def file(self,root,relative):
        root=self.root(root)
        if not isinstance(relative,str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('仅允许项目内相对路径')
        path=root/relative
        if not path.resolve().is_relative_to(root) or any(SECRET_NAMES.search(x) for x in path.parts):
            raise ValueError('路径越界或为敏感文件')
        if any(part in EXCLUDE for part in Path(relative).parts):raise ValueError('路径不可操作')
        return path

    def path(self,tid):
        if not re.fullmatch(r'[a-f0-9-]{36}',tid):raise ValueError('无效任务编号')
        return self.folder/tid/'task.json'

    def get(self,tid):
        data=json.loads(self.path(tid).read_text())
        if data['status'] in ('starting','running') and data.get('worker_pid'):
            try:os.kill(data['worker_pid'],0)
            except OSError:data['status']='interrupted'
        return data

    def list(self):
        rows=[]
        for path in self.folder.glob('*/task.json'):
            try:
                data=self.get(path.parent.name)
                try:data['usage']=self.usage(data)
                except OSError:data.update(usage=None,usage_error='用量日志暂不可读')
                rows.append(data)
            except (ValueError,OSError):pass
        return sorted(rows,key=lambda r:-r['started_at'])

    def validate_request(self,body):
        if not isinstance(body,dict) or not isinstance(body.get('root'),str):raise ValueError('请选择授权项目')
        root=str(self.root(body['root']));goal=body.get('goal');acceptance=body.get('acceptance','')
        platform=body.get('platform','codex');checks=body.get('checks',[])
        if not isinstance(goal,str) or not 1<=len(goal.strip())<=12000 or platform not in ('codex','claude','zcode'):raise ValueError('任务目标或平台无效')
        if not isinstance(acceptance,str) or len(acceptance)>4000:raise ValueError('验收条件过长')
        if not isinstance(checks,list) or any(not isinstance(x,str) or x not in CHECKS for x in checks):raise ValueError('未知验证动作')
        model=body.get('model') or ('gpt-6-sol' if platform=='codex' else 'sonnet' if platform=='claude' else None)
        if platform!='zcode' and model not in MODEL_CATALOG[platform]:raise ValueError('请选择此平台已支持模型')
        tiers=reasoning_tiers(platform,model)
        reasoning=body.get('reasoning','medium' if 'medium' in tiers else 'native')
        if platform=='zcode':
            reasoning='unavailable (native interface)'
        else:
            reasoning=REASONING_ALIAS.get(str(reasoning).lower(),reasoning)
            if reasoning not in tiers:raise ValueError('此模型推理档位无效，可用：'+'/'.join(tiers))
        parent=body.get('parent')
        if parent:
            if not isinstance(parent,str):raise ValueError('接续任务编号无效')
            old=self.get(parent)
            if old['root']!=root or old['platform']!=platform:raise ValueError('接续项目或平台不一致')
        return {'root':root,'goal':goal.strip(),'acceptance':acceptance.strip(),'platform':platform,
                'checks':checks,'model':model,'reasoning':reasoning,'parent':parent}

    def create(self,body,launch=True,schedule_id=None):
        with (self.state/'submission.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            return self._create(body,launch,schedule_id)

    def _create(self,body,launch=True,schedule_id=None):
        body=self.validate_request(body);root=Path(body['root'])
        goal=body['goal'];platform=body['platform'];acceptance=body['acceptance'];checks=body['checks']
        if any(r['root']==str(root) and r['status'] in ('starting','running') for r in self.list()):
            raise ValueError('此项目已有任务执行，先停止或等待结束')
        parent=body.get('parent')
        session=None
        if parent:
            old=self.get(parent)
            if old['root']!=str(root) or old['platform']!=platform:raise ValueError('接续项目或平台不一致')
            session=old.get('session_id')
            if platform=='zcode':session=None
        tid=str(uuid.uuid4());bundle=self.folder/tid;bundle.mkdir(mode=0o700)
        data={'task_id':tid,'root':str(root),'goal':goal,'acceptance':acceptance,'platform':platform,
              'started_at':time.time(),'status':'starting','parent':parent,'session_id':session,
              'checks':checks,'model':body['model'],'reasoning':body['reasoning'],'final_file':str(bundle/'final.txt'),'log_file':str(bundle/'events.jsonl')}
        if schedule_id:data['schedule_id']=schedule_id
        write_json(bundle/'task.json',data)
        audit(self.state,'create_task',data,task_id=tid)
        if launch:
            proc=self._spawn(tid,bundle)
            data['worker_pid']=proc.pid;write_json(bundle/'task.json',data)
            threading.Thread(target=proc.wait,daemon=True).start()
        return data

    def _spawn(self,tid,bundle):
        with (bundle/'worker.log').open('ab') as log:
            return subprocess.Popen([sys.executable,str(PROJECT/'control_center.py'),'worker','--state',str(self.state),'--task',tid],
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)

    @contextlib.contextmanager
    def _submission(self):
        """Lock order is fixed: submission.lock -> quota journal -> SQLite. Never nest submission locks."""
        with (self.state/'submission.lock').open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            yield

    def stop(self,tid,quota_claim=None):
        """quota_claim=None is a manual stop: it revokes an owned pause claim even when the task is already stopped."""
        with self._submission():
            data=self.get(tid)
            if quota_claim is None:self._revoke_claim(tid)
            if data['status'] not in ('starting','running'):return data
            if quota_claim is not None:self._claim_pending(tid,quota_claim)  # claim persisted before the stop request
            marker=self.path(tid).parent/'stop';marker.touch(mode=0o600)
            audit(self.state,'stop_task',data,task_id=tid,quota_pause=quota_claim is not None)
            return {'task_id':tid,'status':'stop_requested'}

    def quota_claim(self,tid):
        """Owned-pause claim file for one task; None when never claimed. Not written by the worker."""
        try:return json.loads((self.path(tid).parent/'quota-claim.json').read_text())
        except FileNotFoundError:return None
        except (OSError,ValueError):return {'state':'corrupt'}

    def _write_claim(self,tid,claim):
        write_json(self.path(tid).parent/'quota-claim.json',claim)

    def _claim_pending(self,tid,quota):
        current=self.quota_claim(tid)
        if current and current.get('state')!='pending':return  # revoked/consumed/corrupt claims are never revived
        if current and current.get('claim_id')==quota['claim_id']:return
        self._write_claim(tid,{'claim_id':quota['claim_id'],'cycle_id':quota['cycle_id'],'state':'pending','fingerprint':quota.get('fingerprint',{})})

    def _revoke_claim(self,tid):
        current=self.quota_claim(tid)
        if current and current.get('state')=='pending':
            current['state']='revoked';self._write_claim(tid,current)

    def _quota_child(self,claim_id):
        for path in self.folder.glob('*/task.json'):
            try:data=json.loads(path.read_text())
            except (OSError,ValueError):continue
            if (data.get('quota_resume') or {}).get('claim_id')==claim_id:return path.parent.name,data
        return None

    def quota_state(self,tid,claim):
        """Read-only classification of one owned pause before any dispatch."""
        if self._quota_child(claim['claim_id']) is not None:return 'dispatched'
        current=self.quota_claim(tid)
        if not current or current.get('claim_id')!=claim['claim_id'] or current.get('cycle_id')!=claim['cycle_id']:return 'mismatch'
        if current.get('state')=='revoked':return 'revoked'
        return 'pending' if current.get('state')=='pending' else 'mismatch'

    def resume_quota(self,tid,claim,busy=None):
        """Dispatch at most one continuation for an owned pause. Never re-dispatches; unknown outcomes are 'uncertain'."""
        with self._submission():
            return self._resume_quota(tid,claim,busy)

    def _resume_quota(self,tid,claim,busy):
        found=self._quota_child(claim['claim_id'])
        if found is not None:
            child_id,child=found
            if child.get('worker_pid') or child.get('status') not in ('starting','uncertain'):return {'status':'resumed','resume_ref':child_id}
            # Persisted continuation without a confirmed worker: outcome unknown, never retried (C4/D14).
            child.update(status='uncertain',error='续跑任务已落盘，但未确认 worker 启动，请人工检查')
            write_json(self.path(child_id),child)
            return {'status':'uncertain','resume_ref':child_id}
        try:parent=self.get(tid)
        except (OSError,ValueError):return {'status':'attention','reason':'task_unreadable'}
        current=self.quota_claim(tid)
        if not current or current.get('claim_id')!=claim['claim_id'] or current.get('cycle_id')!=claim['cycle_id']:return {'status':'attention','reason':'ledger_mismatch'}
        if current.get('state')=='revoked':return {'status':'revoked'}
        if current.get('state')!='pending':return {'status':'attention','reason':'claim_consumed'}
        if parent['status'] in ('starting','running'):return {'status':'waiting','reason':'stop_unconfirmed'}
        if parent['status']!='stopped':return {'status':'attention','reason':'not_stopped'}
        if parent['platform']=='zcode':return {'status':'attention','reason':'zcode_unsupported'}  # D2: no stable session to resume
        fp=current.get('fingerprint') or {}
        launched='pid' in parent
        if launched and not parent.get('session_id'):return {'status':'attention','reason':'no_session'}
        if any(fp.get(k)!=parent.get(k) for k in ('platform','model','reasoning')) or fp.get('root')!=parent['root']:return {'status':'attention','reason':'fingerprint_changed'}
        if fp.get('session_id') is not None and fp['session_id']!=parent.get('session_id'):return {'status':'attention','reason':'fingerprint_changed'}
        if fp.get('session_id') is None and parent.get('session_id') is not None and not launched:return {'status':'attention','reason':'fingerprint_changed'}
        if any(t['root']==parent['root'] and t['task_id']!=tid and t['status'] in ('starting','running','queued') for t in self.list()) or (busy is not None and busy(parent['root'])):
            return {'status':'waiting','reason':'project_busy'}
        if self._before_commit is not None:self._before_commit()  # test seam: lets a test revoke between read and commit
        current=self.quota_claim(tid)
        if not current or current.get('claim_id')!=claim['claim_id'] or current.get('state')!='pending':
            return {'status':'revoked'} if current and current.get('state')=='revoked' else {'status':'attention','reason':'claim_changed'}
        session=parent.get('session_id') if launched else None
        child_id=str(uuid.uuid4());bundle=self.folder/child_id;bundle.mkdir(mode=0o700)
        goal=RESUME_NOTE+'\n原任务目标：\n'+parent['goal'] if session else parent['goal']
        data={'task_id':child_id,'root':parent['root'],'goal':goal,'acceptance':parent['acceptance'],'platform':parent['platform'],
              'started_at':time.time(),'status':'starting','parent':tid,'session_id':session,'checks':parent['checks'],
              'model':parent['model'],'reasoning':parent['reasoning'],'final_file':str(bundle/'final.txt'),'log_file':str(bundle/'events.jsonl'),
              'quota_resume':{'claim_id':claim['claim_id'],'cycle_id':claim['cycle_id'],'parent':tid}}
        write_json(bundle/'task.json',data)
        audit(self.state,'quota_resume_task',data,task_id=child_id,parent=tid)
        self._write_claim(tid,dict(current,state='consumed',resume_ref=child_id))  # one claim, one continuation
        try:proc=self._spawn(child_id,bundle)
        except Exception:
            data.update(status='uncertain',error='续跑任务启动失败，未确认是否已开始，请人工检查')
            write_json(bundle/'task.json',data)
            return {'status':'uncertain','resume_ref':child_id}
        data['worker_pid']=proc.pid;write_json(bundle/'task.json',data)
        threading.Thread(target=proc.wait,daemon=True).start()
        return {'status':'resumed','resume_ref':child_id}

    def accept(self,tid):
        data=self.get(tid)
        if data['status']!='pending_review':raise ValueError('仅验证通过且待验收的任务可确认')
        data.update(status='accepted',accepted_at=time.time());write_json(self.path(tid),data)
        audit(self.state,'accept_task',data,task_id=tid)
        return data

    def artifact(self,tid,relative,offset=0):
        data=self.get(tid)
        self.root(data['root'])
        item=next((x for x in data.get('artifacts',[]) if x['path']==relative),None)
        if item is None:raise ValueError('成果未登记')
        return preview_artifact(self.path(tid).parent/'artifacts',item,relative,offset)

    def diagnostics(self):
        rows=[]
        for platform in ('codex','claude','zcode'):
            executable=shutil.which(platform) if platform!='zcode' else (Path('/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs').is_file())
            recent=next((x for x in self.list() if x['platform']==platform),None)
            status='入口可用，登录及额度需执行验证' if executable else '未找到执行入口'
            if platform=='claude' and executable:
                login=claude_login_state()
                if login.get('installed') is False:status='命令行版未安装'
                elif not login.get('loggedIn'):status='命令行版未登录（与 App 分开）；到下方「控制」点「修复 Claude 登录」'
            rows.append({'name':platform,'installed':bool(executable),
                         'status':status,
                         'category':failure_category(recent),
                         'last_task':public({k:recent.get(k) for k in ('status','error','model','session_id')}) if recent else None})
        ollama_url=os.environ.get('CONTEXT_GATE_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
        try:
            with urllib.request.urlopen(ollama_url+'/api/tags',timeout=3) as response:
                names=[str(x.get('name','')) for x in json.load(response).get('models',[]) if x.get('name')]
            pref=[n for n in names if 'qwen' in n.lower() and '14b' in n.lower()]
            picked=pref[0] if pref else (names[0] if names else '')
            status='本地模型在线：'+picked if picked else '本地 Ollama 在线，尚未拉取模型'
        except Exception:status='本地 Ollama 未连接（可选服务，默认 '+ollama_url+'）'
        recent=[]
        for path in (self.state/'butler').glob('*.json'):
            try:recent.append(json.loads(path.read_text()))
            except (ValueError,OSError):pass
        last=max(recent,key=lambda x:x.get('started_at',0),default={})
        rows.append({'name':'管家','status':status,'category':failure_category({'status':last.get('status'),'error':last.get('error')}),
                     'last_error':public(last.get('error')),
                     'last_status':last.get('status'),'checked_at':time.time()})
        return {'connections':rows,'local_fallback':'按用户要求保留入口，暂未接入'}

    def archive_selection(self,tid,relative):
        data=self.get(tid);project=self.root(data['root'])
        item=next((x for x in data.get('artifacts',[]) if x['path']==relative),None)
        if item is None:raise ValueError('成果未登记')
        return project,self.path(tid).parent/'artifacts',item

    def compare(self,body,groups=None):
        sides=[];roots=[]
        for key in ('left','right'):
            selection=body.get(key)
            if not isinstance(selection,dict):raise ValueError('请选择两份归档成果')
            tid=selection.get('task');relative=selection.get('path')
            if not isinstance(tid,str) or not isinstance(relative,str):raise ValueError('成果选择无效')
            source=selection.get('source','center')
            if source not in ('center','group') or (source=='group' and groups is None):raise ValueError('成果来源无效')
            owner=groups if source=='group' else self
            project,root,item=owner.archive_selection(tid,relative);roots.append(project)
            file=root/relative
            if Path(relative).is_absolute() or '..' in Path(relative).parts or not file.resolve().is_relative_to(root.resolve()):raise ValueError('成果路径越界')
            with file.open('rb') as stream:raw=stream.read(2000001)
            if len(raw)>2000000:raise ValueError('图片对比每份最多2MB；文字最多128KB')
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('归档成果已变化，请重新核对')
            mime=image_mime(raw)
            side={'task':tid,'source':source,'path':relative,'sha256':item['sha256']}
            if mime:side.update(kind='image',data_url='data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii'))
            else:
                if len(raw)>128000:raise ValueError('文字对比每份最多128KB，请使用成果分页预览查看较大文件')
                try:text=raw.decode('utf-8')
                except UnicodeError:raise ValueError('仅支持文字及PNG、JPEG、GIF、WebP图片') from None
                if '\x00' in text:raise ValueError('此成果不是文字文件')
                side.update(kind='text',content=public(text))
            sides.append(side)
        if roots[0]!=roots[1]:raise ValueError('请选择同一项目的两份成果')
        return {'left':sides[0],'right':sides[1],'equal':sides[0]['sha256']==sides[1]['sha256']}

    def changes(self,tid):
        data=self.get(tid);bundle=self.path(tid).parent;root=self.root(data['root']);diffs=[]
        for change in data.get('changes',[]):
            path=self.file(str(root),change['path']);old=bundle/'before'/change['path']
            before=old.read_text(errors='replace') if old.exists() else ''
            after=path.read_text(errors='replace') if path.exists() else ''
            diffs.append({'path':change['path'],'diff':public(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before',tofile='current'))[:64000]),
                          'conflict':digest(path)!=change['after']})
        return {'task_id':tid,'changes':diffs,'note':'显示执行期间文件变化；其他会话的同期修改可能包含在内。'}

    def rollback(self,tid):
        data=self.get(tid);root=self.root(data['root']);bundle=self.path(tid).parent
        if data['status'] not in TERMINAL or data.get('rolled_back'):raise ValueError('任务尚未结束或已撤回')
        lock=self.state/('project-'+hashlib.sha256(str(root).encode()).hexdigest()+'.lock')
        with lock.open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            paths=[(self.file(str(root),x['path']),x) for x in data.get('changes',[])]
            for path,change in paths:
                if digest(path)!=change['after']:raise ValueError('存在后续修改，停止撤回：'+change['path'])
                old=bundle/'before'/change['path']
                if change['before'] and (not old.exists() or digest(old)!=change['before']):raise ValueError('备份不可用，停止撤回')
            rescue=bundle/'rollback-backup';rescue.mkdir(exist_ok=True,mode=0o700)
            for path,change in paths:
                if path.exists():
                    target=rescue/change['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            for path,change in paths:
                if change['before']:
                    path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(bundle/'before'/change['path'],path)
                elif path.exists():path.unlink()
            data['rolled_back']=time.time();write_json(self.path(tid),data)
            audit(self.state,'rollback_task',data,task_id=tid)
        return data

    def read(self,root,path):
        file=self.file(root,path)
        content=file.read_text()
        if len(content)>32000:raise ValueError('文件超过读取范围，请拆分任务')
        return {'path':path,'content':public(content),'sha256':digest(file)}

    def write(self,root,path,content,expected):
        lock=self.state/('project-'+hashlib.sha256(str(self.root(root)).encode()).hexdigest()+'.lock')
        with lock.open('a') as guard:
            fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return self._write(root,path,content,expected)

    def _write(self,root,path,content,expected):
        file=self.file(root,path)
        if not isinstance(content,str) or len(content)>200000:raise ValueError('写入内容无效')
        if digest(file)!=expected:raise ValueError('文件已变化，重新读取后再修改')
        backup=self.state/'file-backups'/uuid.uuid4().hex
        backup.mkdir(parents=True,mode=0o700)
        if file.exists():shutil.copy2(file,backup/'original')
        write_json(backup/'meta.json',{'root':root,'path':path,'before':expected})
        file.parent.mkdir(parents=True,exist_ok=True)
        temp=file.with_name(file.name+'.gate-'+uuid.uuid4().hex)
        temp.write_text(content);os.replace(temp,file)
        return {'path':path,'sha256':digest(file),'backup_id':backup.name}


def manifest(root,backup=None):
    result={}
    for folder,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[x for x in dirs if x not in EXCLUDE and not (Path(folder)/x).is_symlink()]
        for name in files:
            path=Path(folder)/name
            if path.is_symlink() or SECRET_NAMES.search(name):continue
            relative=str(path.relative_to(root))
            if path.stat().st_size>10*1024*1024:continue
            result[relative]=digest(path)
            if backup:
                target=backup/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    return result


def worker(state,tid):
    os.umask(0o077)
    center=Center(state);path=center.path(tid);bundle=path.parent
    data=center.get(tid)
    for _ in range(50):
        if data.get('worker_pid')==os.getpid():break
        time.sleep(.1);data=center.get(tid)
    root=Path(data['root'])
    lock=center.state/('project-'+hashlib.sha256(str(root).encode()).hexdigest()+'.lock')
    with lock.open('a') as guard:
        try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            data.update(status='failed',error='项目已有写任务，未启动');write_json(path,data);return
        if (bundle/'stop').exists():data.update(status='stopped');write_json(path,data);return
        before=manifest(root,bundle/'before');write_json(bundle/'before.json',before)
        if any(digest(bundle/'before'/p)!=sha for p,sha in before.items()):
            data.update(status='failed',error='备份时文件变化，未启动任务');write_json(path,data);return
        prompt='User-authorized task:\n'+data['goal']+'\nAcceptance:\n'+data['acceptance']+'\nOnly this project is writable: '+str(root)+'. Preserve concurrent changes. Read project instructions. Do not change credentials or operate outside the project. Return actual results and evidence; do not claim acceptance.'
        if data.get('parent') and not data.get('session_id'):
            old=center.get(data['parent']);prompt+='\nPrior task goal: '+old['goal']+'\nPrior final: '+public(Path(old['final_file']).read_text() if Path(old['final_file']).exists() else 'Unavailable')
        (bundle/'prompt.txt').write_text(prompt)
        platform=data['platform'];env=dict(os.environ);stdin=prompt
        if platform=='codex':
            argv=['codex','exec']
            if data.get('session_id'):argv+=['resume',data['session_id']]
            else:argv+=['--sandbox','workspace-write','--cd',str(root)]
            argv+=['--skip-git-repo-check','--json','--model',data['model'],'-c','model_reasoning_effort="'+data['reasoning']+'"','-o',data['final_file'],'-']
        elif platform=='claude':
            login=claude_login_state()
            if login.get('loggedIn') is False and not login.get('unknown'):
                open_claude_login()
                data.update(status='failed',error=CLAUDE_LOGIN_HINT,ended_at=time.time());write_json(path,data);return
            argv=['claude','-p','--output-format','stream-json','--verbose','--model',data['model']]+claude_effort_args(data['reasoning'])
            if data.get('session_id'):argv+=['--resume',data['session_id']]
            else:
                data['session_id']=str(uuid.uuid4());argv+=['--session-id',data['session_id']]
        else:
            argv,env,stdin=gate_command('zcode',str(root),bundle/'prompt.txt',request=data['goal'])
        try:
            with (bundle/'events.jsonl').open('w') as output:
                output.write(json.dumps({'type':'control_center.identity',**identity(data)})+'\n');output.flush()
                proc=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.PIPE,stdout=output,stderr=subprocess.STDOUT,
                                      start_new_session=True,text=True)
                data.update(status='running',pid=proc.pid,worker_pid=os.getpid());write_json(path,data)
                if stdin:proc.stdin.write(stdin);proc.stdin.close()
                stopped=False
                while proc.poll() is None:
                    if (bundle/'stop').exists():
                        stopped=True;os.killpg(proc.pid,signal.SIGTERM)
                        try:proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    time.sleep(.5)
            final=[]
            with (bundle/'events.jsonl').open(errors='replace') as log:
                if platform=='zcode':
                    # zcode 事件是多行 JSON：response 是答复文本，sessionId 留作记录。
                    for event in json_objects(log.read()):
                        if not isinstance(event,dict):continue
                        if isinstance(event.get('response'),str) and event['response'].strip():final.append(event['response'])
                        if event.get('sessionId'):data['zcode_session']=event['sessionId']
                else:
                    for line in log:
                        try:event=json.loads(line)
                        except ValueError:continue
                        if event.get('type')=='thread.started':data['session_id']=event.get('thread_id')
                        if event.get('session_id'):data['session_id']=event['session_id']
                        if event.get('model'):data['actual_model']=event['model']
                        if event.get('modelUsage'):data['actual_model']=','.join(event['modelUsage'])
                        if event.get('type')=='turn.failed':
                            data['provider_error']=True
                            error=str(event.get('error',{}).get('message','执行失败'))
                            data['error']='当前登录不支持所选模型，请选择已验证模型' if 'not supported' in error else public(error[:1500])
                        item=event.get('item',{})
                        if item.get('type')=='agent_message':final.append(item.get('text',''))
                        if event.get('type')=='result':final.append(event.get('result',''));data['provider_error']=event.get('is_error',False)
            if not Path(data['final_file']).exists():Path(data['final_file']).write_text('\n'.join(final))
            checks=[]
            if not stopped and proc.returncode==0 and not data.get('provider_error'):
                for name in data['checks']:
                    result=subprocess.run(CHECKS[name],cwd=root,capture_output=True,text=True,timeout=300)
                    checks.append({'name':name,'exit_code':result.returncode,'output':public((result.stdout+result.stderr)[-16000:])})
            status='stopped' if stopped else 'failed' if proc.returncode or data.get('provider_error') else 'validation_failed' if any(x['exit_code'] for x in checks) else 'pending_review'
            data.update(status=status,exit_code=proc.returncode,validation=checks,ended_at=time.time())
        except Exception as exc:data.update(status='failed',error=type(exc).__name__,ended_at=time.time())
        after=manifest(root);write_json(bundle/'after.json',after)
        data['changes']=[{'path':p,'before':before.get(p),'after':after.get(p)} for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
        artifacts=[]
        for change in data['changes']:
            source=root/change['path']
            if source.exists():
                target=bundle/'artifacts'/change['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
                artifacts.append({'path':change['path'],'archive':str(target),'sha256':digest(target)})
        data['artifacts']=artifacts
        data['final']=public(Path(data['final_file']).read_text()) if Path(data['final_file']).exists() else ''
        write_json(path,data)
        audit(center.state,'task_finished',data,task_id=tid,status=data['status'])
        try:
            import evidence
            evidence.record_center_task(dict(data,task_id=tid),center.usage(dict(data,task_id=tid)),CHECKS,center.state)
        except Exception:pass  # evidence is fail-open; the task result is already saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['worker']);parser.add_argument('--state',required=True);parser.add_argument('--task',required=True)
    args=parser.parse_args();worker(args.state,args.task)
