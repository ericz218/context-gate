#!/usr/bin/env python3
"""Restart the console backend without opening or activating the native app.

Stop the running backend and wait for an existing app reconnect.
Only if the app does not bring one up within 20 seconds is a backend started by hand,
and that process must be able to access the memory documents.
Before stopping, refuse when quota pauses or active tasks/group jobs exist (--force skips this).
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONNECTION = Path.home() / '.local' / 'state' / 'context-gate' / 'console-connection.json'
ACTIVE = frozenset(('queued', 'starting', 'running', 'stopping'))
APP_NAME = 'Context Gate 控制台'
APP_EXECUTABLE = Path('/Applications') / (APP_NAME + '.app') / 'Contents/MacOS/ContextGateConsole'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def _get_json(url, timeout=15):
    with _OPENER.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def connection_url(info):
    """Only accept the local token URL written by this console."""
    base = info.get('base_url')
    if isinstance(base, str) and re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/[A-Za-z0-9_-]+/', base):
        try:
            if urllib.parse.urlsplit(base).port:
                return base
        except ValueError:
            pass
    return None


def memory_access(info):
    """Check the registered backend itself, using a status independent of UI text."""
    base = connection_url(info)
    if not base:
        return None
    try:
        data = _get_json(base + 'v1/console/health', timeout=2)
        if isinstance(data, dict) and data.get('service') == 'context-gate-console' and data.get('pid') == info['pid']:
            return data.get('memory_documents')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _patterns():
    """pgrep patterns for both repo locations (source of truth may move).

    Never widen by root-string prefix: only the two exact backend entry
    points count, so an unrelated '.../context-gate...' process is not killed.
    """
    return [str(ROOT / 'console' / 'app.py') + ' --no-browser',
            str(Path.home() / 'Documents' / 'context-gate' / 'console' / 'app.py') + ' --no-browser']


def backend_pids(pattern=None):
    # pattern stays accepted positionally for the existing tests; None means
    # "both known entry points".
    patterns = [pattern] if pattern else _patterns()
    found = set()
    for text in patterns:
        result = subprocess.run(['pgrep', '-f', text], capture_output=True, text=True)
        if result.returncode == 1:
            continue
        if result.returncode != 0:
            raise RuntimeError('pgrep 失败: ' + result.stderr.strip())
        found.update(int(line) for line in result.stdout.split() if line.strip().isdigit())
    return sorted(found)


def precheck(base, timeout=15):
    # base_url ends with the local token and '/', so join paths without a double slash.
    root = base.rstrip('/')
    quota = _get_json(root + '/v1/quota', timeout)
    for state in (quota.get('platforms') or {}).values():
        if (state.get('protection') or {}).get('paused_count', 0) != 0:
            raise RuntimeError('有暂停中的任务')
    for task in _get_json(root + '/v1/center/tasks', timeout).get('tasks') or []:
        if task.get('status') in ACTIVE:
            raise RuntimeError('有执行中的任务')
    for group in _get_json(root + '/v1/groups', timeout).get('groups') or []:
        detail = _get_json(root + '/v1/groups?' + urllib.parse.urlencode({'id': group['id']}), timeout)
        for job in detail.get('jobs') or []:
            if job.get('status') in ACTIVE:
                raise RuntimeError('有执行中的群聊任务')


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_connection():
    info = json.loads(CONNECTION.read_text(encoding='utf-8'))
    if not isinstance(info, dict) or type(info.get('pid')) is not int or info['pid'] <= 1 or not connection_url(info):
        raise ValueError('无效的控制台连接信息')
    return info


def wait_until(check, seconds):
    deadline = time.monotonic() + seconds
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--force', action='store_true', help='skip the precheck for paused quota and active tasks')
    args = parser.parse_args(argv)

    try:
        info = read_connection()
    except FileNotFoundError:
        info = {}
    except (OSError, ValueError) as error:
        print('读取连接文件失败: %s' % error)
        sys.exit(1)
    base = info.get('base_url')
    pid = info.get('pid')

    if isinstance(pid, int) and alive(pid) and not args.force:
        try:
            precheck(base)
        except (RuntimeError, OSError, ValueError, KeyError) as error:
            print('拒绝重载: %s' % error)
            sys.exit(1)

    old = set()
    if isinstance(pid, int) and alive(pid):
        if memory_access(info) is None and pid not in backend_pids():
            print('无法确认登记进程属于控制台，已保留该进程。')
            sys.exit(1)
        old.add(pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if not wait_until(lambda: not any(alive(p) for p in old), 10):
        print('旧后端未在 10 秒内退出: %s' % sorted(p for p in old if alive(p)))
        sys.exit(1)

    # Ask the resident App for a backend even when neither of its windows is open.
    try:
        subprocess.run([str(APP_EXECUTABLE), '--ensure-backend'], timeout=3,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass

    def new_backend_ready():
        try:
            current = read_connection()
        except (OSError, ValueError):
            return False
        current_pid = current.get('pid')
        if not isinstance(current_pid, int) or current_pid in old or not alive(current_pid):
            return False
        return current if memory_access(current) in ('readable', 'missing') else False

    ready = wait_until(new_backend_ready, 20)
    if not ready:
        # The server lock prevents this fallback from taking over a backend
        # that another launcher has already started.
        fallback = subprocess.Popen(['/usr/bin/python3', str(ROOT / 'console' / 'app.py'), '--no-browser',
                                     '--require-memory-access'], cwd=str(ROOT),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        wait_until(lambda: new_backend_ready() or fallback.poll() is not None, 20)
        ready = new_backend_ready()
        if not ready and fallback.poll() == 3:
            print('兜底后端读不到「文稿」目录。请打开「%s」App。' % APP_NAME)
            sys.exit(1)

    if ready:
        print('reloaded pid %s' % ready['pid'])
        return
    print('没有通过记忆文档读取检查的控制台后端。')
    sys.exit(1)


if __name__ == '__main__':
    main()
