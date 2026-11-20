"""Same-origin, read-only bridge to an optional local MemoryOS Galaxy component."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading

_busy = threading.Lock()
MAX_BYTES = 32_000_000


def default_root():
    env = os.environ.get('MEMORY_OS_DIR')
    if env:
        return Path(env).expanduser()
    return Path.home() / 'Library/Application Support/MemoryOS'


ROOT = default_root()


def validate(command, args):
    if (command not in ('snapshot', 'detail', 'search') or not isinstance(args, list)
            or len(args) != (0 if command == 'snapshot' else 1)):
        raise ValueError('无效的星云读取请求。')
    if any(not isinstance(arg, str) or len(arg.encode('utf-8')) > 4096 for arg in args):
        raise ValueError('星云查询过长。')


def resources(runtime=None):
    runtime = Path(runtime) if runtime is not None else default_root()
    candidates = []
    override = os.environ.get('MEMORY_OS_GALAXY_DIR')
    if override:
        candidates.append(Path(override).expanduser())
    candidates.extend([
        runtime / 'GalaxyResources',
        Path('/Applications/MemoryOS.app/Contents/Resources'),
    ])
    required = ('galaxy.html', 'galaxy.py', 'galaxy_reading.py')
    for root in candidates:
        if all((root / name).is_file() for name in required):
            return root
    raise ValueError('本机未安装或未配置 MemoryOS 星云可选组件（见 docs/LOCAL_INTERFACES.md）。')


def page(runtime=None):
    html = (resources(runtime) / 'galaxy.html').read_text(encoding='utf-8')
    start = html.index('function send(command,args,done)')
    end = html.index('window.galaxyReply=', start)
    html = html[:start] + """function send(command,args,done){fetch('galaxy-data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command,args})}).then(async response=>{const result=await response.json();done(result)}).catch(()=>done({error:'unavailable',message:'星云读取失败，请重新读取。'}));}
window.cgHostActive=false;
window.addEventListener('message',e=>{if(e.source!==parent||e.origin!==location.origin||e.data?.type!=='cg-galaxy-active')return;window.cgHostActive=e.data.active===true;ambientFocused=window.cgHostActive;syncAmbientMotion()});
""" + html[end:]
    html = html.replace("connect-src 'none'", "connect-src 'self'")
    # WebKit can suspend requestAnimationFrame in an occluded native window.
    # Paint the first complete snapshot immediately after layout has been built.
    html = html.replace('scene.clear();fit(false)});}', 'scene.clear();fit(false);settleScene()});}', 1)
    html = html.replace('return ambientEnabled&&!reducedMotion.matches&&ambientFocused&&!document.hidden',
                        'return window.cgHostActive!==false&&ambientEnabled&&!reducedMotion.matches&&ambientFocused&&!document.hidden')
    html = html.replace('</style>', '.library-brand{display:none}#librarySidebar{background:#19172bd9;border-color:#8d75bb33}.library-tabs{padding-top:16px}:root{--sidebar:240px}\n</style>', 1)
    return html


def query_local(runtime, command, args):
    root = resources(runtime)
    argv = [str(runtime / 'venv/bin/python'), '-B', '-c',
            "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')",
            str(runtime / 'src'), str(root / 'galaxy.py')]
    if command != 'snapshot':
        # The argument is data even when it starts with a dash.
        argv.append('--' + command + '=' + args[0])
    return run_query(argv)


def run_query(argv, request=None):
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(argv, input=request, stdout=output, stderr=subprocess.DEVNULL, timeout=65)
        if result.returncode or not 0 < output.tell() <= MAX_BYTES:
            raise ValueError('invalid Galaxy output')
        output.seek(0)
        return output.read()


def read(runtime, command, args):
    validate(command, args)
    runtime = Path(runtime) if runtime is not None else default_root()
    if not _busy.acquire(blocking=False):
        return json.dumps({'error': 'busy', 'message': '正在读取，请稍后重试。'}, ensure_ascii=False).encode()
    try:
        return query_local(runtime, command, args)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ValueError('星云读取失败，请检查可选的 MemoryOS 本地服务配置。') from exc
    finally:
        _busy.release()
