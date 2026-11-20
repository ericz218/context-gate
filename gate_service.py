#!/usr/bin/env python3
"""Authenticated loopback service shared by all platform and agent clients."""
import argparse
import dataclasses
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import fcntl
import threading
import time
import uuid
import urllib.error
import urllib.request
from context_gate import Config, DecisionClient, MemoryOSSource, SECRET_NAMES, build_pack

STATE = Path(os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate')).expanduser()
# ensure_service spawns the daemon with an explicit allow-root list. Keep it to
# the two migrated project locations only -- never $HOME or '/'.
DEFAULT_ALLOW_ROOTS = (str(Path.home() / 'Documents'), str(Path.home() / 'Projects'))
DEFAULT_PORT = 8767
MAX_BODY = 16 * 1024 * 1024


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, content.encode())
    finally:
        os.close(fd)


class SharedClient:
    def __init__(self, config, client=None):
        self.client = client or DecisionClient(config)
        self.auth_lock = threading.Lock()
        self.laya_lock = threading.Lock()

    def authenticate(self):
        with self.auth_lock:
            return self.client.authenticate()

    def ask(self, provider, state, questions):
        if provider == 'laya':
            with self.laya_lock:
                return self.client.ask(provider, state, questions)
        # Only serialize authentication, not independent Jev network requests.
        if hasattr(self.client, 'authenticate'):
            self.authenticate()
        return self.client.ask(provider, state, questions)


class Engine:
    def __init__(self, roots, config=None, client=None, state_dir=STATE, memory_source=None):
        self.roots = tuple(Path(p).expanduser().resolve() for p in roots)
        if not self.roots:
            raise ValueError('必须配置允许访问的项目根目录')
        self.config = config or Config()
        self.config.validate()
        self.client = SharedClient(self.config, client)
        self.state_dir = Path(state_dir)
        self.capacity = threading.BoundedSemaphore(4)
        self.metrics_lock = threading.Lock()
        self.memory_source = memory_source

    def validate(self, body):
        if not isinstance(body, dict):
            raise ValueError('请求必须是 JSON 对象')
        root = Path(body.get('root', '')).expanduser().resolve()
        if not root.is_dir() or not any(root.is_relative_to(base) for base in self.roots):
            raise ValueError('项目不在服务允许目录内')
        request = body.get('request')
        if not isinstance(request, str) or not request.strip():
            raise ValueError('缺少当前请求')
        memories = body.get('memory')
        if not isinstance(memories, list) or not memories or any(not isinstance(x, str) for x in memories):
            raise ValueError('memory 必须是现有记忆文档路径数组')
        for m in memories:
            p = Path(m).expanduser().resolve()
            if not p.is_relative_to(root) or any(SECRET_NAMES.search(x) for x in p.parts):
                raise ValueError('记忆文档必须在当前项目内且不能是凭据文件')
        identities = {}
        for key in ('agent_id', 'session_id', 'task_id'):
            value = body.get(key)
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise ValueError('必须提供 ' + key + '（1–128 字符）')
            identities[key] = value
        platform = body.get('platform', 'generic')
        if platform not in ('generic', 'claude', 'codex', 'gpt', 'zcode', 'openai', 'anthropic'):
            raise ValueError('未知 platform')
        hints = body.get('terms', [])
        if not isinstance(hints, list) or len(hints) > 64 or any(not isinstance(t, str) or len(t) > 200 for t in hints):
            raise ValueError('terms 格式无效')
        return root, request, [str(Path(m).expanduser().resolve()) for m in memories], identities, platform, hints

    def pack(self, body):
        root, request, memories, ids, platform, hints = self.validate(body)
        if not self.capacity.acquire(timeout=2):
            raise RuntimeError('服务繁忙，请稍后重试')
        try:
            # Each request is built from its own task; no conversation or selected-pack cache.
            config = dataclasses.replace(self.config,
                force_gate=self.config.force_gate or body.get('force_gate') is True)
            result = build_pack(root, request, memories, config, self.client, hints, self.memory_source)
            result['identity'] = {**ids, 'platform': platform}
            result['accounting_id'] = str(uuid.uuid4())
            from token_stats import save
            save(result['accounting_id'], platform, result['metrics'], False,
                 state_dir=self.state_dir, ready=result['ready_to_send'])
            record = {'at': time.time(), 'platform': platform,
                      'project_hash': hashlib.sha256(str(root).encode()).hexdigest()[:16],
                      'identity_hash': hashlib.sha256(json.dumps(ids, sort_keys=True).encode()).hexdigest()[:16],
                      'mode': result['mode'], 'ready_to_send': result['ready_to_send'], **result['metrics']}
            with self.metrics_lock:
                self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(self.state_dir / 'metrics.jsonl', os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, (json.dumps(record, ensure_ascii=False) + '\n').encode())
                finally:
                    os.close(fd)
            return result
        finally:
            self.capacity.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'ContextGate/2'

    def log_message(self, *args):
        pass  # Never write requests, contents, tokens or auth headers to access logs.

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        header = self.headers.get('Authorization', '')
        return secrets.compare_digest(header, 'Bearer ' + self.server.gate_token)

    def do_GET(self):
        if not self.authorized():
            return self.reply(401, {'error': 'unauthorized'})
        if self.path.startswith('/v1/evidence'):
            if self.headers.get('Origin'):
                return self.reply(403, {'error': 'browser_origin_not_allowed'})
            from evidence import http_get
            try:
                result = http_get(self.path, self.server.engine.state_dir)
            except ValueError as exc:
                return self.reply(400, {'error': 'invalid_request', 'detail': str(exc)[:200]})
            return self.reply(200, result) if result is not None else self.reply(404, {'error': 'not_found'})
        if self.path != '/health':
            return self.reply(404, {'error': 'not_found'})
        return self.reply(200, {'service': 'context-gate', 'version': 2, 'multi_agent': True})

    def do_POST(self):
        if not self.authorized():
            return self.reply(401, {'error': 'unauthorized'})
        # Browser cross-origin requests cannot drive local project reads.
        if self.headers.get('Origin'):
            return self.reply(403, {'error': 'browser_origin_not_allowed'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.reply(413, {'error': 'body_limit'})
            body = json.loads(self.rfile.read(length))
            if self.path == '/v1/pack':
                return self.reply(200, self.server.engine.pack(body))
            if self.path == '/v1/turn':
                from gate_turn import prepare_turn
                payload, metrics = prepare_turn(body['payload'], body['protocol'], body['job'],
                    packer=self.server.engine.pack, secret=self.server.gate_token.encode())
                return self.reply(200, {'payload': payload, 'metrics': metrics})
            if self.path == '/v1/evidence':
                from evidence import http_record, EvidenceError
                try:
                    return self.reply(200, http_record(body, self.server.engine.roots, self.server.engine.state_dir))
                except EvidenceError as exc:
                    return self.reply(409, {'error': 'evidence_chain', 'detail': str(exc)[:200]})
            if self.path == '/v1/warm':
                self.server.engine.client.authenticate()
                return self.reply(200, {'ready': True})
            return self.reply(404, {'error': 'not_found'})
        except (ValueError, TypeError, KeyError) as exc:
            return self.reply(400, {'error': 'invalid_request', 'detail': str(exc)[:200]})
        except Exception as exc:
            return self.reply(503, {'error': 'service_failed', 'error_type': type(exc).__name__})


def make_server(port, token, engine):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.gate_token = token
    server.engine = engine
    server.daemon_threads = True
    return server


def ensure_service(state_dir=STATE):
    directory=Path(state_dir)
    if (directory/'disabled').exists():raise RuntimeError('Context Gate explicitly stopped; run manage.py install to resume')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    def healthy():
        try:
            settings=json.loads((directory/'connection.json').read_text())
            token=(directory/'access-token').read_text().strip()
            request=urllib.request.Request('http://127.0.0.1:'+str(int(settings['port']))+'/health',headers={'Authorization':'Bearer '+token})
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args):return None
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=1) as response:
                return json.load(response).get('service')=='context-gate'
        except (OSError,ValueError,KeyError):return False
    if healthy():return
    with open(directory/'startup.lock','a') as lock:
        os.chmod(directory/'startup.lock',0o600)
        fcntl.flock(lock,fcntl.LOCK_EX)
        if healthy():return
        with open(directory/'service.log','a') as log:
            command=[sys.executable,str(Path(__file__).resolve()),'--port','0','--state-dir',str(directory)]
            for allow_root in DEFAULT_ALLOW_ROOTS:command.extend(['--allow-root',allow_root])
            subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
        for _ in range(30):
            if healthy():return
            time.sleep(.1)
        raise RuntimeError('Context Gate service startup failed')


def call_service(body=None, path='/v1/pack', state_dir=STATE, timeout=180):
    directory = Path(state_dir)
    ensure_service(directory)
    settings = json.loads((directory / 'connection.json').read_text())
    token = (directory / 'access-token').read_text().strip()
    # Only fixed local address: no redirects or user-configurable remote credential forwarding.
    url = 'http://127.0.0.1:' + str(int(settings['port'])) + path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description='Context Gate 跨平台、多 agent 常驻服务')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--allow-root', action='append', required=True)
    parser.add_argument('--config')
    parser.add_argument('--state-dir', default=str(STATE))
    args = parser.parse_args()
    state = Path(args.state_dir).expanduser()
    cfg = Config(**json.loads(Path(args.config).read_text())) if args.config else Config()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    token_path = state / 'access-token'
    token = token_path.read_text().strip() if token_path.exists() else secrets.token_urlsafe(32)
    private_write(token_path, token)
    engine = Engine(args.allow_root, cfg, state_dir=state,
                    memory_source=MemoryOSSource.local(cfg) if cfg.memory_os else None)
    server = make_server(args.port, token, engine)
    private_write(state / 'connection.json', json.dumps({'port': server.server_port, 'pid': os.getpid()}))
    print(json.dumps({'service': 'context-gate', 'port': server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
