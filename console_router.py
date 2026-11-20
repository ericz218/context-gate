"""Console adapter to the router's authenticated in-process management bridge.

The Rust app remains the only owner of settings, SQLite writes, Keychain and
runtime key caches. The console never reads API credentials from the Keychain.
"""
from pathlib import Path
import json
import os
import stat
import re
import subprocess
import time
import urllib.error
import urllib.request

BEDROCK_RUNTIME = re.compile(r'^https://bedrock-runtime\.([a-z0-9-]+)\.amazonaws\.com(?:/|$)')

COMMANDS = frozenset(('snapshot', 'start_server', 'stop_server', 'restart_server', 'reconcile_backboard_usage',
    'upsert_provider', 'set_provider_base_quota_only', 'check_kiro_quotas',
    'delete_provider', 'test_provider_connection',
    'list_provider_keys', 'upsert_provider_key', 'delete_provider_key', 'reveal_provider_key',
    'upsert_model', 'delete_model', 'clear_logs', 'get_local_api_key',
    'regenerate_local_api_key', 'export_config', 'update_settings',
    'bedrock_sync_models', 'bedrock_sync_pricing', 'bedrock_sync_status',
    'list_bedrock_models', 'set_bedrock_model_enabled'))


def probe_url(base):
    """Models-list URL used to test a key. Bedrock's OpenAI-compatible host has no /models."""
    base = base.rstrip('/')
    match = BEDROCK_RUNTIME.match(base)
    if match:
        return 'https://bedrock.' + match.group(1) + '.amazonaws.com/foundation-models'
    return base + '/models'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        # Never forward local or provider credentials to a redirected endpoint.
        return None


class RouterManager:
    def __init__(self, connection_path=None):
        default = Path.home() / 'Library' / 'Application Support' / 'com.localmodelrouter.desktop' / 'console-bridge.json'
        self.connection_path = Path(connection_path or os.environ.get('LMR_CONSOLE_CONNECTION', default))
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def _connection(self):
        # Never follow a symlink or accept a connection file readable by others.
        fd = os.open(self.connection_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 4096:
                raise ValueError('模型路由连接文件权限无效，请重新打开 Local Model Router。')
            with os.fdopen(fd, 'rb', closefd=False) as file:
                data = json.loads(file.read(4097))
        finally:
            os.close(fd)
        if not isinstance(data, dict):
            raise ValueError('模型路由连接信息无效，请重新打开 Local Model Router。')
        port, token = data.get('port'), data.get('token')
        if data.get('version') != 1 or type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii() or not token.isalnum():
            raise ValueError('模型路由连接信息无效，请重新打开 Local Model Router。')
        return port, token

    def call(self, command, args=None):
        if not isinstance(command, str) or command not in COMMANDS:
            raise ValueError('未知的模型路由操作。')
        if args is not None and not isinstance(args, dict):
            raise ValueError('模型路由参数应为对象。')
        try:
            port, token = self._connection()
            payload = json.dumps({'command': command, 'args': args or {}}, ensure_ascii=False).encode()
            if len(payload) > 30000:
                raise ValueError('模型路由参数过长。')
            request = urllib.request.Request(f'http://127.0.0.1:{port}/call', data=payload,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST')
            try:
                response = self.http.open(request, timeout=50 if command == 'test_provider_connection' else 20)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError('模型路由返回超出窗口，未发送不完整数据。')
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError('模型路由返回格式无效。')
                if response.status != 200 or 'result' not in data:
                    # Bridge errors have already passed the router's scrubber.
                    raise ValueError(data.get('error') or '模型路由操作失败。')
                return data['result']
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError('模型路由尚未连接，请打开支持控制台集成的 Local Model Router。') from error

    def snapshot(self, period='all', provider='all'):
        if not isinstance(period, str) or period not in ('all', 'today', 'week', 'month'):
            raise ValueError('时间范围无效。')
        if not isinstance(provider, str) or not provider or len(provider.encode('utf-8')) > 200:
            raise ValueError('供应商筛选无效。')
        try:
            from console_router_quota import attach_quota_support
            selected = None if provider == 'all' else provider
            return attach_quota_support({'connected': True, **self.call('snapshot', {'period': period, 'provider': selected})})
        except ValueError as error:
            return {'connected': False, 'message': str(error)}

    def query_provider_quotas(self, provider_id, include_disabled=True):
        from console_router_quota import query_provider_quotas
        return query_provider_quotas(self, provider_id, include_disabled=include_disabled)

    def query_all_quotas(self, include_disabled=False):
        from console_router_quota import query_all_quotas
        return query_all_quotas(self, include_disabled=include_disabled)

    def action(self, body):
        command = body.get('command')
        args = body.get('args', {})
        if not isinstance(args, dict):
            raise ValueError('模型路由参数应为对象。')
        if command in ('open_app', 'launch_app'):
            try:
                subprocess.run(['open', *(['-gj'] if command == 'launch_app' else []), '-a', 'Local Model Router'], check=True, timeout=10,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError) as error:
                raise ValueError('Local Model Router 未能打开，请检查应用是否安装。') from error
            return {'ok': True}
        if command == 'test_keys':
            return {'result': self.test_keys(args.get('providerId'))}
        if command == 'query_provider_quotas':
            return {'result': self.query_provider_quotas(args.get('providerId'), include_disabled=bool(args.get('includeDisabled', True)))}
        if command == 'query_all_quotas':
            return {'result': self.query_all_quotas(include_disabled=bool(args.get('includeDisabled', False)))}
        return {'result': self.call(command, body.get('args'))}

    def test_keys(self, provider_id):
        """Probe every key of a provider; secrets stay in this process and never reach the page."""
        provider = next((p for p in self.call('snapshot')['providers'] if p.get('id') == provider_id), None)
        if not provider:
            raise ValueError('找不到该供应商。')
        base = provider['baseUrl'].rstrip('/')
        results = []
        for key in self.call('list_provider_keys', {'providerId': provider_id}):
            row = {'id': key['id'], 'label': key['label'], 'enabled': key['enabled'], 'ok': False, 'status': None, 'latencyMs': None, 'message': ''}
            started = time.monotonic()
            try:
                secret = self.call('reveal_provider_key', {'id': key['id']})
                request = urllib.request.Request(probe_url(provider['baseUrl']), headers={'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'})
                try:
                    response = self.http.open(request, timeout=15)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    response.read(1024 * 1024)
                    row['status'] = response.status
                row['ok'] = row['status'] == 200
                row['message'] = '可用' if row['ok'] else {401: '密钥无效或已过期', 403: '密钥被拒绝', 429: '已被限流'}.get(row['status'], 'HTTP %s' % row['status'])
            except ValueError as error:
                row['message'] = str(error)
            except (OSError, urllib.error.URLError):
                row['message'] = '连接上游失败或超时'
            row['latencyMs'] = round((time.monotonic() - started) * 1000)
            results.append(row)
        return results


def _resolve_provider_id(snap, selector):
    providers = snap.get('providers') or []
    text = str(selector).strip()
    if text.isdigit():
        pid = int(text)
        if any(p.get('id') == pid for p in providers):
            return pid
    lowered = text.lower()
    exact = [p for p in providers if str(p.get('name') or '').strip().lower() == lowered]
    if len(exact) == 1:
        return exact[0]['id']
    matches = [p for p in providers if lowered in str(p.get('name') or '').strip().lower()]
    if len(matches) == 1:
        return matches[0]['id']
    raise ValueError(f'无法唯一匹配供应商：{selector}')


def _format_quota_cli(data, single=False):
    def fmt_amt(val, unit):
        if val is None:
            return '—'
        return f'${val:.4f}' if unit == 'USD' else f'{val:.2f} {unit}'

    lines = []
    if single:
        reports = [data]
        unsupported = []
    else:
        t = data['totals']
        lines.append(
            f"总额度: 可用 ${t['usdAvailable']:.4f} USD"
            f" (余额 ${t['usdBalance']:.4f} + 日额 ${t['usdDaily']:.4f})"
            f" | Kiro {t['kiroCredits']:.2f} credits"
            + (f" | 不可用免费额 ${t['extraFreeUsd']:.2f}" if t['extraFreeUsd'] > 0 else '')
            + f" | 已配置 {t['supportedProviders']} / 跳过未配置 {t['unsupportedProviders']}"
        )
        reports = data.get('providers') or []
        unsupported = data.get('unsupportedProviders') or []

    for rep in reports:
        unit = rep['unit']
        dup = f" (去重 {rep['duplicateAccounts']} 个重复账户)" if rep.get('duplicateAccounts') else ''
        lines.append(
            f"\n[{rep['providerId']}] {rep['providerName']} | "
            f"启用合计 {fmt_amt(rep['enabledTotal'], unit)} | "
            f"存活去重 {fmt_amt(rep['allAliveTotal'], unit)} | "
            f"可用 {rep['usableCount']}/{rep['enabledChecked']} 启用 (共检查 {rep['checkedKeys']}/{rep['totalKeys']}){dup}"
        )
        for k in rep.get('keys') or []:
            state = 'ON' if k['enabled'] else 'OFF'
            label = k.get('label') or f"key#{k['id']}"
            dup_tag = ' [重复账户]' if k.get('duplicateAccount') else ''
            ms = f" ({k['latencyMs']}ms)" if k.get('latencyMs') is not None else ''
            lines.append(f"  #{k['id']} {label} [{state}] -> {k['message']}{dup_tag}{ms}")

    if unsupported:
        names = ', '.join(str(p.get('name') or p.get('id')) for p in unsupported)
        lines.append(f"\n未配置（不支持查余额）: {names}")
    return '\n'.join(lines)


def _cli(argv=None):
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog='console_router.py', description='Local Model Router 控制台工具')
    sub = parser.add_subparsers(dest='cmd')
    q = sub.add_parser('quota', help='一键查询已配置供应商的每个 Key 额度与总额度')
    q.add_argument('-p', '--provider', help='只查询指定供应商（ID 或名称）')
    q.add_argument('-a', '--all-keys', action='store_true', help='包含已停用的密钥（查询全部供应商时默认仅查启用密钥）')
    q.add_argument('--json', action='store_true', help='以 JSON 输出')

    args = parser.parse_args(argv)
    if args.cmd != 'quota':
        parser.print_help()
        return 2

    router = RouterManager()
    try:
        if args.provider:
            snap = router.call('snapshot', {'period': 'all', 'provider': None})
            pid = _resolve_provider_id(snap, args.provider)
            data = router.query_provider_quotas(pid, include_disabled=True)
            single = True
        else:
            data = router.query_all_quotas(include_disabled=bool(args.all_keys))
            single = False
    except ValueError as err:
        print(f'错误: {err}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(_format_quota_cli(data, single=single))
    return 0


if __name__ == '__main__':
    raise SystemExit(_cli())
