"""Direct-provider fallback when the Local Model Router (127.0.0.1:8787) is down.

Minimum viable channel, off by default. Provider keys stay owned by the router:
the only key source is the router app's authenticated console bridge
(``reveal_provider_key``), the same path the console already uses for key
speed tests. Nothing here reads the Keychain, and keys are held only for the
duration of one upstream request and never logged, stored or returned.

Consequence: when the router *app* is not running there is no safe key
source, and every call returns ``fallback_unavailable`` with
``reason='no_key_source'``. How keys could be supplied in that case is a
user decision (see README).
"""
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from console_capability import ROUTER_URL, classify, router_reachable, scrub, _NoRedirect

RETRY_STATUSES = frozenset((401, 403, 429, 500, 502, 503, 504))
BLOCKING_STATUSES = frozenset(('retired', 'missing_key'))
MESSAGES = {
    'router_available': '模型路由正常，无需直连备用。',
    'disabled': '直连备用默认关闭；需用户明确启用。',
    'no_key_source': '模型路由 App 未运行，平台密钥只在其钥匙串中，无法安全取用；直连备用不可用。',
    'unknown_model': '路由配置里没有这个模型。',
    'model_disabled': '该模型或其平台在路由配置中已停用。',
    'model_unavailable': '能力表显示该模型已下线或缺少密钥，直连不会成功。',
    'no_provider_key': '该平台没有已启用的密钥。',
    'unsafe_base_url': '平台地址不是 HTTPS（或本机回环），拒绝携带密钥直连。',
    'stream_unsupported': '直连备用暂只支持非流式请求。',
    'alias_unsupported': '虚拟模型有多个按序目标，直连备用不支持按序探测；请用具体模型直连。',
}


def _close_response(response):
    """Close a urllib response without masking the request outcome."""
    if isinstance(response, urllib.error.HTTPError) and getattr(response, 'fp', None) is None:
        return
    try:
        response.close()
    except Exception:
        pass


def _safe_base(url):
    parts = urllib.parse.urlsplit(url or '')
    if parts.scheme == 'https' and parts.hostname:
        return True
    return parts.scheme == 'http' and parts.hostname in ('127.0.0.1', 'localhost', '::1')


def unavailable(reason, router_reachable_flag=False, model=None, **extra):
    return dict({'ok': False, 'fallback': 'fallback_unavailable', 'available': False, 'reason': reason,
                 'message': MESSAGES.get(reason, reason), 'routerReachable': router_reachable_flag,
                 'model': model}, **extra)


class DirectFallback:
    def __init__(self, router_manager, registry=None, enabled=False, router_url=None, opener=None,
                 timeout=60, health=None):
        self.router = router_manager
        self.registry = registry
        self.enabled = bool(enabled)
        self.router_url = router_url or ROUTER_URL
        self.http = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self.timeout = timeout
        self.health = health or (lambda: router_reachable(self.router_url))

    def _mark(self, result):
        if self.registry is not None:
            try:
                self.registry.set_fallback(result)
            except OSError:
                pass
        return result

    def status(self):
        """Whether a direct call could be attempted right now (no upstream request)."""
        health = self.health()
        if health.get('reachable'):
            return self._mark({'ok': True, 'available': False, 'reason': 'router_available',
                               'message': MESSAGES['router_available'], 'routerReachable': True, 'model': None})
        if not self.enabled:
            return self._mark(unavailable('disabled'))
        try:
            self.router.call('snapshot')
        except ValueError:
            return self._mark(unavailable('no_key_source'))
        return self._mark({'ok': True, 'available': True, 'reason': 'ready', 'routerReachable': False,
                           'message': '模型路由端口不可用，但路由 App 仍在运行，可经其管理桥取用密钥直连。', 'model': None})

    def chat(self, model, payload):
        """Non-streaming chat completion. Use only after the router itself failed."""
        if not isinstance(payload, dict):
            raise ValueError('请求体应为对象。')
        health = self.health()
        if health.get('reachable'):
            return {'ok': False, 'fallback': 'not_needed', 'reason': 'router_available',
                    'message': MESSAGES['router_available'], 'routerReachable': True, 'model': model}
        if not self.enabled:
            return self._mark(unavailable('disabled', model=model))
        if payload.get('stream'):
            return unavailable('stream_unsupported', model=model)
        try:
            snapshot = self.router.call('snapshot')
        except ValueError:
            return self._mark(unavailable('no_key_source', model=model))
        wanted = str(model).lower()
        alias_row = next((a for a in snapshot.get('aliases', []) if str(a.get('aliasId', '')).lower() == wanted), None)
        if alias_row is not None:
            # Virtual-model alias: ordered probing is explicitly unimplemented.
            # Never silently pick one provider.
            return unavailable('alias_unsupported', model=model)
        row = next((m for m in snapshot.get('models', []) if str(m.get('modelId', '')).lower() == wanted), None)
        if row is None:
            return unavailable('unknown_model', model=model)
        provider = next((p for p in snapshot.get('providers', []) if p.get('id') == row.get('providerId')), None)
        if provider is None or not row.get('enabled') or not provider.get('enabled'):
            return unavailable('model_disabled', model=model)
        if self.registry is not None:
            record = self.registry.get(row['modelId'], provider.get('name'))
            if record and record['status'] in BLOCKING_STATUSES:
                return self._mark(unavailable('model_unavailable', model=model, capability=record['status']))
        base = str(provider.get('baseUrl', '')).rstrip('/')
        if not _safe_base(base):
            return unavailable('unsafe_base_url', model=model)
        try:
            keys = [k for k in self.router.call('list_provider_keys', {'providerId': provider['id']}) if k.get('enabled') and k.get('hasSecret', True)]
        except ValueError:
            return self._mark(unavailable('no_key_source', model=model))
        if not keys:
            return self._mark(unavailable('no_provider_key', model=model))
        body = json.dumps(dict(payload, model=row.get('upstreamModel') or row['modelId'], stream=False)).encode()
        attempts = []
        for key in keys:
            started = time.monotonic()
            try:
                secret = self.router.call('reveal_provider_key', {'id': key['id']})
            except ValueError as error:
                kind = classify(None, str(error))
                attempts.append({'keyId': key['id'], 'kind': kind if kind == 'missing_key' else 'no_key_source',
                                 'message': scrub(error)})
                continue
            request = urllib.request.Request(base + '/chat/completions', data=body, method='POST',
                                             headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
            del secret
            status, raw, message = None, b'', ''
            try:
                try:
                    response = self.http.open(request, timeout=self.timeout)
                except urllib.error.HTTPError as error:
                    response = error
                try:
                    status = response.status
                    raw = response.read(8 * 1024 * 1024)
                finally:
                    _close_response(response)
            except (socket.timeout, TimeoutError):
                message = 'upstream timed out'
            except (OSError, urllib.error.URLError) as error:
                message = 'upstream connection failed: ' + type(error).__name__
            finally:
                request.headers.pop('Authorization', None)
            latency = round((time.monotonic() - started) * 1000)
            if status is not None and 200 <= status < 300:
                try:
                    data = json.loads(raw)
                except ValueError:
                    attempts.append({'keyId': key['id'], 'kind': 'upstream_error', 'status': status, 'message': '上游返回非 JSON'})
                    break
                return {'ok': True, 'via': 'direct', 'platform': provider.get('name'), 'model': row['modelId'],
                        'status': status, 'latencyMs': latency, 'response': data, 'attempts': attempts}
            if status is not None and not message:
                message = raw[:300].decode('utf-8', 'replace')
            kind = classify(status, message)
            attempts.append({'keyId': key['id'], 'kind': kind, 'status': status, 'latencyMs': latency, 'message': scrub(message)})
            if status not in RETRY_STATUSES or kind == 'gone':
                break
        last = attempts[-1] if attempts else {'kind': 'error'}
        return {'ok': False, 'fallback': 'failed', 'reason': last['kind'], 'message': last.get('message', ''),
                'routerReachable': False, 'model': model, 'attempts': attempts}
