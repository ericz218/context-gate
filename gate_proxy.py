#!/usr/bin/env python3
"""Per-agent REST gateway: gate every call, preserve tool/reasoning protocols.
One process/binding per agent session. Authentication stays with the native client.
"""
import argparse
import codecs
import uuid
import copy
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from gate_service import call_service, private_write, MAX_BODY
from gate_turn import prepare_turn, managed_context
from context_gate import estimate
from token_stats import UsageCollector, save

ROUTES = {'/responses':'responses', '/chat/completions':'chat', '/v1/responses':'responses', '/v1/chat/completions':'chat', '/v1/messages':'anthropic', '/v1/messages/count_tokens':'anthropic'}


def is_initial_attachment(text, initial, path):
    """Recognize only ZCode's complete Read projection of our own pack file."""
    prefix='<system-reminder>\nCalled the Read tool with the following input: '
    suffix='\n</system-reminder>'
    if not path or not isinstance(text,str) or not text.startswith(prefix) or not text.endswith(suffix):return False
    header,separator,body=text[len(prefix):-len(suffix)].partition('\nResult of calling the Read tool:\n')
    if not separator:return False
    try:read=json.loads(header)
    except ValueError:return False
    if read!={'file_path':str(path)}:return False
    lines=re.split(r'\r?\n',initial)
    numbered=[str(i)+'\t'+line for i,line in enumerate(lines,1)]
    if body=='\n'.join(numbered):return True
    # Native Read caps large attachments at 25K tokens. Validate the displayed
    # prefix before replacing it with the complete, freshly gated pack.
    notice,separator,partial=body.partition('\n\n')
    if not separator:return False
    notice=html.unescape(notice)
    common=r'<system-reminder>The file is too large to display in full \(\d+ estimated tokens, limit \d+\)\. '
    match=re.fullmatch(common+r'Showing a partial view of lines 1-(\d+) of (\d+)\. Use Read with offset (\d+) and limit \d+ to continue, or use a search tool to find a specific section\.</system-reminder>',notice)
    if match:
        end,total,next_line=map(int,match.groups())
        return 0<end<len(lines) and total==len(lines) and next_line==end+1 and partial=='\n'.join(numbered[:end])
    if re.fullmatch(common+r'Showing a partial view of the first line because the first line alone exceeds the token budget\. Use Read with a smaller range or use a search tool to find a specific section\.</system-reminder>',notice):
        return partial.startswith('1\t') and len(partial)>2 and numbered[0].startswith(partial)
    return False


def current_request(payload, protocol, fallback):
    items=payload.get('input' if protocol=='responses' else 'messages',[])
    if isinstance(items,str):return items
    for item in reversed(items):
        if not isinstance(item,dict) or item.get('role')!='user':continue
        content=item.get('content',[])
        texts=[content] if isinstance(content,str) else [b.get('text','') for b in content if isinstance(b,dict) and b.get('type') in ('text','input_text')]
        texts=[t for t in texts if t and not t.startswith('[CONTEXT_GATE_MANAGED ')]
        if texts:return '\n'.join(texts)
    return fallback


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def fail(self,code,message):
        self.server.events.append({'local_status':code,'reason':message})
        data=json.dumps({'error':{'message':message,'type':'context_gate'}}).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        prefix='/'+self.server.local_token
        if self.headers.get('Origin') or not self.path.startswith(prefix+'/'):
            return self.fail(403,'Unauthorized local route')
        route=self.path[len(prefix):]
        if urllib.parse.urlparse(route).path not in ('/models','/v1/models'):
            return self.fail(404,'Unsupported metadata endpoint')
        headers={k:v for k,v in self.headers.items() if k.lower() in ('authorization','x-api-key','chatgpt-account-id','openai-beta','user-agent','x-app','x-stainless-lang','x-stainless-package-version','x-stainless-runtime','x-stainless-runtime-version','x-stainless-os','x-stainless-arch')}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(self.server.upstream+route,headers=headers),timeout=20) as r:
                data=r.read(MAX_BODY)
                self.send_response(r.code);self.send_header('Content-Type',r.headers.get('Content-Type','application/json'));self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except Exception:return self.fail(502,'Upstream model metadata unavailable')

    def do_POST(self):
        started=time.perf_counter()
        prefix='/'+self.server.local_token
        if self.headers.get('Origin') or not self.path.startswith(prefix+'/'):
            return self.fail(403,'Unauthorized local route')
        route=urllib.parse.urlsplit(self.path[len(prefix):]).path
        if route not in ROUTES:return self.fail(404,'Unsupported model endpoint')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY:return self.fail(413,'Body limit')
            payload=json.loads(self.rfile.read(length))
            incoming_tokens=estimate(json.dumps(payload,ensure_ascii=False))
            attachment_replacements=0
            job=copy.deepcopy(self.server.job)
            initial=getattr(self.server,'initial_prompt',None)
            if initial:
                field='input' if ROUTES[route]=='responses' else 'messages'
                for item in payload.get(field,[]) if isinstance(payload.get(field),list) else []:
                    if not isinstance(item,dict) or item.get('role')!='user':continue
                    content=item.get('content')
                    block_type='input_text' if ROUTES[route]=='responses' else 'text'
                    def split(text):
                        nonlocal attachment_replacements
                        if is_initial_attachment(text,initial,getattr(self.server,'initial_prompt_path',None)):
                            attachment_replacements+=1
                            return [{'type':block_type,'text':managed_context(initial,job,self.server.secret)}]
                        if not isinstance(text,str) or initial not in text:return None
                        before,after=text.split(initial,1)
                        return ([{'type':block_type,'text':before}] if before else [])+[{'type':block_type,'text':managed_context(initial,job,self.server.secret)}]+([{'type':block_type,'text':after}] if after else [])
                    if isinstance(content,str):
                        replacement=split(content)
                        if replacement:item['content']=replacement
                    elif isinstance(content,list):
                        replaced=[]
                        for block in content:
                            replacement=split(block.get('text')) if isinstance(block,dict) and block.get('type') in ('text','input_text') else None
                            replaced.extend(replacement or [block])
                        item['content']=replaced
            if not getattr(self.server,'fixed_request',False):
                job['request']=current_request(payload,ROUTES[route],job['request'])
            transformed,metrics=prepare_turn(payload,ROUTES[route],job,packer=self.server.packer,secret=self.server.secret)
            if getattr(self.server,'model_override',None):transformed['model']=self.server.model_override
            data=json.dumps(transformed,ensure_ascii=False).encode()
            prepared=time.perf_counter()
            # Forward only explicitly allowed model headers. Never follow redirects with credentials.
            headers={k:v for k,v in self.headers.items() if k.lower() in ('authorization','x-api-key','anthropic-version','anthropic-beta','openai-organization','openai-project','chatgpt-account-id','openai-beta','user-agent','x-app','x-stainless-lang','x-stainless-package-version','x-stainless-runtime','x-stainless-runtime-version','x-stainless-os','x-stainless-arch')}
            headers['Content-Type']='application/json';headers['Accept-Encoding']='identity'
            target=self.server.upstream+self.path[len(prefix):]
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args):return None
            opener=urllib.request.build_opener(NoRedirect())
            upstream_started=time.perf_counter()
            try:response=opener.open(urllib.request.Request(target,data,headers),timeout=180)
            except urllib.error.HTTPError as error:
                response=error
                if error.code==400:
                    from context_gate import scrub
                    body=error.read()
                    try:
                        detail=json.loads(body).get('error',{})
                        self.server.events.append({'error_type':str(detail.get('type',''))[:80], 'message':scrub(str(detail.get('message','')))[:180]})
                    except (ValueError,AttributeError):pass
                    import io
                    error.fp=io.BytesIO(body)
        except (ValueError,TypeError,KeyError):return self.fail(400,'Invalid request or unsupported retained server history')
        except Exception:return self.fail(503,'Context preparation or upstream connection failed; nothing sent without a ready pack')
        protocol_platform = 'anthropic' if ROUTES[route]=='anthropic' else 'openai'
        platform=job.get('platform') if job.get('platform') in ('claude','codex','gpt','zcode') else protocol_platform
        collector = UsageCollector(protocol_platform)
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        event={'endpoint':route,'upstream_status':response.code,
               'at':round(time.time(),3),
               'managed_tokens_removed_estimated':metrics['managed_tokens_removed_estimated'],
               'initial_attachment_replacements':attachment_replacements,
               'request_before_tokens_estimated':incoming_tokens,
               'request_after_tokens_estimated':metrics['request_after_tokens_estimated'],
               'prepare_ms':round((prepared-started)*1000,2),
               'upstream_headers_ms':round((time.perf_counter()-upstream_started)*1000,2),
               'first_response_byte_ms':None,'upstream_total_ms':None,'response_bytes':0}
        self.server.events.append(event)
        metrics_job=metrics['gate_metrics']
        record_id=metrics.get('accounting_id') or str(uuid.uuid4())
        counted='baseline_tokens_estimated' in metrics_job and not route.endswith('/count_tokens')
        if counted:
            event['ledger_id']=record_id  # evidence.py references this row; it never re-bills it
            save(record_id,platform,metrics_job,True,ready=True,timing=event,model=transformed.get('model'))
        with response:
            self.send_response(response.code)
            self.send_header('Content-Type',response.headers.get('Content-Type','application/json'))
            self.send_header('Cache-Control','no-store')
            self.send_header('Connection','close');self.end_headers();self.close_connection=True
            try:
                while True:
                    chunk=response.read1(65536)
                    if not chunk:break
                    if event['first_response_byte_ms'] is None:
                        event['first_response_byte_ms']=round((time.perf_counter()-upstream_started)*1000,2)
                    event['response_bytes']+=len(chunk)
                    try:collector.feed(decoder.decode(chunk))
                    except (ValueError,TypeError,AttributeError):pass  # Accounting must never interrupt inference.
                    self.wfile.write(chunk);self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):pass
            finally:
                event['upstream_total_ms']=round((time.perf_counter()-upstream_started)*1000,2)
                event['total_ms']=round((time.perf_counter()-started)*1000,2)
                streamed='text/event-stream' in response.headers.get('Content-Type','')
                event['stream_completed']=collector.completed if streamed else None
                event['exit_code']=response.code if response.code>=400 else 502 if collector.has_error or (streamed and not collector.completed) else 0
                if counted:
                    save(record_id, platform, metrics_job, True, collector.usage, exit_code=event['exit_code'],timing=event,model=transformed.get('model') or collector.model)


def make_server(port,upstream,job,secret,packer=call_service):
    parsed=urllib.parse.urlparse(upstream)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1')):
        raise ValueError('Upstream must be HTTPS or local loopback')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Unsafe upstream URL')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    server.events=[]
    server.upstream=upstream.rstrip('/');server.job=copy.deepcopy(job);server.secret=secret
    server.local_token=secrets.token_urlsafe(32);server.packer=packer
    return server


def main():
    p=argparse.ArgumentParser(description='每个 agent 独立的每轮 REST 网关（Responses / Chat / Anthropic）')
    p.add_argument('--job',required=True,help='包含 root/memory/request/agent_id/session_id/task_id/platform 的 JSON 文件')
    p.add_argument('--upstream',required=True,help='上游服务根地址，不含 /v1')
    p.add_argument('--port',type=int,default=0);p.add_argument('--connection',required=True)
    a=p.parse_args()
    server=make_server(a.port,a.upstream,json.loads(Path(a.job).read_text()),secrets.token_bytes(32))
    private_write(Path(a.connection),json.dumps({'base_url':'http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token,'agent_id':server.job['agent_id']}))
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
