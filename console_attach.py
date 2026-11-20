"""Group chat attachments chosen by the owner.

Files are saved inside the group's project folder, because every member CLI
(claude / codex / zcode) runs with that folder as its workspace and can read it.
"""
from pathlib import Path
import base64
import binascii
import os
import re
import subprocess
import time
import uuid

from context_gate import SECRET_NAMES

LIMIT = 8 * 1024 * 1024
FOLDER = '.context-gate-attachments'


PICK = ('set out to ""', 'tell me to activate',
        'repeat with f in (choose file with prompt "选择要附加的图片或文件" with multiple selections allowed)',
        'set out to out & POSIX path of f & linefeed', 'end repeat', 'out')


def _root(groups, gid):
    with groups.connect() as db:
        return Path(groups.group(db, gid)['root']).resolve()


def _store(root, gid, name, raw):
    safe = re.sub(r'[^\w.\-]+', '_', Path(name.replace('\\', '/')).name).lstrip('.')[-80:]
    if not safe:
        raise ValueError('附件名称无效')
    if SECRET_NAMES.search(safe):
        raise ValueError('文件名含敏感字样（密钥/凭据等），不允许附加')
    if not raw or len(raw) > LIMIT:
        raise ValueError('附件每份需在1字节至8MB之间')
    folder = root / FOLDER / gid[:8]
    # A symlinked attachment folder must not redirect writes outside the project.
    if folder.parent.is_symlink() or folder.is_symlink():
        raise ValueError('附件目录不在项目内，已拒绝写入')
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not folder.resolve().is_relative_to(root):
        raise ValueError('附件目录不在项目内，已拒绝写入')
    target = folder / ('%s-%s-%s' % (time.strftime('%Y%m%d-%H%M%S'), uuid.uuid4().hex[:6], safe))
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
    return {'path': str(target), 'name': safe, 'size': len(raw)}


def save(groups, body):
    gid, name, encoded = body.get('group'), body.get('name'), body.get('data')
    root = _root(groups, gid)
    if not isinstance(name, str) or not isinstance(encoded, str):
        raise ValueError('附件无效')
    if len(encoded) > ((LIMIT + 2) // 3) * 4:
        raise ValueError('附件每份最多8MB')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError('附件内容无效') from error
    return _store(root, gid, name, raw)


def pick(groups, body):
    """Owner picks files in the system dialog (the native shell has no web file chooser)."""
    gid = body.get('group')
    root = _root(groups, gid)
    try:
        done = subprocess.run(['/usr/bin/osascript'] + [x for line in PICK for x in ('-e', line)],
                              capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise ValueError('选择文件超时，请重试')
    if done.returncode:
        if '-128' in done.stderr:
            return {'files': [], 'errors': [], 'cancelled': True}
        raise ValueError('没能打开文件选择框，请把文件拖进输入框')
    files, errors = [], []
    for line in done.stdout.splitlines()[:20]:
        source = Path(line)
        try:
            if not source.is_file() or source.stat().st_size > LIMIT:
                raise ValueError('附件每份需在1字节至8MB之间')
            files.append(_store(root, gid, source.name, source.read_bytes()))
        except (ValueError, OSError) as error:
            errors.append('%s：%s' % (source.name, error if isinstance(error, ValueError) else '读取失败'))
    return {'files': files, 'errors': errors}
