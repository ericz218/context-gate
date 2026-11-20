"""Public project state from the shared Memory OS; no legacy fallbacks."""
import json
import fcntl
import io
import ipaddress
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

_lock = threading.Lock()
_cache = {'rows': [], 'error': '正在读取共享 Memory OS', 'at': 0}
_pending = False
# Only these four project fields are shown in the workbench card.
STATE_FIELDS = ('current_project_status', 'next_steps', 'preferred_language', 'package_manager')
# The catalog grows with the memory base (~1.5 KB per entry); the guard only exists to stop a
# corrupt or runaway file from being parsed, never to cap real growth.
CATALOG_LIMIT = 64 * 1024 * 1024


class CatalogTooLarge(ValueError):
    """The catalog is bigger than the read guard, not malformed."""


def _catalog_limit():
    raw = os.environ.get('MEMORY_OS_CATALOG_MAX_BYTES')
    try:
        value = int(raw) if raw else CATALOG_LIMIT
    except ValueError:
        return CATALOG_LIMIT
    return value if value >= 1024 * 1024 else CATALOG_LIMIT


def _default_memory_root():
    override = os.environ.get('MEMORY_OS_DIR')
    if override:
        return Path(override).expanduser()
    return Path.home()/'Library/Application Support/MemoryOS'


def _loopback_client():
    """(url, token) of an optional local Memory OS HTTP API, or (None, None) when not configured.
    Re-read every refresh: the service is long-lived and may rotate its client file."""
    url = os.environ.get('MEMORY_OS_HTTP_URL')
    token = os.environ.get('MEMORY_OS_API_TOKEN')
    if not (isinstance(url, str) and isinstance(token, str) and url and token):
        try:
            data = json.loads((_default_memory_root()/'client.json').read_text())
        except (OSError, ValueError):
            return None, None
        url, token = data.get('MEMORY_OS_HTTP_URL'), data.get('MEMORY_OS_API_TOKEN')
    if not isinstance(url, str) or not isinstance(token, str) or not url or not token:
        return None, None
    parsed = urllib.parse.urlparse(url)
    try:
        local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        local = False
    if not local or parsed.scheme not in ('http', 'https'):
        return None, None
    return url.rstrip('/'), token


def _project_values(pid, url, token, opener):
    """(values, reachable) for one project scope, straight from /v1/state.
    Bootstrap stopped carrying project:* keys, so each field must be asked for by scope_id."""
    values = {}
    reachable = True
    for field in STATE_FIELDS:
        query = urllib.parse.urlencode({'key': field, 'scope': 'project', 'scope_id': pid})
        request = urllib.request.Request(url + '/v1/state?' + query, headers={'Authorization': 'Bearer ' + token})
        try:
            with opener.open(request, timeout=5) as response:
                item = json.loads(response.read(1 << 20))
        except urllib.error.HTTPError:
            continue
        except (OSError, ValueError):
            reachable = False
            continue
        ir = item.get('ir') if isinstance(item, dict) else None
        value = ir.get('value') if isinstance(ir, dict) else None
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else ''
        if value.strip():
            values[field] = value
    return values, reachable


def project_rows():
    global _pending
    with _lock:
        if not _pending and time.time() - _cache['at'] > 60:
            _pending = True
            threading.Thread(target=_refresh, daemon=True).start()
        return dict(_cache)


def _refresh():
    global _pending
    rows = []
    error = None
    try:
        cli = os.environ.get('MEMORY_OS_CLI') or str(Path.home()/'.local/bin/memory-os')
        result = subprocess.run([cli, 'context',
                                 '--query', '__bootstrap__', '--max-bytes', '262144'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError('Memory OS 接口读取失败')
        data = json.loads(result.stdout)
        if not isinstance(data.get('state'), dict):
            raise RuntimeError('Memory OS 返回缺少当前状态')
        # Bootstrap only indexes projects now; the card fields live in each project's own scope.
        index = data.get('projects') if isinstance(data.get('projects'), list) else []
        roots = [entry['project_id'] for entry in index
                 if isinstance(entry, dict) and isinstance(entry.get('project_id'), str) and entry['project_id']]
        url, token = _loopback_client()
        if roots and not url:
            error = '共享 Memory OS 接口未配置，项目进度无法读取'
        elif roots:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            unreachable = 0
            for root in roots:
                values, reachable = _project_values(root, url, token, opener)
                unreachable += 0 if reachable else 1
                if not values:
                    continue
                rows.append({'project': Path(root).name, 'root': root, 'status': '共享 Memory OS 当前状态',
                             'handoff': '', 'updated': time.strftime('%Y-%m-%d %H:%M'), 'done': '',
                             'state_text': values.get('current_project_status', '尚未保存项目进度'),
                             'next': values.get('next_steps', ''), 'doing': False,
                             'source': 'Memory OS', 'values': values})
            if unreachable:
                error = ('共享 Memory OS 当前状态读取失败' if unreachable == len(roots)
                         else '部分项目状态读取失败，显示的是已读到的项目')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        error = '共享 Memory OS 不可用：' + type(exc).__name__
    with _lock:
        _cache.update(rows=rows, error=error, at=time.time())
        _pending = False


def human_docs_dir(root=None):
    """Folder for optional MemoryOS human-readable documents."""
    override = os.environ.get('MEMORY_OS_HUMAN_DIR')
    if override: return Path(override).expanduser()
    root = Path(root) if root is not None else _default_memory_root()
    private = root/'ReaderDocuments'
    if private.is_dir():
        return private
    fallback = Path.home()/'Documents/AI记忆-人话版'
    try:
        if fallback.is_dir():
            return fallback
    except PermissionError:
        return fallback
    return private


class MemoryLibrary:
    """Read an optional local human-readable memory snapshot; run only the fixed sync script."""
    def __init__(self, out=None, root=None):
        self.root = Path(root) if root is not None else _default_memory_root()
        self.out = Path(out) if out is not None else human_docs_dir(self.root)
        self.lock = threading.RLock()
        self.catalog = None
        self.stamp = None
        self.process = None
        self.sync_state = {'status': 'idle', 'message': ''}

    def access_status(self):
        """Test the same file the reader uses without parsing or returning the catalog."""
        try:
            with (self.out/'catalog.json').open('rb') as catalog:
                catalog.read(1)
        except PermissionError:
            return 'denied'
        except FileNotFoundError:
            return 'missing'
        except OSError:
            return 'unavailable'
        return 'readable'

    def export(self, kind):
        """Make exports on demand from stable local files, without model calls."""
        if kind not in ('txt', 'md', 'human', 'raw'):
            raise ValueError('请选择全文 TXT、全文 Markdown、人话版 ZIP 或原始版 ZIP。')
        with self.lock:
            if not self.out.is_dir():
                raise ValueError('文档尚未生成，请先同步记忆。')
            # Same lock as the scheduled and manual sync process; do not mix editions.
            with (self.root/'humanize_sync.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('记忆正在同步，请等同步完成后再导出。')
                files = self._export_files(kind)
                contents = []
                size = 0
                for path in files:
                    before = path.lstat()
                    if stat.S_ISDIR(before.st_mode):
                        contents.append((path.relative_to(self.out).as_posix()+'/', b''))
                        continue
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError('导出目录包含链接或特殊文件，请检查文档文件夹。')
                    size += before.st_size
                    if size > 128 * 1024 * 1024:
                        raise ValueError('文档超过导出范围，未裁剪内容。请从文档文件夹复制。')
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(fd, 'rb') as handle:
                        contents.append((path.relative_to(self.out).as_posix(), handle.read(128 * 1024 * 1024 + 1)))
                        after = os.fstat(handle.fileno())
                    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                        raise ValueError('文档在导出时发生变化，请重试。')
                if files != self._export_files(kind):
                    raise ValueError('文档目录在导出时发生变化，请重试。')
                for path, (_, content) in zip(files, contents):
                    if not path.is_dir() and path.read_bytes() != content:
                        raise ValueError('文档在导出时发生变化，请重试。')
                if kind in ('human', 'raw'):
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                        for name, content in contents:
                            archive.writestr('AI记忆-'+('人话版' if kind == 'human' else '原始版')+'/'+name, content)
                    data = buffer.getvalue()
                    label, suffix = ('人话版' if kind == 'human' else '原始版'), 'zip'
                else:
                    parts = ['# 全部记忆\n\n本文件合并本地全部阅读文档，最后附完整原始快照（含归档或到期记录）。']
                    for name, content in contents:
                        if name.endswith('.md'):
                            text = content.decode('utf-8')
                            if kind == 'txt':
                                text = re.sub(r'^#{1,6} +', '', text, flags=re.M)
                                text = re.sub(r'^<details><summary>(.*?)</summary>$', r'\1', text, flags=re.M)
                                text = re.sub(r'^(?:</details>|```(?:json)?)\s*$', '', text, flags=re.M)
                            parts.append(('## 来源文件：' if kind == 'md' else '来源文件：')+name+'\n\n'+text)
                    raw = next(content for name, content in contents if name == '原始记录/当前快照.json')
                    parts.append(('## 完整原始快照\n\n```json\n' if kind == 'md' else '完整原始快照\n\n')+raw.decode('utf-8')+('\n```' if kind == 'md' else ''))
                    if kind == 'txt':
                        parts[0] = parts[0].lstrip('# ')
                    data = ('\n\n'.join(parts)+'\n').encode('utf-8')
                    label, suffix = '全文', kind
        folder = self.out/'导出'
        if folder.is_symlink():
            raise ValueError('导出文件夹不能是链接，请检查文档文件夹。')
        folder.mkdir(mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.export-', dir=folder)
        dest = folder/('记忆-'+label+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+Path(temporary).name[-8:]+'.'+suffix)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, dest)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return dest

    def _export_files(self, kind):
        roots = [self.out/'原始记录'] if kind == 'raw' else [self.out/'目录.md', self.out/'大纲.md', self.out/'详细', self.out/'历史生成', self.out/'原始记录', self.out/'catalog.json']
        files = []
        for root in roots:
            if root.name == '历史生成' and not root.exists():
                continue
            if root.is_symlink():
                raise ValueError('导出目录包含链接，请检查文档文件夹。')
            if not root.exists():
                raise ValueError('阅读文档不完整，请重新同步后导出。')
            paths = [root, *sorted(root.rglob('*'))] if root.is_dir() else [root]
            for path in paths:
                if any(part.startswith('.') for part in path.relative_to(self.out).parts):
                    continue
                if path.is_symlink():
                    raise ValueError('导出目录包含链接，请检查文档文件夹。')
                if path.is_file() or path.is_dir():
                    files.append(path)
                else:
                    raise ValueError('导出目录包含特殊文件，请检查文档文件夹。')
        if self.out/'原始记录/当前快照.json' not in files:
            raise ValueError('缺少完整原始快照，请重新同步后导出。')
        return files

    def snapshot(self, since=''):
        # 同一份原子快照只解析一次；后台刷新保留当前选择和已展开的原文。
        with self.lock:
            error = ''
            error_code = ''
            try:
                path = self.out/'catalog.json'
                stat = path.stat()
                stamp = (stat.st_mtime_ns, stat.st_size)
                if stamp != self.stamp:
                    limit = _catalog_limit()
                    if stat.st_size > limit:
                        raise CatalogTooLarge('记忆文档已增长到 %.1f MB，超过当前读取上限 %.0f MB（内容未截断）。设置环境变量 MEMORY_OS_CATALOG_MAX_BYTES 提高上限后重启控制台。'
                                              % (stat.st_size / 1048576, limit / 1048576))
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if (not isinstance(data, dict) or data.get('schema_version') != 2
                            or not isinstance(data.get('groups'), list)
                            or not isinstance(data.get('generated_at'), str)):
                        raise ValueError('文档版本不匹配，请重新同步')
                    entries = [entry for group in data['groups'] for entry in group['entries']]
                    if data.get('total') != len(entries) or len({entry['id'] for entry in entries}) != len(entries):
                        raise ValueError('文档条目不完整，请重新同步')
                    self.catalog = data
                    self.stamp = stamp
            except FileNotFoundError:
                error = '还没有生成完整阅读文档，请点击“同步记忆”。'
            except CatalogTooLarge as exc:
                error = str(exc)
                if self.catalog is not None:
                    error += '已保留上次内容。'
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, PermissionError):
                    error_code = 'permission_denied'
                    error = '无法读取记忆文档。请检查 macOS「隐私与安全性 → 文件与文件夹」里的控制台文稿访问权限。'
                elif isinstance(exc, OSError):
                    error = '记忆文档读取失败（系统错误 %s）。' % exc.errno
                else:
                    error = '记忆文档格式或完整性检查失败，请重新同步。'
                if self.catalog is not None:
                    error += '已保留上次内容。'
            # 遵循控制台的凭据脱敏规则，原始值仅在本地源文件完整保留。
            from console_search import public
            unchanged = self.catalog is not None and since == self.catalog['generated_at']
            return public({'catalog': None if unchanged else self.catalog,
                           'generated_at': self.catalog['generated_at'] if self.catalog else '',
                           'error': error, 'error_code': error_code, 'sync': dict(self.sync_state)})

    def sync(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return {'status': 'running', 'message': '同步正在进行，完成后自动更新。'}
            command = [str(self.root/'venv/bin/python'), str(self.root/'humanize_sync.py')]
            if self.out == self.root/'ReaderDocuments':
                command.append('--reader-only')
            try:
                self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                self.sync_state = {'status': 'error', 'message': '未检测到本地 Memory OS 可选服务（见 docs/LOCAL_INTERFACES.md）。'}
                return dict(self.sync_state)
            process = self.process
            self.sync_state = {'status': 'running', 'message': '正在读取记忆库，生成完整中文文档…'}
            threading.Thread(target=self._wait_sync, args=(process,), daemon=True).start()
            return dict(self.sync_state)

    def _wait_sync(self, process):
        code = process.wait()
        with self.lock:
            if self.process is not process:
                return
            if code == 0:
                self.sync_state = {'status': 'done', 'message': '同步完成，完整文档已更新。'}
            elif code == 75:
                self.sync_state = {'status': 'waiting', 'message': '另一处正在同步，完成后会自动更新。'}
            else:
                self.sync_state = {'status': 'error', 'message': '同步失败，上次完整内容已保留。请重试，或查看 MemoryOS 同步日志。'}
            self.process = None
