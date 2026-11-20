"""Per-key and aggregate quota queries for router providers with verified balance APIs.

Only providers with a real key-level remaining quota/balance endpoint are configured here.
Providers that lack a key balance endpoint (or expose only placeholder limits like
unlimited NewAPI/OneAPI keys) are intentionally left unconfigured.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BACKBOARD_BALANCE_URL = os.environ.get('BACKBOARD_BALANCE_URL', 'https://app.backboard.io/api/billing/balance')
KIRO_HOSTS = frozenset(('q.us-east-1.amazonaws.com', 'q.eu-central-1.amazonaws.com'))
SECRET_RE = re.compile(r'(Bearer\s+[^\s]+|(?:espr|bb|lmr|ksk|rc)_[A-Za-z0-9_-]{8,}|(?:sk|rc)-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,})')


def scrub_secrets(text):
    return SECRET_RE.sub('[REDACTED]', str(text or ''))


def _as_float(value):
    if value is None or isinstance(value, bool):
        return 0.0
    return float(value)


def quota_profile(provider):
    """Return quota adapter config for a provider, or None if unsupported."""
    if not isinstance(provider, dict):
        return None
    base = str(provider.get('baseUrl') or '').strip()
    if not base:
        return None
    try:
        parts = urllib.parse.urlsplit(base)
    except ValueError:
        return None

    host = (parts.hostname or '').lower()
    path = parts.path.rstrip('/')
    has_extra = bool(parts.username or parts.password or parts.query or parts.fragment)

    if parts.scheme == 'https' and host in KIRO_HOSTS and not parts.port and path == '' and not has_extra:
        return {'id': 'kiro', 'kind': 'credits', 'unit': 'credits', 'label': 'Kiro 点数'}

    if parts.scheme == 'https' and host == 'developer.amd.com.cn' and path in ('/radeon/api/v1', '/radeon/api') and not parts.port and not has_extra:
        return {'id': 'amd_tokenfactory', 'kind': 'daily', 'unit': 'USD', 'label': 'AMD TokenFactory 日额度'}

    name = str(provider.get('name') or '').strip().lower()
    is_backboard_cloud = parts.scheme == 'https' and host == 'app.backboard.io' and not parts.port and not has_extra
    is_backboard_shim = parts.scheme == 'http' and host in ('127.0.0.1', 'localhost') and name == 'backboard' and path in ('/v1', '') and not has_extra
    if is_backboard_cloud or is_backboard_shim:
        return {'id': 'backboard', 'kind': 'balance', 'unit': 'USD', 'label': 'Backboard 可用余额'}

    return None


def attach_quota_support(snapshot_data):
    """Annotate router snapshot providers with configured quota capability flags."""
    if not isinstance(snapshot_data, dict):
        return snapshot_data
    providers = snapshot_data.get('providers')
    if not isinstance(providers, list):
        return snapshot_data
    enriched = []
    for provider in providers:
        item = dict(provider) if isinstance(provider, dict) else provider
        if isinstance(item, dict):
            prof = quota_profile(item)
            item['quotaSupported'] = prof is not None
            item['quotaKind'] = prof['kind'] if prof else None
            item['quotaUnit'] = prof['unit'] if prof else None
        enriched.append(item)
    return dict(snapshot_data, providers=enriched)


def _read_http_error(err):
    raw = b''
    try:
        if getattr(err, 'fp', None) is not None:
            raw = err.read(4096) or b''
    except Exception:
        raw = b''
    finally:
        close = getattr(err, 'close', None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    text = raw.decode('utf-8', 'replace').strip() if raw else ''
    if text:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                detail = obj.get('detail')
                if not detail and isinstance(obj.get('error'), dict):
                    detail = obj['error'].get('message')
                if isinstance(detail, str) and detail.strip():
                    return scrub_secrets(detail.strip())[:160]
        except Exception:
            pass
        return scrub_secrets(re.sub(r'\s+', ' ', text))[:160]
    return scrub_secrets(getattr(err, 'reason', '') or '')[:160]


def _get_json(http, url, headers, timeout=12):
    req = urllib.request.Request(url, headers=headers, method='GET')
    with http.open(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024)
        status = getattr(resp, 'status', 200)
    if status != 200:
        raise RuntimeError(f'HTTP {status}')
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict):
        raise ValueError('返回格式无效')
    return data


def _parse_backboard(data):
    credit_fields = ('paid_credit_usd', 'subscription_credits_usd', 'nash_credit_usd')
    has_credit_fields = any(field in data for field in credit_fields)
    if not has_credit_fields and 'balance_usd' not in data:
        raise ValueError('余额返回缺少额度字段')
    bal = _as_float(data.get('balance_usd')) if 'balance_usd' in data else 0.0
    free = max(0.0, _as_float(data.get('free_credit_usd')))
    if 'balance_usd' in data and bal <= 0.0:
        avail = 0.0
    elif has_credit_fields:
        avail = (
            max(0.0, _as_float(data.get('paid_credit_usd')))
            + max(0.0, _as_float(data.get('subscription_credits_usd')))
            + max(0.0, _as_float(data.get('nash_credit_usd')))
        )
    else:
        avail = max(0.0, bal)

    cid = data.get('client_id')
    account_id = f'client:{cid}' if cid is not None else None
    if avail > 0:
        msg = f'可用 ${avail:.4f}'
        if free > 0:
            msg += f'（免费 ${free:.2f} 不可用）'
    else:
        msg = f'可用额度已耗尽（免费 ${free:.2f} 不可用）' if free > 0 else '余额已耗尽'
    return {
        'ok': True,
        'remaining': round(avail, 6),
        'limit': round(max(0.0, bal), 6) if 'balance_usd' in data else None,
        'used': None,
        'extraFree': round(free, 6),
        'accountId': account_id,
        'message': msg,
    }


def _parse_amd(data):
    if 'daily_cost_remaining_usd' not in data and 'daily_cost_limit_usd' not in data:
        raise ValueError('余额返回缺少日额度字段')
    limit = max(0.0, _as_float(data.get('daily_cost_limit_usd')))
    used = max(0.0, _as_float(data.get('daily_cost_used_usd')))
    rem = max(0.0, _as_float(data['daily_cost_remaining_usd']) if 'daily_cost_remaining_usd' in data else (limit - used))
    all_cost = max(0.0, _as_float((data.get('all_time') or {}).get('cost')))
    org = data.get('organization_id')
    msg = f'今日剩余 ${rem:.4f} / ${limit:.2f}'
    if all_cost > 0:
        msg += f'（累计 ${all_cost:.4f}）'
    return {
        'ok': True,
        'remaining': round(rem, 6),
        'limit': round(limit, 6),
        'used': round(used, 6),
        'extraFree': 0.0,
        'accountId': f'org:{org}' if org else None,
        'message': msg,
    }


def _parse_kiro(data, base_quota_only=False):
    breakdowns = data.get('usageBreakdownList')
    if not isinstance(breakdowns, list) or not breakdowns:
        raise ValueError('未返回 Kiro 额度明细')
    base_rem = 0.0
    base_lim = 0.0
    base_used = 0.0
    bonus_rem = 0.0
    bonus_lim = 0.0
    bonus_used = 0.0
    for item in breakdowns:
        if not isinstance(item, dict):
            continue
        lim = _as_float(item.get('usageLimitWithPrecision') if item.get('usageLimitWithPrecision') is not None else item.get('usageLimit'))
        used = _as_float(item.get('currentUsageWithPrecision') if item.get('currentUsageWithPrecision') is not None else item.get('currentUsage'))
        base_lim += max(0.0, lim)
        base_used += max(0.0, used)
        base_rem += max(0.0, lim - used)
        for bonus in item.get('bonuses') or []:
            if not isinstance(bonus, dict) or str(bonus.get('status') or '').upper() != 'ACTIVE':
                continue
            blim = max(0.0, _as_float(bonus.get('usageLimit')))
            bused = max(0.0, _as_float(bonus.get('currentUsage')))
            bonus_lim += blim
            bonus_used += bused
            bonus_rem += max(0.0, blim - bused)

    paused = bool(base_quota_only and base_rem <= 0.0)
    rem = base_rem if base_quota_only else (base_rem + bonus_rem)
    extra_bonus = bonus_rem if base_quota_only else 0.0
    plan = str(((data.get('subscriptionInfo') or {}).get('subscriptionTitle')) or '').strip()
    uid = (data.get('userInfo') or {}).get('userId')
    parts = [f'{plan}'] if plan else []
    if base_quota_only:
        if paused:
            parts.append(f'基础额度已用完（已暂停，赠送 {bonus_rem:.2f} 未启用）' if bonus_rem > 0 else '基础额度已用完（已暂停）')
        elif bonus_rem > 0:
            parts.append(f'仅基础 {base_rem:.2f} credits（赠送 {bonus_rem:.2f} 未启用）')
        else:
            parts.append(f'仅基础 {base_rem:.2f} / {base_lim:.2f} credits')
    else:
        if bonus_rem > 0:
            parts.append(f'剩余 {rem:.2f} credits（基础 {base_rem:.2f} + 赠送 {bonus_rem:.2f}）')
        else:
            parts.append(f'剩余 {rem:.2f} / {base_lim:.2f} credits')
    return {
        'ok': True,
        'remaining': round(rem, 6),
        'limit': round(base_lim if base_quota_only else (base_lim + bonus_lim), 6),
        'used': round(base_used if base_quota_only else (base_used + bonus_used), 6),
        'extraFree': 0.0,
        'extraBonusCredits': round(extra_bonus, 6),
        'baseRemaining': round(base_rem, 6),
        'bonusRemaining': round(bonus_rem, 6),
        'paused': paused,
        'pauseReason': 'base_quota_exhausted' if paused else None,
        'accountId': f'kiro:{uid}' if uid else None,
        'plan': plan or None,
        'message': ' · '.join(parts),
    }


def _fetch_one_key(http, provider, profile, secret, balance_urls=None):
    pid = profile['id']
    base = str(provider.get('baseUrl') or '').strip().rstrip('/')
    override_url = (balance_urls or {}).get(pid)
    base_quota_only = bool(provider.get('baseQuotaOnly'))
    if pid == 'backboard':
        url = override_url or BACKBOARD_BALANCE_URL
        headers = {'X-API-Key': secret, 'Accept': 'application/json', 'User-Agent': 'context-gate-router-quota/1.0'}
        parser = _parse_backboard
    elif pid == 'amd_tokenfactory':
        url = override_url or (base + '/usage' if base.endswith('/v1') else base + '/v1/usage')
        headers = {'Authorization': 'Bearer ' + secret, 'Accept': 'application/json'}
        parser = _parse_amd
    elif pid == 'kiro':
        host = urllib.parse.urlsplit(base).hostname
        url = override_url or f'https://{host}/getUsageLimits?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST'
        headers = {'Authorization': 'Bearer ' + secret.strip(), 'TokenType': 'API_KEY', 'Accept': 'application/json'}
        parser = lambda data: _parse_kiro(data, base_quota_only=base_quota_only)
    else:
        raise ValueError('该供应商暂不支持查询密钥额度')

    data = _get_json(http, url, headers)
    return parser(data)


def _format_http_error(err):
    code = getattr(err, 'code', None)
    detail = _read_http_error(err)
    if code == 401:
        msg = '密钥无效或已停用（401）'
    elif code == 403:
        msg = '密钥被拒绝或已停用（403）'
    elif code == 429:
        msg = '已被限流（429）'
    else:
        msg = f'HTTP {code}'
    return code, (f'{msg} · {detail}' if detail and code not in (401, 403) else msg)


def _probe_key_task(http, provider, profile, key_row, secret, balance_urls):
    base_row = {
        'id': key_row['id'],
        'label': str(key_row.get('label') or ''),
        'enabled': bool(key_row.get('enabled')),
        'priority': key_row.get('priority'),
        'quotaKind': profile['kind'],
        'unit': profile['unit'],
        'ok': False,
        'status': None,
        'remaining': None,
        'limit': None,
        'used': None,
        'extraFree': 0.0,
        'extraBonusCredits': 0.0,
        'baseRemaining': key_row.get('baseRemaining'),
        'bonusRemaining': key_row.get('bonusRemaining'),
        'paused': bool(key_row.get('paused')),
        'pauseReason': key_row.get('pauseReason'),
        'accountId': None,
        'duplicateAccount': False,
        'latencyMs': None,
        'message': '',
    }
    started = time.monotonic()
    try:
        parsed = _fetch_one_key(http, provider, profile, secret, balance_urls=balance_urls)
        base_row.update(parsed)
        base_row['status'] = 200
    except urllib.error.HTTPError as err:
        code, msg = _format_http_error(err)
        base_row['status'] = code
        base_row['message'] = msg
    except ValueError as err:
        base_row['message'] = scrub_secrets(str(err))
    except (OSError, urllib.error.URLError, RuntimeError, json.JSONDecodeError) as err:
        base_row['message'] = '查询上游失败或超时：' + scrub_secrets(type(err).__name__)
    base_row['latencyMs'] = round((time.monotonic() - started) * 1000)
    return base_row


def _aggregate_provider_quotas(provider, profile, all_keys, results):
    enabled_total = 0.0
    all_alive_total = 0.0
    extra_free_total = 0.0
    extra_bonus_total = 0.0
    seen_enabled_accounts = set()
    seen_all_accounts = set()
    duplicate_accounts = 0

    for row in results:
        if not row['ok'] or row['remaining'] is None:
            continue
        rem = row['remaining']
        acc = row.get('accountId')
        all_key = acc if acc else ('key:' + str(row['id']))
        if all_key not in seen_all_accounts:
            seen_all_accounts.add(all_key)
            all_alive_total += rem
        if row['enabled']:
            if acc and acc in seen_enabled_accounts:
                row['duplicateAccount'] = True
                duplicate_accounts += 1
            else:
                if acc:
                    seen_enabled_accounts.add(acc)
                enabled_total += rem
                extra_free_total += row.get('extraFree') or 0.0
                extra_bonus_total += row.get('extraBonusCredits') or 0.0

    ok_rows = [r for r in results if r['ok']]
    enabled_rows = [r for r in results if r['enabled']]
    usable_rows = [
        r for r in enabled_rows
        if r['ok'] and not r.get('paused') and (r['remaining'] or 0.0) > 0
    ]
    paused_count = sum(1 for r in enabled_rows if r.get('paused'))
    return {
        'providerId': provider['id'],
        'providerName': provider['name'],
        'providerEnabled': bool(provider.get('enabled')),
        'baseQuotaOnly': bool(provider.get('baseQuotaOnly')),
        'quotaKind': profile['kind'],
        'unit': profile['unit'],
        'checkedAt': int(time.time() * 1000),
        'totalKeys': len(all_keys),
        'checkedKeys': len(results),
        'enabledChecked': len(enabled_rows),
        'okCount': len(ok_rows),
        'usableCount': len(usable_rows),
        'pausedCount': paused_count,
        'enabledTotal': round(enabled_total, 6),
        'allAliveTotal': round(all_alive_total, 6),
        'extraFreeTotal': round(extra_free_total, 6),
        'extraBonusCredits': round(extra_bonus_total, 6),
        'duplicateAccounts': duplicate_accounts,
        'keys': results,
    }


def query_provider_quotas(router, provider_id, include_disabled=True, balance_urls=None, provider=None, max_workers=8):
    """Query remaining quota/balance for one supported provider's keys."""
    if provider is None:
        provider = next((p for p in router.call('snapshot')['providers'] if p.get('id') == provider_id), None)
    if not provider:
        raise ValueError('找不到该供应商。')
    profile = quota_profile(provider)
    if not profile:
        raise ValueError('该供应商暂不支持查询密钥额度。')

    if profile['id'] == 'kiro' and not balance_urls:
        try:
            router.call('check_kiro_quotas', {'providerId': provider_id, 'includeDisabled': bool(include_disabled)})
        except ValueError:
            pass

    all_keys = router.call('list_provider_keys', {'providerId': provider_id})
    target_keys = all_keys if include_disabled else [k for k in all_keys if k.get('enabled')]

    # Read secrets sequentially via the loopback bridge before concurrent upstream HTTP.
    pending = []
    prefilled = {}
    for key_row in target_keys:
        kid = key_row['id']
        if key_row.get('hasSecret') is False:
            prefilled[kid] = {
                'id': kid, 'label': str(key_row.get('label') or ''), 'enabled': bool(key_row.get('enabled')),
                'priority': key_row.get('priority'), 'quotaKind': profile['kind'], 'unit': profile['unit'],
                'ok': False, 'status': None, 'remaining': None, 'limit': None, 'used': None,
                'extraFree': 0.0, 'accountId': None, 'duplicateAccount': False, 'latencyMs': 0, 'message': '待补密钥',
            }
            continue
        try:
            secret = router.call('reveal_provider_key', {'id': kid})
        except ValueError as err:
            prefilled[kid] = {
                'id': kid, 'label': str(key_row.get('label') or ''), 'enabled': bool(key_row.get('enabled')),
                'priority': key_row.get('priority'), 'quotaKind': profile['kind'], 'unit': profile['unit'],
                'ok': False, 'status': None, 'remaining': None, 'limit': None, 'used': None,
                'extraFree': 0.0, 'accountId': None, 'duplicateAccount': False, 'latencyMs': 0,
                'message': scrub_secrets(str(err)),
            }
            continue
        if not str(secret or '').strip():
            prefilled[kid] = {
                'id': kid, 'label': str(key_row.get('label') or ''), 'enabled': bool(key_row.get('enabled')),
                'priority': key_row.get('priority'), 'quotaKind': profile['kind'], 'unit': profile['unit'],
                'ok': False, 'status': None, 'remaining': None, 'limit': None, 'used': None,
                'extraFree': 0.0, 'accountId': None, 'duplicateAccount': False, 'latencyMs': 0, 'message': '密钥为空',
            }
            continue
        pending.append((key_row, secret))

    probed = {}
    if len(pending) == 1 or max_workers <= 1:
        for key_row, secret in pending:
            probed[key_row['id']] = _probe_key_task(router.http, provider, profile, key_row, secret, balance_urls)
    elif pending:
        workers = min(max(1, int(max_workers)), len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                (kr['id'], pool.submit(_probe_key_task, router.http, provider, profile, kr, sec, balance_urls))
                for kr, sec in pending
            ]
            for kid, fut in futures:
                probed[kid] = fut.result()

    ordered_results = [prefilled[k['id']] if k['id'] in prefilled else probed[k['id']] for k in target_keys]
    return _aggregate_provider_quotas(provider, profile, all_keys, ordered_results)


def query_all_quotas(router, include_disabled=False, balance_urls=None, max_workers=8):
    """Query all configured quota-capable providers and compute aggregate totals."""
    providers = router.call('snapshot').get('providers') or []
    supported_reports = []
    unsupported = []

    for provider in providers:
        prof = quota_profile(provider)
        if not prof:
            unsupported.append({'id': provider.get('id'), 'name': provider.get('name')})
            continue
        report = query_provider_quotas(
            router,
            provider.get('id'),
            include_disabled=include_disabled,
            balance_urls=balance_urls,
            provider=provider,
            max_workers=max_workers,
        )
        supported_reports.append(report)

    usd_balance = sum(r['enabledTotal'] for r in supported_reports if r['unit'] == 'USD' and r['quotaKind'] == 'balance')
    usd_daily = sum(r['enabledTotal'] for r in supported_reports if r['unit'] == 'USD' and r['quotaKind'] == 'daily')
    kiro_credits = sum(r['enabledTotal'] for r in supported_reports if r['quotaKind'] == 'credits')
    extra_free = sum(r['extraFreeTotal'] for r in supported_reports if r['unit'] == 'USD')
    extra_bonus_credits = sum(r.get('extraBonusCredits', 0.0) for r in supported_reports if r['quotaKind'] == 'credits')

    return {
        'checkedAt': int(time.time() * 1000),
        'includeDisabled': bool(include_disabled),
        'providers': supported_reports,
        'unsupportedProviders': unsupported,
        'totals': {
            'usdAvailable': round(usd_balance + usd_daily, 6),
            'usdBalance': round(usd_balance, 6),
            'usdDaily': round(usd_daily, 6),
            'kiroCredits': round(kiro_credits, 6),
            'extraFreeUsd': round(extra_free, 6),
            'extraBonusCredits': round(extra_bonus_credits, 6),
            'supportedProviders': len(supported_reports),
            'unsupportedProviders': len(unsupported),
            'checkedKeys': sum(r['checkedKeys'] for r in supported_reports),
            'usableKeys': sum(r['usableCount'] for r in supported_reports),
        },
    }
