#!/usr/bin/env python3
"""Watch proxy between the ZCode app and the Z.ai coding-plan endpoint.

Forwards every request byte-for-byte (minus hop-by-hop headers), records the
model and real usage of each Messages call in the shared token ledger, and
never lets accounting break a chat. Self-contained on purpose: the installed
copy runs from ~/.local/state, where LaunchAgents can read, so it imports
nothing from the repository. Accounting-only by design: app conversations
carry no project/memory identity, so there is nothing to filter here.
"""
import argparse
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path(os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate')).expanduser()
DEFAULT_UPSTREAM = 'https://zcode.z.ai/api/v1/zcode-plan/anthropic'
DEFAULT_PORT = 8768
MAX_BODY = 32 * 1024 * 1024
HOP_HEADERS = {'host', 'content-length', 'connection', 'accept-encoding', 'transfer-encoding'}


def load_rules():
    """Mirror prices.py just enough for money sums; prices.json is the shared truth."""
    rules = []
    try:
        user = json.loads((STATE / 'prices.json').read_text()).get('rules')
        if isinstance(user, list):
            rules = [r for r in user if isinstance(r, dict) and isinstance(r.get('match'), str)]
    except (OSError, ValueError):
        pass
    for rule in rules:
        for key in ('input', 'output', 'cache_read', 'cache_write'):
            value = rule.get(key)
            rule[key] = max(0.0, float(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if rule.get('input') is None:
            continue
        rule['input'] = rule['input'] or 0.0
        rule['cache_read'] = rule['cache_read'] if rule.get('cache_read') is not None else round(rule['input'] * 0.1, 6)
        rule['cache_write'] = rule['cache_write'] if rule.get('cache_write') is not None else round(rule['input'] * 1.25, 6)
        rule['output'] = rule['output'] or 0.0
    return [r for r in rules if r.get('input') is not None]


def row_cost(model, usage, rules):
    name = str(model or '').lower()
    for rule in rules:
        if rule['match'].lower() in name:
            creation = min(usage.get('cache_creation') or 0, usage.get('input') or 0)
            plain = (usage.get('input') or 0) - creation
            return round(plain / 1e6 * rule['input']
                         + creation / 1e6 * rule['cache_write']
                         + (usage.get('cached') or 0) / 1e6 * rule['cache_read']
                         + (usage.get('output') or 0) / 1e6 * rule['output'], 6)
    return None


def extract_events(text):
    """Yield JSON objects from a buffer of SSE/NDJSON/plain-JSON responses."""
    decoder = json.JSONDecoder()
    buffer = text
    while True:
        start = buffer.find('{')
        if start < 0:
            return
        buffer = buffer[start:]
        try:
            event, end = decoder.raw_decode(buffer)
        except ValueError:
            return
        yield event
        buffer = buffer[end:]


def sniff(text):
    """Pull model and Anthropic usage out of head+tail buffers of the response.

    input follows the ledger convention: plain + cache-read + cache-creation
    (the subsets are stored separately and re-priced by row_cost).
    """
    result = {'model': None, 'input': None, 'output': 0, 'cached': 0, 'cache_creation': None}
    for event in extract_events(text):
        if not isinstance(event, dict):
            continue
        message = event.get('message') if isinstance(event.get('message'), dict) else event
        if result['model'] is None and isinstance(message.get('model'), str):
            result['model'] = message['model']
        usage = message.get('usage') if isinstance(message.get('usage'), dict) else None
        if usage is None:
            continue
        parts = [usage.get('input_tokens') or 0,
                 usage.get('cache_read_input_tokens') or 0,
                 usage.get('cache_creation_input_tokens') or 0]
        if all(isinstance(part, int) for part in parts):
            result['input'] = (result['input'] or 0) + sum(parts)
        read = usage.get('cache_read_input_tokens')
        if isinstance(read, int) and read >= 0:
            result['cached'] = (result['cached'] or 0) + read
        creation = usage.get('cache_creation_input_tokens')
        if isinstance(creation, int) and creation >= 0:
            result['cache_creation'] = (result['cache_creation'] or 0) + creation
        output = usage.get('output_tokens')
        if isinstance(output, int) and output >= 0:
            result['output'] = max(result['output'], output)
    return result


def save_row(record_id, platform, model, usage, exit_code, before_est, duration_ms=None):
    """Ledger insert; a failure here must never affect the chat (fail-open)."""
    try:
        (STATE / 'tokens.sqlite3').chmod(0o600)
    except OSError:
        pass
    try:
        with sqlite3.connect(STATE / 'tokens.sqlite3') as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER)')
            connection.execute('CREATE INDEX IF NOT EXISTS idx_turns_at ON turns(at)')
            cols = {r[1] for r in connection.execute('PRAGMA table_info(turns)')}
            for name, kind in (('ready', 'INTEGER'), ('jev_actual_input', 'INTEGER'), ('jev_actual_output', 'INTEGER'), ('model', 'TEXT'), ('cache_creation', 'INTEGER'), ('duration_ms', 'REAL')):
                if name not in cols:
                    connection.execute(f'ALTER TABLE turns ADD COLUMN {name} {kind}')
            connection.execute('INSERT OR REPLACE INTO turns (id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,cached,exit_code,ready,jev_actual_input,jev_actual_output,model,cache_creation,duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                record_id, time.time(), platform, 1, before_est, before_est, 0,
                usage.get('input'), usage.get('output'), usage.get('cached'), exit_code, 1, None, None, model, usage.get('cache_creation'), duration_ms))
        connection.close()
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args): pass

    def reply_local(self, code, message):
        data = json.dumps({'error': message}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def forward(self, body):
        if self.server.token_prefix:
            if not self.path.startswith(self.server.token_prefix + '/'):
                return self.reply_local(403, 'Unauthorized local route')
            url = self.server.upstream + self.path[len(self.server.token_prefix):]
        else:
            # Tokenless mode: the Anthropic SDK drops base-URL paths, so a path
            # token cannot survive; loopback binding is the boundary instead.
            url = self.server.upstream + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        headers['Accept-Encoding'] = 'identity'
        request = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        upstream_started = time.perf_counter()
        try:
            response = urllib.request.urlopen(request, timeout=600)
        except urllib.error.HTTPError as error:
            response = error
        except Exception:
            return self.reply_local(502, 'watch proxy cannot reach upstream; chat not sent')
        self.send_response(response.code)
        for key, value in response.headers.items():
            if key.lower() not in HOP_HEADERS:
                self.send_header(key, value)
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        # The CLI appends query params (e.g. ?beta=true) to the Messages route.
        route = self.path.split('?', 1)[0]
        accounting = (self.command == 'POST'
                      and route.endswith('/messages')
                      and not route.rstrip('/').endswith('count_tokens'))
        head, tail, fed = b'', b'', 0
        try:
            while True:
                chunk = response.read1(65536) if hasattr(response, 'read1') else response.read(65536)
                if not chunk:
                    break
                fed += len(chunk)
                self.wfile.write(chunk)
                self.wfile.flush()
                if fed <= 65536:
                    head += chunk
                else:
                    tail = (tail + chunk)[-262144:]
        except (BrokenPipeError, ConnectionResetError):
            pass
        if not accounting:
            return
        try:
            if fed <= 65536:
                text = head.decode('utf-8', errors='replace')
            else:
                kept = min(fed - 65536, 262144)
                text = head.decode('utf-8', errors='replace') + tail[len(tail) - kept:].decode('utf-8', errors='replace')
            found = sniff(text)
            model = found['model'] or self.server.last_body_model
            if not model:
                return
            usage = {k: found[k] for k in ('input', 'output', 'cached', 'cache_creation')}
            before = len(body) // 4
            duration_ms = round((time.perf_counter() - upstream_started) * 1000, 1)
            save_row('watch-' + uuid.uuid4().hex, self.server.platform, model, usage,
                     0 if 200 <= response.code < 400 else response.code, before, duration_ms)
        except Exception:
            pass

    def do_POST(self):
        if self.server.token_prefix and not self.path.startswith(self.server.token_prefix + '/'):
            return self.reply_local(403, 'Unauthorized local route')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.reply_local(413, 'Body limit')
            body = self.rfile.read(length)
        except (ValueError, OSError):
            return self.reply_local(400, 'Invalid request body')
        try:
            self.server.last_body_model = json.loads(body).get('model')
        except ValueError:
            self.server.last_body_model = None
        self.forward(body)

    def do_GET(self):
        if self.server.token_prefix and not self.path.startswith(self.server.token_prefix + '/'):
            return self.reply_local(403, 'Unauthorized local route')
        self.forward(None)


def make_server(port, upstream, platform='zcode', token=True):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.upstream = upstream.rstrip('/')
    server.platform = platform
    server.local_token = secrets.token_urlsafe(32) if token else None
    server.token_prefix = ('/' + server.local_token) if token else None
    return server


def instance_names(platform):
    """The zcode instance keeps its original file names for compatibility."""
    if platform == 'zcode':
        return 'zcode-watch.py', 'zcode-watch-connection.json', 'local.context-gate.zcode-watch'
    return f'watch-{platform}.py', f'watch-{platform}-connection.json', f'local.context-gate.watch-{platform}'


def install(platform, port, upstream, token=True):
    script_name, connection_name, label = instance_names(platform)
    target = STATE / script_name
    target.write_text(Path(__file__).read_text())
    os.chmod(target, 0o600)
    plist_dir = Path.home() / 'Library/LaunchAgents'
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / (label + '.plist')
    token_args = '' if token else '\n\t\t<string>--no-token</string>'
    plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
	<key>Label</key><string>{label}</string>
	<key>ProgramArguments</key><array>
		<string>/usr/bin/python3</string><string>{target}</string>
		<string>--port</string><string>{port}</string>
		<string>--upstream</string><string>{upstream}</string>
		<string>--platform</string><string>{platform}</string>{token_args}
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>StandardErrorPath</key><string>{STATE}/{script_name}.err.log</string>
</dict></plist>''')
    print('installed:', target, '+', plist)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--upstream', default=DEFAULT_UPSTREAM)
    parser.add_argument('--platform', default='zcode')
    parser.add_argument('--no-token', action='store_true', help='loopback-only; the Anthropic SDK drops base-URL paths, so the claude instance runs without a path token')
    parser.add_argument('--install', action='store_true', help='copy self to STATE and write the LaunchAgent')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.install:
        install(args.platform, args.port, args.upstream, token=not args.no_token)
        return 0
    server = make_server(args.port, args.upstream, args.platform, token=not args.no_token)
    script_name, connection_name, _ = instance_names(args.platform)
    url = 'http://127.0.0.1:' + str(server.server_port) + (server.token_prefix or '') + '/'
    fd = os.open(STATE / connection_name, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps({'base_url': url, 'upstream': server.upstream, 'platform': args.platform, 'pid': os.getpid()}).encode())
    finally:
        os.close(fd)
    print(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
