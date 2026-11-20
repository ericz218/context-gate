#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git-sync：本地 Git 仓库 <-> GitHub 自动双向同步（可选工具）。

只用 Python 3.9 标准库。
不做的事：force push、reset --hard、删除分支、丢弃任一边数据、改 .gitignore、直接改外部记忆库数据库。
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
import uuid

HOME_DIR = os.environ.get('GITSYNC_HOME') or os.path.expanduser('~/.local/state/context-gate/git-sync')
REGISTRY = os.path.join(HOME_DIR, 'registry.json')
REGISTRY_MD = os.path.join(HOME_DIR, 'REGISTRY.md')
LOG_DIR = os.path.join(HOME_DIR, 'logs')
STATE_DIR = os.path.join(HOME_DIR, 'state')
HOSTTAG = os.environ.get('GITSYNC_HOSTTAG') or socket.gethostname().split('.')[0] or 'local'
QUIET_SECONDS = int(os.environ.get('GITSYNC_QUIET_SECONDS', '60'))
MAX_FILE_BYTES = int(os.environ.get('GITSYNC_MAX_FILE_BYTES', str(90 * 1024 * 1024)))
GITLEAKS = os.environ.get('GITSYNC_GITLEAKS') or shutil.which('gitleaks') or '/opt/homebrew/bin/gitleaks'
GH = os.environ.get('GITSYNC_GH') or shutil.which('gh') or '/opt/homebrew/bin/gh'
NOTIFY_MODE = os.environ.get('GITSYNC_NOTIFY', 'osascript')  # osascript | file:<path> | none
MEMORY_CONFIG = os.environ.get('GITSYNC_MEMORY_CONFIG',
                               os.path.expanduser('~/Library/Application Support/MemoryOS/client.json'))
GITHUB_OWNER = os.environ.get('GITSYNC_GITHUB_OWNER', '')
NET_TIMEOUT = 300
NOTIFY_THROTTLE = 6 * 3600
STATUSES = ('ok', 'conflict', 'blocked', 'paused', 'disabled')
ENV_BASE = {'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/usr/bin/false', 'SSH_ASKPASS': '/usr/bin/false',
            'LC_ALL': 'en_US.UTF-8', 'GIT_MERGE_AUTOEDIT': 'no'}
os.environ.setdefault('PATH', '/usr/bin:/bin')
if '/opt/homebrew/bin' not in os.environ['PATH'].split(':'):
    os.environ['PATH'] = os.environ['PATH'] + ':/opt/homebrew/bin'


# ---------------------------------------------------------------- 基础工具

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def stamp():
    return datetime.datetime.now().strftime('%Y%m%d-%H%M%S')


_RUN_ID = uuid.uuid4().hex[:12]
_LOG_FILE = None


def log(msg, repo=None):
    global _LOG_FILE
    os.makedirs(LOG_DIR, exist_ok=True)
    line = '%s [%s] %s%s' % (now_iso(), _RUN_ID, ('[%s] ' % repo) if repo else '', msg)
    path = os.path.join(LOG_DIR, 'git-sync-%s.log' % datetime.date.today().isoformat())
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    if os.environ.get('GITSYNC_VERBOSE') or sys.stdout.isatty():
        print(line, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.tmp-', suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.replace(tmp, path)


def notify(title, msg, key=None):
    """macOS 通知。key 相同的通知 6 小时内只发一次。通知里绝不放密钥内容。"""
    path = os.path.join(STATE_DIR, 'notified.json')
    sent = load_json(path, {})
    if key:
        if time.time() - sent.get(key, 0) < NOTIFY_THROTTLE:
            log('通知已节流：%s：%s' % (title, msg))
            return
        sent[key] = time.time()
        save_json(path, sent)
    log('通知：%s：%s' % (title, msg))
    if NOTIFY_MODE == 'osascript':
        try:
            subprocess.run(['/usr/bin/osascript', '-e', 'on run argv',
                            '-e', 'display notification (item 2 of argv) with title (item 1 of argv) sound name "Basso"',
                            '-e', 'end run', title, msg[:900]], timeout=20, capture_output=True)
        except Exception as exc:  # 通知失败不影响同步
            log('通知发送失败：%s' % type(exc).__name__)
    elif NOTIFY_MODE.startswith('file:'):
        with open(NOTIFY_MODE[5:], 'a', encoding='utf-8') as f:
            f.write(json.dumps({'title': title, 'msg': msg, 'key': key}, ensure_ascii=False) + '\n')


class GitError(Exception):
    pass


class Busy(Exception):
    pass


def fs(b):
    return b.decode('utf-8', 'surrogateescape')


def git(repo, *args, env=None, check=True, timeout=120, input=None, net=False):
    cmd = ['git', '-C', repo, '-c', 'core.quotepath=false']
    if net and os.path.exists(GH):
        cmd += ['-c', 'credential.helper=', '-c', 'credential.helper=!%s auth git-credential' % GH]
    cmd += list(args)
    e = dict(os.environ)
    e.update(ENV_BASE)
    if env:
        e.update(env)
    p = subprocess.run(cmd, cwd=repo, env=e, input=input, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        raise GitError('git %s 失败(%d)：%s' % (' '.join(args[:3]), p.returncode, fs(p.stderr).strip()[-400:]))
    return p


def gout(repo, *args, **kw):
    return fs(git(repo, *args, **kw).stdout).strip()


def rev(repo, ref):
    p = git(repo, 'rev-parse', '--verify', '--quiet', ref + '^{commit}', check=False)
    return fs(p.stdout).strip() if p.returncode == 0 else None


def is_ancestor(repo, a, b):
    return git(repo, 'merge-base', '--is-ancestor', a, b, check=False).returncode == 0


def parse_github(url):
    m = re.match(r'^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?$',
                 url or '')
    return (m.group(1), m.group(2)) if m else (None, None)


# ---------------------------------------------------------------- MemoryOS

class Memory:
    """只走 MemoryOS HTTP API（/v1/remember），不碰数据库。"""

    def __init__(self):
        self.url = self.token = None
        try:
            st = os.stat(MEMORY_CONFIG)
            if st.st_mode & 0o077:
                raise ValueError('MemoryOS 客户端配置权限不是 0600')
            cfg = load_json(MEMORY_CONFIG, {})
            self.url = cfg.get('MEMORY_OS_HTTP_URL', '').rstrip('/')
            self.token = cfg.get('MEMORY_OS_API_TOKEN')
        except (OSError, ValueError) as exc:
            log('MemoryOS 配置不可用：%s' % exc)

    def remember(self, body):
        """返回 (状态, 结果)。状态：done / retry / failed。"""
        if not self.url or not self.token:
            return 'retry', 'MemoryOS 配置不可用'
        req = urllib.request.Request(self.url + '/v1/remember', data=json.dumps(body, ensure_ascii=False).encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': 'Bearer ' + self.token})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.load(resp)
            if result.get('event_id'):
                return 'done', result
            return 'failed', 'MemoryOS 未写入：%s' % json.dumps(result, ensure_ascii=False)[:300]
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc).get('detail')
            except Exception:
                detail = ''
            if exc.code in (409, 422):
                return 'failed', 'HTTP %d %s' % (exc.code, str(detail)[:300])
            return 'retry', 'HTTP %d %s' % (exc.code, str(detail)[:300])
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return 'retry', type(exc).__name__

    def get_history(self, key, scope_id):
        from urllib.parse import urlencode
        q = urlencode({'key': key, 'scope': 'project', 'scope_id': scope_id})
        req = urllib.request.Request(self.url + '/v1/history?' + q, headers={'Authorization': 'Bearer ' + self.token})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)


SOURCE_AGENT = 'git-sync'
SOURCE_MODEL = 'none (deterministic script tools/git_sync_engine.py)'


def memory_create_body(r, c):
    key = c['memory']['key']
    files = c.get('files') or []
    files_txt = '、'.join(files[:30]) + ('（共 %d 个）' % len(files) if len(files) > 30 else '')
    branch_line = '冲突分支：%s（%s）' % (c['branch'], c['branch_where'])
    lines = [
        '自动 Git 历史：git-sync 在 %s 发现仓库 %s 有无法自动合并的冲突，已暂停对它的自动合并。' % (c['detected_at'], r['name']),
        '仓库：%s（GitHub：%s）' % (r['name'], r.get('remote_url') or '无'),
        '本机路径：%s' % r['path'],
        '同步分支：%s' % r['branch'],
        '方向：%s' % c['direction_label'],
        '冲突文件：%s' % (files_txt or '（见冲突分支）'),
        '本地提交：%s' % c['local_commit'],
        '远端提交：%s（%s）' % (c['remote_commit'], c['remote_ref']),
        branch_line,
        '说明：%s' % c['detail'],
    ]
    source = '\n'.join(lines)
    value = {
        '标题': '自动 Git 历史：%s 同步冲突（%s）' % (r['name'], c['direction_label']),
        '仓库': r['name'], 'GitHub': r.get('remote_url') or '', '本机路径': r['path'], '同步分支': r['branch'],
        '方向': c['direction_label'], '冲突文件': files[:50], '本地提交': c['local_commit'],
        '远端提交': c['remote_commit'], '远端引用': c['remote_ref'], '冲突分支': c['branch'],
        '冲突分支位置': c['branch_where'], '发现时间': c['detected_at'], '状态': '未解决',
        '处理方法': '在本机把两边合并（git merge）并提交，或在 GitHub 上合并冲突分支；git-sync 检测到可以正常合并后自动恢复并把本条降权归档。',
    }
    ir = {'schema_version': '2', 'action': 'create', 'memory_type': 'episodic', 'scope': 'project',
          'scope_id': c['memory']['scope_id'], 'key': key, 'value': value, 'expected_version': 0,
          'importance': 0.9, 'confidence': 0.95, 'stability': 0.5, 'future_utility': 0.8, 'weight': 0.99,
          'sensitivity': 'private', 'evidence_quotes': [branch_line], 'reason_code': 'git_sync_conflict',
          'tier': 'HOT'}
    return {'request_id': 'git-sync:%s:create' % key, 'candidate': ir, 'source_text': source,
            'source_agent': SOURCE_AGENT, 'source_model': SOURCE_MODEL, 'source_session': 'git-sync-run-' + _RUN_ID}


def memory_resolve_bodies(r, c):
    key = c['memory']['key']
    created_value = c['memory']['create']['body']['candidate']['value']
    value = dict(created_value)
    value['状态'] = '已解决'
    value['解决时间'] = c['resolved_at']
    value['解决方式'] = c['resolution']
    line = '状态：已解决（%s，%s）' % (c['resolved_at'], c['resolution'])
    source1 = '\n'.join([
        '自动 Git 历史：仓库 %s 在 %s 发现的同步冲突已解决，git-sync 已恢复自动同步。' % (r['name'], c['detected_at']),
        '冲突分支：%s' % c['branch'], line,
        '按规则把这条冲突记忆降到归档标准：weight=0.1，随后 action=archive、tier=ARCHIVED。'])
    base = {'schema_version': '2', 'memory_type': 'episodic', 'scope': 'project',
            'scope_id': c['memory']['scope_id'], 'key': key, 'value': value, 'importance': 0.9,
            'confidence': 0.95, 'stability': 0.5, 'future_utility': 0.8, 'weight': 0.1, 'sensitivity': 'private',
            'evidence_quotes': [line]}
    sup = dict(base, action='supersede', expected_version=1, reason_code='git_sync_conflict_resolved', tier='COLD')
    arc = dict(base, action='archive', expected_version=2, reason_code='git_sync_conflict_archived', tier='ARCHIVED')
    sess = 'git-sync-run-' + _RUN_ID
    return ({'request_id': 'git-sync:%s:resolve' % key, 'candidate': sup, 'source_text': source1,
             'source_agent': SOURCE_AGENT, 'source_model': SOURCE_MODEL, 'source_session': sess},
            {'request_id': 'git-sync:%s:archive' % key, 'candidate': arc, 'source_text': source1,
             'source_agent': SOURCE_AGENT, 'source_model': SOURCE_MODEL, 'source_session': sess})


def process_memory_ops(r, mem):
    """按顺序补写 create -> resolve -> archive。失败可重试的留到下一轮。"""
    for c in ([r['conflict']] if r.get('conflict') else []) + list(r.get('conflict_history') or []):
        m = c.get('memory')
        if not m:
            continue
        for step in ('create', 'resolve', 'archive'):
            op = m.get(step)
            if not op:
                break
            if op['status'] == 'done':
                continue
            if op['status'] == 'failed':
                break
            state, result = mem.remember(op['body'])
            op['attempts'] = op.get('attempts', 0) + 1
            if state == 'done':
                op['status'] = 'done'
                op['event_id'] = result.get('event_id')
                op['version'] = result.get('version')
                log('MemoryOS %s 已写入：%s v%s' % (step, m['key'], result.get('version')), r['name'])
                continue
            op['error'] = str(result)[:300]
            if state == 'failed':
                op['status'] = 'failed'
                log('MemoryOS %s 写入被拒（不再重试）：%s' % (step, op['error']), r['name'])
                notify('Git 同步：MemoryOS 写入失败', '%s 的冲突记忆 %s 未写入，见日志' % (r['name'], step),
                       key='memfail:%s:%s' % (m['key'], step))
            else:
                log('MemoryOS %s 暂不可写，下轮重试：%s' % (step, op['error']), r['name'])
            break


# ---------------------------------------------------------------- 单仓库同步

class Skip(Exception):
    pass


class RepoSync:
    def __init__(self, r, mem):
        self.r = r
        self.mem = mem
        self.repo = r['path']
        self.name = r['name']
        self.block_reasons = []
        self.warnings = []
        self.actions = []

    def log(self, msg):
        log(msg, self.name)

    # ---- 环境检查
    def git_dir(self):
        return gout(self.repo, 'rev-parse', '--absolute-git-dir')

    def busy_reason(self, gd):
        for f in ('index.lock', 'MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'BISECT_LOG', 'rebase-merge',
                  'rebase-apply'):
            if os.path.exists(os.path.join(gd, f)):
                return f
        return None

    def status_entries(self):
        out = git(self.repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all',
                  env={'GIT_OPTIONAL_LOCKS': '0'}).stdout
        parts = out.split(b'\0')
        entries = []
        i = 0
        while i < len(parts):
            p = parts[i]
            if not p:
                i += 1
                continue
            xy, path = fs(p[:2]), fs(p[3:])
            entries.append((xy, path))
            if xy[0] in 'RC':
                i += 1  # 跳过原路径
            i += 1
        return entries

    def recent_path(self, entries):
        """60 秒静默检查。嵌套仓库目录和排除清单里的路径不会被提交，不计入。"""
        t = time.time()
        skip = set(self.r.get('exclude') or [])
        for xy, path in entries:
            if path.rstrip('/') in skip or (xy == '??' and path.endswith('/') and
                                            os.path.exists(os.path.join(self.repo, path, '.git'))):
                continue
            try:
                st = os.lstat(os.path.join(self.repo, path.rstrip('/')))
            except OSError:
                continue
            if t - st.st_mtime < QUIET_SECONDS:
                return path
        return None

    # ---- 主流程
    def run(self):
        r = self.r
        r['last_check'] = now_iso()
        if not os.path.isdir(self.repo):
            raise Skip('路径不存在（外接卷未挂载？）')
        try:
            os.listdir(self.repo)
        except PermissionError:
            self.block('macOS 权限：同步器无权读取该目录（需给 GitSync.app 完全磁盘访问权限，见 README）',
                       key='tcc:' + self.name)
            return self.finish()
        gd = self.git_dir()
        b = self.busy_reason(gd)
        if b:
            raise Skip('仓库正被其他操作占用（%s），本轮跳过' % b)
        cur = gout(self.repo, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
        entries = self.status_entries()
        r['pending_changes'] = len(entries) if not r.get('auto_commit', True) else 0
        recent = self.recent_path(entries) if r.get('auto_commit', True) else None
        if recent:
            raise Skip('最近 %d 秒内有文件改动（%s），等下一轮' % (QUIET_SECONDS, recent))

        if r['status'] == 'conflict':
            self.fetch()
            if not self.check_resolved(entries):
                r['last_result'] = '冲突未解决，自动合并已暂停（冲突分支 %s）' % r['conflict']['branch']
                self.log(r['last_result'])
                return
            entries = self.status_entries()

        # 任何分支都原样同步：在哪条分支上工作，就提交到这条分支、和 GitHub 上同名分支互通；
        # 绝不把支线合进主线（claude/* 自动合并只在主线 default_branch 上做）。
        r.setdefault('default_branch', r['branch'])
        if not cur:
            self.fetch()
            self.block('当前不在任何分支上（分离 HEAD），本轮只拉取不提交', key='branch:%s:detached' % self.name)
            return self.finish()
        if cur != r['branch']:
            self.log('跟随当前工作分支：%s → %s' % (r['branch'], cur))
            r['branch'] = cur

        if r['mode'] == 'sync' and entries and r.get('auto_commit', True):
            self.autocommit(entries, gd)
        elif entries and not r.get('auto_commit', True):
            self.warnings.append('本机有未提交改动；本轮只同步已提交版本')
        self.fetch()
        if not self.integrate_upstream():
            return self.finish()
        if r['mode'] == 'sync' and r.get('claude_merge') and r['branch'] == r.get('default_branch'):
            if not self.merge_claude_branches():
                return self.finish()
        if r['mode'] == 'sync' and r.get('push', True):
            self.push_branch()
        return self.finish()

    def finish(self):
        r = self.r
        r['warnings'] = self.warnings
        if r['status'] != 'conflict':
            if self.block_reasons:
                r['status'] = 'blocked'
                r['status_reason'] = '；'.join(self.block_reasons)
            else:
                r['status'] = 'ok'
                r['status_reason'] = ''
                r['last_sync'] = now_iso()
        r['last_result'] = '；'.join(self.actions + self.warnings + self.block_reasons) or '无变化'
        self.log('结果：%s（状态 %s）' % (r['last_result'], r['status']))

    def block(self, reason, key=None, notify_msg=None):
        self.block_reasons.append(reason)
        self.log('阻止：' + reason)
        if key:
            notify('Git 同步：%s 需要处理' % self.name, notify_msg or reason, key=key)

    # ---- 自动提交
    def autocommit(self, entries, gd):
        r = self.r
        embedded = [p.rstrip('/') for xy, p in entries
                    if xy == '??' and p.endswith('/') and os.path.exists(os.path.join(self.repo, p, '.git'))]
        lock = os.path.join(gd, 'index.lock')
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise Skip('仓库正被其他操作占用（index.lock），本轮跳过')
        os.close(fd)
        own_lock = True
        tmp_index = os.path.join(gd, 'gitsync-index.tmp')
        try:
            idx = os.path.join(gd, 'index')
            if os.path.exists(idx):
                shutil.copyfile(idx, tmp_index)
            elif os.path.exists(tmp_index):
                os.unlink(tmp_index)
            env = {'GIT_INDEX_FILE': tmp_index}
            spec = ['--', '.'] + [':(exclude,top)%s' % p for p in embedded + list(r.get('exclude') or [])]
            git(self.repo, 'add', '-A', *spec, env=env, timeout=600)
            changed = self.staged_changes(env)
            big = []
            for st, path in changed:
                if st in 'AMT':
                    full = os.path.join(self.repo, path)
                    try:
                        if not os.path.islink(full) and os.path.getsize(full) > MAX_FILE_BYTES:
                            big.append(path)
                    except OSError:
                        pass
            if big:
                git(self.repo, 'reset', '-q', 'HEAD', '--', *big, env=env)
                for p in big:
                    self.warnings.append('文件超过 %dMB 未提交：%s' % (MAX_FILE_BYTES // 1048576, p))
                    notify('Git 同步：%s 有大文件未提交' % self.name,
                           '%s 超过 %dMB，未提交（GitHub 单文件上限 100MB）' % (p, MAX_FILE_BYTES // 1048576),
                           key='big:%s:%s' % (self.name, p))
                changed = self.staged_changes(env)
            if embedded:
                self.log('跳过嵌套仓库目录：%s' % '、'.join(embedded))
            if not changed:
                return
            leaks = self.gitleaks(env)
            if leaks:
                if isinstance(leaks, str):
                    self.block('密钥扫描失败（%s），为安全起见本轮不提交' % leaks, key='leakerr:' + self.name)
                else:
                    files = sorted(set(x['file'] for x in leaks))
                    self.block('gitleaks 在待提交内容里发现疑似密钥（%d 处，文件：%s），已拦下不提交' % (len(leaks), '、'.join(files[:10])),
                               key='leak:%s:%s' % (self.name, hashlib.sha1('|'.join(files).encode()).hexdigest()[:10]),
                               notify_msg='疑似密钥 %d 处（文件：%s），已拦下不提交；请移除或加入 .gitignore' % (
                                   len(leaks), '、'.join(files[:5])))
                return
            tree = gout(self.repo, 'write-tree', env=env)
            parent = rev(self.repo, 'HEAD')
            ts = now_iso()
            listing = '\n'.join('%s %s' % (s, p) for s, p in changed[:40])
            if len(changed) > 40:
                listing += '\n…共 %d 个文件' % len(changed)
            msg = 'auto-sync %s %s\n\n%s\n' % (ts, HOSTTAG, listing)
            args = ['commit-tree', tree, '-F', '-'] + (['-p', parent] if parent else [])
            commit = fs(git(self.repo, *args, input=msg.encode(), env=self.author_env(env)).stdout).strip()
            git(self.repo, 'update-ref', '-m', 'git-sync: auto-sync commit', 'refs/heads/' + r['branch'], commit,
                parent or '0' * 40)
            os.replace(tmp_index, lock)
            os.replace(lock, idx)
            own_lock = False
            self.actions.append('自动提交 %s（%d 个文件）' % (commit[:8], len(changed)))
            self.log('自动提交 %s：%d 个文件' % (commit[:8], len(changed)))
        finally:
            if os.path.exists(tmp_index):
                os.unlink(tmp_index)
            if own_lock and os.path.exists(lock):
                os.unlink(lock)

    def preview(self):
        """只读预览：在临时索引里暂存，报告将提交的文件数、超大文件、gitleaks 结果。不提交、不动真实索引。"""
        if not os.path.isdir(self.repo):
            return {'error': '路径不存在'}
        gd = self.git_dir()
        entries = self.status_entries()
        info = {'dirty': len(entries), 'busy': self.busy_reason(gd), 'recent': self.recent_path(entries),
                'branch': gout(self.repo, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)}
        if not entries:
            return info
        embedded = [p.rstrip('/') for xy, p in entries
                    if xy == '??' and p.endswith('/') and os.path.exists(os.path.join(self.repo, p, '.git'))]
        fd, tmp_index = tempfile.mkstemp(dir=STATE_DIR, prefix='preview-index-')
        os.close(fd)
        try:
            idx = os.path.join(gd, 'index')
            if os.path.exists(idx):
                shutil.copyfile(idx, tmp_index)
            else:
                os.unlink(tmp_index)
            env = {'GIT_INDEX_FILE': tmp_index}
            git(self.repo, 'add', '-A', '--', '.', *[':(exclude,top)%s' % p for p in embedded + list(self.r.get('exclude') or [])],
                env=env, timeout=900)
            changed = self.staged_changes(env)
            big = [p for st, p in changed if st in 'AMT' and os.path.isfile(os.path.join(self.repo, p))
                   and not os.path.islink(os.path.join(self.repo, p))
                   and os.path.getsize(os.path.join(self.repo, p)) > MAX_FILE_BYTES]
            if big:
                git(self.repo, 'reset', '-q', 'HEAD', '--', *big, env=env)
            leaks = self.gitleaks(env)
            info.update(changes=len(changed), embedded=embedded, big=big,
                        leaks=leaks if isinstance(leaks, str) else sorted(set('%s(%s)' % (x['file'], x['rule']) for x in leaks)))
        finally:
            if os.path.exists(tmp_index):
                os.unlink(tmp_index)
        return info

    def staged_changes(self, env):
        has_head = rev(self.repo, 'HEAD') is not None
        if has_head:
            out = git(self.repo, 'diff', '--cached', '--no-renames', '--name-status', '-z', 'HEAD', env=env).stdout
        else:
            out = git(self.repo, 'diff', '--cached', '--no-renames', '--name-status', '-z', '--root', env=env).stdout
        parts = [fs(x) for x in out.split(b'\0') if x]
        return [(parts[i][0], parts[i + 1]) for i in range(0, len(parts) - 1, 2)]

    def author_env(self, env=None):
        e = dict(env or {})
        name = gout(self.repo, 'config', 'user.name', check=False)
        email = gout(self.repo, 'config', 'user.email', check=False)
        if not name:
            e['GIT_AUTHOR_NAME'] = e['GIT_COMMITTER_NAME'] = os.environ.get('GITSYNC_AUTHOR_NAME', 'git-sync')
        if not email and os.environ.get('GITSYNC_AUTHOR_EMAIL'):
            e['GIT_AUTHOR_EMAIL'] = e['GIT_COMMITTER_EMAIL'] = os.environ['GITSYNC_AUTHOR_EMAIL']
        return e

    def gitleaks(self, env):
        if not os.path.exists(GITLEAKS):
            return 'gitleaks 未安装'
        fd, report = tempfile.mkstemp(dir=STATE_DIR, prefix='gitleaks-', suffix='.json')
        os.close(fd)
        try:
            cmd = [GITLEAKS, 'git', '--staged', '--no-banner', '--redact', '--exit-code', '1', '--report-format',
                   'json', '--report-path', report, '--log-level', 'error']
            cfg = os.path.join(self.repo, '.gitleaks.toml')
            if os.path.exists(cfg):
                cmd += ['-c', cfg]
            cmd.append(self.repo)
            e = dict(os.environ)
            e.update(ENV_BASE)
            e.update(env)
            p = subprocess.run(cmd, cwd=self.repo, env=e, capture_output=True, timeout=900)
            try:
                with open(report, encoding='utf-8') as f:
                    findings = json.load(f)
            except (OSError, ValueError):
                findings = None
            if p.returncode == 0:
                return []
            if findings:
                return [{'file': x.get('File'), 'rule': x.get('RuleID'), 'line': x.get('StartLine')} for x in findings]
            return 'gitleaks 退出码 %d' % p.returncode
        finally:
            os.unlink(report)

    # ---- 网络
    def fetch(self):
        git(self.repo, 'fetch', '--no-write-fetch-head', r_remote(self.r), net=True, timeout=NET_TIMEOUT)

    def remote_ref(self, branch):
        return 'refs/remotes/%s/%s' % (r_remote(self.r), branch)

    def push_branch(self):
        r = self.r
        local = rev(self.repo, 'refs/heads/' + r['branch'])
        remote = rev(self.repo, self.remote_ref(r['branch']))
        if not local or local == remote:
            return
        if remote and not is_ancestor(self.repo, remote, local):
            self.log('远端 %s 不是本地祖先，本轮不推送（下轮合并后再推）' % r['branch'])
            return
        git(self.repo, 'push', '--no-verify', r_remote(r), 'refs/heads/%s:refs/heads/%s' % (r['branch'], r['branch']),
            net=True, timeout=NET_TIMEOUT)
        self.actions.append('推送 %s → %s' % (local[:8], r['branch']))
        self.log('已推送 %s %s' % (r['branch'], local[:8]))

    # ---- 合并
    def blob(self, oid):
        return git(self.repo, 'cat-file', 'blob', oid).stdout

    def append_merge(self, st):
        """两边相对共同祖先都只是在文件末尾追加 -> 两边都保留；判断不了返回 None。"""
        base, ours, theirs = st.get(1), st.get(2), st.get(3)
        if not ours or not theirs or ours[0] != theirs[0] or ours[0] not in ('100644', '100755'):
            return None
        o, t = self.blob(ours[1]), self.blob(theirs[1])
        if b'\0' in o or b'\0' in t:
            return None
        if base is None:
            if o.startswith(t):
                return o
            if t.startswith(o):
                return t
            return None
        b = self.blob(base[1])
        if b and not b.endswith(b'\n'):
            return None
        if not (o.startswith(b) and t.startswith(b)):
            return None
        to, tt = o[len(b):], t[len(b):]
        if not to:
            return t
        if not tt or to == tt:
            return o
        return b + to + (b'' if to.endswith(b'\n') else b'\n') + tt

    def plan(self, head, target):
        """('noop'|'ff'|'merge'|'conflict', 结果提交或树, 文件列表)。只计算，不动工作区。"""
        if is_ancestor(self.repo, target, head):
            return 'noop', head, []
        if is_ancestor(self.repo, head, target):
            return 'ff', target, []
        p = git(self.repo, 'merge-tree', '--write-tree', '-z', head, target, check=False, timeout=600)
        if p.returncode not in (0, 1):
            raise GitError('merge-tree 失败：%s' % fs(p.stderr)[-300:])
        parts = p.stdout.split(b'\0')
        tree = fs(parts[0])
        if p.returncode == 0:
            return 'merge', tree, []
        stages = {}
        i = 1
        while i < len(parts) and parts[i] != b'':
            meta, path = parts[i].split(b'\t', 1)
            mode, oid, stage = fs(meta).split(' ')
            stages.setdefault(fs(path), {})[int(stage)] = (mode, oid)
            i += 1
        if not stages:
            return 'conflict', None, ['（merge-tree 报告冲突但未列出文件）']
        resolved, unresolved = {}, []
        for path, st in sorted(stages.items()):
            content = self.append_merge(st)
            if content is None:
                unresolved.append(path)
            else:
                resolved[path] = ((st.get(2) or st.get(3))[0], content)
        if unresolved:
            return 'conflict', None, unresolved
        fd, tmp_index = tempfile.mkstemp(dir=STATE_DIR, prefix='index-')
        os.close(fd)
        os.unlink(tmp_index)
        env = {'GIT_INDEX_FILE': tmp_index}
        try:
            git(self.repo, 'read-tree', tree, env=env)
            for path, (mode, content) in resolved.items():
                oid = gout(self.repo, 'hash-object', '-w', '--stdin', input=content)
                git(self.repo, 'update-index', '--add', '--cacheinfo', '%s,%s,%s' % (mode, oid, path), env=env)
            tree = gout(self.repo, 'write-tree', env=env)
        finally:
            if os.path.exists(tmp_index):
                os.unlink(tmp_index)
        self.log('尾部追加自动合并：%s' % '、'.join(resolved))
        return 'merge', tree, list(resolved)

    def dirty_overlap(self, head, new_rev):
        """工作区未提交改动（含未跟踪文件）和这次要带进来的改动是否撞到同一文件。"""
        entries = self.status_entries()
        if not entries:
            return []
        dirty = set(p.rstrip('/') for _, p in entries)
        out = git(self.repo, 'diff', '--no-renames', '--name-only', '-z', head, new_rev).stdout
        incoming = [fs(x) for x in out.split(b'\0') if x]
        hit = []
        for p in incoming:
            if p in dirty or any(p.startswith(d + '/') for d in dirty):
                hit.append(p)
        return hit

    def integrate(self, target, label):
        """把 target 合进本地同步分支。返回 True=成功或无事；False=已记为冲突。"""
        head = rev(self.repo, 'HEAD')
        kind, result, files = self.plan(head, target)
        if kind == 'noop':
            return True
        if kind == 'conflict':
            self.conflict(head, target, label, files, 'content')
            return False
        if kind == 'merge':
            ts = now_iso()
            msg = 'auto-sync %s %s\n\n合并 %s%s\n' % (ts, HOSTTAG, label,
                                                    ('（尾部追加自动合并：%s）' % '、'.join(files)) if files else '')
            new = fs(git(self.repo, 'commit-tree', result, '-p', head, '-p', target, '-F', '-', input=msg.encode(),
                         env=self.author_env()).stdout).strip()
        else:
            new = result
        hit = self.dirty_overlap(head, new)
        if hit:
            self.conflict(head, target, label, hit, 'dirty')
            return False
        p = git(self.repo, 'merge', '--ff-only', '--no-edit', '--no-verify', new, check=False, timeout=600)
        if p.returncode != 0:
            self.conflict(head, target, label, [fs(p.stderr).strip()[-200:]], 'dirty')
            return False
        what = '快进' if kind == 'ff' else '合并'
        self.actions.append('%s %s（%s）' % (what, label, new[:8]))
        self.log('%s %s → %s' % (what, label, new[:8]))
        return True

    def integrate_upstream(self):
        r = self.r
        target = rev(self.repo, self.remote_ref(r['branch']))
        if not target:
            return True  # 远端还没有这个分支：之后推送
        return self.integrate(target, '%s/%s' % (r_remote(r), r['branch']))

    def merge_claude_branches(self):
        r = self.r
        base = r.setdefault('claude_baseline', {})
        handled = r.setdefault('claude_handled', {})
        out = gout(self.repo, 'for-each-ref', '--format=%(refname)%09%(objectname)',
                   'refs/remotes/%s/claude/' % r_remote(r))
        prefix = 'refs/remotes/%s/' % r_remote(r)
        for line in filter(None, out.splitlines()):
            ref, sha = line.split('\t')
            name = ref[len(prefix):]
            if name in base:
                if sha != base[name] and handled.get(name) != sha:
                    handled[name] = sha
                    self.warnings.append('基线分支 %s 有新提交，按规则不自动合并' % name)
                    notify('Git 同步：%s' % self.name, '基线分支 %s 有新提交，未自动合并（需要你决定）' % name,
                           key='baseline:%s:%s:%s' % (self.name, name, sha))
                continue
            if handled.get(name) == sha:
                continue
            if is_ancestor(self.repo, sha, 'HEAD'):
                handled[name] = sha
                continue
            if not self.integrate(sha, name):
                return False
            handled[name] = sha
        return True

    # ---- 冲突
    def conflict(self, head, target, label, files, why):
        r = self.r
        ts = stamp()
        is_claude = label.startswith('claude/')
        ahead = head and not is_ancestor(self.repo, head, target)
        push_ok = r['mode'] == 'sync' and r.get('push', True)
        if is_claude:
            direction, dl = 'claude', '云端分支合并'
        elif why == 'content' and ahead and push_ok:
            direction, dl = 'push', '推送方向'
        else:
            direction, dl = 'pull', '拉取方向'
        bname = 'sync-conflict/%s/%s' % (r['name'], ts)
        n = 1
        while rev(self.repo, 'refs/heads/' + bname):
            n += 1
            bname = 'sync-conflict/%s/%s-%d' % (r['name'], ts, n)
        if direction == 'push':
            snap, where, detail = head, 'GitHub + 本机', '本地这份已提交并推到 GitHub 冲突分支；本地 %s 和远端都没有被改动。' % r['branch']
        elif direction == 'claude':
            snap, where, detail = target, ('GitHub + 本机' if push_ok else '本机'), \
                '云端分支 %s 无法干净合进 %s；已建冲突分支保存云端那份，%s 未改动。' % (label, r['branch'], r['branch'])
        else:
            snap, where, detail = target, '本机', '远端那份已保存到本机冲突分支；工作区里的本地改动没有被动过。'
            if why == 'dirty':
                detail = '本地未提交的改动和远端改动撞到同一文件；' + detail
        git(self.repo, 'branch', bname, snap)
        if where.startswith('GitHub'):
            try:
                git(self.repo, 'push', '--no-verify', r_remote(r), 'refs/heads/%s:refs/heads/%s' % (bname, bname),
                    net=True, timeout=NET_TIMEOUT)
            except GitError as exc:
                where = '本机（推送到 GitHub 失败，下轮不会重试，请手动推送）'
                self.log('冲突分支推送失败：%s' % exc)
        detected = now_iso()
        scope = r.get('memory_scope') or r['path']
        c = {'kind': direction, 'direction_label': dl, 'why': why, 'detected_at': detected, 'branch': bname,
             'branch_where': where, 'local_commit': head, 'remote_commit': target, 'remote_ref': label,
             'files': files[:200], 'detail': detail,
             'memory': {'key': 'git-sync/冲突/%s/%s' % (r['name'], ts), 'scope_id': scope}}
        c['memory']['create'] = {'status': 'pending', 'body': memory_create_body(r, c)}
        r['conflict'] = c
        r['status'] = 'conflict'
        r['status_reason'] = '%s冲突：%s' % (dl, '、'.join(files[:5]))
        self.actions.append('冲突（%s）：%s → 冲突分支 %s' % (dl, '、'.join(files[:5]), bname))
        self.log('冲突（%s）%s：文件 %s；冲突分支 %s（%s）' % (dl, label, files[:20], bname, where))
        notify('Git 同步冲突：%s' % self.name,
               '%s：%s 无法自动合并（%s）。已建分支 %s，自动合并已暂停。' % (dl, label, '、'.join(files[:3]), bname),
               key='conflict:%s:%s' % (self.name, bname))

    def check_resolved(self, entries):
        r = self.r
        c = r['conflict']
        head = rev(self.repo, 'HEAD')
        if c['kind'] == 'claude':
            target = rev(self.repo, 'refs/remotes/%s/%s' % (r_remote(r), c['remote_ref']))
            if not target:
                return self.mark_resolved('云端分支已不存在')
        else:
            target = rev(self.repo, self.remote_ref(r['branch']))
            if not target:
                return self.mark_resolved('远端分支已不存在')
        cur = gout(self.repo, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
        if cur != r['branch']:
            return False
        kind, result, files = self.plan(head, target)
        if kind == 'conflict':
            return False
        if kind != 'noop':
            check_rev = result
            if kind == 'merge':
                check_rev = fs(git(self.repo, 'commit-tree', result, '-p', head, '-m', 'probe').stdout).strip()
            if self.dirty_overlap(head, check_rev):
                return False
        how = {'noop': '本地已包含对方改动', 'ff': '可以快进', 'merge': '现在可以干净合并'}[kind]
        return self.mark_resolved(how)

    def mark_resolved(self, how):
        r = self.r
        c = r['conflict']
        c['resolved_at'] = now_iso()
        c['resolution'] = '检测到冲突已解决：%s' % how
        if c.get('memory', {}).get('create', {}).get('status') != 'failed':
            sup, arc = memory_resolve_bodies(r, c)
            c['memory']['resolve'] = {'status': 'pending', 'body': sup}
            c['memory']['archive'] = {'status': 'pending', 'body': arc}
        hist = r.setdefault('conflict_history', [])
        hist.insert(0, c)
        del hist[20:]
        r['conflict'] = None
        r['status'] = 'ok'
        r['status_reason'] = ''
        self.actions.append('冲突已解决（%s），恢复自动同步' % how)
        self.log('冲突 %s 已解决：%s' % (c['branch'], how))
        notify('Git 同步：%s 冲突已解决' % self.name, '%s；已恢复自动同步。冲突分支 %s 保留未删。' % (how, c['branch']),
               key='resolved:%s:%s' % (self.name, c['branch']))
        return True


def r_remote(r):
    return r.get('remote') or 'origin'


# ---------------------------------------------------------------- 登记表

def load_registry():
    return load_json(REGISTRY, {'version': 1, 'repos': []})


def save_registry(reg):
    save_json(REGISTRY, reg)
    write_registry_md(reg)


def write_registry_md(reg):
    rows = ['# Git 自动同步登记表', '',
            '> 由 gitsync.py 每轮自动生成，勿手改；改状态用 `gitsync.py pause/resume`（见 README.md）。生成时间：%s' % now_iso(), '',
            '| 仓库 | GitHub | 本机路径 | 同步分支 | 可见性 | 模式 | 状态 | 最近同步 | 说明 |',
            '|---|---|---|---|---|---|---|---|---|']
    order = {s: i for i, s in enumerate(('conflict', 'blocked', 'paused', 'ok', 'disabled'))}
    for r in sorted(reg['repos'], key=lambda x: (order.get(x['status'], 9), x['name'])):
        path = r['path'] + ((' （别名 %s）' % r['alias_path']) if r.get('alias_path') else '')
        note = r.get('status_reason') or r.get('last_result') or ''
        if r['status'] == 'disabled':
            note = r.get('status_reason', '')
        rows.append('| %s | %s | `%s` | %s | %s | %s | **%s** | %s | %s |' % (
            r['name'], r.get('remote_url') or '—', path, r.get('branch') or '—', r.get('visibility', '—'),
            {'sync': '双向', 'pull-only': '只拉取', 'none': '—'}.get(r.get('mode'), r.get('mode')), r['status'],
            r.get('last_sync') or '—', note.replace('|', '/').replace('\n', ' ')[:300]))
    with open(REGISTRY_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')


def find_repo(reg, name):
    for r in reg['repos']:
        if r['name'] == name:
            return r
    raise SystemExit('登记表里没有仓库：%s' % name)


class RunLock:
    def __init__(self, wait=0):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.f = open(os.path.join(STATE_DIR, 'run.lock'), 'a+')
        deadline = time.time() + wait
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.time() >= deadline:
                    raise
                time.sleep(2)


# ---------------------------------------------------------------- 命令

def cmd_run(args):
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        lock = RunLock()
    except BlockingIOError:
        log('上一轮还在运行，本次退出（防重入）')
        return 0
    reg = load_registry()
    mem = Memory()
    if not args.only:
        last = load_json(os.path.join(STATE_DIR, 'discover.json'), {}).get('at', 0)
        if time.time() - last > 3600:
            try:
                discover(reg)
            except Exception as exc:
                log('扫描新项目出错：%s' % exc)
            save_json(os.path.join(STATE_DIR, 'discover.json'), {'at': time.time()})
            save_registry(reg)
    log('==== 开始一轮同步（%d 个仓库登记）' % len(reg['repos']))
    counts = {}
    for r in reg['repos']:
        if args.only and r['name'] not in args.only:
            continue
        if r['status'] == 'disabled':
            fetch_listed(r)
        if r['status'] not in ('disabled', 'paused'):
            try:
                RepoSync(r, mem).run()
            except Skip as exc:
                r['last_result'] = str(exc)
                log('跳过：%s' % exc, r['name'])
            except subprocess.TimeoutExpired as exc:
                r['last_result'] = '超时：%s' % ' '.join(map(str, exc.cmd[:6]))
                log(r['last_result'], r['name'])
            except Exception as exc:
                r['last_result'] = '出错：%s' % str(exc)[:300]
                log('出错：%s\n%s' % (exc, traceback.format_exc()[-1500:]), r['name'])
        try:
            process_memory_ops(r, mem)
        except Exception as exc:
            log('MemoryOS 补写出错：%s' % exc, r['name'])
        counts[r['status']] = counts.get(r['status'], 0) + 1
        save_registry(reg)
    save_registry(reg)
    log('==== 本轮结束：%s' % '，'.join('%s %d' % kv for kv in sorted(counts.items())))
    del lock
    return 0


def cmd_status(args):
    reg = load_registry()
    for r in reg['repos']:
        if r['status'] == 'disabled' and not args.all:
            continue
        print('%-28s %-9s %-9s %-26s %s' % (r['name'], r['status'], r.get('mode'), r.get('last_sync') or '-',
                                            (r.get('status_reason') or r.get('last_result') or '')[:120]))
    print('\n完整登记表：%s' % REGISTRY_MD)


def mutate(fn):
    def wrapper(args):
        lock = RunLock(wait=600)
        reg = load_registry()
        fn(reg, args)
        save_registry(reg)
        del lock
    return wrapper


@mutate
def cmd_pause(reg, args):
    r = find_repo(reg, args.name)
    if r['status'] == 'disabled':
        raise SystemExit('%s 是 disabled，不需要暂停' % r['name'])
    r['paused_from'] = r['status']
    r['status'] = 'paused'
    r['status_reason'] = '手动暂停 %s' % now_iso()
    print('已暂停 %s' % r['name'])


@mutate
def cmd_resume(reg, args):
    r = find_repo(reg, args.name)
    if r['status'] != 'paused':
        raise SystemExit('%s 当前状态是 %s，不是 paused' % (r['name'], r['status']))
    r['status'] = 'conflict' if r.get('conflict') else 'ok'
    r['status_reason'] = ''
    print('已恢复 %s（状态 %s），下一轮开始同步' % (r['name'], r['status']))


@mutate
def cmd_resolve(reg, args):
    r = find_repo(reg, args.name)
    if not r.get('conflict'):
        raise SystemExit('%s 没有未解决的冲突' % r['name'])
    c = r['conflict']
    if c['kind'] == 'claude':
        r.setdefault('claude_handled', {})[c['remote_ref']] = c['remote_commit']
    RepoSync(r, Memory()).mark_resolved('用户手动标记已解决')
    print('已标记解决；下一轮恢复同步')


@mutate
def cmd_set(reg, args):
    r = find_repo(reg, args.name)
    if args.field == 'branch':
        r['branch'] = args.value
    elif args.field == 'path':
        path = os.path.realpath(os.path.expanduser(args.value))
        if not os.path.isdir(path) or gout(path, 'rev-parse', '--show-toplevel', check=False) != path:
            raise SystemExit('请选择项目仓库的根文件夹')
        actual = gout(path, 'remote', 'get-url', r_remote(r), check=False)
        if parse_github(actual) != parse_github(r.get('remote_url')) or not parse_github(actual)[0]:
            raise SystemExit('这个文件夹对应另一个 GitHub 项目，未修改同步位置')
        r['path'] = path
        r['status_reason'] = ''
    elif args.field == 'auto-commit':
        if args.value not in ('on', 'off'): raise SystemExit('auto-commit 只能是 on 或 off')
        r['auto_commit'] = args.value == 'on'
    elif args.field == 'follow-branch':
        if args.value not in ('on', 'off'): raise SystemExit('follow-branch 只能是 on 或 off')
        r['follow_branch'] = args.value == 'on'
    elif args.field == 'mode':
        if args.value not in ('sync', 'pull-only'):
            raise SystemExit('mode 只能是 sync 或 pull-only')
        r['mode'] = args.value
    elif args.field == 'push':
        r['push'] = args.value == 'on'
    elif args.field == 'claude-merge':
        r['claude_merge'] = args.value == 'on'
    elif args.field == 'enable':
        enable_repo(r)
    elif args.field == 'disable':
        if r['status'] != 'disabled':
            r['enabled_mode'] = r.get('mode')
        r['status'] = 'disabled'
        r['status_reason'] = '本机未勾选同步：只取回 GitHub 上的版本信息，不改本机文件'
    elif args.field == 'exclude':
        lst = r.setdefault('exclude', [])
        if args.value not in lst:
            lst.append(args.value)
    elif args.field == 'include':
        r['exclude'] = [x for x in r.get('exclude', []) if x != args.value]
    elif args.field == 'release-baseline':
        r.get('claude_baseline', {}).pop(args.value, None)
        r.get('claude_handled', {}).pop(args.value, None)
    else:
        raise SystemExit('未知字段')
    print('已更新 %s：%s=%s' % (r['name'], args.field, args.value))


def enable_repo(r):
    if not r.get('remote_url'):
        raise SystemExit('%s 没有连接 GitHub，无法开启同步' % r['name'])
    if not os.path.isdir(r['path']):
        raise SystemExit('%s 的文件夹不存在（硬盘未连接？）' % r['name'])
    owner, _ = parse_github(r['remote_url'])
    mode = r.get('enabled_mode') if r.get('enabled_mode') not in (None, 'none') else r.get('mode')
    if mode in (None, 'none'):
        mode = 'sync' if owner in (None, GITHUB_OWNER) and r.get('visibility') != 'public' else 'pull-only'
    if owner and owner != GITHUB_OWNER:
        mode = 'pull-only'  # 别人的仓库永远只取回，不上传
    r['mode'] = mode
    r['push'] = mode == 'sync'
    if r['status'] in ('disabled', 'blocked'):
        try:
            git(r['path'], 'fetch', '--no-write-fetch-head', r_remote(r), net=True, timeout=NET_TIMEOUT)
            if not r.get('claude_baseline'):
                r['claude_baseline'] = snapshot_claude_baseline(r['path'], r_remote(r))
        except Exception:
            pass
    r['status'] = 'conflict' if r.get('conflict') else 'ok'
    r['status_reason'] = ''


DISCOVER_ROOTS = [os.path.expanduser(x.strip()) for x in
                  os.environ.get('GITSYNC_DISCOVER_ROOTS', '~/Projects').split(':') if x.strip()]
LOCAL_SETTINGS = os.path.join(STATE_DIR, 'local-settings.json')


def discover(reg, verbose=False):
    """把本机新出现的 Git 仓库登记进目录（默认不同步；本机设置 default_enabled=true 时自己的仓库自动勾选）。"""
    settings = load_json(LOCAL_SETTINGS, {})
    known = {os.path.realpath(r['path']) for r in reg['repos']}
    names = {r['name'] for r in reg['repos']}
    added = []
    for root in DISCOVER_ROOTS:
        if not os.path.isdir(root):
            continue
        cands = [root] if os.path.isdir(os.path.join(root, '.git')) else []
        for dp, dns, _ in os.walk(root):
            depth = dp[len(root):].count(os.sep)
            dns[:] = [d for d in dns if d not in ('node_modules', '.git', '__pycache__', 'backups', '.venv', 'venv')
                      and not d.startswith('.')]
            if depth >= 3:
                dns[:] = []
            for d in list(dns):
                if os.path.isdir(os.path.join(dp, d, '.git')):
                    cands.append(os.path.join(dp, d))
        for path in cands:
            real = os.path.realpath(path)
            if real in known or '/sync-conflict' in real:
                continue
            known.add(real)
            name = os.path.basename(path) or path
            e = new_entry(real, name)
            owner, repo = parse_github(e['remote_url'])
            if repo and owner == GITHUB_OWNER:
                e['name'] = repo
            elif repo:
                e['name'] = '3p-' + repo
            base, n = e['name'], 2
            while e['name'] in names:
                e['name'] = '%s--%d' % (base, n); n += 1
            names.add(e['name'])
            e['status_reason'] = ('本机未勾选同步' if e['remote_url'] else '没有连接 GitHub（需要先建仓库才能同步）')
            if e['remote_url'] and owner == GITHUB_OWNER:
                e['visibility'] = github_visibility(owner, repo)
                if settings.get('default_enabled') and not real.startswith('/Volumes/'):  # 外接卷上的备份副本永不自动开启
                    try:
                        enable_repo(e)
                    except SystemExit:
                        pass
            reg['repos'].append(e)
            added.append(e['name'])
            log('目录新增：%s（%s）%s' % (e['name'], real, '，已按本机默认开启同步' if e['status'] != 'disabled' else ''))
    return added


def fetch_listed(r):
    """未勾选的仓库：只取回 GitHub 上的分支/版本信息，不碰本机文件。每小时一次。"""
    if not r.get('remote_url') or not os.path.isdir(r.get('path') or ''):
        return
    last = r.get('last_listed_fetch') or ''
    if last and time.time() - datetime.datetime.fromisoformat(last).timestamp() < 3600:
        return
    try:
        git(r['path'], 'fetch', '--no-write-fetch-head', '--quiet', r_remote(r), net=True, timeout=120)
        r['last_listed_fetch'] = now_iso()
        r['last_check'] = r['last_listed_fetch']
    except Exception as exc:
        r['last_listed_fetch'] = now_iso()
        log('未勾选项目取回版本信息失败：%s' % str(exc)[:160], r['name'])


def snapshot_claude_baseline(path, remote='origin'):
    out = gout(path, 'for-each-ref', '--format=%(refname)%09%(objectname)', 'refs/remotes/%s/claude/' % remote)
    prefix = 'refs/remotes/%s/' % remote
    return {ref[len(prefix):]: sha for ref, sha in (l.split('\t') for l in out.splitlines() if l)}


def new_entry(path, name, **kw):
    url = gout(path, 'remote', 'get-url', 'origin', check=False) or None
    branch = gout(path, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False) or None
    e = {'name': name, 'path': path, 'alias_path': None, 'memory_scope': path, 'remote': 'origin',
         'remote_url': url, 'branch': branch, 'visibility': 'unknown', 'mode': 'none', 'push': False,
         'claude_merge': False, 'claude_baseline': {}, 'claude_handled': {}, 'status': 'disabled',
         'status_reason': '', 'last_sync': None, 'last_check': None, 'last_result': '', 'warnings': [],
         'conflict': None, 'conflict_history': [], 'added_at': now_iso()}
    e.update(kw)
    return e


@mutate
def cmd_add(reg, args):
    """登记一个仓库（启用双向同步时会记录当时已有的 claude/* 分支作为基线）。"""
    path = os.path.abspath(args.path)
    if any(r['path'] == path for r in reg['repos']):
        raise SystemExit('已登记：%s' % path)
    name = args.name or os.path.basename(path)
    e = new_entry(path, name)
    owner, repo = parse_github(e['remote_url'])
    if repo and not args.name:
        e['name'] = repo
    e['visibility'] = args.visibility or github_visibility(owner, repo)
    if args.mode:
        e['mode'] = args.mode
    elif e['remote_url'] and owner == GITHUB_OWNER:
        e['mode'] = 'sync' if e['visibility'] == 'private' else 'pull-only'
    e['push'] = e['mode'] == 'sync'
    e['status'] = 'ok' if e['mode'] != 'none' else 'disabled'
    if e['status'] == 'ok':
        git(path, 'fetch', '--no-write-fetch-head', 'origin', net=True, timeout=NET_TIMEOUT)
        e['claude_baseline'] = snapshot_claude_baseline(path)
        default = gout(path, 'symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD', check=False)
        e['claude_merge'] = e['mode'] == 'sync' and (default in ('origin/' + (e['branch'] or ''),) or
                                                     (not default and e['branch'] == 'main'))
    if args.memory_scope:
        e['memory_scope'] = args.memory_scope
    if args.alias_path:
        e['alias_path'] = args.alias_path
    reg['repos'].append(e)
    print(json.dumps({k: e[k] for k in ('name', 'path', 'remote_url', 'branch', 'visibility', 'mode', 'status',
                                        'claude_merge', 'claude_baseline')}, ensure_ascii=False, indent=1))


@mutate
def cmd_discover(reg, args):
    print(json.dumps(discover(reg), ensure_ascii=False))


def github_visibility(owner, repo):
    if not owner or not os.path.exists(GH):
        return 'unknown'
    p = subprocess.run([GH, 'api', 'repos/%s/%s' % (owner, repo), '--jq', '.private'], capture_output=True,
                       timeout=60, text=True)
    if p.returncode != 0:
        return 'unknown'
    return 'private' if p.stdout.strip() == 'true' else 'public'


def cmd_preview(args):
    reg = load_registry()
    os.makedirs(STATE_DIR, exist_ok=True)
    for r in reg['repos']:
        if r['status'] == 'disabled' or (args.only and r['name'] not in args.only):
            continue
        try:
            info = RepoSync(r, None).preview()
        except Exception as exc:
            info = {'error': str(exc)[:300]}
        print(json.dumps({'name': r['name'], **info}, ensure_ascii=False), flush=True)


def cmd_memory_selftest(args):
    """往 MemoryOS 写一条明确标注为“同步器自检”的记录，随后立即按冲突解决规则降权归档。"""
    mem = Memory()
    scope = args.scope or HOME_DIR
    ts = stamp()
    r = {'name': 'git-sync-自检', 'path': scope, 'branch': 'main', 'remote_url': ''}
    c = {'detected_at': now_iso(), 'branch': 'sync-conflict/git-sync-自检/%s（不存在，自检）' % ts,
         'branch_where': '无（自检记录）', 'direction_label': '同步器自检', 'local_commit': '0' * 40,
         'remote_commit': '0' * 40, 'remote_ref': 'selftest', 'files': ['（同步器自检，无真实冲突）'],
         'detail': '这是 git-sync 安装时的同步器自检记录，不是真实冲突；写入后立即降权归档。',
         'memory': {'key': 'git-sync/冲突/同步器自检/%s' % ts, 'scope_id': scope}}
    c['memory']['create'] = {'status': 'pending', 'body': memory_create_body(r, c)}
    c['memory']['create']['body']['candidate']['value']['标题'] = '自动 Git 历史：同步器自检（非真实冲突）'
    c['resolved_at'] = now_iso()
    c['resolution'] = '同步器自检完成，立即归档'
    r['conflict_history'] = [c]
    for step in ('create',):
        state, res = mem.remember(c['memory'][step]['body'])
        print(step, state, res if state != 'done' else {k: res.get(k) for k in ('event_id', 'version')})
        if state != 'done':
            return 1
        c['memory'][step].update(status='done', event_id=res.get('event_id'), version=res.get('version'))
    sup, arc = memory_resolve_bodies(r, c)
    for step, body in (('resolve', sup), ('archive', arc)):
        state, res = mem.remember(body)
        print(step, state, res if state != 'done' else {k: res.get(k) for k in ('event_id', 'version')})
        if state != 'done':
            return 1
    hist = mem.get_history(c['memory']['key'], scope)
    for h in hist:
        ir = h['ir']
        print('v%s action=%s weight=%s tier=%s status=%s' % (h['version'], ir['action'], ir.get('weight'),
                                                             ir.get('tier'), h.get('status')))
    print('key=%s scope_id=%s' % (c['memory']['key'], scope))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='Git 自动同步器')
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('run', help='同步一轮')
    p.add_argument('--only', nargs='*')
    p = sub.add_parser('status', help='看状态')
    p.add_argument('--all', action='store_true')
    for n in ('pause', 'resume', 'resolve'):
        sub.add_parser(n).add_argument('name')
    p = sub.add_parser('set', help='改登记项：branch/mode/push/claude-merge/enable/exclude/include/release-baseline')
    p.add_argument('name')
    p.add_argument('field')
    p.add_argument('value', nargs='?', default='')
    p = sub.add_parser('add', help='登记新仓库')
    p.add_argument('path')
    p.add_argument('--name')
    p.add_argument('--mode', choices=('sync', 'pull-only', 'none'))
    p.add_argument('--visibility', choices=('private', 'public', 'unknown'))
    p.add_argument('--memory-scope')
    p.add_argument('--alias-path')
    sub.add_parser('discover', help='扫描本机新仓库加入目录')
    p = sub.add_parser('preview', help='只读预览将要自动提交的内容')
    p.add_argument('--only', nargs='*')
    p = sub.add_parser('memory-selftest')
    p.add_argument('--scope')
    args = ap.parse_args(argv)
    cmd = args.cmd or 'run'
    if cmd == 'run' and not args.cmd:
        args.only = None
    return {'run': cmd_run, 'status': cmd_status, 'pause': cmd_pause, 'resume': cmd_resume, 'resolve': cmd_resolve,
            'set': cmd_set, 'add': cmd_add, 'discover': cmd_discover, 'preview': cmd_preview, 'memory-selftest': cmd_memory_selftest}[cmd](args) or 0


if __name__ == '__main__':
    sys.exit(main())
