from pathlib import Path
import socket,struct,json,uuid,time,stat,os
class DesktopIPC:
 def __init__(self,path,allow_interrupt=False):
  self.allow_interrupt=allow_interrupt
  path=Path(path);s=path.lstat();d=path.parent.stat()
  if not stat.S_ISSOCK(s.st_mode) or s.st_uid!=os.getuid() or d.st_uid!=os.getuid() or d.st_mode&0o022:raise RuntimeError('unsafe socket ownership/directory')
  self.socket=socket.socket(socket.AF_UNIX)
  try:
   self.socket.settimeout(4);self.socket.connect(str(path));self.client='initializing-client'
   self.client=self.request('initialize',{'clientType':'quota_guard_readonly_probe'},version=0)['result']['clientId']
  except Exception:
   self.socket.close();raise
 def frame(self,obj):
  raw=json.dumps(obj,separators=(',',':')).encode();self.socket.sendall(struct.pack('<I',len(raw))+raw)
 def exact(self,n):
  b=b''
  while len(b)<n:
   part=self.socket.recv(n-len(b))
   if not part:raise EOFError('closed')
   b+=part
  return b
 def receive(self):
  size=struct.unpack('<I',self.exact(4))[0]
  if size<1 or size>8*1024*1024:raise RuntimeError('frame exceeds safe probe cap')
  return json.loads(self.exact(size))
 def request(self,method,params,version=1,target=None,timeout=3):
  if method not in {'initialize','thread-owner-discovery'} and not (self.allow_interrupt and method=='thread-follower-interrupt-turn'):raise ValueError('probe is read-only')
  rid=str(uuid.uuid4());self.frame({'type':'request','requestId':rid,'sourceClientId':self.client,'method':method,'version':version,'params':params,'targetClientId':target,'timeoutMs':int(timeout*1000)})
  until=time.monotonic()+timeout+.2
  self.socket.settimeout(timeout+.2)
  while time.monotonic()<until:
   r=self.receive()
   if r.get('type')=='client-discovery-request':self.frame({'type':'client-discovery-response','requestId':r['requestId'],'response':{'canHandle':False}})
   if r.get('type')=='response' and r.get('requestId')==rid:return r
   # Broadcast payloads are discarded; no text or credential logging.
  raise TimeoutError('response timeout')
 def snapshot(self,thread,owner):
  self.socket.settimeout(4)
  params={'conversationId':thread,'hostId':'local','following':True}
  self.frame({'type':'broadcast','method':'thread-stream-following-changed','version':1,'sourceClientId':self.client,'targetClientIds':[owner],'params':params})
  try:
   until=time.monotonic()+4
   while time.monotonic()<until:
    r=self.receive()
    if r.get('type')=='client-discovery-request':self.frame({'type':'client-discovery-response','requestId':r['requestId'],'response':{'canHandle':False}})
    q=r.get('params',{});change=q.get('change',{})
    if r.get('method')=='thread-stream-state-changed' and r.get('version')!=11:raise ValueError('unknown snapshot version')
    if r.get('method')=='thread-stream-state-changed' and q.get('conversationId')==thread and r.get('sourceClientId')==owner and change.get('type')=='snapshot':
     state=change.get('conversationState',{})
     history=state.get('turnHistory',{})
     if history.get('kind')=='canonical':
      entities=history.get('history',{}).get('entitiesByKey')
      if not isinstance(entities,dict):raise ValueError('unknown canonical schema')
      candidates=list(entities.values())+state.get('turns',[])
     elif history.get('kind') in {None,'legacy'}:candidates=state.get('turns',[])
     else:raise ValueError('unknown history kind')
     turns={t['turnId']:{'turnId':t['turnId'],'status':t.get('status')} for t in candidates if isinstance(t,dict) and t.get('turnId')}
     return {'thread':thread,'owner':owner,'runtime':state.get('threadRuntimeStatus'),'turns':list(turns.values()),'goal_status':state.get('threadGoal',{}).get('status') if isinstance(state.get('threadGoal'),dict) else None}
   raise TimeoutError('snapshot timeout')
  finally:
   params['following']=False
   self.frame({'type':'broadcast','method':'thread-stream-following-changed','version':1,'sourceClientId':self.client,'targetClientIds':[owner],'params':params})
 def close(self):self.socket.close()
