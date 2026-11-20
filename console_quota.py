"""Read subscription limits without model turns; credentials never leave readers."""
import base64
import copy
import datetime
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request

INTERVALS = (5, 15, 30, 60, 180, 300, 600, 1800)
MIN_INTERVAL = {'claude': 60}  # Claude usage endpoint answers 429 to faster polling
PLATFORMS = ('codex', 'claude')
DEFAULT = {'enabled': False, 'interval': 60, 'five_hour_threshold': 10, 'weekly_threshold': 5, 'notify': True, 'stop_all': False, 'resume_paused': False}
WINDOW_SECONDS = {'five_hour': 5*3600, 'weekly': 7*86400}
RANGES = ('day', 'week', 'month', 'year', 'all')
RANGE_SECONDS = {'week': 7*86400, 'month': 30*86400, 'year': 365*86400}
HISTORY_FILE = 'quota-history.jsonl'
HISTORY_KEEP = 5000
HISTORY_BYTES = 10*1024*1024


class QuotaError(Exception):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def percent(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return max(0, min(100, 100-value))


def reset_time(value):
    if type(value) in (int, float) and math.isfinite(value) and value > 0:
        return value
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo: return dt.timestamp()
        except ValueError: pass
    return None


def parse_claude(data):
    if not isinstance(data, dict): raise QuotaError('Claude额度响应无效')
    return [{'bucket': 'claude', 'window': name, 'remaining': percent((data.get(key) or {}).get('utilization')), 'resets_at': reset_time((data.get(key) or {}).get('resets_at'))}
            for name, key in [('five_hour', 'five_hour'), ('weekly', 'seven_day')]
            if isinstance(data.get(key), dict)]


def parse_codex(data):
    if not isinstance(data, dict): raise QuotaError('Codex额度响应无效')
    buckets = data.get('rateLimitsByLimitId')
    if not isinstance(buckets, dict) or not buckets:
        single = data.get('rateLimits')
        buckets = {str(single.get('limitId') or 'codex'): single} if isinstance(single, dict) else {}
    windows = []
    for identifier, bucket in buckets.items():
        if not isinstance(bucket, dict): continue
        for key in ('primary', 'secondary'):
            w = bucket.get(key)
            if not isinstance(w, dict): continue
            duration = w.get('windowDurationMins')
            if duration not in (300, 10080): continue
            windows.append({'bucket': str(identifier)[:100], 'window': 'five_hour' if duration == 300 else 'weekly',
                            'remaining': percent(w.get('usedPercent')), 'resets_at': reset_time(w.get('resetsAt'))})
    return windows


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None


def read_claude():
    try:
        p = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', 'Claude Code-credentials', '-w'], capture_output=True, timeout=8)
        if p.returncode: raise QuotaError('未找到Claude Code登录；请先登录后刷新')
        token = json.loads(p.stdout).get('claudeAiOauth', {}).get('accessToken')
        if not isinstance(token, str) or not token: raise QuotaError('Claude Code未提供订阅登录令牌')
        req = urllib.request.Request('https://api.anthropic.com/api/oauth/usage', headers={
            'Authorization': 'Bearer '+token, 'anthropic-beta': 'oauth-2025-04-20', 'Accept': 'application/json'})
        # No redirects or inherited proxy: credentials go only to the fixed official endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=15) as response:
            raw = response.read(262145)
        if len(raw) > 262144: raise QuotaError('Claude额度响应超出预期')
        return parse_claude(json.loads(raw))
    except urllib.error.HTTPError as exc:
        if exc.code == 401: raise QuotaError('Claude登录已过期；请在Claude Code重新登录后刷新') from None
        if exc.code == 429:
            try: delay = max(60, float(exc.headers.get('Retry-After', 60)))
            except (ValueError, TypeError): delay = 60
            if not math.isfinite(delay): delay = 60
            raise QuotaError('Claude额度查询受限，正在等待重试', min(delay, 86400)) from None
        raise QuotaError('Claude额度接口不可用（HTTP %s）' % exc.code) from None
    except QuotaError: raise
    except (OSError, ValueError, subprocess.SubprocessError):
        raise QuotaError('Claude额度读取失败；请检查登录与网络后刷新') from None


def codex_executable():
    configured = os.environ.get('QUOTAGUARD_CODEX')
    if configured and Path(configured).is_file() and os.access(configured, os.X_OK): return configured
    executable = shutil.which('codex')
    if executable: return executable
    for bundled in (Path('/opt/homebrew/bin/codex'), Path('/usr/local/bin/codex'), Path('/Applications/Codex.app/Contents/Resources/codex')):
        if bundled.is_file() and os.access(bundled, os.X_OK): return str(bundled)
    raise QuotaError('未找到Codex CLI；请安装或设置QUOTAGUARD_CODEX')


def read_codex():
    p = None
    try:
        p = subprocess.Popen([codex_executable(), 'app-server', '--stdio'], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=Path.home())
        def send(message):
            p.stdin.write((json.dumps(message)+'\n').encode()); p.stdin.flush()
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'quota_guard', 'title': 'QuotaGuard', 'version': '1.0.0'}}})
        buffer = b''; total = 0; deadline = time.monotonic()+25
        account = None; windows = None
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if not sel.select(max(0, deadline-time.monotonic())): break
                chunk = os.read(p.stdout.fileno(), 65536)
                if not chunk: raise QuotaError('Codex额度服务提前退出；请检查登录')
                total += len(chunk); buffer += chunk
                if total > 262144: raise QuotaError('Codex额度响应超出预期')
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    msg = json.loads(line)
                    if msg.get('id') not in (1, 2, 3, 4): continue
                    if 'error' in msg: raise QuotaError('无法读取Codex额度；请检查ChatGPT登录')
                    if msg['id'] == 1:
                        send({'method': 'initialized', 'params': {}})
                        send({'id': 2, 'method': 'account/read', 'params': {'refreshToken': False}})
                    elif msg['id'] == 2:
                        current = (msg.get('result') or {}).get('account') or {}
                        account = current.get('email') if current.get('type') == 'chatgpt' else None
                        if not isinstance(account, str) or not account: account = None
                        send({'id': 3, 'method': 'account/rateLimits/read'})
                    elif msg['id'] == 3:
                        windows = parse_codex(msg.get('result'))
                        send({'id': 4, 'method': 'account/read', 'params': {'refreshToken': False}})
                    else:
                        current = (msg.get('result') or {}).get('account') or {}
                        after = current.get('email') if current.get('type') == 'chatgpt' else None
                        if not isinstance(after, str) or not after: after = None
                        if after != account: raise QuotaError('Codex账号在检查期间切换，请重新检查')
                        return {'account': account, 'windows': windows}
        raise QuotaError('Codex额度读取超时；请检查网络')
    except QuotaError: raise
    except (OSError, ValueError, subprocess.SubprocessError):
        raise QuotaError('Codex额度读取失败；请检查登录与网络后刷新') from None
    finally:
        if p:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=1)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
            if p.stdin: p.stdin.close()
            if p.stdout: p.stdout.close()


CONSOLE_APP = Path('/Applications/Context Gate 控制台.app/Contents/MacOS/ContextGateConsole')


def post_notice(platform):
    # Only fixed strings; no credentials, process names or browser text in AppleScript.
    scripts = {
        'codex': 'display notification "Codex订阅额度已达到提醒门槛，请查看控制台。" with title "订阅额度提醒"',
        'claude': 'display notification "Claude订阅额度已达到提醒门槛，请查看控制台。" with title "订阅额度提醒"',
    }
    if platform not in scripts: return False
    # The resident console app posts the alert under its own name (and falls back itself when not yet
    # authorized). A non-zero exit means no resident instance took it, so use AppleScript here.
    try:
        if CONSOLE_APP.is_file() and subprocess.run([str(CONSOLE_APP), '--notify', platform], stdout=subprocess.DEVNULL,
                                                    stderr=subprocess.DEVNULL, timeout=5).returncode == 0: return True
    except (OSError, subprocess.SubprocessError): pass
    try:
        return subprocess.run(['/usr/bin/osascript', '-e', scripts[platform]], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError): return False


notify_native = post_notice  # default notifier; test runners replace this name, never post_notice


def read_claude_account():
    """Current Claude Code account label (email preferred); None when unknown."""
    try:
        data = json.loads((Path.home() / '.claude.json').read_text())
    except (OSError, ValueError):
        return None
    oauth = data.get('oauthAccount') if isinstance(data.get('oauthAccount'), dict) else {}
    for key in ('emailAddress', 'email'):
        value = oauth.get(key)
        if isinstance(value, str) and '@' in value:
            return value
    user = data.get('userID')
    return str(user) if isinstance(user, (str, int)) and user else None


def read_codex_account():
    """Current Codex CLI account label from the local auth file; never a token value."""
    try:
        auth_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()
        tokens = json.loads((auth_home / 'auth.json').read_text()).get('tokens')
    except (OSError, ValueError):
        return None
    if not isinstance(tokens, dict):
        return None
    id_token = tokens.get('id_token')
    if isinstance(id_token, str) and id_token.count('.') >= 2:
        try:
            payload = id_token.split('.')[1]
            payload += '=' * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            for key in ('email', 'preferred_username'):
                value = claims.get(key)
                if isinstance(value, str) and value:
                    return value
        except ValueError:
            pass
    for key in ('account_id', 'email'):
        value = tokens.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def claude_login_osascript():
    # Fixed script: no user input is ever interpolated; the CLI owns the login.
    script = 'tell application "Terminal"\nactivate\ndo script "claude /login"\nend tell'
    return subprocess.run(['/usr/bin/osascript', '-e', script],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode == 0


def local_midnight(clock):
    now = datetime.datetime.fromtimestamp(clock())
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def prices_rules(state_dir):
    """Billing-page price rules (prices.py) in the console's persisted cost
    mode; None-priced models contribute no money."""
    import prices
    return prices.load_rules(state_dir, prices.load_mode(state_dir))


def notice_window_key(w):
    # An exhausted quota is one ongoing state; reset metadata is not a recovery.
    return (w['bucket'], w['window'], 'zero' if w['remaining'] == 0 else w['resets_at'])


class Quotas:
    """One quota reader and one serialized action worker; no AI or task dispatch."""
    def __init__(self, state_dir, readers=None, clock=time.time, stop_handler=None, notifier=None,
                 ledger=None, account_readers=None, login_runner=None, rules_loader=None, protection=None):
        self.path = Path(state_dir)/'quota-settings.json'
        self.readers = readers or {'codex': read_codex, 'claude': read_claude}
        self.clock = clock
        self.stop_handler = stop_handler
        # Owned-pause protection (console_quota_stop.Protection). None keeps the legacy stop_handler path.
        self.protection = protection
        self.notifier = notifier or notify_native
        self.ledger = Path(ledger) if ledger else Path(state_dir)/'tokens.sqlite3'
        self.state_dir = Path(state_dir)
        self.account_readers = account_readers or {'codex': read_codex_account, 'claude': read_claude_account}
        self.login_runner = login_runner or claude_login_osascript
        self.rules_loader = rules_loader or (lambda: prices_rules(self.state_dir))
        self.usage_cache = {}
        self.claude_login_at = 0
        self.lock = threading.RLock(); self.wake = threading.Event(); self.closed = threading.Event()
        self.prefs = {p: dict(DEFAULT) for p in PLATFORMS}
        try: self.prefs = self.validate(json.loads(self.path.read_text()))
        except (OSError, ValueError): pass
        self.states = {p: {'windows': [], 'status': 'not_checked', 'error': '', 'checked_at': None,
                           'updated_at': None, 'next_at': None, 'failures': 0, 'refreshing': False, 'stop_result': None, 'notification_sent': None, 'stop_attempted_at': None, 'account': None, 'read_duration_ms': None} for p in PLATFORMS}
        self.pending = set()
        self.account_epochs = {p: 0 for p in PLATFORMS}
        self.stop_seen = {p: set() for p in PLATFORMS}
        self.notify_seen = {p: set() for p in PLATFORMS}
        self.thread = None
        self.action_thread = None
        self.action_wake = threading.Event()
        self.actions = {}  # at most one queued action per platform
        self.action_lock = threading.Lock()  # pause/reconcile never overlap; Protection is called outside self.lock
        self.notice_path = Path(state_dir)/'quota-notices.json'
        self.cooldown_path = Path(state_dir)/'quota-cooldown.json'
        self._restore_notices()
        self._restore_recent()
        self._restore_cooldown()

    def _restore_notices(self):
        try:
            data = json.loads(self.notice_path.read_text())
            if not isinstance(data, dict) or data.get('version') != 1: return
            for p in PLATFORMS:
                self.notify_seen[p] = {tuple(k) for k in data.get(p, []) if isinstance(k, list) and len(k) == 4
                                       and isinstance(k[0], (str, type(None))) and all(isinstance(v, (str, int, float, type(None))) for v in k)}
        except (OSError, ValueError, TypeError): pass

    def _save_notices(self):
        """Caller holds self.lock. Persist only notification dedupe, never stop retries."""
        try:
            self.notice_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.notice_path.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(dict(version=1, **{p: list(self.notify_seen[p]) for p in PLATFORMS}), stream)
            os.replace(temporary, self.notice_path)
        except OSError: pass

    def _restore_recent(self):
        """Restart continuity: a backend restart used to blank both cards back to
        未检查 until the next read; with auto-checks off that meant forever. Reuse
        the newest attributed history snapshot when it is fresh. Display only:
        checked_at stays unset, so the page keeps saying when the last real check
        happened, resume evaluation keeps demanding a real post-restart check, and
        the first real refresh still re-decides alerts and stops."""
        for p in PLATFORMS:
            try:
                for entry in reversed(self._history_windows(p)):
                    ts = entry.get('ts')
                    if not isinstance(ts, (int, float)) or self.clock()-ts > 3600: break
                    account = entry.get('account'); windows = entry.get('windows')
                    if account and isinstance(windows, list) and windows and all(
                            isinstance(w, dict) and w.get('window') in ('five_hour', 'weekly') and 'remaining' in w
                            for w in windows):
                        self.states[p].update(windows=windows, status='ok', updated_at=ts, account=account)
                        break
            except Exception:
                pass

    def _restore_cooldown(self):
        """Only a failed last read keeps its 429 backoff across restarts; success restarts still read at once."""
        try:
            data = json.loads(self.cooldown_path.read_text())
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('platforms'), dict): return
            now = self.clock()
            for p in PLATFORMS:
                try:
                    entry = data['platforms'].get(p)
                    if not isinstance(entry, dict): continue
                    account, next_at, failures = entry.get('account'), entry.get('next_at'), entry.get('failures')
                    if not isinstance(account, str) or not account or account != self._account(p): continue
                    if type(next_at) not in (int, float) or not math.isfinite(next_at) or not now < next_at <= now+1800: continue
                    if type(failures) is not int or not 1 <= failures <= 64: continue
                    error = entry.get('error')
                    error = error[:200] if isinstance(error, str) and error else '额度读取失败，请稍后重试'
                    retry_at = entry.get('retry_at')
                    retry_at = retry_at if type(retry_at) in (int, float) and math.isfinite(retry_at) else now
                    self.states[p].update(account=account, status='error', error=error, failures=failures, next_at=next_at,
                                          retry_at=min(max(retry_at, now), now+60))
                except Exception: continue
        except Exception: pass

    def _save_cooldown(self):
        """Caller holds self.lock. Persist backoff only for platforms whose last read failed."""
        try:
            platforms = {}
            for p in PLATFORMS:
                state = self.states[p]
                account, next_at = state.get('account'), state.get('next_at')
                if state['status'] != 'error' or not isinstance(account, str) or not account or type(next_at) not in (int, float): continue
                platforms[p] = dict(account=account, next_at=next_at, retry_at=state.get('retry_at'), failures=state['failures'], error=str(state['error'])[:200])
            self.cooldown_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.cooldown_path.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(dict(version=1, platforms=platforms), stream)
            os.replace(temporary, self.cooldown_path)
        except Exception: pass

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or set(data) != set(PLATFORMS): raise ValueError('请提供两平台额度设置')
        out = {}
        for platform in PLATFORMS:
            prefs = data[platform]
            if not isinstance(prefs, dict): raise ValueError('额度设置字段无效')
            prefs = dict(prefs); prefs.setdefault('resume_paused', False)  # old clients omit it: off (D13)
            if set(prefs) != set(DEFAULT): raise ValueError('额度设置字段无效')
            if type(prefs['enabled']) is not bool or type(prefs['interval']) is not int or prefs['interval'] not in INTERVALS: raise ValueError('额度检查间隔无效')
            for key in ('five_hour_threshold', 'weekly_threshold'):
                if type(prefs[key]) not in (int, float) or not math.isfinite(prefs[key]) or not 1 <= prefs[key] <= 100: raise ValueError('提醒门槛须为1至100的剩余百分比')
            if type(prefs['notify']) is not bool or type(prefs['stop_all']) is not bool or type(prefs['resume_paused']) is not bool: raise ValueError('额度开关须为布尔值')
            if prefs['resume_paused'] and not (prefs['enabled'] and prefs['stop_all']): raise ValueError('额度恢复后自动继续需同时开启自动检查与报警后停止')
            prefs['interval'] = max(prefs['interval'], MIN_INTERVAL.get(platform, 0))
            out[platform] = dict(prefs)
        return out

    def settings(self, body=None):
        revoked = []
        with self.lock:
            if body is not None:
                prefs = self.validate(body)
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = self.path.with_suffix('.tmp')
                fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    os.fchmod(stream.fileno(), 0o600); json.dump(prefs, stream)
                os.replace(temporary, self.path)
                # Turning auto-continue off (or its dependencies off, which validate forces through this path) revokes owned pauses (D8).
                revoked = [p for p in PLATFORMS if self.prefs[p]['resume_paused'] and not prefs[p]['resume_paused']]
                self.prefs = prefs
                for p in PLATFORMS:
                    if prefs[p]['enabled']: self.states[p]['next_at'] = max(self.clock(), self.states[p].get('retry_at', 0))
                    if not prefs[p]['stop_all']: self.stop_seen[p].clear()
                    if not prefs[p]['notify']: self.notify_seen[p].clear()
                self._save_notices()
                self.wake.set()
            current = copy.deepcopy(self.prefs)
        # Protection takes its own locks; never call it while holding self.lock (D10).
        if revoked and self.protection is not None:
            try: self.protection.revoke(revoked)
            except Exception: pass
        return current

    def _observe_account(self, platform):
        """Caller holds self.lock; account switches do not inherit old cooldowns."""
        current = self._account(platform)
        state = self.states[platform]
        if current == state['account']: return
        self.account_epochs[platform] += 1
        state.update(account=current, windows=[], status='not_checked', error='',
                     checked_at=None, updated_at=None, failures=0, retry_at=0,
                     stop_result=None, stop_attempted_at=None, notification_sent=None,
                     next_at=self.clock() if self.prefs[platform]['enabled'] else None)
        self.usage_cache.clear()
        self.stop_seen[platform].clear()
        self.actions.pop(platform, None)
        self._save_cooldown()  # drop the old account's backoff from disk right away
        if self.prefs[platform]['enabled']: self.wake.set()

    def snapshot(self):
        with self.lock:
            for p in PLATFORMS:
                self._observe_account(p)
            platforms = copy.deepcopy(self.states)
            raw_states = copy.deepcopy(self.states); prefs_copy = copy.deepcopy(self.prefs)
            for p, state in platforms.items():
                state['settings'] = dict(self.prefs[p])
                state['alerts'] = [w['window'] for w in state['windows'] if state['status']=='ok' and w['remaining'] is not None and
                                   w['remaining'] <= self.prefs[p][w['window']+'_threshold']]
                for w in state['windows']:
                    w['usage'] = self._window_usage(p, w, state['account'])
        # Read-only journal summary, outside self.lock (D9/D10).
        summary = self._protection_summary(raw_states, prefs_copy)
        for p, state in platforms.items(): state['protection'] = summary[p]
        return {'platforms': platforms, 'intervals': list(INTERVALS), 'usage_sync': self._usage_sync()}

    def _usage_sync(self):
        """Read importer metadata only; never run/import or infer completion from file mtime."""
        try:
            path = self.state_dir/'usage-import-status.json'
            if path.stat().st_size > 4096: return {}
            data = json.loads(path.read_text())
            if not isinstance(data, dict): return {}
            out = {}
            for key in ('last_started', 'last_completed', 'next_due'):
                value = data.get(key)
                if key not in data: continue
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0): return {}
                out[key] = value
            for key in ('imported', 'skipped'):
                if key not in data: continue
                value = data[key]
                if value is not None and (type(value) is not int or value < 0): return {}
                out[key] = value
            if 'error' in data:
                if data['error'] not in (None, 'database_busy', 'database_error', 'io_error', 'import_error'): return {}
                out['error'] = data['error']
            return out
        except (OSError, ValueError, TypeError, OverflowError): return {}

    def _protection_summary(self, states, prefs):
        idle = {p: {'status': 'idle', 'paused_count': 0, 'resumed_count': 0, 'attention_count': 0, 'blocked_by': [], 'external_resume_supported': False} for p in PLATFORMS}
        if self.protection is None: return idle
        try: return self.protection.snapshot(states, prefs)
        except Exception: return {p: dict(idle[p], status='attention', attention_count=1) for p in PLATFORMS}

    def _pause_payload(self, platform):
        """Blockers of this platform's low windows; caller holds self.lock."""
        state = self.states[platform]
        blockers = [{'platform': platform, 'account': state['account'], 'bucket': w['bucket'], 'window': w['window'],
                     'threshold': self.prefs[platform][w['window']+'_threshold'], 'reset': w['resets_at'], 'observed_at': state['updated_at']}
                    for w in state['windows'] if w['remaining'] is not None and w['remaining'] <= self.prefs[platform][w['window']+'_threshold']]
        return {'platform': platform, 'blockers': blockers, 'accounts': {p: self.states[p]['account'] for p in PLATFORMS},
                'auto_resume': bool(self.prefs[platform]['resume_paused'])}

    def _reconcile_now(self):
        """Evaluate owned pauses against fresh state copies; never under self.lock (D10)."""
        if self.protection is None: return
        with self.lock:
            for p in PLATFORMS:
                self._observe_account(p)
            states = copy.deepcopy(self.states); prefs = copy.deepcopy(self.prefs)
        def live():
            with self.lock:
                for p in PLATFORMS:
                    self._observe_account(p)
                return copy.deepcopy(self.states), copy.deepcopy(self.prefs)
        if not self.action_lock.acquire(blocking=False): return
        try:
            if not self.closed.is_set(): self.protection.reconcile(states, prefs, live=live)
        except Exception: pass
        finally: self.action_lock.release()

    def _account(self, platform):
        """Current local account label; never cache across sign-in changes."""
        for attempt in range(2):
            try: account = self.account_readers[platform]()
            except Exception: account = None
            if isinstance(account, str) and account: return account
            if not attempt: time.sleep(.02)  # atomic rewrite gap; confirmed logout still clears immediately
        return None

    def _window_usage(self, platform, window, account):
        """Tokens and reference cost of one account inside one quota window.

        Only rows stamped with that platform account count; unattributed
        (pre-feature) rows and other accounts never enter the sum.
        """
        resets = window.get('resets_at')
        if not resets or not account: return None
        duration = WINDOW_SECONDS.get(window.get('window'))
        if not duration: return None
        key = (platform, account, window['window'], resets)
        cached = self.usage_cache.get(key)
        now = self.clock()
        if cached and now-cached[0] < 10: return cached[1]
        usage = None
        try:
            with sqlite3.connect(f'file:{self.ledger}?mode=ro', uri=True, timeout=2) as db:
                groups = db.execute(
                    'SELECT model, SUM(actual_input), SUM(actual_output), SUM(cached), SUM(cache_creation) '
                    'FROM turns WHERE platform=? AND sent=1 AND account IS ? AND at>=? AND at<? '
                    'AND actual_input IS NOT NULL AND actual_output IS NOT NULL GROUP BY model',
                    (platform, account, resets-duration, resets)).fetchall()
        except sqlite3.Error:
            self.usage_cache[key] = (now, None)
            return None
        if not groups:
            usage = {'tokens': None, 'cost': None, 'reason': 'not_recorded'}
            self.usage_cache[key] = (now, usage)
            return usage
        rules = self.rules_loader()
        tokens = 0; cost = 0.0; priced = False
        for model, total_input, total_output, total_cached, creation in groups:
            tokens += (total_input or 0) + (total_output or 0)
            value = None
            try:
                value = self._row_cost(model, total_input or 0, total_output or 0, total_cached or 0, creation or 0, rules)
            except Exception:
                value = None
            if value is not None: priced = True; cost += value
        usage = {'tokens': tokens, 'cost': round(cost, 6) if priced else None}
        self.usage_cache[key] = (now, usage)
        return usage

    def _row_cost(self, model, total_input, total_output, total_cached, creation, rules):
        import prices
        return prices.row_cost(model, total_input, total_output, total_cached, rules=rules,
                               state_dir=self.state_dir, cache_creation=creation, platform=None)

    def _append_history(self, platform, windows, account=None):
        """One JSONL line per successful check, capped by rewrite; best effort."""
        try:
            path = self.state_dir/HISTORY_FILE
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            entry = json.dumps({'platform': platform, 'account': account, 'ts': self.clock(), 'windows': windows}, ensure_ascii=False)
            oversized = path.exists() and path.stat().st_size > HISTORY_BYTES
            if path.exists() and not oversized:
                with path.open(errors='replace') as stream:
                    oversized = sum(1 for _ in stream) >= HISTORY_KEEP
            if oversized:
                lines = [line for line in path.read_text(errors='replace').splitlines() if line.strip()][-max(1, HISTORY_KEEP-1):]
                lines.append(entry)
                temporary = path.with_suffix('.tmp')
                temporary.write_text('\n'.join(lines)+'\n')
                os.replace(temporary, path)
            else:
                with path.open('a') as stream: stream.write(entry+'\n')
        except OSError:
            pass

    def _history_windows(self, platform):
        """Snapshot entries for a platform, oldest first; broken lines skipped."""
        entries = []
        try:
            for line in (self.state_dir/HISTORY_FILE).read_text(errors='replace').splitlines():
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get('platform') == platform and isinstance(entry.get('windows'), list):
                    entries.append(entry)
        except OSError:
            pass
        return entries

    def _window_percent(self, platform, window_name, start, end, account):
        """Only an attributed snapshot can supply one account's used percent."""
        if account == 'all': return None, 'multiple_accounts'
        if not account: return None, 'unknown_account'
        best = None; reason = 'no_snapshot'
        for entry in self._history_windows(platform):
            if not isinstance(entry.get('ts'), (int, float)) or not start <= entry['ts'] < end: continue
            if not entry.get('account'):
                reason = 'unattributed_snapshot'; continue
            if entry['account'] != account: continue
            reason = 'window_mismatch'
            for window in entry['windows']:
                if not isinstance(window, dict) or window.get('window') != window_name: continue
                resets = window.get('resets_at')
                # The log window is estimated from ledger rows and can sit minutes off the platform's
                # real window; accept a snapshot whose real window mostly overlaps it.
                if not isinstance(resets, (int, float)) or abs(resets-end) > (end-start)/2: continue
                remaining = window.get('remaining')
                if type(remaining) in (int, float) and math.isfinite(remaining):
                    best = max(0, min(100, 100-remaining))
        return best, None if best is not None else reason

    def usage(self, platform, account='all', range_name='all', tier='5h', detail=False, start=None, end=None):
        """Per-window usage rows for the log section; read-only ledger access."""
        if platform not in PLATFORMS: raise ValueError('未知额度平台')
        if tier not in ('5h', 'week'): raise ValueError('额度档位无效')
        if range_name not in RANGES: raise ValueError('时间区间无效')
        detail_at = None
        if detail:
            try: detail_at = (float(start), float(end))
            except (TypeError, ValueError): raise ValueError('明细窗口时间无效') from None
            if not 0 < detail_at[0] < detail_at[1] or detail_at[1]-detail_at[0] > WINDOW_SECONDS['weekly']:
                raise ValueError('明细窗口时间无效')
        now = self.clock()
        range_start = local_midnight(self.clock) if range_name == 'day' else (
            now-RANGE_SECONDS[range_name] if range_name != 'all' else None)
        accounts = []
        try:
            with sqlite3.connect(f'file:{self.ledger}?mode=ro', uri=True, timeout=2) as db:
                accounts = sorted(row[0] for row in db.execute(
                    'SELECT DISTINCT account FROM turns WHERE platform=? AND account IS NOT NULL', (platform,)))
        except sqlite3.Error:
            return {'accounts': [], 'windows': []}
        if account != 'all' and account not in accounts: raise ValueError('未知账号')
        params = [platform]
        query = ('SELECT at, model, actual_input, actual_output, cached, cache_creation FROM turns '
                 'WHERE platform=? AND sent=1 AND account IS NOT NULL '
                 'AND at IS NOT NULL AND actual_input IS NOT NULL AND actual_output IS NOT NULL')
        if account != 'all':
            query += ' AND account=?'; params.append(account)
        if range_start is not None:
            query += ' AND at>=?'; params.append(range_start)
        query += ' ORDER BY at'
        rows = []
        try:
            with sqlite3.connect(f'file:{self.ledger}?mode=ro', uri=True, timeout=2) as db:
                rows = db.execute(query, params).fetchall()
        except sqlite3.Error:
            rows = []
        rules = self.rules_loader()
        anchored = True
        window_basis = 'estimated'
        if tier == '5h':
            windows = self._rolling_windows(rows)
        else:
            anchor = self._weekly_anchor(platform, account)
            if account != 'all' and anchor is not None: window_basis = 'account_snapshot'
            if anchor is None: anchor = self._weekly_anchor(platform)
            anchored = anchor is not None
            windows = self._weekly_windows(rows, platform, range_start, now, anchor)
        out = []
        for start_at, end_at, group in windows:
            tokens = sum((input_total or 0)+(output or 0) for _, _, input_total, output, _, _ in group)
            cost = 0.0; priced = False
            by_model = {}
            for _, model, input_total, output, cached, creation in group:
                key = str(model)
                sums = by_model.setdefault(key, [0, 0, 0, 0])
                sums[0] += input_total or 0; sums[1] += output or 0
                sums[2] += cached or 0; sums[3] += creation or 0
            for model, (model_input, model_output, model_cached, creation) in by_model.items():
                try: value = self._row_cost(model, model_input, model_output, model_cached, creation, rules)
                except Exception: value = None
                if value is not None: priced = True; cost += value
            percent, percent_reason = self._window_percent(platform, 'five_hour' if tier == '5h' else 'weekly', start_at, end_at, account)
            entry = {'start': start_at, 'end': end_at, 'percent': percent, 'percent_reason': percent_reason, 'window_basis': window_basis,
                     'tokens': tokens, 'cost': round(cost, 6) if priced else None}
            if detail and detail_at and abs(start_at-detail_at[0]) < 1 and abs(end_at-detail_at[1]) < 1:
                models = []
                for model, sums in by_model.items():
                    models.append({'model': model, 'input': sums[0], 'output': sums[1], 'cache_read': sums[2],
                                   'cache_creation': sums[3], 'tokens': sums[0]+sums[1],
                                   'cost': self._safe_cost(model, sums, rules)})
                models.sort(key=lambda item: -(item['cost'] or 0))
                entry['models'] = models
            out.append(entry)
        return {'accounts': accounts, 'windows': out, 'anchored': anchored}

    def _safe_cost(self, model, sums, rules):
        try: return self._row_cost(model, sums[0], sums[1], sums[2], sums[3], rules)
        except Exception: return None

    @staticmethod
    def _rolling_windows(rows):
        """5h windows: a window opens at the first request when none is open
        and covers [start, start+5h); the first later request opens the next."""
        windows = []
        open_start = None; group = []
        for at, model, input_total, output, cached, creation in rows:
            if open_start is None or at >= open_start+WINDOW_SECONDS['five_hour']:
                if group: windows.append((open_start, open_start+WINDOW_SECONDS['five_hour'], group))
                open_start = at; group = []
            group.append((at, model, input_total, output, cached, creation))
        if group: windows.append((open_start, open_start+WINDOW_SECONDS['five_hour'], group))
        return windows

    def _weekly_anchor(self, platform, account='all'):
        """Known weekly reset; platform fallback only supplies estimated grouping."""
        anchor = None
        state = self.states.get(platform) or {}
        for window in state.get('windows') or []:
            if account != 'all' and state.get('account') != account: continue
            if window.get('window') == 'weekly' and isinstance(window.get('resets_at'), (int, float)):
                anchor = window['resets_at']
        for entry in reversed(self._history_windows(platform)):
            if account != 'all' and entry.get('account') != account: continue
            for window in entry.get('windows') or []:
                if isinstance(window, dict) and window.get('window') == 'weekly' and isinstance(window.get('resets_at'), (int, float)):
                    anchor = window['resets_at'] if anchor is None else max(anchor, window['resets_at'])
        return anchor

    def _weekly_windows(self, rows, platform, range_start, now, anchor=None):
        """Weekly windows anchored at the latest known weekly reset, 7d each,
        walking backwards until before the earliest request."""
        if not rows: return []
        if anchor is None: anchor = self._weekly_anchor(platform)
        if anchor is None or anchor <= 0: return []
        duration = WINDOW_SECONDS['weekly']
        earliest = rows[0][0]
        windows = []
        end = anchor
        while True:
            start = end-duration
            if start >= now:
                end = start; continue
            group = [row for row in rows if start <= row[0] < end]
            if group and (range_start is None or end > range_start):
                windows.append((start, end, group))
            if start <= earliest: break
            end = start
        windows.reverse()
        return windows

    def claude_login(self):
        """Pop a Terminal running `claude /login`; the CLI owns all credentials."""
        with self.lock:
            now = self.clock()
            if now-self.claude_login_at < 30:
                return {'spawned': False, 'error': '已弹出过登录窗口；请在浏览器完成授权并按终端提示粘贴码'}
            self.claude_login_at = now
        try:
            spawned = bool(self.login_runner())
        except Exception:
            return {'spawned': False, 'error': '无法打开终端；请手动打开终端运行 claude /login'}
        return {'spawned': spawned, 'error': None if spawned else '终端启动失败；请手动运行 claude /login'}

    def request(self, platform):
        if platform not in PLATFORMS: raise ValueError('未知额度平台')
        with self.lock:
            self._observe_account(platform)
            state = self.states[platform]
            # Manual clicks respect cooldown and never queue behind a running read.
            if not state['refreshing'] and self.clock() >= state.get('retry_at', 0):
                self.pending.add(platform); self.wake.set()
        return self.snapshot()

    def refresh(self, platform):
        with self.lock:
            self._observe_account(platform)
            state = self.states[platform]
            if state['refreshing'] or self.clock() < state.get('retry_at', 0): return
            state['refreshing'] = True
            started_at = self.clock()
            epoch = self.account_epochs[platform]
            delay = self.prefs[platform]['interval']
        read_started = time.monotonic(); read_finished = None
        try:
            before = self._account(platform)
            result = self.readers[platform]()
            if isinstance(result, dict):
                windows = result.get('windows'); account = result.get('account')
                if not isinstance(account, str) or not account: account = None
            else:
                windows = result; account = self._account(platform)
                if account != before: raise QuotaError('账号在检查期间切换，请重新检查')
            if not windows or not any(w['remaining'] is not None for w in windows): raise QuotaError('平台未提供可用额度；不会按0%处理')
            read_finished = time.monotonic()
            with self.lock:
                current = self._account(platform)
                if self.closed.is_set() or epoch != self.account_epochs[platform]: return
                if current != account:
                    raise QuotaError('账号在检查期间切换，请重新检查')
                state.update(windows=windows, status='ok', error='', updated_at=self.clock(), failures=0)
                if state['account'] != account:
                    self.account_epochs[platform] += 1
                    epoch = self.account_epochs[platform]
                    state['stop_attempted_at'] = None
                state['account'] = account
                self.usage_cache.clear()
                self._append_history(platform, windows, account)
                delay = self.prefs[platform]['interval']
                low_keys = {(w['bucket'], w['window'], w['resets_at']) for w in windows if w['remaining'] is not None and w['remaining'] <= self.prefs[platform][w['window']+'_threshold']}
                self.stop_seen[platform].intersection_update(low_keys)
                notice_keys = {(account, *notice_window_key(w)) for w in windows if w['remaining'] is not None and w['remaining'] <= self.prefs[platform][w['window']+'_threshold']}
                recovered = {(account, w['bucket'], w['window'], 'zero') for w in windows if w['remaining'] is not None and w['remaining'] > 0}
                retained_notices = {k for k in self.notify_seen[platform] if k[0] != account or k in notice_keys or (k[3] == 'zero' and k not in recovered)}
                if retained_notices != self.notify_seen[platform]:
                    self.notify_seen[platform] = retained_notices
                    self._save_notices()
                should_notify = bool(notice_keys-self.notify_seen[platform]) and self.prefs[platform]['notify']
                should_stop = bool(low_keys) and self.prefs[platform]['stop_all'] and (state['stop_attempted_at'] is None or self.clock()-state['stop_attempted_at'] >= 30)
                if should_stop: self.stop_seen[platform].update(low_keys)
            if should_stop or should_notify:
                action = (account, epoch, should_stop, should_notify, notice_keys)
                if self.action_thread is not None:
                    with self.lock:
                        self.actions[platform] = action
                        self.action_wake.set()
                else:
                    self._act(platform, action)  # direct callers/tests retain synchronous completion
        except Exception as exc:
            with self.lock:
                if self.closed.is_set() or epoch != self.account_epochs[platform]: return
                state['failures'] += 1
                # Retry-After up to a day froze a card for a day and disabled the manual
                # button with it; the 429 handler's value is a request hint, not a lock-out.
                delay = min(1800, max(self.prefs[platform]['interval'], min(1800, 60*2**min(state['failures']-1, 5)), getattr(exc, 'retry_after', 0)))
                state.update(status='error', error=str(exc) if isinstance(exc, QuotaError) else '额度读取失败，请稍后重试')
        finally:
            with self.lock:
                if self.closed.is_set() or epoch != self.account_epochs[platform]:
                    state['refreshing'] = False
                    return
                now = self.clock()
                next_at = now+delay if state['status'] == 'error' else max(now, started_at+delay)
                # Manual re-check stays usable during long platform backoffs: at most a minute of cooldown.
                retry_at = now+min(delay, 60) if state['status'] == 'error' else max(now, started_at+5)
                state.update(refreshing=False, checked_at=now, next_at=next_at, retry_at=retry_at,
                             read_duration_ms=round(((read_finished or time.monotonic())-read_started)*1000, 1))
                self._save_cooldown()
        # Resume evaluation happens after every attempt, success or failure, outside self.lock (D10).
        self._reconcile_now()

    def _act(self, platform, action):
        account, epoch, stop, notify, notice_keys = action
        with self.action_lock:
            with self.lock:
                state = self.states[platform]
                if self.closed.is_set() or epoch != self.account_epochs[platform] or self._account(platform) != account or state['account'] != account or state['status'] != 'ok': return
                low = {(account, *notice_window_key(w)) for w in state['windows']
                       if w['remaining'] is not None and w['remaining'] <= self.prefs[platform][w['window']+'_threshold']}
                if not low or not low.intersection(notice_keys): return
                stop = stop and self.prefs[platform]['stop_all'] and (state['stop_attempted_at'] is None or self.clock()-state['stop_attempted_at'] >= 30)
                notify = notify and self.prefs[platform]['notify'] and bool(low-self.notify_seen[platform])
                payload = self._pause_payload(platform) if stop and self.protection is not None else None
                if stop: state['stop_attempted_at'] = self.clock()  # reserve before releasing lock
            if stop:
                try:
                    result = self.protection.pause(payload) if self.protection is not None else (
                        self.stop_handler(platform) if self.stop_handler else {'ok': False, 'error': '本机停止控制尚未接入，未停止会话'})
                except Exception: result = {'ok': False, 'error': '本机停止控制失败，未确认会话停止'}
                with self.lock:
                    if not self.closed.is_set() and epoch == self.account_epochs[platform] and state['account'] == account and self._account(platform) == account:
                        state['stop_result'] = result
            if notify:
                with self.lock:
                    # A slow stop may cross account/window/settings changes. Re-check before notice.
                    if self.closed.is_set() or epoch != self.account_epochs[platform] or state['account'] != account or self._account(platform) != account or not self.prefs[platform]['notify']: return
                    current_low = {(account, *notice_window_key(w)) for w in state['windows']
                                   if state['status'] == 'ok' and w['remaining'] is not None and w['remaining'] <= self.prefs[platform][w['window']+'_threshold']}
                    keys = current_low.intersection(notice_keys)-self.notify_seen[platform]
                    if not keys: return
                try: sent = bool(self.notifier(platform))
                except Exception: sent = False
                with self.lock:
                    if not self.closed.is_set() and epoch == self.account_epochs[platform] and state['account'] == account and self._account(platform) == account:
                        state['notification_sent'] = sent
                        if sent:
                            self.notify_seen[platform].update(keys)
                            self._save_notices()

    def _run_actions(self):
        while not self.closed.is_set():
            with self.lock:
                actions = self.actions; self.actions = {}
            for p, action in actions.items():
                if self.closed.is_set(): break
                self._act(p, action)
            self._reconcile_now()
            self.action_wake.wait(1); self.action_wake.clear()

    def start(self):
        if self.thread: return
        self.action_thread = threading.Thread(target=self._run_actions, name='quota-actions', daemon=True)
        self.action_thread.start()
        self.thread = threading.Thread(target=self.run, name='quota-reader', daemon=True); self.thread.start()

    def run(self):
        self._reconcile_now()  # restart: owned pauses are re-evaluated from the journal, never assumed
        while not self.closed.is_set():
            with self.lock:
                for p in PLATFORMS:
                    self._observe_account(p)
                due = [p for p in PLATFORMS if p in self.pending or (self.prefs[p]['enabled'] and self.clock() >= (self.states[p]['next_at'] or 0))]
                self.pending.difference_update(due)
            for p in due:
                if self.closed.is_set(): break
                self.refresh(p)
            self.wake.wait(1); self.wake.clear()

    def close(self):
        self.closed.set(); self.wake.set(); self.action_wake.set()
        with self.lock: self.actions.clear()
        if self.thread: self.thread.join(timeout=2)
        if self.action_thread: self.action_thread.join(timeout=2)
