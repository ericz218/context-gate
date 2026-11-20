"""ZCode model sync. Caller supplies router alias IDs; no network or Keychain.

No real account writes are performed on import. sync(..., apply=True) is explicit.
All returned values contain paths, IDs and counts only, never credential material.
"""
import copy
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path

PROVIDER_ID = 'local-model-router'
CLAUDE_PROVIDER_ID = 'lmr-claude'
BASE_URL = os.environ.get('LMR_ROUTER_URL', 'http://127.0.0.1:8787').rstrip('/') + '/v1'
AUTO_SYNC_COMMANDS = frozenset(('set_bedrock_model_enabled', 'upsert_model', 'delete_model', 'upsert_provider', 'delete_provider'))
BACKUP_KEEP = 10


def safe_path(path):
    p = Path(path)
    return not any(parent.is_symlink() for parent in (p, *p.parents))


def discover(home):
    home = Path(home)
    roots = [('default', home / '.zcode')]
    roots += [(p.name, p / '.zcode') for p in sorted(home.glob('zcode-account*'))
              if re.fullmatch(r'zcode-account[1-9][0-9]*', p.name)]
    return [{'id': name, 'path': str(root / 'v2/provider_config.json')}
            for name, root in roots if (root / 'v2/provider_config.json').is_file()
            and safe_path(root / 'v2/provider_config.json')]


def read_config(path):
    p = Path(path)
    if not safe_path(p) or not stat.S_ISREG(p.stat().st_mode):
        raise ValueError('Account configuration must be a regular file')
    raw = p.read_bytes()
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('Account configuration too large')
    d = json.loads(raw)
    if d.get('schemaVersion') != 1:
        raise ValueError('Unsupported ZCode provider configuration version')
    c = d.get('config', {})
    if not isinstance(c.get('providerConfigRules', {}).get('providerRules'), list):
        raise ValueError('Invalid provider rules')
    if not isinstance(c.get('modelConfigRules', {}), dict):
        raise ValueError('Invalid model rules')
    return d, raw


def lmr_rule(document):
    rows = document['config']['providerConfigRules']['providerRules']
    ids = [r.get('providerId') for r in rows if isinstance(r, dict)]
    if len(ids) != len(set(ids)) or len(ids) != len(rows):
        raise ValueError('Duplicate or invalid provider ID')
    for rule in rows:
        cfg = rule.get('config', {})
        if rule.get('providerId') == PROVIDER_ID:
            if (cfg.get('api') or {}).get('baseUrl', '').rstrip('/') != BASE_URL:
                raise ValueError('Existing router provider URL differs')
            return rule
    return None


def model_templates(documents):
    """Per-model config templates and one common optionSpecs, taken from readable accounts."""
    templates = {}
    common = None
    for d in documents:
        c = d['config']
        for rule in c['providerConfigRules']['providerRules']:
            if isinstance(rule, dict) and rule.get('providerId') == PROVIDER_ID:
                cfg = rule.get('config')
                if common is None and isinstance(cfg, dict) and isinstance(cfg.get('optionSpecs'), dict) and cfg['optionSpecs']:
                    common = copy.deepcopy(cfg['optionSpecs'])
        models = c.get('modelConfigRules', {})
        for key in ('providerModelRules', 'manualProviderModelRules'):
            rows = models.get(key)
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict) or r.get('providerId') not in (PROVIDER_ID, CLAUDE_PROVIDER_ID):
                    continue
                mid, cfg = r.get('modelId'), r.get('config')
                if not isinstance(mid, str) or mid in templates or not isinstance(cfg, dict):
                    continue
                if any(isinstance(cfg.get(k), dict) and cfg[k] for k in ('properties', 'optionSpecs')):
                    templates[mid] = copy.deepcopy(cfg)
    return templates, common


def fill_capabilities(cfg, mid, templates, common_specs, details):
    """Fill only missing keys; existing properties/optionSpecs are never touched."""
    tpl = (templates or {}).get(mid) or {}
    if 'properties' not in cfg:
        props = tpl.get('properties')
        if isinstance(props, dict) and props:
            cfg['properties'] = copy.deepcopy(props)
        else:
            props = {'supportsToolCall': True}
            info = (details or {}).get(mid) or {}
            if isinstance(info.get('supportsImage'), bool):
                props['inputFormat'] = {'supportsImage': info['supportsImage']}
            cw = info.get('contextWindow')
            if isinstance(cw, int) and not isinstance(cw, bool) and cw > 0:
                props['contextWindow'] = cw
            cfg['properties'] = props
    if 'optionSpecs' not in cfg:
        specs = tpl.get('optionSpecs')
        if not (isinstance(specs, dict) and specs):
            specs = common_specs
        if isinstance(specs, dict) and specs:
            cfg['optionSpecs'] = copy.deepcopy(specs)


def merge(document, aliases, source_rule=None, mirror=False, templates=None, common_specs=None, details=None):
    out = copy.deepcopy(document)
    c = out['config']
    rule = lmr_rule(out)
    if mirror and not aliases and rule is None:
        return out
    if rule is None:
        if source_rule is None:
            raise ValueError('No existing Local Model Router connection to reuse')
        rule = copy.deepcopy(source_rule)  # Opaque access block is retained, never inspected.
        rule['config']['personalModelIds'] = []
        rule['config']['modelOrder'] = []
        c['providerConfigRules']['providerRules'].append(rule)
        if 'providerOrder' in c and PROVIDER_ID not in c['providerOrder']:
            c['providerOrder'].append(PROVIDER_ID)
    rules = c.setdefault('modelConfigRules', {})
    smart = rules.setdefault('providerModelRules', [])
    manual = rules.setdefault('manualProviderModelRules', [])
    if not isinstance(smart, list) or not isinstance(manual, list):
        raise ValueError('Invalid model rules')

    # The installed Claude group has its own connection to the same router.
    # Route Kiro models there on both selected sync and automatic sync.
    claude = next((r for r in c['providerConfigRules']['providerRules']
                   if r.get('providerId') == CLAUDE_PROVIDER_ID), None)
    if claude is not None and (claude.get('config', {}).get('api') or {}).get('baseUrl', '').rstrip('/') != BASE_URL:
        claude = None
    kiro = [mid for mid in aliases if mid.startswith('kiro/')] if claude else []
    if claude:
        for key in ('personalModelIds', 'modelOrder'):
            existing = rule['config'].get(key, [])
            if not isinstance(existing, list):
                raise ValueError('Invalid router model membership')
            rule['config'][key] = [mid for mid in existing
                                   if mid not in kiro and not (mirror and mid.startswith('kiro/'))]
            if mirror:
                existing_claude = claude['config'].get(key, [])
                if not isinstance(existing_claude, list):
                    raise ValueError('Invalid Claude model membership')
                claude['config'][key] = [mid for mid in existing_claude
                                         if not mid.startswith('kiro/') or mid in kiro]
        for rows in (smart, manual):
            claude_ids = {r['modelId'] for r in rows if r.get('providerId') == CLAUDE_PROVIDER_ID}
            for r in rows[:]:
                mid = r.get('modelId')
                if r.get('providerId') != PROVIDER_ID or mid not in kiro:
                    continue
                if mid in claude_ids:
                    rows.remove(r)
                else:
                    r['providerId'] = CLAUDE_PROVIDER_ID
                    claude_ids.add(mid)
        if mirror:
            for r in smart + manual:
                mid = r.get('modelId')
                if (r.get('providerId') == CLAUDE_PROVIDER_ID and isinstance(mid, str)
                        and mid.startswith('kiro/') and mid not in kiro):
                    r.setdefault('config', {})['enabled'] = False

    merge_membership(rule, [mid for mid in aliases if mid not in kiro],
                     smart, manual, mirror, templates, common_specs, details)
    if kiro:
        merge_membership(claude, kiro, smart, manual, False, templates, common_specs, details)
    return out


def merge_membership(rule, aliases, smart, manual, mirror, templates, common_specs, details):
    provider_id = rule['providerId']
    rule['enabled'] = True
    cfg = rule['config']
    for key in ('personalModelIds', 'modelOrder'):
        existing = cfg.setdefault(key, [])
        if not isinstance(existing, list):
            raise ValueError('Invalid router model membership')
        if mirror:
            existing[:] = [mid for mid in existing if mid in aliases]
        existing.extend(mid for mid in aliases if mid not in existing)

    model_rules = {}
    for r in smart + manual:
        if r.get('providerId') == provider_id:
            model_rules.setdefault(r.get('modelId'), []).append(r)
    for mid in aliases:
        found = model_rules.get(mid)
        if not found:
            found = [{'providerId': provider_id, 'modelId': mid, 'config': {}}]
            smart.extend(found)
        for r in found:
            config = r.setdefault('config', {})
            config['enabled'] = True
            fill_capabilities(config, mid, templates, common_specs, details)
    if mirror:
        for mid, found in model_rules.items():
            if mid not in aliases:
                for r in found:
                    r.setdefault('config', {})['enabled'] = False


def commit(path, before, after):
    """Back up with owner-only permissions, detect changes, atomically replace."""
    p = Path(path)
    if not safe_path(p) or p.read_bytes() != before:
        raise RuntimeError('Account changed during synchronization; retry')
    backup = p.with_name(p.name + '.lmr-backup-' + str(time.time_ns()))
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(before)
        f.flush()
        os.fsync(f.fileno())
    fd, tmp = tempfile.mkstemp(prefix='.lmr-sync-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(after)
            f.flush()
            os.fsync(f.fileno())
        if not safe_path(p) or p.read_bytes() != before:
            raise RuntimeError('Account changed during synchronization; retry')
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    prune_backups(p)
    directory = os.open(p.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return str(backup)


def prune_backups(path, keep=BACKUP_KEEP):
    """Keep only the newest backups named '<file>.lmr-backup-<digits>' (regular files)."""
    p = Path(path)
    pattern = re.compile(re.escape(p.name) + r'\.lmr-backup-([0-9]+)')
    found = []
    for child in p.parent.iterdir():
        m = pattern.fullmatch(child.name)
        if m and child.is_file() and not child.is_symlink():
            found.append((int(m.group(1)), child))
    found.sort(key=lambda item: item[0], reverse=True)
    for _, child in found[keep:]:
        try:
            child.unlink()
        except OSError:
            pass


def sync(home, aliases, account_ids=None, apply=False, mirror=False, details=None):
    if not isinstance(aliases, list) or (not aliases and not mirror) or len(aliases) > 500:
        raise ValueError('Select at least one router model')
    if any(not isinstance(m, str) or not m or len(m) > 256 or any(ord(x) < 32 for x in m) for m in aliases):
        raise ValueError('Invalid router model ID')
    if account_ids is not None and (not isinstance(account_ids, list) or not account_ids
            or any(not isinstance(a, str) or not a for a in account_ids)):
        raise ValueError('Invalid ZCode account selection')
    aliases = list(dict.fromkeys(aliases))
    accounts = discover(home)
    by_id = {a['id']: a for a in accounts}
    chosen = list(by_id) if account_ids is None else list(dict.fromkeys(account_ids))
    if not chosen or any(a not in by_id for a in chosen):
        raise ValueError('Unknown ZCode account')
    loaded = {}
    source = None
    # Invalid source configuration fails closed; never print parser errors/content.
    for account in accounts:
        aid = account['id']
        try:
            d, raw = read_config(account['path'])
            rule = lmr_rule(d)
            loaded[aid] = (d, raw)
            if source is None and rule is not None:
                source = rule
        except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError):
            loaded[aid] = None
    templates, common_specs = model_templates([v[0] for v in loaded.values() if v is not None])
    results = []
    for aid in chosen:
        result = {'accountId': aid, 'ok': False, 'changed': False, 'message': ''}
        try:
            if loaded[aid] is None:
                raise ValueError('invalid configuration')
            d, raw = loaded[aid]
            updated = merge(d, aliases, source, mirror=mirror, templates=templates,
                            common_specs=common_specs, details=details)
            changed = updated != d
            if apply and changed:
                after = (json.dumps(updated, ensure_ascii=False, indent=2) + '\n').encode()
                commit(by_id[aid]['path'], raw, after)
            result.update(ok=True, changed=changed,
                          message='已同步，ZCode 会自动刷新。' if apply and changed
                          else '已包含所选模型。' if not changed else '可同步。')
        except (ValueError, OSError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError):
            result['message'] = '同步失败：配置无效、缺少路由连接或文件已被其他程序修改。'
        results.append(result)
    return {'results': results, 'modelCount': len(aliases)}


def available_models(snapshot):
    if snapshot.get('connected') is not True:
        raise ValueError('模型路由尚未连接。')
    rows = snapshot.get('models')
    if not isinstance(rows, list):
        raise ValueError('模型路由目录无效。')
    models = []
    seen = set()
    for row in rows:
        if row.get('enabled') is not True or row.get('providerEnabled') is not True:
            continue
        mid = row.get('modelId')
        if not isinstance(mid, str) or not mid or mid in seen:
            raise ValueError('模型路由目录含重复或无效 ID。')
        seen.add(mid)
        models.append({'id': mid, 'name': row.get('displayName') or mid})
    return models


def parse_modalities(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, list) and value:
        return value
    return None


def registry_rows(router):
    """Bedrock registry rows for capability details. Any failure yields an empty table."""
    try:
        data = router.call('list_bedrock_models', {'input': {'providerId': 0}})
    except Exception:
        return []
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if len(lists) == 1 else []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict)]


def model_details(router):
    """modelId -> {'supportsImage': bool, 'contextWindow': int}, only fields that can be read."""
    by_key = {}
    for row in registry_rows(router):
        for key in (row.get('inferenceProfileId'), row.get('modelId')):
            if isinstance(key, str) and key:
                by_key.setdefault(key, row)
    details = {}
    for m in router.snapshot().get('models') or []:
        if not isinstance(m, dict) or m.get('enabled') is not True or m.get('providerEnabled') is not True:
            continue
        mid = m.get('modelId')
        row = by_key.get(m.get('upstreamModel')) if isinstance(m.get('upstreamModel'), str) else None
        if not isinstance(mid, str) or row is None:
            continue
        info = {}
        mods = parse_modalities(row.get('inputModalities'))
        if mods is not None:
            info['supportsImage'] = 'IMAGE' in mods
        cw = row.get('contextWindow')
        if isinstance(cw, int) and not isinstance(cw, bool) and cw > 0:
            info['contextWindow'] = cw
        if info:
            details[mid] = info
    return details


def auto_sync(router, home):
    if not discover(home):
        return {'ok': True, 'accounts': 0, 'changed': 0, 'failed': 0}
    ids = [m['id'] for m in available_models(router.snapshot())]
    rows = sync(home, ids, None, apply=True, mirror=True, details=model_details(router))['results']
    return {'ok': all(r['ok'] for r in rows), 'accounts': len(rows),
            'changed': sum(1 for r in rows if r['changed']),
            'failed': sum(1 for r in rows if not r['ok'])}


def options(router, home):
    return {'models': available_models(router.snapshot()),
            'accounts': [{'id': a['id'], 'label': '默认账号' if a['id'] == 'default'
                          else 'ZCode 账号 ' + a['id'].removeprefix('zcode-account')}
                         for a in discover(home)], 'mode': 'merge'}


def sync_request(router, home, body, apply=True):
    if not isinstance(body, dict) or set(body) - {'model_ids', 'account_ids'}:
        raise ValueError('同步参数无效。')
    if 'account_ids' in body and not isinstance(body['account_ids'], list):
        raise ValueError('账号选择应为数组。')
    mids = body.get('model_ids')
    if not isinstance(mids, list) or not mids or any(not isinstance(m, str) for m in mids):
        raise ValueError('请选择有效的路由模型。')
    allowed = {m['id'] for m in available_models(router.snapshot())}
    if any(mid not in allowed for mid in mids):
        raise ValueError('所选模型已禁用或不在路由目录中，请刷新后重试。')
    return sync(home, mids, body.get('account_ids'), apply=apply, details=model_details(router))
