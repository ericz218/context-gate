"""Quota stop draft. No signals/cancellation unless enabled=True explicitly.
Internal desktop protocol pinned to the researched application build.
Never logs transcript bodies, process arguments, tokens, or environment.
"""
from pathlib import Path
import sqlite3,time,json,plistlib,subprocess,ctypes,os,signal,fcntl,uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from console_quota_ipc import DesktopIPC
APP=Path('/Applications/ChatGPT.app')
SUPPORTED_BUILD='20156'

def build_supported():
 return plistlib.loads((APP/'Contents/Info.plist').read_bytes()).get('CFBundleVersion')==SUPPORTED_BUILD

def thread_ids(database=None):
 p=Path(database) if database else Path.home()/'.codex/state_5.sqlite'
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
  # ID-only inventory. No user text, auth material or rollout content read.
  # DISTINCT: the live table briefly carried duplicate rows and one sweep was
  # observed spending its whole budget re-probing the same thread.
  return [r[0] for r in db.execute('SELECT DISTINCT id FROM threads WHERE archived=0 ORDER BY updated_at DESC, id DESC')]

def thread_inventory(database=None):
 """(id, updated_at) newest-first. Any new event in a thread moves its updated_at,
 which re-invalidates that thread's cached no-owner answer on the next sweep."""
 p=Path(database) if database else Path.home()/'.codex/state_5.sqlite'
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
  # DISTINCT: the live table briefly carried duplicate rows and one sweep was
  # observed spending its whole budget re-probing the same thread.
  return [(r[0],r[1]) for r in db.execute('SELECT DISTINCT id,updated_at FROM threads WHERE archived=0 ORDER BY updated_at DESC, id DESC')]

def inspect_thread(ipc,thread):
 r=ipc.request('thread-owner-discovery',{'hostId':'local','conversationId':thread},timeout=1.0)
 if r.get('resultType')!='success':return {'thread':thread,'owner':None,'reason':r.get('error','unknown owner response')}
 owner=r.get('handledByClientId')
 if not isinstance(owner,str):raise ValueError('unknown owner schema')
 return ipc.snapshot(thread,owner)

def stop_codex_thread(ipc,snapshot,enabled=False,timeout=5,goal_api=None):
 active=[t for t in snapshot.get('turns',[]) if t.get('status')=='inProgress']
 base={'provider':'codex','thread':snapshot['thread'],'owner':snapshot.get('owner'),'cancel_sent':False,'verified':False}
 if len(active)!=1:
  return dict(base,state='idle' if not active and snapshot.get('runtime',{}).get('type')=='idle' else 'unknown',reason='no exact active turn' if not active else 'ambiguous active turn')
 turn=active[0]['turnId'];base['turn']=turn
 if not enabled:return dict(base,state='active',reason='control disabled')
 goal_status=snapshot.get('goal_status')
 goal_paused=goal_status!='active'
 if goal_status=='active' and goal_api is not None:
  # Only an independently connected live owner's public appserver may implement this.
  # No fabricated goal request is sent through the internal desktop IPC.
  try:
   goal_api.pause(snapshot['thread'])
   goal_paused=goal_api.status(snapshot['thread'])=='paused'
  except Exception:goal_paused=False
 base['goal_paused']=goal_paused
 if not goal_paused:base['goal_pause_error']='No public live goal control endpoint; active goal may generate another turn'
 # Refresh owner+turn to avoid canceling a replacement task.
 fresh=inspect_thread(ipc,snapshot['thread'])
 if fresh.get('owner')!=snapshot.get('owner') or not any(t.get('turnId')==turn and t.get('status')=='inProgress' for t in fresh.get('turns',[])):
  return dict(base,state='changed',reason='owner or turn changed before cancel')
 r=ipc.request('thread-follower-interrupt-turn',{'conversationId':snapshot['thread'],'mode':'user-stop','expectedTurnId':turn},version=4,target=snapshot['owner'])
 base['cancel_sent']=True
 result=r.get('result',{})
 if r.get('resultType')!='success' or result.get('ok') is not True or result.get('interruptedTurnId')!=turn:
  return dict(base,state='unverified',reason=r.get('error','interrupt acknowledgement does not match exact turn'))
 until=time.monotonic()+timeout
 while time.monotonic()<until:
  after=inspect_thread(ipc,snapshot['thread'])
  if after.get('owner')!=snapshot['owner']:return dict(base,state='unverified',reason='owner disappeared; cancellation terminal not verified')
  found=next((t for t in after.get('turns',[]) if t.get('turnId')==turn),None)
  if found and found.get('status') in {'interrupted','completed','failed'}:
   newer=any(t.get('status')=='inProgress' for t in after.get('turns',[]))
   return dict(base,state='interrupted' if found['status']=='interrupted' else 'ended',verified=True,evidence='actual owner interrupt ACK + owner terminal snapshot',terminal=found['status'],new_active_turn=newer,reason='new turn started; global stop incomplete' if newer else None,goal_pause_error=result.get('goalPauseError') or base.get('goal_pause_error'))
  time.sleep(.1)
 return dict(base,state='unverified',reason='owner terminal status timeout')

_noowner_cache={}  # database -> {thread: (updated_at, wall_seen_at, definitive)}
NOOWNER_TTL_DEFINITIVE=1800  # the app itself answered that no live client owns the thread
NOOWNER_TTL_AMBIGUOUS=300    # discovery timed out without an answer: re-probe sooner

def discover_codex(database=None,socket_path=None,enabled=False,budget=20,workers=4):
 if not build_supported():return {'provider':'codex','covered':False,'reason':'unknown desktop build; internal protocol disabled','sessions':[]}
 deadline=time.monotonic()+budget;rows=[];errors=[];complete=True;cached=0;skipped_ambiguous=0
 path=socket_path or Path.home()/'.codex/ipc/ipc.sock'
 ipc=DesktopIPC(path,allow_interrupt=enabled)
 # Every parallel probe owns its socket; DesktopIPC's stream is not multiplex-safe.
 def probe(thread):
  connection=DesktopIPC(path,allow_interrupt=False)
  try:return inspect_thread(connection,thread)
  finally:connection.close()
 try:
  inventory=thread_inventory(database);cache=_noowner_cache.setdefault(str(database),{});fresh={};pending=[]
  for thread,updated in inventory:
   seen=cache.get(thread)
   if seen and seen[0]==updated and time.time()-seen[1]<(NOOWNER_TTL_DEFINITIVE if seen[2] else NOOWNER_TTL_AMBIGUOUS):
    fresh[thread]=seen;cached+=1
    if not seen[2]:skipped_ambiguous+=1
   else:pending.append((thread,updated))
  # Bounded batches preserve newest-first priority. Never submit the whole inventory.
  # A batch already in flight is allowed to finish its bounded IPC timeouts on expiry.
  workers=max(1,min(4,int(workers)))
  with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='quota-discovery') as pool:
   for offset in range(0,len(pending),workers):
    if time.monotonic()>=deadline:complete=False;break
    batch=pending[offset:offset+workers]
    futures=[pool.submit(probe,t) for t,_ in batch] if workers>1 else []
    for index,(thread,updated) in enumerate(batch):
     try:s=futures[index].result() if futures else inspect_thread(ipc,thread)
     except (OSError,ValueError,EOFError,TimeoutError,RuntimeError) as e:
      errors.append({'thread':thread,'reason':type(e).__name__});complete=False
      fresh[thread]=(updated,time.time(),False);continue
     if s.get('owner') is not None:
      try:rows.append(stop_codex_thread(ipc,s,enabled))
      except (OSError,ValueError,EOFError,TimeoutError) as e:
       errors.append({'thread':thread,'reason':type(e).__name__});complete=False
      # Owned threads are never cached, so every sweep re-checks current turns.
     elif s.get('reason')=='no-client-found':
      fresh[thread]=(updated,time.time(),True)
     else:
      # App-side timeout proves only lack of a timely claimant, never lack of an owner.
      errors.append({'thread':thread,'reason':s.get('reason','unknown owner response')});complete=False
      fresh[thread]=(updated,time.time(),False)
  cache.update(fresh)
  live_ids={t for t,_ in inventory}
  for stale in [t for t in cache if t not in live_ids]:del cache[stale]
  if skipped_ambiguous:complete=False
 finally:ipc.close()
 return {'provider':'codex','covered':complete and not errors,'sessions':rows,'errors':errors,'discovery_complete':complete,'cached_noowner':cached,'transport':'desktop internal IPC; supported build only','limits':['Independent Codex CLI/appservers, cloud chats, ephemeral threads absent from SQLite not covered','Terminal snapshot is local owner state, not upstream billing receipt; no claim of zero post-stop token charge','Expected-turn interrupt does not guarantee future turns/automation are blocked','Only explicit no-client-found is cached as unowned for up to 30 minutes; App/transport timeout remains uncovered and is retried after 5 minutes; new thread events re-probe immediately','Discovery uses at most 4 independent read-only sockets per batch; budget stops new batches, in-flight IPC and exact stop verification finish with their own timeouts']}

def process_table():
 out=subprocess.check_output(['ps','-axo','pid=,ppid=,comm='],text=True)
 return {int(x[0]):{'pid':int(x[0]),'ppid':int(x[1]),'comm':x[2]} for line in out.splitlines() if len(x:=line.strip().split(None,2))==3}

def process_executable(pid):
 lib=ctypes.CDLL('/usr/lib/libproc.dylib');buf=ctypes.create_string_buffer(4096)
 n=lib.proc_pidpath(pid,buf,len(buf))
 return Path(os.fsdecode(buf.value)).resolve() if n>0 else None

def claude_candidates(table=None,known_executable=None,exe_reader=process_executable):
 import shutil
 table=table or process_table();known=Path(known_executable or shutil.which('claude') or '/nonexistent').resolve();matches={}
 for pid,row in table.items():
  if Path(row['comm']).name!='claude':continue
  exe=exe_reader(pid)
  if exe is not None and exe==known:matches[pid]=dict(row,executable=str(exe))
 # Only top-level actual CLI, never duplicate child/helper matches.
 return [r for pid,r in matches.items() if r['ppid'] not in matches]

def stop_claude(candidate,enabled=False,headless=False,timeout=3):
 base={'provider':'claude','pid':candidate['pid'],'cancel_sent':False,'verified':False}
 if not enabled:return dict(base,state='unverified',reason='control disabled; no active-turn evidence for unmanaged CLI')
 # Explicit all-session stop authorizes one SIGINT to precise CLI identity.
 # Interactive process survival is not proof the remote turn ended.
 if process_executable(candidate['pid'])!=Path(candidate['executable']):return dict(base,state='changed',reason='PID executable changed')
 os.kill(candidate['pid'],signal.SIGINT);base['cancel_sent']=True
 until=time.monotonic()+timeout
 while time.monotonic()<until:
  if process_executable(candidate['pid']) is None:return dict(base,state='client_exited',verified=True,evidence='exact CLI exited after SIGINT',limits='Transport closed; no upstream billing receipt')
  time.sleep(.1)
 return dict(base,state='signal_sent',reason='SIGINT sent to exact CLI; process remains, turn/remote cancellation unverified')

def stop_managed(center,groups,schedules=None,enabled=False,timeout=5):
 rows=[];jobs=[];groups_by_id={}
 for task in center.list():
  if task.get('status') in {'starting','running'}:rows.append({'task_id':task['task_id'],'state':'active','cancel_sent':False,'verified':False})
 with groups.connect() as db:
  jobs=[dict(x) for x in db.execute("SELECT id,gid,member,status FROM jobs WHERE status IN ('queued','running','stopping')")]
 for j in jobs:groups_by_id.setdefault(j['gid'],set()).add(j['member'])
 waiting=[] if schedules is None else [x['id'] for x in schedules.list() if x.get('status')=='waiting']
 if not enabled:return {'provider':'context-gate','sessions':rows,'group_jobs':[{'id':j['id'],'state':j['status']} for j in jobs],'waiting_schedules':waiting,'covered':False,'reason':'control disabled'}
 # Existing Centre.stop and Groups.stop coordinate worker-owned native cancellation.
 for r in rows:center.stop(r['task_id']);r['cancel_sent']=True
 for gid,members in groups_by_id.items():groups.stop({'group':gid,'members':sorted(members)})
 until=time.monotonic()+timeout
 remaining=set(j['id'] for j in jobs)
 while time.monotonic()<until:
  for r in rows:
   r['state']=center.get(r['task_id'])['status'];r['verified']=r['state'] in {'stopped','interrupted','failed','pending_review','accepted','validation_failed'}
  with groups.connect() as db:
   statuses={x['id']:x['status'] for x in db.execute('SELECT id,status FROM jobs')}
  remaining={jid for jid in remaining if statuses.get(jid) in {'queued','running','stopping'}}
  if not remaining and all(r['verified'] for r in rows):break
  time.sleep(.1)
 return {'provider':'context-gate','sessions':rows,'group_jobs':[{'id':j['id'],'cancel_sent':True,'state':statuses.get(j['id'],'missing'),'verified':j['id'] not in remaining and j['id'] in statuses} for j in jobs],'covered':not remaining and all(r['verified'] for r in rows) and not waiting,'waiting_schedules':waiting,'reason':'Current native queues stopped/verified where possible; future scheduler bookings unchanged and remain uncovered' if waiting else 'Future manual submissions/automation require admission latch in host'}

def stop_all_local(enabled=False,managed=None,**kwargs):
 results=[]
 if managed is not None:
  try:results.append(dict(stop_managed(enabled=enabled,**managed),discovery_complete=True))
  except Exception as e:results.append({'provider':'context-gate','covered':False,'reason':type(e).__name__})
 else:results.append({'provider':'context-gate','covered':False,'reason':'No live center/groups handles supplied'})
 try:results.append(discover_codex(enabled=enabled,**kwargs))
 except Exception as e:results.append({'provider':'codex','covered':False,'reason':type(e).__name__,'sessions':[],'discovery_complete':False,'error':type(e).__name__})
 try:results.append({'provider':'claude','covered':False,'sessions':[stop_claude(c,enabled=enabled) for c in claude_candidates()],'discovery_complete':True,'reason':'Exact CLI SIGINT dispatched when enabled; surviving interactive process has no trusted terminal-state ACK; no app/service killed'})
 except Exception as e:results.append({'provider':'claude','covered':False,'reason':type(e).__name__,'sessions':[],'discovery_complete':False,'error':type(e).__name__})
 return stop_summary(results,enabled=enabled)

ACTIVE_EXCLUDED={'idle','unknown','missing'}
def stop_summary(platforms,enabled=True,managed_resumable=0):
 """Honest coverage: idle only when discovery is complete and nothing active was found."""
 rows=[r for p in platforms for r in list(p.get('sessions',[]))+list(p.get('group_jobs',[]))]
 active=sum(r.get('state') not in ACTIVE_EXCLUDED for r in rows)
 sent=sum(bool(r.get('cancel_sent')) for r in rows);verified=sum(bool(r.get('verified')) for r in rows)
 errors=sum(len(p.get('errors',[]))+bool(p.get('error')) for p in platforms)
 complete=all(bool(p.get('discovery_complete')) for p in platforms)
 uncovered=sum((not p.get('discovery_complete')) or bool(p.get('error')) for p in platforms)+sum(r.get('state')=='unknown' for r in rows)
 if active==0 and complete and not errors:status='idle'
 elif enabled and sent==0 and verified==0 and (active or errors):status='failed'
 else:status='partial'
 return {'enabled':enabled,'ok':status=='idle','all_local_sessions_stopped':status=='idle','coverage_status':status,
         'summary':{'discovered_active':active,'cancel_sent':sent,'verified':verified,'managed_resumable':managed_resumable,'uncovered':uncovered},
         'platforms':platforms,'note':'External desktop/CLI sessions are stop-only and never auto-resumed. Partial coverage is reported as partial, not idle.'}

TARGET_STATES={'paused','resumed','attention','uncertain','revoked'}
PLATFORM_NAMES=('codex','claude')
CLOSED_CYCLES_KEPT=50

class LedgerError(Exception):pass

def write_private(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(temp,path)

class Protection:
 """Owned quota pauses: claims for work this console itself stopped, and resume coordination.

 Lock order is fixed: submission.lock (adapters) -> journal lock -> SQLite. The journal lock is never
 held while calling adapters or external stops. external=None performs no external stop (D12); the app
 injects the real one through the module-global stop_all_local.
 """
 def __init__(self,state,center,groups,schedules=None,external=None,clock=time.time,timeout=5):
  self.state=Path(state);self.path=self.state/'quota-pauses.json';self.lock_path=self.state/'quota-pauses.lock'
  self.center=center;self.groups=groups;self.schedules=schedules;self.external=external;self.clock=clock;self.timeout=timeout

 # ---- journal ----
 def _read(self):
  """Read-only. Missing journal is empty and creates nothing; malformed journal raises LedgerError."""
  try:text=self.path.read_text()
  except FileNotFoundError:return {'version':1,'cycles':[]}
  try:data=json.loads(text)
  except ValueError:raise LedgerError('journal unreadable')
  if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('cycles'),list):raise LedgerError('journal schema')
  for c in data['cycles']:
   if not isinstance(c,dict) or c.get('status') not in ('open','closed') or not isinstance(c.get('blockers'),list) or not isinstance(c.get('targets'),list):raise LedgerError('journal schema')
   for t in c['targets']:
    if not isinstance(t,dict) or t.get('kind') not in ('center','group') or t.get('status') not in TARGET_STATES or t.get('platform') not in PLATFORM_NAMES+('zcode',):raise LedgerError('journal schema')
  return data

 @contextmanager
 def _mutate(self):
  self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
  with self.lock_path.open('a') as guard:
   os.chmod(self.lock_path,0o600);fcntl.flock(guard,fcntl.LOCK_EX)
   data=self._read()
   yield data
   write_private(self.path,data)

 def _close(self,data):
  for c in data['cycles']:
   if c['status']=='open' and not any(t['status']=='paused' for t in c['targets']):c['status']='closed'
  closed=[c for c in data['cycles'] if c['status']=='closed']
  if len(closed)>CLOSED_CYCLES_KEPT:
   drop={id(c) for c in closed[:-CLOSED_CYCLES_KEPT]};data['cycles']=[c for c in data['cycles'] if id(c) not in drop]

 @staticmethod
 def _unreadable():
  return {p:{'status':'attention','paused_count':0,'resumed_count':0,'attention_count':1,'blocked_by':[{'platform':p,'account':None,'reason':'read_error'}],'external_resume_supported':False} for p in PLATFORM_NAMES}

 # ---- read side (GET /v1/quota): pure, never creates files, never raises ----
 def snapshot(self,states=None,prefs=None):
  try:data=self._read()
  except (OSError,LedgerError,ValueError):return self._unreadable()
  out={p:{'status':'idle','paused_count':0,'resumed_count':0,'attention_count':0,'blocked_by':[],'external_resume_supported':False} for p in PLATFORM_NAMES}
  for cycle in data['cycles']:
   blocked=self._blocked(cycle,states,prefs) if cycle['status']=='open' and states is not None and prefs is not None else []
   for t in cycle['targets']:
    s=out.get(t['platform'])
    if s is None:continue
    if t['status']=='paused':s['paused_count']+=1;s['blocked_by'].extend(blocked)
    elif t['status']=='resumed':s['resumed_count']+=1
    elif t['status'] in ('attention','uncertain'):s['attention_count']+=1
  for s in out.values():
   unique=[]
   for b in s['blocked_by']:
    if b not in unique:unique.append(b)
   s['blocked_by']=unique
   s['status']='attention' if s['attention_count'] else 'waiting' if s['paused_count'] and unique else 'paused' if s['paused_count'] else 'resumed' if s['resumed_count'] else 'idle'
  return out

 # ---- blockers (D5/D6/D7); reset is never compared ----
 def _blocked(self,cycle,states,prefs):
  out=[]
  triggers={b['platform'] for b in cycle['blockers']}
  for b in cycle['blockers']:
   reason=self._trigger_reason(b,states,prefs)
   if reason:out.append({'platform':b['platform'],'account':b.get('account'),'reason':reason})
  held={t['platform'] for t in cycle['targets'] if t['status']=='paused' and t['platform'] in PLATFORM_NAMES}
  for p in sorted(held-triggers):
   reason=self._target_platform_reason(cycle,p,states,prefs)
   if reason:out.append({'platform':p,'account':cycle.get('accounts',{}).get(p),'reason':reason})
  return out

 @staticmethod
 def _trigger_reason(b,states,prefs):
  p=b['platform'];s=states[p];pref=prefs[p]
  if not (pref.get('enabled') and pref.get('stop_all') and pref.get('resume_paused')):return 'resume_disabled'
  if not b.get('account'):return 'unknown_account'
  if s.get('account')!=b['account']:return 'account_changed' if s.get('account') else 'unknown_account'
  if s.get('status')!='ok':return 'read_error'
  if s.get('checked_at') is None:return 'not_checked_after_pause'  # restart-restored display: a real check is still required before resuming
  if (s.get('updated_at') or 0)<=(b.get('observed_at') or 0):return 'not_checked_after_pause'
  windows=[w for w in s.get('windows',[]) if w.get('bucket')==b.get('bucket') and w.get('window')==b.get('window')]
  if not windows or windows[0].get('remaining') is None:return 'window_missing'
  if windows[0]['remaining']<=b['threshold']:return 'low_quota'
  return None

 @staticmethod
 def _target_platform_reason(cycle,p,states,prefs):
  if not prefs[p].get('enabled'):return None  # D5: a disabled, unrelated platform never blocks
  s=states[p];account=cycle.get('accounts',{}).get(p)
  if not account:return 'unknown_account'
  if s.get('account')!=account:return 'account_changed' if s.get('account') else 'unknown_account'
  if s.get('status')!='ok':return 'read_error'
  if s.get('checked_at') is None:return 'not_checked_after_pause'  # restart-restored display: a real check is still required before resuming
  if (s.get('updated_at') or 0)<=cycle['created_at']:return 'not_checked_after_pause'
  windows=[w for w in s.get('windows',[]) if w.get('remaining') is not None]
  if not windows:return 'window_missing'
  if any(w['remaining']<=prefs[p][w['window']+'_threshold'] for w in windows):return 'low_quota'
  return None

 # ---- pause side (called by Quotas outside its lock) ----
 def pause(self,payload):
  """payload: platform, blockers, accounts, auto_resume. Stops active managed work (claimed when auto_resume) and external local work."""
  auto=bool(payload.get('auto_resume'));orders=[];managed=None
  if auto:
   try:orders=self._capture(payload)
   except (OSError,LedgerError,ValueError):managed=self._stop_plain()  # broken ledger: stop without ownership, never resumable
   else:managed=self._stop_claimed(orders)
  else:managed=self._stop_plain()
  return self._result(managed)

 def _candidates(self):
  out=[]
  for task in self.center.list():
   if task.get('status') in ('starting','running'):
    out.append({'kind':'center','id':task['task_id'],'platform':task.get('platform'),
                'fingerprint':{'platform':task.get('platform'),'model':task.get('model'),'reasoning':task.get('reasoning'),'root':task.get('root'),'session_id':task.get('session_id')}})
  with self.groups.connect() as db:
   for row in db.execute("SELECT j.id AS id,m.platform AS platform FROM jobs j JOIN members m ON m.id=j.member WHERE j.status IN ('queued','running') AND j.stop=0"):
    out.append({'kind':'group','id':row['id'],'platform':row['platform']})
  return out

 def _capture(self,payload):
  candidates=self._candidates()  # inventory first; the journal lock is only held for the ledger edit
  orders=[]
  with self._mutate() as data:
   open_cycles=[c for c in data['cycles'] if c['status']=='open']
   cycle=open_cycles[-1] if open_cycles else None
   held={}
   for c in open_cycles:
    for t in c['targets']:
     if t['status']=='paused':held[(t['kind'],t['id'])]=(c,t)
   fresh=[x for x in candidates if (x['kind'],x['id']) not in held]
   again=[x for x in candidates if (x['kind'],x['id']) in held]
   if cycle is None and not fresh:return []  # nothing owned to pause: no ledger write
   if cycle is None:
    cycle={'id':str(uuid.uuid4()),'status':'open','created_at':self.clock(),'accounts':dict(payload.get('accounts',{})),'blockers':[],'targets':[]}
    data['cycles'].append(cycle)
   self._merge_blockers(cycle,payload.get('blockers',[]))  # repeated and additional blockers join the open cycle
   for x in fresh:
    claim=str(uuid.uuid4())
    cycle['targets'].append({'kind':x['kind'],'id':x['id'],'platform':x['platform'],'claim_id':claim,'status':'paused','reason':None,'resume_ref':None})
    orders.append(dict(x,claim_id=claim,cycle_id=cycle['id']))
   for x in again:
    c,t=held[(x['kind'],x['id'])]
    orders.append(dict(x,claim_id=t['claim_id'],cycle_id=c['id']))  # re-issue the stop for still-active held work
  return orders

 @staticmethod
 def _merge_blockers(cycle,blockers):
  for b in blockers:
   key=(b['platform'],b.get('account'),b.get('bucket'),b.get('window'))
   old=next((x for x in cycle['blockers'] if (x['platform'],x.get('account'),x.get('bucket'),x.get('window'))==key),None)
   if old:old.update(threshold=b['threshold'],reset=b.get('reset'),observed_at=b['observed_at'])  # re-observed: newest time
   else:cycle['blockers'].append(dict(b))

 def _stop_claimed(self,orders):
  center_rows=[];group_rows=[];group_orders=[]
  for o in orders:
   if o['kind']=='center':
    try:
     self.center.stop(o['id'],quota_claim={'claim_id':o['claim_id'],'cycle_id':o['cycle_id'],'fingerprint':o.get('fingerprint',{})})
     center_rows.append({'task_id':o['id'],'state':'active','cancel_sent':True,'verified':False})
    except Exception as e:center_rows.append({'task_id':o['id'],'state':'active','cancel_sent':False,'verified':False,'reason':type(e).__name__})
   else:group_orders.append(o)
  if group_orders:
   try:
    for r in self.groups.quota_pause([{'id':o['id'],'claim_id':o['claim_id'],'cycle_id':o['cycle_id']} for o in group_orders]):
     group_rows.append({'id':r['id'],'state':'active','cancel_sent':bool(r.get('cancel_sent')),'verified':False,'reason':r.get('reason')})
   except Exception as e:group_rows=[{'id':o['id'],'state':'active','cancel_sent':False,'verified':False,'reason':type(e).__name__} for o in group_orders]
  deadline=time.monotonic()+self.timeout
  while True:
   for r in center_rows:
    r['status']=self._center_status(r['task_id']);r['verified']=r['status']=='stopped'
   statuses=self._group_statuses()
   for r in group_rows:
    r['status']=statuses.get(r['id'],'missing');r['verified']=r['status']=='stopped'
   if all(r['verified'] for r in center_rows+group_rows) or time.monotonic()>=deadline:break
   time.sleep(.1)
  waiting=self._waiting_schedules()
  return {'provider':'context-gate','sessions':center_rows,'group_jobs':group_rows,'discovery_complete':True,'waiting_schedules':waiting,
          'covered':all(r['verified'] for r in center_rows+group_rows) and not waiting,
          'reason':'Current native queues stopped/verified where possible; future scheduler bookings unchanged and remain uncovered' if waiting else 'Future manual submissions/automation require admission latch in host'}

 def _stop_plain(self):
  try:managed=stop_managed(self.center,self.groups,self.schedules,enabled=True,timeout=self.timeout)
  except Exception as e:return {'provider':'context-gate','sessions':[],'group_jobs':[],'covered':False,'discovery_complete':False,'error':type(e).__name__,'reason':type(e).__name__}
  managed.setdefault('discovery_complete',True)
  return managed

 def _center_status(self,tid):
  try:return self.center.get(tid)['status']
  except Exception:return 'unknown'

 def _group_statuses(self):
  with self.groups.connect() as db:return {row['id']:row['status'] for row in db.execute('SELECT id,status FROM jobs')}

 def _waiting_schedules(self):
  if self.schedules is None:return []
  try:return [x['id'] for x in self.schedules.list() if x.get('status')=='waiting']
  except Exception:return []

 def _result(self,managed):
  platforms=[managed]
  if self.external is None:
   platforms+=[{'provider':p,'covered':False,'sessions':[],'discovery_complete':False,'reason':'control disabled; external stop control not connected'} for p in PLATFORM_NAMES]
  else:
   try:external=self.external()
   except Exception as e:external={'platforms':[{'provider':'external','covered':False,'sessions':[],'discovery_complete':False,'error':type(e).__name__,'reason':type(e).__name__}]}
   platforms+=[p for p in external.get('platforms',[]) if p.get('provider')!='context-gate']
  return stop_summary(platforms,enabled=True,managed_resumable=self._resumable())

 def _resumable(self):
  try:data=self._read()
  except (OSError,LedgerError,ValueError):return 0
  return sum(t['status']=='paused' for c in data['cycles'] if c['status']=='open' for t in c['targets'])

 # ---- revocation (D8) ----
 def revoke(self,platforms):
  with self._mutate() as data:
   for c in data['cycles']:
    if c['status']!='open' or not any(b['platform'] in platforms for b in c['blockers']):continue
    for t in c['targets']:
     if t['status']=='paused':t.update(status='attention',reason='resume_disabled')
   self._close(data)

 # ---- resume (D2-D7, D10, D14) ----
 def _busy(self,root):
  return self.groups.root_busy(root)

 def reconcile(self,states,prefs,live=None):
  """Resume owned pauses whose blockers have all cleared. Adapters run without the journal lock."""
  try:data=self._read()
  except (OSError,LedgerError,ValueError):return None   # broken journal: never resume
  work=[(c,t) for c in data['cycles'] if c['status']=='open' for t in c['targets'] if t['status']=='paused']
  for cycle,target in work:
   adapter=self.center if target['kind']=='center' else self.groups
   claim={'claim_id':target['claim_id'],'cycle_id':cycle['id']}
   try:state=adapter.quota_state(target['id'],claim)
   except Exception:state='mismatch'
   if state=='revoked':result={'status':'revoked'}
   elif state=='mismatch':result={'status':'attention','reason':'ledger_mismatch'}
   else:
    if self._blocked(cycle,states,prefs) and state!='dispatched':continue
    if live is not None:
     states,prefs=live()
     if self._blocked(cycle,states,prefs) and state!='dispatched':continue
    try:result=adapter.resume_quota(target['id'],claim,busy=self._busy if target['kind']=='center' else None)
    except Exception:result={'status':'uncertain','reason':'resume dispatch uncertain; inspect manually'}
   self._record(cycle['id'],target['kind'],target['id'],target['claim_id'],result)

 def _record(self,cycle_id,kind,tid,claim_id,result):
  with self._mutate() as data:
   for c in data['cycles']:
    if c['id']!=cycle_id:continue
    for t in c['targets']:
     if (t['kind'],t['id'],t['claim_id'])!=(kind,tid,claim_id) or t['status']!='paused':continue
     status=result.get('status')
     if status=='resumed':t.update(status='resumed',resume_ref=result.get('resume_ref'))
     elif status=='revoked':t.update(status='revoked')
     elif status=='waiting':t.update(reason=result.get('reason'))
     elif status=='uncertain':t.update(status='uncertain',reason=result.get('reason'),resume_ref=result.get('resume_ref'))
     else:t.update(status='attention',reason=result.get('reason','unknown'))
   self._close(data)

if __name__=='__main__':print(json.dumps(stop_all_local(enabled=False),ensure_ascii=False,indent=2))
