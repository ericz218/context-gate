from pathlib import Path
import tempfile,socket,struct,json,threading
from console_quota_ipc import DesktopIPC
from console_quota_stop import stop_codex_thread,claude_candidates

def run_case(kind):
 with tempfile.TemporaryDirectory() as d:
  path=Path(d)/'fake.sock';server=socket.socket(socket.AF_UNIX);server.bind(str(path));server.listen();requests=[];state={'turn':'turn-a','status':'inProgress'};error=[]
  def exact(c,n):
   b=b''
   while len(b)<n:
    x=c.recv(n-len(b))
    if not x:raise EOFError
    b+=x
   return b
  def send(c,r):
   raw=json.dumps(r).encode();c.sendall(struct.pack('<I',len(raw))+raw)
  def worker():
   try:
    c,_=server.accept()
    with c:
     while True:
      try:n=struct.unpack('<I',exact(c,4))[0];r=json.loads(exact(c,n))
      except EOFError:break
      method=r['method']
      if r['type']=='request':
       requests.append(r)
       if method=='initialize':result={'clientId':'probe'}
       elif method=='thread-owner-discovery':result={'supportsUntrustedAppInput':True}
       elif method=='thread-follower-interrupt-turn':
        assert r['version']==4 and r['targetClientId']=='owner' and r['params']['expectedTurnId']=='turn-a'
        state['status']='inProgress' if kind=='no-terminal' else 'interrupted';result={'ok':True,'interruptedTurnId':'turn-a'}
       else:raise AssertionError(method)
       send(c,{'type':'response','requestId':r['requestId'],'resultType':'success','handledByClientId':'owner','result':result})
      elif method=='thread-stream-following-changed' and r['params']['following']:
       if kind=='race':state['turn']='turn-b'
       send(c,{'type':'broadcast','sourceClientId':'owner','method':'thread-stream-state-changed','version':999 if kind=='unknown-schema' else 11,'params':{'conversationId':'thread','hostId':'local','change':{'type':'snapshot','conversationState':{'turns':[],'turnHistory':{'kind':'canonical','history':{'entitiesByKey':{'key':{'turnId':state['turn'],'status':state['status'],'items':[{'text':'must never be logged'}]}}}},'threadRuntimeStatus':{'type':'active'}}}}})
   except Exception as e:error.append(e)
  t=threading.Thread(target=worker);t.start();ipc=DesktopIPC(path,allow_interrupt=True)
  snap={'thread':'thread','owner':'owner','runtime':{'type':'active'},'turns':[{'turnId':'turn-a','status':'inProgress'}]}
  try:
   if kind=='unknown-schema':
    try:ipc.snapshot('thread','owner')
    except ValueError:pass
    else:raise AssertionError('unknown schema accepted')
   else:
    result=stop_codex_thread(ipc,snap,enabled=kind!='disabled',timeout=.05)
    cancels=[r for r in requests if r['method']=='thread-follower-interrupt-turn']
    if kind in {'race','disabled'}:assert not cancels and not result['verified']
    elif kind=='no-terminal':assert cancels and not result['verified']
    else:assert len(cancels)==1 and result['verified'] and result['terminal']=='interrupted'
   # Transcript field never enters returned metadata.
   if kind!='unknown-schema':assert 'must never' not in json.dumps(result)
  finally:ipc.close();t.join(2);server.close()
  assert not t.is_alive() and not error,error
for case in ['success','race','disabled','no-terminal','unknown-schema']:run_case(case)
known=Path('/fake/claude')
table={1:{'pid':1,'ppid':0,'comm':'Claude'},2:{'pid':2,'ppid':1,'comm':'claude'},3:{'pid':3,'ppid':2,'comm':'claude'},4:{'pid':4,'ppid':0,'comm':'node'},5:{'pid':5,'ppid':0,'comm':'claude'}}
rows=claude_candidates(table,known,lambda pid:known if pid in {2,3} else Path('/fake/other'))
assert [r['pid'] for r in rows]==[2]
print('PASS fake Unix socket: exact owner+turn cancellation, terminal verification, race refusal, disabled control, timeout failure, unknown protocol rejection, transcript redaction, precise Claude identity filtering')
