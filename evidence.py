#!/usr/bin/env python3
"""Append-only, hash-chained evidence records for AI tasks.

One JSON line per task outcome under <state>/evidence/ (0700 dir, 0600 files),
never inside a repository. Every line carries seq, prev_hash and its own
sha256 over the canonical JSON, so `verify` detects edited, reordered,
dropped or truncated records; evidence.head.json pins the last seq/hash.

Evidence never writes the token ledger. Tokens and cost are *references* to
ledger row ids plus a read-only summary; ledger statistics (token_stats,
console_data) do not read this file, so nothing is billed twice. Fields that
cannot be measured stay null and the record says where each value came from.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

STATE = Path(os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate')).expanduser()
FOLDER = 'evidence'
LOG_NAME = 'evidence.jsonl'
HEAD_NAME = 'evidence.head.json'
LOCK_NAME = 'evidence.lock'
GENESIS = '0' * 64
SCHEMA = 1
MAX_LINE = 256 * 1024
KINDS = ('gate_run', 'center_task', 'group_job', 'external')
# Platform -> API vendor. ZCode fronts several vendors, so it stays unknown.
PROVIDERS = {'claude': 'anthropic', 'anthropic': 'anthropic', 'codex': 'openai', 'gpt': 'openai', 'openai': 'openai'}
SECRET = re.compile(r'(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}'
                    r'|xox[baprs]-[A-Za-z0-9-]{10,}|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{16,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})')
SESSION_ID = re.compile(r'[0-9A-Za-z][0-9A-Za-z_-]{7,79}')
_thread_lock = threading.Lock()


class EvidenceError(Exception):
    pass


class EvidenceHeadMismatch(EvidenceError):
    """Head disagrees with a verified chain (not content tampering).

    Kept distinct from hash_mismatch/chain_broken so operators can tell
    'the log is intact but head.json points elsewhere' apart from 'records
    were edited'. Only repair_head() may resolve this state, and only after
    verify() passes with matching expect_count/expect_last.
    """
    pass


# ---------------------------------------------------------------- storage

def folder(state_dir=STATE):
    return Path(state_dir).expanduser() / FOLDER


def canonical(record):
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def record_hash(record):
    body = {k: v for k, v in record.items() if k != 'hash'}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def _private_open(path, flags):
    fd = os.open(path, flags | os.O_CREAT, 0o600)
    os.fchmod(fd, 0o600)
    return fd


def _read_head(path):
    try:
        head = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise EvidenceError('evidence.head.json 无法解析，先运行 verify')
    if not isinstance(head, dict) or type(head.get('seq')) is not int or not isinstance(head.get('hash'), str):
        raise EvidenceError('evidence.head.json 格式无效，先运行 verify')
    return head


def _write_head(path, record):
    tmp = path.with_name(path.name + '.tmp')
    fd = _private_open(tmp, os.O_WRONLY | os.O_TRUNC)
    try:
        os.write(fd, json.dumps({'seq': record['seq'], 'hash': record['hash'], 'at': record['at']}).encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _last_record(path):
    """Last line of the log, checked on its own; None for an empty log."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    if size == 0:
        return None
    with open(path, 'rb') as handle:
        take = min(size, MAX_LINE + 2)
        handle.seek(size - take)
        tail = handle.read(take)
    if not tail.endswith(b'\n'):
        raise EvidenceError('证据文件末行不完整（可能被截断或改动），先运行 verify')
    line = tail[:-1].rsplit(b'\n', 1)[-1]
    try:
        record = json.loads(line.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise EvidenceError('证据文件末行不是有效 JSON，先运行 verify')
    if not isinstance(record, dict) or record.get('hash') != record_hash(record) or canonical(record).encode() != line:
        raise EvidenceError('证据文件末行哈希不符，拒绝在被改动的链上追加；先运行 verify')
    return record


def append(fields, state_dir=STATE):
    """Append one record under an exclusive lock; returns the stored record."""
    base = folder(state_dir)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base, 0o700)
    log, head_path = base / LOG_NAME, base / HEAD_NAME
    with _thread_lock:
        lock_fd = _private_open(base / LOCK_NAME, os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            last = _last_record(log)
            head = _read_head(head_path)
            if head is not None:
                in_sync = last is not None and head['seq'] == last['seq'] and head['hash'] == last['hash']
                # A crash between the append and the head update leaves the
                # head exactly one record behind; anything else is tampering.
                one_behind = last is not None and last['seq'] == head['seq'] + 1 and last['prev_hash'] == head['hash']
                if not (in_sync or one_behind):
                    raise EvidenceError('证据文件与 head 不一致（记录被删除或截断），先运行 verify')
            elif last is not None and last['seq'] != 1:
                raise EvidenceError('evidence.head.json 缺失，先运行 verify')
            record = dict(fields)
            record.update(v=SCHEMA, seq=(last['seq'] + 1) if last else 1,
                          prev_hash=last['hash'] if last else GENESIS)
            record.pop('hash', None)
            record['hash'] = record_hash(record)
            line = (canonical(record) + '\n').encode()
            if len(line) > MAX_LINE:
                raise EvidenceError('单条证据超过 256 KiB')
            fd = _private_open(log, os.O_WRONLY | os.O_APPEND)
            try:
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view):]
                os.fsync(fd)
            finally:
                os.close(fd)
            _write_head(head_path, record)
            return record
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def verify(state_dir=STATE, expect_head=None):
    base = folder(state_dir)
    log, head_path = base / LOG_NAME, base / HEAD_NAME
    errors, warnings = [], []
    count, prev, last = 0, GENESIS, None

    def error(line, reason):
        if len(errors) < 50:
            errors.append({'line': line, 'reason': reason})

    if log.exists():
        mode = log.stat().st_mode & 0o777
        if mode != 0o600:
            warnings.append('证据文件权限为 {:o}，应为 600'.format(mode))
        data = log.read_bytes()
        lines = data.split(b'\n')
        if lines and lines[-1] == b'':
            lines.pop()
        elif data:
            error(len(lines), 'partial_last_line')
        for number, raw in enumerate(lines, 1):
            count += 1
            try:
                record = json.loads(raw.decode('utf-8'))
                if not isinstance(record, dict):
                    raise ValueError
            except (UnicodeDecodeError, ValueError):
                error(number, 'invalid_json')
                prev = None
                continue
            if canonical(record).encode() != raw:
                error(number, 'not_canonical_bytes')
            if record.get('hash') != record_hash(record):
                error(number, 'hash_mismatch')
            if prev is not None and record.get('prev_hash') != prev:
                error(number, 'chain_broken')
            if record.get('seq') != number:
                error(number, 'seq_mismatch')
            prev = record.get('hash')
            last = record
    try:
        head = _read_head(head_path)
    except EvidenceError as exc:
        head = None
        error(None, str(exc))
    if head is not None:
        if last is None:
            error(None, 'log_missing_but_head_present')
        elif head['seq'] > count:
            error(None, 'truncated: head seq {} > records {}'.format(head['seq'], count))
        elif head['seq'] == count and head['hash'] != last.get('hash'):
            error(None, 'head_hash_mismatch')
        elif head['seq'] == count - 1:
            warnings.append('head 落后一条（追加后写 head 前中断），下次追加会自动对齐')
        elif head['seq'] < count - 1:
            error(None, 'head_behind_by_{}'.format(count - head['seq']))
    elif head is None and count > 0:
        # No reconciliation here: a missing head is only a truncatability
        # warning. repair_head() below is the sole writer of head.json.
        error(None, 'head_missing')
    if expect_head and (last is None or last.get('hash') != expect_head):
        error(None, 'expected_head_not_last')
    return {'ok': not errors, 'records': count, 'last_seq': last.get('seq') if last else 0,
            'last_hash': last.get('hash') if last else None, 'errors': errors, 'warnings': warnings,
            'file': str(log)}


def repair_head(state_dir=STATE, expect_count=None, expect_last=None):
    """Rewrite evidence.head.json after a fully verified chain.

    Preconditions (all verified in this call, no background reconciliation):
    - verify() passes except for head-related errors (head_mismatch /
      head_missing / truncated-head / head_behind): the record chain itself
      (hash/prev_hash/seq/canonical bytes) must be intact.
    - expect_count and expect_last (last record hash) match verify() output.
    Only the head file is rewritten; no record is added, edited or deleted,
    and append()'s one-behind self-heal (head == last - 1) is untouched.
    """
    base = folder(state_dir)
    result = verify(base.parent)
    chain_errors = [e for e in result['errors']
                    if e['reason'] not in ('head_hash_mismatch', 'head_missing', 'head_behind_by_1',
                                           'log_missing_but_head_present') and not (
                        e['reason'].startswith('head_behind_by_') or e['reason'].startswith('truncated'))]
    head_path = base / HEAD_NAME
    head_exists = head_path.exists()
    if chain_errors or not result['last_hash']:
        raise EvidenceHeadMismatch('链本身未通过 verify，拒绝重写 head：' +
                                   ','.join(sorted({e['reason'] for e in result['errors']}))[:200])
    if expect_count is not None and result['records'] != expect_count:
        raise EvidenceHeadMismatch('expect-count 与 verify 记录数不一致')
    if expect_last is not None and result['last_hash'] != expect_last:
        raise EvidenceHeadMismatch('expect-last 与链尾哈希不一致')
    log = base / LOG_NAME
    last = _last_record(log)
    if last is None or last.get('hash') != result['last_hash']:
        raise EvidenceHeadMismatch('链尾记录与 verify 输出不一致')
    _write_head(head_path, last)
    return {'repaired': True, 'seq': last['seq'], 'hash': last['hash'],
            'head_existed': head_exists}


def read_records(state_dir=STATE):
    log = folder(state_dir) / LOG_NAME
    if not log.exists():
        return []
    rows = []
    for raw in log.read_bytes().splitlines():
        try:
            record = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            continue
        if isinstance(record, dict):
            rows.append(record)
    return rows


# ---------------------------------------------------------------- sources

def clean(value, limit=500):
    if value is None:
        return None
    return SECRET.sub('[REDACTED]', str(value))[:limit]


def count(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(name + ' 必须是非负整数')
    return value


def number(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 1e15:
        raise ValueError(name + ' 必须是非负数')
    return round(float(value), 6)


def clean_url(value):
    if not value:
        return None
    parts = urllib.parse.urlsplit(str(value).strip())
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('CI 链接必须是不含账号密码的 https 地址')
    # Query strings can carry signed tokens (artifact downloads); keep the path only.
    return clean(urllib.parse.urlunsplit(('https', parts.netloc, parts.path, '', '')), 400)


def git_info(root):
    if not root:
        return {'commit': None, 'dirty': None, 'branch': None, 'source': None, 'error': 'no_root'}
    def run(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                              errors='replace', timeout=30, stdin=subprocess.DEVNULL)
    try:
        head = run('rev-parse', 'HEAD')
        if head.returncode:
            return {'commit': None, 'dirty': None, 'branch': None, 'source': 'git', 'error': 'not_a_git_repo_or_no_commit'}
        branch = run('rev-parse', '--abbrev-ref', 'HEAD')
        status = run('status', '--porcelain=v1', '--untracked-files=normal')
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'commit': None, 'dirty': None, 'branch': None, 'source': 'git', 'error': type(exc).__name__}
    lines = [x for x in status.stdout.splitlines() if x.strip()] if status.returncode == 0 else None
    untracked = sum(x.startswith('??') for x in lines) if lines is not None else None
    return {'commit': head.stdout.strip(), 'branch': branch.stdout.strip() or None,
            'dirty': bool(lines) if lines is not None else None,
            'changed_tracked': (len(lines) - untracked) if lines is not None else None,
            'untracked': untracked, 'source': 'git', 'error': None if lines is not None else 'status_failed'}


def _ledger(state_dir):
    path = Path(state_dir).expanduser() / 'tokens.sqlite3'
    if not path.exists():
        return None
    connection = sqlite3.connect('file:' + urllib.parse.quote(str(path)) + '?mode=ro', uri=True, timeout=5)
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='turns'").fetchone():
        connection.close()
        return None
    return connection


def ledger_rows(ids, state_dir=STATE):
    connection = _ledger(state_dir)
    if connection is None:
        return {}
    try:
        cols = {r[1] for r in connection.execute('PRAGMA table_info(turns)')}
        wanted = ['id', 'at', 'platform', 'model', 'sent', 'actual_input', 'actual_output', 'cached', 'cache_creation', 'duration_ms']
        select = ','.join(name if name in cols else 'NULL' for name in wanted)
        rows = {}
        ids = list(ids)
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            query = 'SELECT ' + select + ' FROM turns WHERE id IN (' + ','.join('?' * len(chunk)) + ')'
            for values in connection.execute(query, chunk):
                rows[values[0]] = dict(zip(wanted, values))
        return rows
    finally:
        connection.close()


def ledger_summary(ids, state_dir=STATE):
    """Read-only roll-up of referenced ledger rows. Never inserts anything."""
    unique = []
    for value in ids or ():
        if isinstance(value, str) and 0 < len(value) <= 200 and value not in unique:
            unique.append(value)
    if not unique:
        return None
    rows = ledger_rows(unique, state_dir)
    measured = [rows[i] for i in unique if i in rows and rows[i]['actual_input'] is not None]
    import prices
    rules = prices.load_rules(state_dir)
    cost, unpriced = 0.0, 0
    for row in measured:
        value = prices.row_cost(row['model'], row['actual_input'], row['actual_output'], row['cached'], rules,
                                cache_creation=row['cache_creation'], platform=row['platform'])
        if value is None:
            unpriced += 1
        else:
            cost += value
    priced = len(measured) - unpriced
    return {'ids': unique, 'found': sum(i in rows for i in unique), 'missing': [i for i in unique if i not in rows],
            'measured_rows': len(measured),
            'input_tokens': sum(r['actual_input'] for r in measured),
            'output_tokens': sum(r['actual_output'] or 0 for r in measured),
            'cached_input_tokens': sum(r['cached'] or 0 for r in measured),
            'cache_creation_tokens': sum(r['cache_creation'] or 0 for r in measured),
            'request_ms_sum': round(sum(r['duration_ms'] or 0 for r in measured), 2) if any(r['duration_ms'] is not None for r in measured) else None,
            'cost_usd': round(cost, 6) if priced else None, 'priced_rows': priced, 'unpriced_rows': unpriced,
            'models': sorted({r['model'] for r in measured if r['model']}),
            'platforms': sorted({r['platform'] for r in measured if r['platform']}),
            'resolved_at': round(time.time(), 3)}


def session_transcripts(platform, session_id):
    """Locate native transcripts for a session id (same files usage_import reads)."""
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        return []
    import usage_import
    if platform == 'claude':
        root = usage_import.CLAUDE_PROJECTS
        return sorted(set(root.glob('*/' + session_id + '.jsonl')) | set(root.glob('*/' + session_id + '/subagents/*.jsonl')))
    if platform in ('codex', 'gpt'):
        return sorted(usage_import.CODEX_SESSIONS.rglob('rollout-*' + session_id + '*.jsonl'))
    return []


def transcript_refs(paths, since=None, until=None, state_dir=STATE):
    """Map native transcript usage entries to existing ledger rows.

    Exact match first (usage_import derives row ids from the same keys), then
    the importer's own fingerprint rule (platform, model, input, output within
    600 s) for rows that a watch proxy recorded under its own id. Entries with
    no ledger row are counted separately and never billed.
    """
    import usage_import
    groups = {}
    for raw in paths or ():
        path = Path(raw).expanduser()
        try:
            text = path.read_text(errors='replace')
        except OSError:
            continue
        if '"token_usage_record"' in text or path.name.startswith('rollout-'):
            parsed, prefix, platform = usage_import.codex_entries(text)[0], 'imp-codex-', 'codex'
            dedupe = lambda key: key
        else:
            parsed, prefix, platform = list(usage_import.claude_entries(text)), 'imp-claude-', 'claude'
            # Claude Code writes one assistant line per content block, all with
            # the same message id/request id and usage: one API call. The
            # importer keys rows by id|request|timestamp, so the ledger may
            # hold several rows for one call; reference one, report the rest.
            dedupe = lambda key: key if key.startswith('|') else key.rsplit('|', 1)[0]
        for at, model, input_total, output, cached, creation, duration, key in parsed:
            if (since is not None and at < since) or (until is not None and at > until):
                continue
            group = groups.setdefault((platform, dedupe(key)), {
                'rids': [], 'entry': (platform, at, model, input_total, output, cached, creation)})
            row_id = prefix + hashlib.sha1(key.encode()).hexdigest()[:24]
            if row_id not in group['rids']:
                group['rids'].append(row_id)
    if not groups:
        return None
    connection = _ledger(state_dir)
    ids, used, exact, fingerprint, duplicates = [], set(), 0, 0, []
    unmatched = {'entries': 0, 'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0}
    try:
        for group in sorted(groups.values(), key=lambda g: g['entry'][1]):
            platform, at, model, input_total, output, cached, creation = group['entry']
            match = None
            if connection is not None:
                present = [rid for rid in group['rids']
                           if connection.execute('SELECT 1 FROM turns WHERE id=?', (rid,)).fetchone()]
                if present:
                    match, exact = present[0], exact + 1
                    duplicates += present[1:]
                else:
                    for other, other_at in connection.execute(
                            'SELECT id,at FROM turns WHERE sent=1 AND platform=? AND model IS ? AND actual_input=? AND actual_output=? AND at BETWEEN ? AND ? ORDER BY abs(at-?)',
                            (platform, model, input_total, output, at - 600, at + 600, at)):
                        if other not in used:
                            match, fingerprint = other, fingerprint + 1
                            break
            if match is None or match in used:
                unmatched['entries'] += 1
                unmatched['input_tokens'] += input_total or 0
                unmatched['output_tokens'] += output or 0
                unmatched['cached_input_tokens'] += cached or 0
                continue
            used.add(match)
            ids.append(match)
    finally:
        if connection is not None:
            connection.close()
    return {'ids': ids, 'calls': len(groups), 'matched_exact': exact, 'matched_fingerprint': fingerprint,
            'unmatched': unmatched, 'ledger_duplicate_rows': len(duplicates), 'ledger_duplicate_ids': duplicates[:50],
            'files': len(list(paths or ())), 'window': [since, until],
            'note': '每个 API 调用只引用一行账本；ledger_duplicate_rows 为账本里同一调用的额外行（未计入本证据）。' if duplicates else None}


TEST_RAN = re.compile(r'^Ran (\d+) tests? in ', re.M)
TEST_RESULT = re.compile(r'^(OK|FAILED)(?: \(([^)]*)\))?\s*$', re.M)
PYTEST = re.compile(r'^=+ (.+?) in [\d.]+s(?: \([^)]*\))? =+\s*$', re.M)


def parse_test_output(text):
    """Counts from unittest or pytest summaries; {} when no summary is found."""
    text = text or ''
    ran, result = TEST_RAN.findall(text), TEST_RESULT.findall(text)
    if ran and result:
        total = int(ran[-1])
        parts = dict((k.strip(), int(v)) for k, v in re.findall(r'([a-z ]+)=(\d+)', result[-1][1]))
        failed = parts.get('failures', 0) + parts.get('unexpected successes', 0)
        errors, skipped = parts.get('errors', 0), parts.get('skipped', 0)
        return {'framework': 'unittest', 'total': total, 'passed': max(0, total - failed - errors - skipped),
                'failed': failed, 'errors': errors, 'skipped': skipped,
                'summary': clean('Ran {} tests; {}'.format(total, ' '.join(x for x in result[-1] if x)), 200)}
    found = PYTEST.findall(text)
    if found:
        parts = {}
        for value, name in re.findall(r'(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected)', found[-1]):
            name = 'errors' if name.startswith('error') else name
            parts[name] = parts.get(name, 0) + int(value)
        if parts:
            failed = parts.get('failed', 0) + parts.get('xpassed', 0)
            passed = parts.get('passed', 0) + parts.get('xfailed', 0)
            return {'framework': 'pytest', 'total': passed + failed + parts.get('errors', 0) + parts.get('skipped', 0),
                    'passed': passed, 'failed': failed, 'errors': parts.get('errors', 0),
                    'skipped': parts.get('skipped', 0), 'summary': clean(found[-1], 200)}
    return {}


def run_test(command, root, timeout=1800):
    """Run one test command *without a shell* (only from the CLI, never HTTP)."""
    argv = shlex.split(command)
    if not argv:
        raise ValueError('测试命令为空')
    started = time.perf_counter()
    result = {'command': clean(command), 'source': 'executed', 'exit_code': None, 'error': None}
    try:
        proc = subprocess.run(argv, cwd=str(root) if root else None, capture_output=True, text=True,
                              errors='replace', timeout=timeout, stdin=subprocess.DEVNULL)
        output = proc.stdout + proc.stderr
        result['exit_code'] = proc.returncode
    except FileNotFoundError:
        output, result['error'] = '', 'command_not_found'
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or '') + (exc.stderr or '') if isinstance(exc.stdout, str) else ''
        result['error'] = 'timeout'
    result['duration_ms'] = round((time.perf_counter() - started) * 1000, 2)
    # Raw output is not stored (may hold secrets); its hash lets a kept copy be matched later.
    result['output_sha256'] = hashlib.sha256(output.encode()).hexdigest()
    counts = parse_test_output(output)
    result.update({k: counts.get(k) for k in ('framework', 'total', 'passed', 'failed', 'errors', 'skipped', 'summary')})
    return result


def reported_test(item):
    if not isinstance(item, dict) or not item.get('command'):
        raise ValueError('测试结果需要 command')
    code = item.get('exit_code')
    if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
        raise ValueError('exit_code 必须是整数')
    # Reported results stay labelled as reported; only this module's own
    # runner may write source=executed.
    result = {'command': clean(item['command']), 'source': 'reported', 'exit_code': code}
    for name in ('total', 'passed', 'failed', 'errors', 'skipped'):
        result[name] = count(item.get(name), name)
    result['duration_ms'] = number(item.get('duration_ms'), 'duration_ms')
    if item.get('summary'):
        result['summary'] = clean(item['summary'], 200)
    return result


def gh_runs(root, commit):
    """Best-effort GitHub Actions runs for a commit via the local gh login."""
    try:
        proc = subprocess.run(['gh', 'run', 'list', '--commit', commit, '--json', 'url,databaseId,name,status,conclusion', '-L', '10'],
                              cwd=str(root), capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        runs = json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        runs = None
    if not isinstance(runs, list):
        return None
    return [{'url': clean_url(r.get('url')), 'id': r.get('databaseId'), 'name': clean(r.get('name'), 120),
             'status': clean(r.get('status'), 40), 'conclusion': clean(r.get('conclusion'), 40)}
            for r in runs if isinstance(r, dict) and r.get('url')]


# ---------------------------------------------------------------- records

def build(spec, state_dir=STATE):
    """Normalize one evidence record. Values only from the given spec, the
    referenced ledger rows, git, or transcripts; each group names its source."""
    kind = spec.get('kind') or 'external'
    if kind not in KINDS:
        raise ValueError('kind 无效')
    root = spec.get('root')
    root = str(Path(root).expanduser().resolve()) if root else None
    platform = clean(spec.get('platform'), 40)
    provider = clean(spec.get('provider'), 60)
    provider_source = 'reported' if provider else None
    if not provider and platform in PROVIDERS:
        provider, provider_source = PROVIDERS[platform], 'platform_map'
    ledger_ids = list(spec.get('ledger_ids') or [])
    transcripts = None
    if spec.get('transcripts'):
        transcripts = transcript_refs(spec['transcripts'], spec.get('since'), spec.get('until'), state_dir)
        if transcripts:
            ledger_ids += transcripts['ids']
    ledger = ledger_summary(ledger_ids, state_dir)
    model = clean(spec.get('model'), 120)
    model_source = (spec.get('model_source') or 'reported') if model else None
    if not model and ledger and ledger['models']:
        model, model_source = ','.join(ledger['models']), 'ledger'
    reported = spec.get('tokens') or {}
    reported = {k: count(reported.get(k), k) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_creation_tokens')}
    if ledger and ledger['measured_rows']:
        tokens = {k: ledger[k] for k in reported}
        tokens['source'] = 'ledger'
    elif any(v is not None for v in reported.values()):
        tokens = dict(reported, source=spec.get('tokens_source') or 'reported')
    else:
        tokens = dict.fromkeys(reported)
        tokens['source'] = None
    cost_reported = number(spec.get('cost_usd'), 'cost_usd')
    if ledger and ledger['cost_usd'] is not None:
        cost = {'value': ledger['cost_usd'], 'source': 'ledger+prices', 'unpriced_rows': ledger['unpriced_rows']}
    elif cost_reported is not None:
        cost = {'value': cost_reported, 'source': spec.get('cost_source') or 'reported'}
    else:
        cost = {'value': None, 'source': None}
    duration = number(spec.get('duration_ms'), 'duration_ms')
    duration_source = spec.get('duration_source') or ('reported' if duration is not None else None)
    started, ended = number(spec.get('started_at'), 'started_at'), number(spec.get('ended_at'), 'ended_at')
    if duration is None and started is not None:
        duration = round(((ended if ended is not None else time.time()) - started) * 1000, 2)
        duration_source = spec.get('duration_source') or 'started_at'
    git = spec.get('git')
    if git is None and root and spec.get('collect_git', True):
        git = git_info(root)
    tests = []
    for item in spec.get('tests_executed') or ():
        tests.append(item)
    for item in spec.get('tests') or ():
        tests.append(reported_test(item))
    ci_run, artifacts = clean_url(spec.get('ci_run_url')), [clean_url(x) for x in spec.get('ci_artifact_urls') or () if x]
    ci = {'run_url': ci_run, 'artifact_urls': artifacts, 'runs': spec.get('ci_runs'),
          'source': spec.get('ci_source') or ('reported' if ci_run or artifacts else None)}
    now = time.time()
    record = {
        'id': 'ev-' + uuid.uuid4().hex, 'at': round(now, 3),
        'at_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
        'kind': kind, 'task_id': clean(spec.get('task_id'), 120), 'session_id': clean(spec.get('session_id'), 120),
        'agent': clean(spec.get('agent'), 80), 'status': clean(spec.get('status'), 40),
        'exit_code': spec.get('exit_code') if isinstance(spec.get('exit_code'), int) and not isinstance(spec.get('exit_code'), bool) else None,
        'root': root, 'git': git,
        'model': {'platform': platform, 'provider': provider, 'provider_source': provider_source,
                  'model': model, 'model_source': model_source,
                  'reasoning': clean(spec.get('reasoning'), 40), 'reasoning_source': 'reported' if spec.get('reasoning') else None},
        'tokens': tokens,
        'tokens_reported': reported if tokens['source'] == 'ledger' and any(v is not None for v in reported.values()) else None,
        'ledger': ledger, 'transcripts': transcripts,
        'cost_usd': cost, 'duration_ms': {'value': duration, 'source': duration_source},
        'tests': tests, 'ci': ci, 'note': clean(spec.get('note'), 2000), 'origin': clean(spec.get('origin'), 80),
    }
    record['missing'] = [name for name, empty in (
        ('task_id', not record['task_id']), ('root', not root), ('git.commit', not (git or {}).get('commit')),
        ('model', not model), ('tokens', tokens['source'] is None), ('cost_usd', cost['value'] is None),
        ('duration_ms', duration is None), ('tests', not tests), ('ci', not (ci_run or artifacts or spec.get('ci_runs'))),
    ) if empty]
    return record


def record(spec, state_dir=STATE):
    return append(build(spec, state_dir), state_dir)


def find(state_dir, ref):
    for row in read_records(state_dir):
        if row.get('id') == ref or str(row.get('seq')) == str(ref):
            return row
    return None


def brief(row):
    tests = row.get('tests') or []
    return {'seq': row.get('seq'), 'id': row.get('id'), 'at': row.get('at_iso'), 'kind': row.get('kind'),
            'task_id': row.get('task_id'), 'status': row.get('status'),
            'model': (row.get('model') or {}).get('model'), 'platform': (row.get('model') or {}).get('platform'),
            'commit': ((row.get('git') or {}).get('commit') or '')[:12] or None, 'dirty': (row.get('git') or {}).get('dirty'),
            'input_tokens': (row.get('tokens') or {}).get('input_tokens'), 'output_tokens': (row.get('tokens') or {}).get('output_tokens'),
            'tokens_source': (row.get('tokens') or {}).get('source'),
            'cost_usd': (row.get('cost_usd') or {}).get('value'), 'duration_ms': (row.get('duration_ms') or {}).get('value'),
            'tests': [{'command': t.get('command'), 'exit_code': t.get('exit_code'), 'passed': t.get('passed'), 'failed': t.get('failed')} for t in tests],
            'missing': row.get('missing')}


def summary(state_dir=STATE, rows=None):
    """Totals over records; ledger rows referenced by several records count once."""
    rows = read_records(state_dir) if rows is None else rows
    ids = []
    for row in rows:
        ids += (row.get('ledger') or {}).get('ids') or []
    resolved = ledger_summary(ids, state_dir) if ids else None
    return {'records': len(rows), 'ledger_refs_unique': len(set(ids)), 'ledger_refs_total': len(ids),
            'ledger': {k: v for k, v in (resolved or {}).items() if k not in ('ids', 'missing')} or None,
            'records_without_ledger_tokens': sum((r.get('tokens') or {}).get('source') != 'ledger' for r in rows),
            'note': '金额与 tokens 只按去重后的账本行汇总；证据本身不计费。'}


# ---------------------------------------------------------------- hooks (fail-open)

def _warn(where, exc):
    try:
        print('证据记录失败（不影响任务）：' + where + ' ' + type(exc).__name__ + ' ' + clean(str(exc), 200), file=sys.stderr)
    except Exception:
        pass


def record_gate_task(state, state_dir=STATE):
    """Evidence for a dispatched gate_run task (task registry JSON)."""
    try:
        turns = state.get('turns') or []
        ids = [state.get('accounting_id')] + [t.get('ledger_id') for t in turns if isinstance(t, dict)]
        usage = state.get('usage') or {}
        spec = {'kind': 'gate_run', 'origin': 'gate_run', 'task_id': state.get('task_id'), 'session_id': state.get('session_id'),
                'agent': state.get('agent_id'), 'root': state.get('root'), 'platform': state.get('platform'),
                'model': state.get('requested_model'), 'model_source': 'task.requested_model' if state.get('requested_model') else None,
                'reasoning': state.get('reasoning_effort'), 'status': state.get('status'), 'exit_code': state.get('exit_code'),
                'started_at': state.get('started_at'), 'ended_at': state.get('ended_at'), 'duration_source': 'task',
                'ledger_ids': [i for i in ids if i],
                'tokens': {'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
                           'cached_input_tokens': usage.get('cached_input_tokens'),
                           'cache_creation_tokens': usage.get('cache_creation_input_tokens')},
                'tokens_source': 'task.usage(native_client)',
                'note': 'gate_run 不运行测试；需要测试证据时由 agent 用 evidence.py record --task-id 追加。'}
        return record(spec, state_dir)
    except Exception as exc:
        _warn('gate_run', exc)
        return None


def _usage_tokens(usage):
    usage = usage if isinstance(usage, dict) else {}
    return {'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
            'cached_input_tokens': usage.get('cached_input_tokens'), 'cache_creation_tokens': usage.get('cache_write_input_tokens')}


def record_center_task(data, usage=None, checks=None, state_dir=STATE):
    """Evidence for a 任务中心 task after its worker wrote the final state."""
    try:
        tests = []
        for check in data.get('validation') or ():
            if check.get('name') != 'tests':
                continue
            counts = parse_test_output(check.get('output'))
            tests.append({'command': ' '.join((checks or {}).get('tests') or ['tests']), 'exit_code': check.get('exit_code'),
                          'source': 'center_task_check', **{k: counts.get(k) for k in ('total', 'passed', 'failed', 'errors', 'skipped', 'summary')}})
        platform = data.get('platform')
        session = data.get('session_id')
        spec = {'kind': 'center_task', 'origin': 'control_center', 'task_id': data.get('task_id'), 'session_id': session,
                'root': data.get('root'), 'platform': platform,
                'model': data.get('actual_model') or data.get('model'),
                'model_source': 'native_event' if data.get('actual_model') else 'task.model',
                'reasoning': data.get('reasoning'), 'status': data.get('status'), 'exit_code': data.get('exit_code'),
                'started_at': data.get('started_at'), 'ended_at': data.get('ended_at'), 'duration_source': 'task',
                'transcripts': session_transcripts(platform, session),
                'since': (data.get('started_at') or 0) - 60, 'until': (data.get('ended_at') or time.time()) + 60,
                'tokens': _usage_tokens(usage), 'tokens_source': 'native_task_log',
                'cost_usd': (usage or {}).get('reported_usd'), 'cost_source': 'native_task_log',
                'tests_executed': tests}
        return record(spec, state_dir)
    except Exception as exc:
        _warn('center_task', exc)
        return None


def record_group_job(state_dir, job, member, status, started_at, usage=None):
    """Evidence for one 群聊 member turn (native run only)."""
    try:
        platform, session = member.get('platform'), member.get('session')
        paths = session_transcripts(platform, session)
        native = member.get('native_path')
        if native and Path(native).is_file() and Path(native).resolve().is_relative_to((Path.home() / '.codex').resolve()):
            paths = sorted(set(paths) | {Path(native)})
        spec = {'kind': 'group_job', 'origin': 'group_chat', 'task_id': job.get('id'), 'session_id': session,
                'agent': member.get('slug'), 'root': member.get('root'), 'platform': platform,
                'model': member.get('actual_model') or member.get('model'),
                'model_source': 'native_event' if member.get('actual_model') else 'member.model',
                'reasoning': member.get('effort'), 'status': status, 'started_at': started_at, 'ended_at': time.time(),
                'duration_source': 'group_worker', 'transcripts': paths, 'since': started_at - 60, 'until': time.time() + 60,
                'tokens': _usage_tokens(usage), 'tokens_source': (usage or {}).get('source') or 'native_event',
                'cost_usd': (usage or {}).get('reported_usd'), 'cost_source': 'native_event'}
        return record(spec, state_dir)
    except Exception as exc:
        _warn('group_job', exc)
        return None


# ---------------------------------------------------------------- HTTP (gate_service)

HTTP_FIELDS = ('kind', 'task_id', 'session_id', 'agent', 'root', 'platform', 'provider', 'model', 'reasoning', 'status',
               'exit_code', 'ledger_ids', 'tokens', 'cost_usd', 'duration_ms', 'started_at', 'ended_at', 'tests',
               'ci_run_url', 'ci_artifact_urls', 'note')


def http_record(body, roots, state_dir=STATE):
    """POST /v1/evidence: reported values only. Never runs commands; the root
    must be inside the service's allowed roots (git is read there)."""
    if not isinstance(body, dict):
        raise ValueError('body 必须是对象')
    unknown = set(body) - set(HTTP_FIELDS) - {'claude_session', 'codex_session', 'since', 'until'}
    if unknown:
        raise ValueError('未知字段：' + ','.join(sorted(unknown))[:200])
    spec = {k: body.get(k) for k in HTTP_FIELDS if k in body}
    if spec.get('kind') not in (None, 'external'):
        raise ValueError('接口只接受 kind=external')
    if spec.get('root'):
        root = Path(str(spec['root'])).expanduser().resolve()
        if not any(root == r or root.is_relative_to(r) for r in roots):
            raise ValueError('root 不在服务允许的项目范围内')
        spec['root'] = str(root)
    for key in ('ledger_ids', 'tests', 'ci_artifact_urls'):
        if key in spec and not isinstance(spec[key], list):
            raise ValueError(key + ' 必须是数组')
    if 'tokens' in spec and not isinstance(spec['tokens'], dict):
        raise ValueError('tokens 必须是对象')
    paths = []
    if body.get('claude_session'):
        paths += session_transcripts('claude', body['claude_session'])
    if body.get('codex_session'):
        paths += session_transcripts('codex', body['codex_session'])
    if paths:
        spec.update(transcripts=paths, since=number(body.get('since'), 'since'), until=number(body.get('until'), 'until'))
    spec['origin'] = 'http'
    stored = record(spec, state_dir)
    return {'id': stored['id'], 'seq': stored['seq'], 'hash': stored['hash'], 'missing': stored['missing']}


def http_get(path, state_dir=STATE):
    parts = urllib.parse.urlsplit(path)
    query = urllib.parse.parse_qs(parts.query)
    if parts.path == '/v1/evidence/verify':
        return verify(state_dir)
    if parts.path == '/v1/evidence':
        rows = read_records(state_dir)
        task = (query.get('task_id') or [None])[0]
        if task:
            rows = [r for r in rows if r.get('task_id') == task]
        try:
            limit = max(1, min(500, int((query.get('limit') or ['50'])[0])))
        except ValueError:
            raise ValueError('limit 无效')
        return {'records': [brief(r) for r in rows[-limit:]][::-1], 'summary': summary(state_dir, rows)}
    return None


# ---------------------------------------------------------------- CLI

def _epoch(value):
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    import datetime
    stamp = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp.timestamp()


def _gate_task(ref, state_dir):
    path = Path(ref).expanduser()
    if not path.is_file():
        if not re.fullmatch(r'[0-9a-f-]{36}', ref):
            raise ValueError('--from-task 需要任务编号或任务 JSON 路径')
        path = Path(state_dir).expanduser() / 'gate-tasks' / (ref + '.json')
    return json.loads(path.read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description='Context Gate 证据记录（append-only，哈希链）')
    parser.add_argument('--state-dir', default=str(STATE))
    sub = parser.add_subparsers(dest='command', required=True)
    rec = sub.add_parser('record', help='追加一条证据')
    rec.add_argument('--task-id', '--task')
    rec.add_argument('--session-id')
    rec.add_argument('--agent')
    rec.add_argument('--kind', choices=KINDS, help='默认 external；带 --from-task 时默认 gate_run')
    rec.add_argument('--root', default=os.getcwd())
    rec.add_argument('--no-git', action='store_true')
    rec.add_argument('--platform')
    rec.add_argument('--provider')
    rec.add_argument('--model')
    rec.add_argument('--reasoning')
    rec.add_argument('--status')
    rec.add_argument('--exit-code', type=int)
    rec.add_argument('--from-task', help='gate_run 任务编号或任务 JSON：自动带入任务/模型/账本行')
    rec.add_argument('--ledger-id', action='append', default=[])
    rec.add_argument('--transcript', action='append', default=[], help='Claude/Codex 原生转录文件')
    rec.add_argument('--claude-session')
    rec.add_argument('--codex-session')
    rec.add_argument('--since', help='转录时间窗起点（epoch 或 ISO）')
    rec.add_argument('--until')
    for name in ('input', 'output', 'cached', 'cache-creation'):
        rec.add_argument('--' + name + '-tokens', type=int)
    rec.add_argument('--cost-usd', type=float)
    rec.add_argument('--duration-ms', type=float)
    rec.add_argument('--started-at', help='任务开始时间（epoch 或 ISO），用于计算耗时')
    rec.add_argument('--tests', '--run-test', dest='run_tests', action='append', default=[],
                     help='在 root 下直接执行（不经 shell）并记录退出码和通过/失败数')
    rec.add_argument('--test-timeout', type=int, default=1800)
    rec.add_argument('--test-cmd', help='已执行过的测试命令（只上报结果，不执行）')
    rec.add_argument('--test-exit', type=int)
    for name in ('total', 'passed', 'failed', 'errors', 'skipped'):
        rec.add_argument('--test-' + name, type=int)
    rec.add_argument('--ci-run')
    rec.add_argument('--ci-artifact', action='append', default=[])
    rec.add_argument('--ci-from-gh', action='store_true', help='用本机 gh 查询该 commit 的 Actions runs')
    rec.add_argument('--note')
    ver = sub.add_parser('verify', help='校验哈希链')
    ver.add_argument('--expect-head')
    rep = sub.add_parser('repair-head', help='verify 通过后重写 head（只改 head 文件）')
    rep.add_argument('--expect-count', type=int, required=True)
    rep.add_argument('--expect-last', required=True)
    lst = sub.add_parser('list', help='列出证据')
    lst.add_argument('--task-id')
    lst.add_argument('--limit', type=int, default=20)
    lst.add_argument('--summary', action='store_true')
    shw = sub.add_parser('show', help='查看一条完整证据')
    shw.add_argument('ref', help='证据 id 或 seq')
    shw.add_argument('--resolve', action='store_true', help='按账本当前状态重新汇总引用（不改文件）')
    a = parser.parse_args(argv)
    state = Path(a.state_dir).expanduser()
    try:
        if a.command == 'verify':
            result = verify(state, a.expect_head)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['ok'] else 1
        if a.command == 'repair-head':
            try:
                result = repair_head(state, a.expect_count, a.expect_last)
            except EvidenceHeadMismatch as exc:
                print('head 修复拒绝：' + clean(str(exc), 300), file=sys.stderr)
                return 2
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if a.command == 'list':
            rows = read_records(state)
            if a.task_id:
                rows = [r for r in rows if r.get('task_id') == a.task_id]
            out = {'records': [brief(r) for r in rows[-max(1, a.limit):]][::-1]}
            if a.summary:
                out['summary'] = summary(state, rows)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        if a.command == 'show':
            row = find(state, a.ref)
            if row is None:
                print('找不到证据：' + a.ref, file=sys.stderr)
                return 1
            if a.resolve:
                row = dict(row, ledger_now=ledger_summary((row.get('ledger') or {}).get('ids'), state))
            print(json.dumps(row, ensure_ascii=False, indent=2))
            return 0
        spec = {}
        if a.from_task:
            task = _gate_task(a.from_task, state)
            usage = task.get('usage') or {}
            spec.update(task_id=task.get('task_id'), root=task.get('root'), platform=task.get('platform'),
                        model=task.get('requested_model'), reasoning=task.get('reasoning_effort'),
                        status=task.get('status'), exit_code=task.get('exit_code'),
                        started_at=task.get('started_at'), ended_at=task.get('ended_at'), duration_source='task',
                        ledger_ids=[i for i in [task.get('accounting_id')] + [t.get('ledger_id') for t in task.get('turns') or [] if isinstance(t, dict)] if i],
                        tokens={'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
                                'cached_input_tokens': usage.get('cached_input_tokens'),
                                'cache_creation_tokens': usage.get('cache_creation_input_tokens')},
                        tokens_source='task.usage(native_client)')
        explicit = {'task_id': a.task_id, 'session_id': a.session_id, 'agent': a.agent, 'platform': a.platform,
                    'provider': a.provider, 'model': a.model, 'reasoning': a.reasoning, 'status': a.status,
                    'exit_code': a.exit_code, 'cost_usd': a.cost_usd, 'duration_ms': a.duration_ms, 'note': a.note,
                    'started_at': _epoch(a.started_at), 'ci_run_url': a.ci_run}
        spec.update({k: v for k, v in explicit.items() if v is not None})
        if a.model:
            spec['model_source'] = 'reported'
        if a.started_at:
            spec['ended_at'] = None
            spec['duration_source'] = 'started_at'
        if not a.from_task or a.root != os.getcwd():
            spec['root'] = a.root
        spec['kind'] = a.kind or ('gate_run' if a.from_task else 'external')
        spec['collect_git'] = not a.no_git
        spec['ledger_ids'] = (spec.get('ledger_ids') or []) + a.ledger_id
        reported = {'input_tokens': a.input_tokens, 'output_tokens': a.output_tokens,
                    'cached_input_tokens': a.cached_tokens, 'cache_creation_tokens': a.cache_creation_tokens}
        if any(v is not None for v in reported.values()):
            spec['tokens'], spec['tokens_source'] = reported, 'reported'
        paths = list(a.transcript)
        if a.claude_session:
            paths += session_transcripts('claude', a.claude_session)
        if a.codex_session:
            paths += session_transcripts('codex', a.codex_session)
        if paths:
            spec.update(transcripts=paths, since=_epoch(a.since), until=_epoch(a.until))
        root = Path(spec['root']).expanduser().resolve() if spec.get('root') else None
        spec['tests_executed'] = [run_test(cmd, root, a.test_timeout) for cmd in a.run_tests]
        if a.test_cmd:
            spec['tests'] = [{'command': a.test_cmd, 'exit_code': a.test_exit, 'total': a.test_total, 'passed': a.test_passed,
                              'failed': a.test_failed, 'errors': a.test_errors, 'skipped': a.test_skipped}]
        spec['ci_artifact_urls'] = a.ci_artifact
        spec['origin'] = 'cli'
        record_fields = build(spec, state)
        if a.ci_from_gh and (record_fields.get('git') or {}).get('commit'):
            runs = gh_runs(root, record_fields['git']['commit'])
            record_fields['ci']['runs'] = runs
            if runs:
                record_fields['ci']['source'] = 'gh'
                if 'ci' in record_fields['missing']:
                    record_fields['missing'].remove('ci')
        stored = append(record_fields, state)
        print(json.dumps({'id': stored['id'], 'seq': stored['seq'], 'hash': stored['hash'], 'missing': stored['missing'],
                          'tokens': stored['tokens'], 'cost_usd': stored['cost_usd'], 'tests': stored['tests'],
                          'git': stored['git']}, ensure_ascii=False, indent=2))
        return 0
    except (EvidenceError, ValueError, OSError) as exc:
        print('证据错误：' + clean(str(exc), 300), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
