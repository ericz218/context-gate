"""Dynamic capability registry for Local Model Router platforms and models.

One record per "platform/model": availability (last success / failure and the
classified last error such as 410 retired, timeout or missing key), latency
P50/P95, error rate, catalog price, tool-call / Responses support and the last
active probe.

Sources:
- Passive (default): router.db opened read-only (``mode=ro``). Only providers,
  models, provider key *counts* and request metadata are read; never secrets,
  debug details or prompts. The router remains the only writer.
- Active probe (off unless the caller passes ``consume_quota=True``): one tiny
  chat completion through the local router per model, with a cooldown and
  exponential backoff. Every probe consumes provider quota.

State lives in ``<state_dir>/router-capabilities.json`` (0600). Python standard
library only; no key is ever written, logged or returned.
"""
from pathlib import Path
import argparse
import json
import math
import os
import re
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROUTER_DB = Path(os.environ.get(
    'ROUTER_DB', '~/Library/Application Support/com.localmodelrouter.desktop/router.db')).expanduser()
ROUTER_URL = os.environ.get('LMR_ROUTER_URL', 'http://127.0.0.1:8787')
CATALOG_PATH = Path(__file__).resolve().parent / 'console' / 'wallet_catalog.json'
STATE_NAME = 'router-capabilities.json'
STATE_VERSION = 1

WINDOW_DAYS = 7
CACHE_SECONDS = 15
PROBE_COOLDOWN_S = 6 * 3600
PROBE_MAX_BACKOFF_S = 7 * 86400
PROBE_TIMEOUT_S = 30
PROBE_MAX_TOKENS = 8

# Failure kinds that mean "this model cannot serve right now".
HARD_KINDS = frozenset(('gone', 'missing_key', 'timeout', 'auth', 'forbidden', 'not_found',
                        'network', 'upstream_error', 'router_unavailable', 'error'))
# Reaching the model with a malformed request says nothing about availability.
SOFT_KINDS = frozenset(('client_error',))
STATUS_FOR_KIND = {'gone': 'retired', 'missing_key': 'missing_key', 'timeout': 'timeout'}

# Prices are only attached when the router platform is the catalog's own API
# provider; creator prices are never applied to a different hosting platform.
HOST_API_PROVIDER = {
    'api.meta.ai': 'Meta',
    'integrate.api.nvidia.com': 'NVIDIA',
    'api.anthropic.com': 'Anthropic',
    'api.openai.com': 'OpenAI',
    'api.deepseek.com': 'DeepSeek',
    'api.x.ai': 'xAI',
    'api.mistral.ai': 'Mistral',
}

_SECRET_PATTERNS = (
    (re.compile(r'(?i)(authorization[\s:=]+(?:bearer\s+)?|bearer\s+)[^\s,}"\']+'), r'\1[REDACTED]'),
    (re.compile(r'(?i)((?:api[_-]?key|access[_-]?token|secret)["\s:=]+)[^\s,}"\']+'), r'\1[REDACTED]'),
    (re.compile(r'\b(?:sk-[\w-]{12,}|lmr_[\w-]{8,}|nvapi-[\w-]{12,}|AKIA[0-9A-Z]{12,})'), '[REDACTED]'),
)


def scrub(text, limit=240):
    """Bounded, credential-free error text for display and persistence."""
    if text is None:
        return ''
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def classify(status, message=''):
    """Map an HTTP status (or None for transport errors) plus error text to a kind."""
    m = (message or '').lower()
    if isinstance(status, int) and 200 <= status < 300:
        return 'ok'
    if status == 410 or 'end of life' in m or 'end-of-life' in m or 'reached its end' in m:
        return 'gone'
    if 'keychain' in m and any(x in m for x in ('not found', 'cannot locate', 'cannot read', 'missing')):
        return 'missing_key'
    if status in (408, 504) or 'timed out' in m or 'timeout' in m:
        return 'timeout'
    if status == 429:
        return 'rate_limited'
    if status == 401:
        return 'auth'
    if status == 403:
        return 'forbidden'
    if status == 404:
        return 'not_found'
    if status in (400, 413, 415, 422):
        return 'client_error'
    if status == 502 or status is None and ('refused' in m or 'connection' in m or 'unreachable' in m):
        return 'network'
    if isinstance(status, int) and status >= 500:
        return 'upstream_error'
    return 'error'


def percentile(values, p):
    """Nearest-rank percentile; None for an empty sample."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if not 0 < p <= 100:
        raise ValueError('percentile must be in (0, 100]')
    return data[max(0, math.ceil(p / 100 * len(data)) - 1)]


def window_stats(rows):
    """rows: iterable of (status, latency_ms, error_message). Latency uses successes only."""
    total = failures = 0
    latencies, kinds = [], {}
    for status, latency, message in rows:
        total += 1
        kind = classify(status, message)
        if kind == 'ok':
            latencies.append(latency)
        else:
            failures += 1
            kinds[kind] = kinds.get(kind, 0) + 1
    return {
        'requests': total,
        'failures': failures,
        'errorRate': round(failures / total, 4) if total else None,
        'p50Ms': percentile(latencies, 50),
        'p95Ms': percentile(latencies, 95),
        'latencySamples': len(latencies),
        'kinds': kinds,
    }


def probe_delay(consecutive_failures, kind, cooldown=PROBE_COOLDOWN_S, max_backoff=PROBE_MAX_BACKOFF_S):
    """Seconds until the next probe: cooldown after success, doubling per failure."""
    if kind == 'gone':
        return max_backoff
    if kind in ('ok', 'client_error') or not consecutive_failures:
        return min(cooldown, max_backoff)
    return min(cooldown * (2 ** min(int(consecutive_failures), 16)), max_backoff)


def probe_due(entry, now_ms, cooldown=PROBE_COOLDOWN_S, max_backoff=PROBE_MAX_BACKOFF_S):
    """Return (due, wait_seconds, reason) for a stored probe entry."""
    if not entry or not entry.get('lastAt'):
        return True, 0, 'never_probed'
    nxt = entry.get('nextAt')
    if not isinstance(nxt, (int, float)):
        nxt = entry['lastAt'] + probe_delay(entry.get('consecutiveFailures', 0), entry.get('kind'),
                                            cooldown, max_backoff) * 1000
    if now_ms >= nxt:
        return True, 0, 'cooldown_elapsed'
    reason = 'retired_backoff' if entry.get('kind') == 'gone' else 'backoff' if entry.get('consecutiveFailures') else 'cooldown'
    return False, math.ceil((nxt - now_ms) / 1000), reason


def availability(last_success_at, last_event, rate_limited_recent=False, error_rate=None, stale_before=None):
    """Derive (status, reason) from the latest decisive event.

    A success older than ``stale_before`` (window start) no longer proves availability: keys can be lost
    or models retired since, so such a model is 'unknown' until a new request or probe succeeds."""
    if not last_event and not last_success_at:
        return 'unknown', 'no_data'
    if last_event and last_event['kind'] in HARD_KINDS and (not last_success_at or last_event['at'] >= last_success_at):
        return STATUS_FOR_KIND.get(last_event['kind'], 'unavailable'), last_event['kind']
    if last_event and last_event['kind'] == 'rate_limited' and (not last_success_at or last_event['at'] >= last_success_at):
        return 'degraded', 'rate_limited'
    if error_rate is not None and error_rate >= 0.5:
        return 'degraded', 'high_error_rate'
    if last_success_at and stale_before is not None and last_success_at < stale_before:
        return 'unknown', 'stale_success'
    if last_success_at:
        return 'available', 'recent_success'
    return 'unknown', 'only_client_errors'


def load_catalog(path=CATALOG_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data.get('models') or []
    except (OSError, ValueError, AttributeError):
        return []


def catalog_price(catalog, base_url, upstream_model):
    """Exact (platform, model name) match against the wallet catalog, else None."""
    host = (urllib.parse.urlsplit(base_url or '').hostname or '').lower()
    api_provider = HOST_API_PROVIDER.get(host)
    if not api_provider or not upstream_model:
        return None
    name = str(upstream_model).rsplit('/', 1)[-1].lower()
    for model in catalog:
        if model.get('apiProvider') != api_provider:
            continue
        names = {str(model.get('name') or '').lower(), str(model.get('id') or '').rsplit('/', 1)[-1].lower()}
        if name in names:
            if model.get('inputPrice') in (None, '') and model.get('outputPrice') in (None, ''):
                return None
            return {'input': model.get('inputPrice'), 'output': model.get('outputPrice'),
                    'cacheRead': model.get('cacheReadPrice'), 'currency': model.get('currency') or 'USD',
                    'unit': model.get('pricingUnit') or 'MILLION_TOKENS', 'catalogId': model.get('id'),
                    'verifiedAt': model.get('priceLastVerifiedAt') or model.get('verifiedAt'),
                    'source': 'wallet_catalog'}
    return None


def _close_response(response):
    """Close a urllib response without masking the request outcome."""
    if isinstance(response, urllib.error.HTTPError) and getattr(response, 'fp', None) is None:
        return
    try:
        response.close()
    except Exception:
        pass


def router_reachable(base=ROUTER_URL, timeout=1.5, opener=None):
    """Any HTTP answer from /v1/models (401 without a key) means the router is serving."""
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    started = time.monotonic()
    try:
        response = opener.open(urllib.request.Request(base.rstrip('/') + '/v1/models'), timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    except (OSError, urllib.error.URLError) as error:
        return {'reachable': False, 'detail': scrub(getattr(error, 'reason', error), 120),
                'latencyMs': round((time.monotonic() - started) * 1000)}
    try:
        status = response.status
    finally:
        _close_response(response)
    return {'reachable': True, 'status': status, 'latencyMs': round((time.monotonic() - started) * 1000)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def _write_private(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, sort_keys=True, indent=1)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _model_key(platform, model):
    return (platform or '?') + '/' + (model or '?')


class CapabilityRegistry:
    def __init__(self, state_dir, db_path=None, router_url=None, catalog_path=None,
                 window_days=WINDOW_DAYS, clock=None, opener=None):
        self.state_path = Path(state_dir).expanduser() / STATE_NAME
        self.db_path = Path(db_path).expanduser() if db_path else ROUTER_DB
        self.router_url = router_url or ROUTER_URL
        self.catalog_path = catalog_path or CATALOG_PATH
        self.window_days = window_days
        self.clock = clock or time.time
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        self.lock = threading.RLock()
        self._cache = None
        self._cache_at = 0.0
        self.state = self._load()

    # ---- persistence -------------------------------------------------
    def _load(self):
        try:
            data = json.loads(self.state_path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data.get('version') == STATE_VERSION:
                data.setdefault('probes', {})
                data.setdefault('config', {})
                data.setdefault('fallback', None)
                return data
        except (OSError, ValueError):
            pass
        return {'version': STATE_VERSION, 'config': {}, 'probes': {}, 'fallback': None, 'snapshot': None}

    def _save(self):
        _write_private(self.state_path, self.state)

    def now_ms(self):
        return int(self.clock() * 1000)

    # ---- passive collection -----------------------------------------
    def _connect(self):
        if not self.db_path.is_file():
            raise FileNotFoundError(str(self.db_path))
        return sqlite3.connect(self.db_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)

    def _collect(self, now_ms):
        since = now_ms - self.window_days * 86400 * 1000
        with self._connect() as db:
            providers = {row[0]: {'id': row[0], 'name': row[1], 'baseUrl': row[2], 'enabled': bool(row[3]), 'keyCount': row[4]}
                         for row in db.execute('select p.id, p.name, p.base_url, p.enabled, '
                                               '(select count(*) from provider_keys k where k.provider_id = p.id and k.enabled = 1) '
                                               'from providers p')}
            models = [{'id': r[0], 'displayName': r[1], 'model': r[2], 'providerId': r[3], 'upstreamModel': r[4], 'enabled': bool(r[5])}
                      for r in db.execute('select id, display_name, model_id, provider_id, upstream_model, enabled from models')]
            # Virtual-model aliases share the router.db file but live in their
            # own tables (exact names 'aliases' + 'alias_targets', verified
            # read-only on the live db). Only exact table names count.
            aliases = []
            alias_tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
            if 'aliases' in alias_tables and 'alias_targets' in alias_tables:
                try:
                    target_rows = db.execute(
                        'select alias_id, model_ref from alias_targets order by alias_id, position').fetchall()
                    by_alias = {}
                    for alias_id, model_ref in target_rows:
                        by_alias.setdefault(alias_id, []).append(model_ref)
                    for alias_id, alias_name, enabled in db.execute(
                            'select id, alias_id, enabled from aliases'):
                        aliases.append({'aliasId': alias_name, 'enabled': bool(enabled),
                                        'targets': list(by_alias.get(alias_id, []))})
                except sqlite3.Error:
                    aliases = []
            window = {}
            for provider, model, status, latency, message in db.execute(
                    'select provider_name, lower(resolved_model), status, latency_ms, error_message from requests '
                    'where ts >= ? and resolved_model is not null order by ts', (since,)):
                window.setdefault((provider, model), []).append((status, latency, message))
            last = {}
            for provider, model, ok_at, fail_at, responses_ok in db.execute(
                    'select provider_name, lower(resolved_model), '
                    'max(case when status between 200 and 299 then ts end), '
                    'max(case when status not between 200 and 299 then ts end), '
                    "max(case when endpoint = 'responses' and status between 200 and 299 then 1 else 0 end) "
                    'from requests where resolved_model is not null group by 1, 2'):
                last[(provider, model)] = {'okAt': ok_at, 'failAt': fail_at, 'responses': bool(responses_ok)}
            # Latest hard/rate-limit failure after the last success decides availability;
            # a later 400 must not hide an earlier timeout or retirement.
            for (provider, model), info in last.items():
                info['failure'] = info['lastError'] = None
                if info['failAt'] is None:
                    continue
                rows = db.execute(
                    'select ts, status, error_message from requests where provider_name is ? and lower(resolved_model) = ? '
                    'and status not between 200 and 299 order by ts desc limit 50', (provider, model)).fetchall()
                for index, (ts, status, message) in enumerate(rows):
                    event = {'at': ts, 'status': status, 'kind': classify(status, message), 'message': scrub(message)}
                    if index == 0:
                        info['lastError'] = event
                    if info['okAt'] and ts < info['okAt']:
                        break
                    if event['kind'] not in SOFT_KINDS:
                        info['failure'] = event
                        break
        return providers, models, window, last, aliases

    def _record(self, platform, provider, model_name, model_row, window_rows, last, catalog, now_ms):
        key = _model_key(platform, model_row['model'] if model_row else model_name)
        stats = window_stats(window_rows or [])
        info = last or {}
        probe = self.state['probes'].get(key)
        candidates = []
        if info.get('failure'):
            candidates.append(info['failure'])
        probe_failed = bool(probe and probe.get('lastAt') and probe.get('kind') not in (None, 'ok'))
        # A probe that never reached the router says nothing about the model itself.
        if probe_failed and probe['kind'] not in SOFT_KINDS and probe['kind'] != 'router_unavailable':
            candidates.append({'at': probe['lastAt'], 'status': probe.get('status'), 'kind': probe['kind'],
                               'message': probe.get('message', ''), 'source': 'probe'})
        last_failure = max(candidates, key=lambda e: e['at']) if candidates else None
        ok_at = info.get('okAt')
        if probe and probe.get('kind') == 'ok' and probe.get('lastAt') and (not ok_at or probe['lastAt'] > ok_at):
            ok_at = probe['lastAt']
        status, reason = availability(ok_at, last_failure, error_rate=stats['errorRate'],
                                      stale_before=now_ms - self.window_days * 86400 * 1000)
        last_error = info.get('lastError')
        if probe_failed and (not last_error or probe['lastAt'] > last_error['at']):
            last_error = {'at': probe['lastAt'], 'status': probe.get('status'), 'kind': probe['kind'],
                          'message': probe.get('message', ''), 'source': 'probe'}
        fail_times = [t for t in (info.get('failAt'), probe['lastAt'] if probe_failed else None) if t]
        fail_at = max(fail_times) if fail_times else None
        upstream = model_row['upstreamModel'] if model_row else None
        return {
            'key': key,
            'platform': platform,
            'model': model_row['model'] if model_row else model_name,
            'displayName': model_row['displayName'] if model_row else None,
            'upstreamModel': upstream,
            'configured': model_row is not None,
            'enabled': bool(model_row and model_row['enabled'] and provider and provider['enabled']),
            'keyCount': provider['keyCount'] if provider else None,
            'status': status,
            'statusReason': reason,
            'lastSuccessAt': ok_at,
            'lastFailureAt': fail_at,
            'lastError': last_error,
            'window': dict(stats, days=self.window_days),
            'price': catalog_price(catalog, provider and provider['baseUrl'], upstream) if model_row else None,
            'toolCalls': 'unknown',
            'responsesApi': 'supported' if info.get('responses') else 'unknown',
            'probe': {k: probe.get(k) for k in ('lastAt', 'kind', 'status', 'latencyMs', 'consecutiveFailures', 'nextAt')} if probe else None,
        }

    def snapshot(self, refresh=False, check_router=True):
        """Capability table built from router.db (read-only) plus stored probe results."""
        with self.lock:
            if not refresh and self._cache and time.monotonic() - self._cache_at < CACHE_SECONDS:
                if check_router and self._cache.get('router') is None:
                    self._cache = dict(self._cache, router=router_reachable(self.router_url, opener=self.opener))
                return self._cache
            now_ms = self.now_ms()
            result = {'version': STATE_VERSION, 'generatedAt': now_ms, 'windowDays': self.window_days,
                      'source': {'routerDb': 'read-only', 'probe': 'opt-in (consumes quota)'}, 'records': []}
            try:
                providers, models, window, last, aliases = self._collect(now_ms)
            except (OSError, sqlite3.Error) as error:
                result['error'] = 'router.db 无法只读打开：' + type(error).__name__
                providers, models, window, last, aliases = {}, [], {}, {}, []
            catalog = load_catalog(self.catalog_path)
            seen = set()
            for row in sorted(models, key=lambda m: (providers.get(m['providerId'], {}).get('name', ''), m['model'].lower())):
                provider = providers.get(row['providerId'])
                platform = provider['name'] if provider else None
                pair = (platform, row['model'].lower())
                seen.add(pair)
                result['records'].append(self._record(platform, provider, row['model'], row, window.get(pair), last.get(pair), catalog, now_ms))
            by_name = {p['name']: p for p in providers.values()}
            for pair, rows in window.items():
                if pair in seen:
                    continue
                result['records'].append(self._record(pair[0], by_name.get(pair[0]), pair[1], None, rows, last.get(pair), catalog, now_ms))
            # Aliases get their own display records only when the exact alias
            # tables exist. Probing is refused below: ordered-target probing
            # is not implemented, and single-row results would corrupt stats.
            model_ids = {str(m['model']).lower() for m in models}
            exact_targets = {str(t).lower() for a in aliases for t in a.get('targets', [])}
            for alias in aliases:
                targets = [str(t) for t in alias.get('targets', [])]
                result['records'].append({
                    'key': 'alias/' + alias['aliasId'],
                    'platform': None,
                    'model': alias['aliasId'],
                    'displayName': alias['aliasId'],
                    'upstreamModel': None,
                    'configured': True,
                    'enabled': bool(alias.get('enabled')),
                    'keyCount': None,
                    'status': 'unknown',
                    'statusReason': 'ambiguous_alias',
                    'lastSuccessAt': None,
                    'lastFailureAt': None,
                    'lastError': None,
                    'window': dict(window_stats([]), days=self.window_days),
                    'price': None,
                    'toolCalls': 'unknown',
                    'responsesApi': 'unknown',
                    'probe': None,
                    'alias': True,
                    'aliasTargets': targets,
                    'aliasResolvable': len(targets) == 1 and targets[0].lower() in model_ids,
                    'aliasChain': any(t.lower() not in model_ids and t.lower() in exact_targets or
                                      t.lower() not in model_ids for t in targets),
                })
            result['aliases'] = [{'aliasId': a['aliasId'], 'targets': list(a.get('targets', [])),
                                  'enabled': bool(a.get('enabled'))} for a in aliases]
            result['router'] = router_reachable(self.router_url, opener=self.opener) if check_router else None
            result['fallback'] = self.state.get('fallback')
            result['counts'] = {}
            for record in result['records']:
                result['counts'][record['status']] = result['counts'].get(record['status'], 0) + 1
            comparable = {k: v for k, v in result.items() if k not in ('generatedAt', 'router')}
            previous = self.state.get('snapshot') or {}
            if {k: v for k, v in previous.items() if k not in ('generatedAt', 'router')} != comparable:
                self.state['snapshot'] = result
                try:
                    self._save()
                except OSError:
                    result['persistError'] = '能力表未能写入状态目录'
            self._cache, self._cache_at = result, time.monotonic()
            return result

    def get(self, model, platform=None):
        """One record by key ("platform/model") or by model id (case-insensitive).

        Aliases win over same-named model rows: the live router resolves the
        requested name through its alias engine first, so naming an alias must
        surface the explicit alias record rather than a concrete row.
        """
        wanted = model.lower()
        records = self.snapshot(check_router=False)['records']
        for record in records:
            if record.get('alias') and (record['key'].lower() == wanted or record['model'].lower() == wanted):
                return record
        for record in records:
            if record['key'].lower() == wanted or (record['model'].lower() == wanted and (platform is None or record['platform'] == platform)):
                return record
        return None

    def candidates(self, statuses=('available', 'degraded'), require_tools=False, require_responses=False,
                   max_p95_ms=None, prefer='fast'):
        """Enabled models ordered for automatic selection (fastest or cheapest first)."""
        rank = {s: i for i, s in enumerate(statuses)}
        out = []
        for r in self.snapshot(check_router=False)['records']:
            if not r['enabled'] or r['status'] not in rank:
                continue
            if require_tools and r['toolCalls'] != 'supported':
                continue
            if require_responses and r['responsesApi'] != 'supported':
                continue
            if max_p95_ms is not None and (r['window']['p95Ms'] is None or r['window']['p95Ms'] > max_p95_ms):
                continue
            out.append(r)
        def price(r):
            try:
                return float(r['price']['input']) if r['price'] else math.inf
            except (TypeError, ValueError):
                return math.inf
        def latency(r):
            return r['window']['p50Ms'] if r['window']['p50Ms'] is not None else math.inf
        key = (lambda r: (rank[r['status']], price(r), latency(r))) if prefer == 'cheap' else (lambda r: (rank[r['status']], latency(r), price(r)))
        return sorted(out, key=key)

    # ---- fallback marker ---------------------------------------------
    def set_fallback(self, status):
        """Store the latest direct-fallback verdict so the table shows it."""
        with self.lock:
            entry = {k: status.get(k) for k in ('available', 'reason', 'message', 'routerReachable', 'model')}
            entry['at'] = self.now_ms()
            self.state['fallback'] = entry
            self._cache = None
            self._save()
            return entry

    # ---- active probe --------------------------------------------------
    def probe(self, model, key_provider, consume_quota=False, force=False, timeout=PROBE_TIMEOUT_S,
              cooldown=PROBE_COOLDOWN_S, max_backoff=PROBE_MAX_BACKOFF_S):
        """One tiny completion through the local router. Requires consume_quota=True.

        key_provider() returns the router's local API key; it is used for this
        request only and never stored or returned.
        """
        if not consume_quota:
            return {'probed': False, 'skipped': 'quota_not_acknowledged',
                    'message': '主动探测会消耗供应商额度，需显式 consume_quota=True。'}
        record = self.get(model)
        if record is None:
            return {'probed': False, 'skipped': 'unknown_model'}
        if record.get('alias'):
            # Virtual-model alias: without ordered-target probing every alias
            # is ambiguous from the prober's view. Refuse explicitly.
            return {'probed': False, 'skipped': 'ambiguous_alias'}
        if not record['configured']:
            return {'probed': False, 'skipped': 'not_configured'}
        key = record['key']
        with self.lock:
            entry = self.state['probes'].get(key)
            due, wait, reason = probe_due(entry, self.now_ms(), cooldown, max_backoff)
            if not due and not force:
                return {'probed': False, 'skipped': reason, 'retryInSeconds': wait}
        body = json.dumps({'model': record['model'], 'messages': [{'role': 'user', 'content': 'ping'}],
                           'max_tokens': PROBE_MAX_TOKENS, 'stream': False}).encode()
        secret = key_provider()
        if not isinstance(secret, str) or not secret:
            return {'probed': False, 'skipped': 'no_local_key'}
        request = urllib.request.Request(self.router_url.rstrip('/') + '/v1/chat/completions', data=body, method='POST',
                                         headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
        del secret
        started = time.monotonic()
        status, message = None, ''
        try:
            try:
                response = self.opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            try:
                status = response.status
                raw = response.read(65536)
            finally:
                _close_response(response)
            if not 200 <= status < 300:
                try:
                    data = json.loads(raw)
                    err = data.get('error') if isinstance(data, dict) else None
                    message = (err.get('message') if isinstance(err, dict) else err) or data.get('detail') or raw[:300].decode('utf-8', 'replace')
                except (ValueError, AttributeError):
                    message = raw[:300].decode('utf-8', 'replace')
        except (socket.timeout, TimeoutError):
            message = 'probe timed out after %ss' % timeout
        except urllib.error.URLError as error:
            reason_obj = getattr(error, 'reason', error)
            message = ('probe timed out after %ss' % timeout) if isinstance(reason_obj, (socket.timeout, TimeoutError)) else 'router connection failed: %s' % reason_obj
        except OSError as error:
            message = 'router connection failed: %s' % type(error).__name__
        finally:
            request.headers.pop('Authorization', None)
        latency = round((time.monotonic() - started) * 1000)
        kind = classify(status, message)
        if status is None and kind in ('network', 'error'):
            kind = 'router_unavailable'
        with self.lock:
            failures = 0 if kind in ('ok', 'client_error') else (entry or {}).get('consecutiveFailures', 0) + 1
            now = self.now_ms()
            stored = {'lastAt': now, 'kind': kind, 'status': status, 'latencyMs': latency,
                      'message': scrub(message), 'consecutiveFailures': failures,
                      'nextAt': now + probe_delay(failures, kind, cooldown, max_backoff) * 1000,
                      'consumesQuota': True}
            self.state['probes'][key] = stored
            self._cache = None
            self._save()
        return dict(stored, probed=True, key=key)


def _runtime_local_key(path='~/Library/Application Support/MemoryOS/runtime.json'):
    # Kept only for backward compatibility of the reference: the CLI no longer
    # uses it. MemoryOS extractor credentials must never be sent as the Local
    # Model Router bearer -- they are a different trust domain.
    raise ValueError('MemoryOS runtime key 不得用作模型路由本地密钥。')


def _bridge_local_key(router_manager=None):
    """Fetch the router's own local API key through its authenticated bridge.

    The secret lives only in this process (used once by probe()), and is
    never printed, logged, persisted or returned inside a snapshot record.
    """
    from console_router import RouterManager
    manager = router_manager or RouterManager()
    return manager.call('get_local_api_key')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Router capability registry (read-only router.db; probes consume quota).')
    parser.add_argument('--state-dir', default=os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate'))
    parser.add_argument('--db', default=None)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('snapshot')
    probe = sub.add_parser('probe')
    probe.add_argument('model')
    probe.add_argument('--consume-quota', action='store_true', help='required: one tiny completion is billed by the provider')
    probe.add_argument('--force', action='store_true', help='ignore cooldown/backoff')
    probe.add_argument('--timeout', type=int, default=PROBE_TIMEOUT_S)
    args = parser.parse_args(argv)
    registry = CapabilityRegistry(args.state_dir, db_path=args.db)
    if args.cmd == 'snapshot':
        print(json.dumps(registry.snapshot(refresh=True), ensure_ascii=False, indent=1))
    else:
        def key_provider():
            # Key stays in this process only; a down/unreachable bridge must
            # surface as no_local_key (probe skipped), never as a fallback
            # to an unrelated credential file.
            try:
                secret = _bridge_local_key()
            except ValueError:
                raise ValueError('no_local_key')
            if not isinstance(secret, str) or not secret:
                raise ValueError('no_local_key')
            return secret

        try:
            result = registry.probe(args.model, key_provider, consume_quota=args.consume_quota,
                                    force=args.force, timeout=args.timeout)
        except ValueError as error:
            result = {'probed': False, 'skipped': 'no_local_key', 'message': str(error)[:200]}
        print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
