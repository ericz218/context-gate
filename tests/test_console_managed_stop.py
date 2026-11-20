import sqlite3
from pathlib import Path
from unittest.mock import patch
import console_quota_stop as q
class Centre:
 def __init__(self):self.rows={'one':{'task_id':'one','status':'running'},'two':{'task_id':'two','status':'accepted'}};self.stops=[]
 def list(self):return list(self.rows.values())
 def stop(self,tid):self.stops.append(tid);self.rows[tid]['status']='stopped'
 def get(self,tid):return self.rows[tid]
class Groups:
 def __init__(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.db.execute('create table jobs(id,gid,member,status)');self.db.executemany('insert into jobs values(?,?,?,?)',[('j1','g1','m1','queued'),('j2','g1','m2','running')]);self.calls=[]
 def connect(self):return self.db
 def stop(self,body):
  self.calls.append(body)
  for mid in body['members']:self.db.execute("update jobs set status='stopped' where member=?",(mid,))
class Schedules:
 def list(self):return [{'id':'booking','status':'waiting'}]
c=Centre();g=Groups();r=q.stop_managed(c,g,enabled=False);assert not c.stops and not g.calls and r['covered'] is False
r=q.stop_managed(c,g,enabled=True);assert c.stops==['one'] and g.calls==[{'group':'g1','members':['m1','m2']}] and r['covered'] and all(x['verified'] for x in r['group_jobs'])
c=Centre();g=Groups();r=q.stop_managed(c,g,Schedules(),enabled=True);assert not r['covered'] and r['waiting_schedules']==['booking']
candidate={'pid':101,'executable':'/fake/claude'}
with patch.object(q,'process_executable',return_value=Path('/fake/claude')),patch.object(q.os,'kill') as kill:
 r=q.stop_claude(candidate,enabled=True,headless=False,timeout=0)
 kill.assert_called_once_with(101,q.signal.SIGINT);assert r['state']=='signal_sent' and not r['verified']
with patch.object(q,'process_executable',return_value=Path('/fake/reused-pid')),patch.object(q.os,'kill') as kill:
 r=q.stop_claude(candidate,enabled=True,timeout=0);kill.assert_not_called();assert r['state']=='changed'
with patch.object(q,'process_executable'),patch.object(q.os,'kill') as kill:
 q.stop_claude(candidate,enabled=False);kill.assert_not_called()
print('PASS: Centre and Groups native queue stop and terminal verification; scheduler uncovered; exact interactive SIGINT once, PID mismatch refusal, disabled no signals')
class Goal:
 def __init__(self):self.value='active';self.calls=[]
 def pause(self,thread):self.calls.append(thread);self.value='paused'
 def status(self,thread):return self.value
class IPC:
 def request(self,method,params,**kwargs):
  if method=='thread-owner-discovery':return {'resultType':'success','handledByClientId':'owner'}
  assert method=='thread-follower-interrupt-turn' and params['expectedTurnId']=='turn'
  self.stopped=True;return {'resultType':'success','result':{'ok':True,'interruptedTurnId':'turn'}}
 def snapshot(self,thread,owner):return {'thread':thread,'owner':owner,'turns':[{'turnId':'turn','status':'interrupted' if getattr(self,'stopped',False) else 'inProgress'}],'goal_status':'paused'}
snapshot={'thread':'thread','owner':'owner','turns':[{'turnId':'turn','status':'inProgress'}],'goal_status':'active'}
goal=Goal();r=q.stop_codex_thread(IPC(),snapshot,enabled=True,goal_api=goal);assert r['verified'] and r['goal_paused'] and goal.calls==['thread']
r=q.stop_codex_thread(IPC(),snapshot,enabled=True);assert r['verified'] and not r['goal_paused'] and r['goal_pause_error']
print('PASS: independent goal API pauses + verifies before exact-turn cancel; absent goal adapter explicitly incomplete')
import tempfile
with tempfile.TemporaryDirectory() as d:
 db=Path(d)/'state.sqlite';conn=sqlite3.connect(db);conn.execute('create table threads(id, archived, updated_at)');conn.executemany('insert into threads values(?,?,?)',[('old',0,1),('new',0,100),('archive',1,200)]);conn.commit();conn.close()
 assert q.thread_ids(db)==['new','old']
print('PASS: discovery newest-first, archived excluded')
