#!/usr/bin/env python3
"""Import per-request model/usage from local app logs into the shared ledger.

Covers traffic that cannot be intercepted:
- Claude Code CLI + Desktop: ~/.claude/projects/*/*.jsonl assistant entries
  carry message.model, full token usage and durationMs per API call. Subagent
  transcripts live one level deeper (projects/<proj>/<session>/subagents/
  agent-*.jsonl) and are imported too — they bypass the watch proxy exactly
  like the main session does.
- ZCode app: its own ledger ~/.zcode/cli/db/db.sqlite (model_usage) keeps one
  row per model request since 2026-09-15, including provider_id and duration_ms; the app's
  rollout model-io files are pruned after days, so the DB is the source.
- Codex CLI: ~/.codex/sessions/**/rollout-*.jsonl token_usage_record entries
  carry usage per response; the model comes from turn_context payloads.
  A session DeepAI Code launched is billed to DeepAI Code (Codex access),
  except turns whose provider is an explicit other upstream such as the
  built-in openai provider (api.openai.com), which stay on Codex.
- DeepAI Code direct calls: pi session jsonl under
  ~/.deepai-code/userdata/deepai/pi/deepai/sessions. Assistant usage is the
  measured call. Embedded cost fields are ignored; prices come from the
  shared rules.
- Cursor through DeepAI Code: provider event logs
  ~/.deepai-code/userdata/logs/provider/events*.log, run.completed usage
  only. There is no separate Cursor platform.
- Local Model Router: the read-only requests table in router.db, including
  requests whose measured usage is still NULL.
- Antigravity (desktop + agy CLI): per-conversation SQLite DBs under
  ~/.gemini/antigravity*/conversations/. steps.step_payload holds transcript
  JSON whose PLANNER_RESPONSE entries carry real input/output/cache_read
  tokens with created_at; gen_metadata maps each generation's
  last_step_index to its model (a display name like "Claude Opus 4.6
  (Thinking)" or a gemini-* id). Token rows arrive only in transcript-export
  steps, so coverage lags live sessions — imported as-is, never estimated.
  The DBs stay locked/WAL while the app runs, so they are read immutable
  from a temp copy and never written.

Accounting-only, like the watch proxies. Self-contained (no repository
imports) so the installed copy runs from ~/.local/state under LaunchAgents.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from itertools import chain
from pathlib import Path

STATE = Path(os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate')).expanduser()
CLAUDE_PROJECTS = Path.home() / '.claude/projects'
ZCODE_DB = Path.home() / '.zcode/cli/db/db.sqlite'
ROUTER_DB = Path(os.environ.get(
    'ROUTER_DB', '~/Library/Application Support/com.localmodelrouter.desktop/router.db')).expanduser()
# Both connections are managed by console_zcode_sync and point at this router.
ROUTER_PROVIDER_IDS = ('local-model-router', 'lmr-claude')
CODEX_SESSIONS = Path.home() / '.codex/sessions'
ANTIGRAVITY_ROOTS = (Path.home() / '.gemini/antigravity',
                     Path.home() / '.gemini/antigravity-cli')
DEEPAI_PI_ROOT = Path.home() / '.deepai-code/userdata/deepai/pi/deepai/sessions'
DEEPAI_PROVIDER_LOGS = Path.home() / '.deepai-code/userdata/logs/provider'
# Codex's built-in "openai" provider is api.openai.com. openai_token_sharing
# is DeepAI Code's Codex subscription-sharing route.
FOREIGN_CODEX_PROVIDERS = {'openai'}
DEEPAI_CODEX_PROVIDERS = {'openai_token_sharing'}
DEEPAI_CODEX_RECLASS_KEY = 'deepai-codex-reclass-v1'
DEEPAI_ACCESS = ('codex', 'cursor', 'direct')
ANTIGRAVITY_DISPLAY_MODELS = {
    'Claude Opus 4.6 (Thinking)': 'claude-opus-4-6-thinking',
    'Claude Sonnet 4.6 (Thinking)': 'claude-sonnet-4-6',
    'Claude Sonnet 4.6': 'claude-sonnet-4-6',
    'Gemini 3.8 Flash (High)': 'gemini-3.8-flash-high',
    'Gemini 3.8 Flash (Medium)': 'gemini-3.8-flash-medium',
    'Gemini 3.8 Flash (Low)': 'gemini-3.8-flash-low',
    'GPT-OSS 120B (Medium)': 'gpt-oss-120b-medium',
}
# gen_metadata stores some model ids truncated with a trailing '-n' marker
# (e.g. 'gemini-3.8-flash-n'); the effort suffix only exists in the display
# name, so these normalize to the bare model id. Protobuf-era ids carry a
# '-tiered'/'-trial' serving suffix instead; both normalize to the public
# model id so pricing/display keep working.
ANTIGRAVITY_MODEL_ALIASES = {'gemini-3.8-flash-n': 'gemini-3.8-flash',
                             'gemini-3.8-flash-tiered': 'gemini-3.8-flash',
                             'gemini-4-argon-trial': 'gemini-4-argon'}
_ANTIGRAVITY_MODEL_ENUM = re.compile(r'model_enum\s*.{0,4}?(MODEL_[A-Z0-9_]+)', re.S)
_ANTIGRAVITY_LAST_STEP = re.compile(r'last_step_index\s*.{0,4}?(\d+)', re.S)
_ANTIGRAVITY_GEN_MODEL = re.compile(
    r'(claude-opus-[a-z0-9.\-]+|claude-sonnet-[a-z0-9.\-]+|gemini-[a-z0-9.\-]+|gpt-oss-[a-z0-9.\-]+)')
_ANTIGRAVITY_GEN_DISPLAY = re.compile(
    r'((?:Claude (?:Opus|Sonnet)|Gemini|GPT-OSS)[ -~]{0,40}?\((?:Thinking|High|Medium|Low)\))')
ZCODE_DB_KEY = 'zcode-db-completed-ms'
ZCODE_PROVIDER_BACKFILL_KEY = 'zcode-provider-id-backfill-v1'
# Completed rows can appear (running→completed) after started_at; re-scan a
# lookback window so late completions are not missed past the watermark.
ZCODE_DB_LOOKBACK_MS = 3_600_000


def load_rules():
    rules = []
    try:
        user = json.loads((STATE / 'prices.json').read_text()).get('rules')
        if isinstance(user, list):
            rules = [r for r in user if isinstance(r, dict) and isinstance(r.get('match'), str)]
    except (OSError, ValueError):
        pass
    for rule in rules:
        for key in ('input', 'output', 'cache_read', 'cache_write'):
            value = rule.get(key)
            rule[key] = max(0.0, float(value)) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if rule.get('input') is None:
            continue
        rule['input'] = rule['input'] or 0.0
        rule['cache_read'] = rule['cache_read'] if rule.get('cache_read') is not None else round(rule['input'] * 0.1, 6)
        rule['cache_write'] = rule['cache_write'] if rule.get('cache_write') is not None else round(rule['input'] * 1.25, 6)
        rule['output'] = rule['output'] or 0.0
    return [r for r in rules if r.get('input') is not None]


def open_ledger():
    connection = sqlite3.connect(STATE / 'tokens.sqlite3')
    connection.execute('BEGIN IMMEDIATE')
    connection.execute('CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER)')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_turns_at ON turns(at)')
    cols = {r[1] for r in connection.execute('PRAGMA table_info(turns)')}
    for name, kind in (('ready', 'INTEGER'), ('jev_actual_input', 'INTEGER'), ('jev_actual_output', 'INTEGER'), ('model', 'TEXT'), ('cache_creation', 'INTEGER'), ('duration_ms', 'REAL'), ('provider_id', 'TEXT'), ('account', 'TEXT'), ('kiro_credits', 'REAL'), ('context_usage_percent', 'REAL')):
        if name not in cols:
            connection.execute(f'ALTER TABLE turns ADD COLUMN {name} {kind}')
    return connection


def claude_account():
    """Current Claude Code account label (email preferred); None when unknown."""
    try:
        data = json.loads((Path.home() / '.claude.json').read_text())
    except (OSError, ValueError):
        return None
    oauth = data.get('oauthAccount') if isinstance(data.get('oauthAccount'), dict) else {}
    for key in ('emailAddress', 'email'):
        value = oauth.get(key)
        if isinstance(value, str) and '@' in value:
            return value
    user = data.get('userID')
    return str(user) if isinstance(user, (str, int)) and user else None


def codex_account():
    """Current Codex CLI account label from the local auth file; never a token value."""
    try:
        tokens = json.loads((Path.home() / '.codex/auth.json').read_text()).get('tokens')
    except (OSError, ValueError):
        return None
    if not isinstance(tokens, dict):
        return None
    id_token = tokens.get('id_token')
    if isinstance(id_token, str) and id_token.count('.') >= 2:
        try:
            payload = id_token.split('.')[1]
            payload += '=' * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            for key in ('email', 'preferred_username'):
                value = claims.get(key)
                if isinstance(value, str) and value:
                    return value
        except ValueError:
            pass
    for key in ('account_id', 'email'):
        value = tokens.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def existing_fingerprints(connection):
    """Two dedup layers. External: watch/gateway rows only — identical nearby
    calls from any import source must not double-count them, while re-parses
    (same row id) still update via REPLACE. All: every ledger row — used only
    by sources whose requests may also exist under a retired source's row id
    (zcode db vs the old model-io imports)."""
    fingerprints={'external':{},'all':{}}
    for row_id, at, platform, model, actual_input, actual_output, provider_id in connection.execute('SELECT id,at,platform,model,actual_input,actual_output,provider_id FROM turns WHERE sent=1'):
        if None in (at, actual_input, actual_output):
            continue
        key=(platform, model, actual_input, actual_output)
        fingerprints['all'].setdefault(key, []).append((at, row_id, provider_id))
        if not row_id.startswith('imp-'):
            fingerprints['external'].setdefault(key, []).append((at, row_id, provider_id))
    return fingerprints


def is_duplicate(fingerprints, platform, model, at, actual_input, actual_output, record_id, dedup_all=False, provider_id=None):
    layers=('external','all') if dedup_all else ('external',)
    for layer in layers:
        for other_at, other_id, other_provider_id in fingerprints[layer].get((platform, model, actual_input, actual_output), ()):
            if other_id == record_id:
                continue
            if (record_id.startswith('imp-zcode-') and other_id.startswith('imp-zcode-') and
                    provider_id is not None and other_provider_id is not None):
                continue
            if abs(other_at - at) <= 600:
                return True
    return False


def parse_iso(text):
    try:
        import calendar
        base, _, frac = text.partition('.')
        # Antigravity stamps are '...Z' with no fractional part; strptime
        # rejects the trailing Z, so only strip it when there is no fraction.
        epoch = calendar.timegm(time.strptime(base[:-1] if not frac and base.endswith('Z') else base, '%Y-%m-%dT%H:%M:%S'))
        return epoch + float('0.' + frac[:-1]) if frac else float(epoch)
    except (ValueError, AttributeError):
        return None


def iter_new_text(path, offsets):
    """Yield decoded text of the not-yet-processed tail of a log file."""
    try:
        size = path.stat().st_size
    except OSError:
        return
    start = offsets.get(str(path), 0)
    if size < start:
        start = 0
    if size == start:
        return
    try:
        with open(path, 'rb') as file:
            file.seek(start)
            tail = file.read(size - start)
        # A live writer can leave a partial JSON/UTF-8 line at EOF. Only
        # advance through complete records so the next run retries that tail.
        end = tail.rfind(b'\n') + 1
        if not end:
            return
        offsets[str(path)] = start + end
        yield tail[:end].decode('utf-8', errors='replace')
    except OSError:
        return


def claude_entries(text):
    for line in text.splitlines():
        if '"type":"assistant"' not in line.replace(' ', ''):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get('type') != 'assistant':
            continue
        message = entry.get('message') or {}
        usage = message.get('usage') or {}
        model = message.get('model')
        plain = usage.get('input_tokens')
        if not isinstance(model, str) or not isinstance(plain, int) or plain < 0:
            continue
        if model == '<synthetic>':
            continue
        creation = usage.get('cache_creation_input_tokens') or 0
        read = usage.get('cache_read_input_tokens') or 0
        output = usage.get('output_tokens') or 0
        duration = entry.get('durationMs')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
            duration = None
        at = parse_iso(entry.get('timestamp') or '')
        if at is None:
            continue
        key = str(message.get('id') or '') + '|' + str(entry.get('requestId') or '') + '|' + str(at)
        yield at, model, plain + creation + read, output, read, creation, duration, key


def _nonneg_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _count(value):
    """Missing counts as 0. A present but unusable value is an error (None)."""
    if value is None:
        return 0
    return _nonneg_int(value)


def _route_text(value, limit=300):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _route_fields(payload):
    """Pull originator, model provider and base URL out of one Codex payload."""
    if not isinstance(payload, dict):
        return None, None, None
    settings = payload.get('thread_settings') if isinstance(payload.get('thread_settings'), dict) else {}
    origin = _route_text(payload.get('originator'), 80)
    provider = None
    for source in (payload, settings):
        for key in ('model_provider_id', 'model_provider'):
            value = _route_text(source.get(key), 80)
            if value:
                provider = value
                break
        if provider:
            break
    base = None
    for source in (payload, settings):
        for key in ('base_url', 'baseUrl', 'openai_base_url'):
            value = _route_text(source.get(key))
            if value:
                base = value
                break
        if base:
            break
    return origin, provider, base


def codex_bill_target(originator, model_provider, base_url=None):
    """Return (platform, provider_id) for one Codex turn.

    DeepAI Code sessions bill to deepai with access 'codex'. An explicit other
    upstream — the built-in openai provider, or a base URL on api.openai.com —
    stays on Codex even when DeepAI Code launched the session.
    """
    provider = (model_provider or '').strip().lower()
    host = (base_url or '').lower()
    if 'api.openai.com' in host or provider in FOREIGN_CODEX_PROVIDERS:
        return 'codex', None
    if (originator or '') == 'DeepAI Code' or provider in DEEPAI_CODEX_PROVIDERS or provider.startswith('deepai'):
        return 'deepai', 'codex'
    return 'codex', None


def codex_file_may_bill_deepai(route):
    if not isinstance(route, dict):
        return False
    origin = route.get('originator') or ''
    provider = (route.get('provider') or '').strip().lower()
    return origin == 'DeepAI Code' or provider in DEEPAI_CODEX_PROVIDERS or provider.startswith('deepai')


def peek_codex_route(path):
    """Route from the first record. None when the file cannot be read."""
    try:
        with path.open('r', errors='replace') as handle:
            line = handle.readline()
    except OSError:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return {}
    payload = entry.get('payload') if isinstance(entry, dict) else None
    origin, provider, base = _route_fields(payload)
    return {'originator': origin, 'provider': provider, 'base_url': base}


def _merge_route(route, origin, provider, base):
    route = dict(route or {})
    if origin:
        route['originator'] = origin
    if provider:
        route['provider'] = provider
    if base:
        route['base_url'] = base
    return route


def codex_routed_entries(text, known_model=None, known_route=None):
    """Like codex_entries, plus the billing platform of each usage record.

    Entries are 10-tuples: the usual 8 fields, then platform and provider_id.
    known_route is the originator/provider/base_url seen in earlier chunks.
    """
    model = known_model
    route = dict(known_route or {})
    entries = []
    for line in text.splitlines():
        if ('"token_usage_record"' not in line and '"turn_context"' not in line
                and '"session_meta"' not in line and '"thread_settings_applied"' not in line):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        payload = entry.get('payload') if isinstance(entry.get('payload'), dict) else {}
        kind = entry.get('type')
        if kind == 'session_meta' or payload.get('type') == 'thread_settings_applied':
            origin, provider, base = _route_fields(payload if kind == 'session_meta' else payload)
            if kind != 'session_meta':
                origin = None
            route = _merge_route(route, origin, provider, base)
            continue
        if kind == 'turn_context':
            value = payload.get('model')
            if isinstance(value, str) and value:
                model = value
            continue
        usage = payload.get('usage')
        response_id = payload.get('response_id')
        at = parse_iso(entry.get('timestamp') or '')
        if not isinstance(usage, dict) or not response_id or at is None:
            continue
        input_total = usage.get('input_tokens')
        if not isinstance(input_total, int) or isinstance(input_total, bool) or input_total < 0:
            continue
        platform, provider_id = codex_bill_target(route.get('originator'), route.get('provider'), route.get('base_url'))
        entries.append((at, model, input_total, usage.get('output_tokens') or 0,
                        usage.get('cached_input_tokens') or 0, usage.get('cache_write_input_tokens') or 0,
                        None, str(response_id), platform, provider_id))
    return entries, model, route


def codex_entries(text, known_model=None):
    """Return ([entries], last_model_seen) for one chunk of a rollout file.

    Entries are (at, model, input, output, cached, creation, duration, key)
    tuples. The model lives in turn_context payloads that precede each turn's
    usage records; known_model seeds chunks that start mid-turn.
    """
    entries, model, _route = codex_routed_entries(text, known_model)
    return [entry[:8] for entry in entries], model


def deepai_direct_entries(text):
    """Assistant turns from a DeepAI Code pi session. Input includes cache."""
    entries = []
    for line in text.splitlines():
        if '"usage"' not in line or '"assistant"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get('message') if isinstance(entry.get('message'), dict) else None
        if not message or message.get('role') != 'assistant':
            continue
        usage = message.get('usage') if isinstance(message.get('usage'), dict) else None
        if not usage:
            continue
        plain = _nonneg_int(usage.get('input') if 'input' in usage else usage.get('input_tokens'))
        output = _count(usage.get('output') if 'output' in usage else usage.get('output_tokens'))
        cached = _count(usage.get('cacheRead') if 'cacheRead' in usage else usage.get('cache_read_input_tokens'))
        creation = _count(usage.get('cacheWrite') if 'cacheWrite' in usage else usage.get('cache_creation_input_tokens'))
        if plain is None or None in (output, cached, creation):
            continue
        model = message.get('model') or message.get('responseModel')
        if not isinstance(model, str) or not model:
            continue
        at = parse_iso(entry.get('timestamp') or '')
        if at is None:
            continue
        duration = message.get('durationMs')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
            duration = None
        key = str(message.get('responseId') or '') + '|' + str(entry.get('id') or '')
        if key == '|':
            continue
        entries.append((at, model, plain + cached + creation, output, cached, creation, duration, key))
    return entries


_LOG_STAMP = re.compile(r'^\[(\d{4}-\d{2}-\d{2}T[^\]]+)\]')


def deepai_cursor_entries(text):
    """Completed Cursor runs recorded by DeepAI Code. No separate Cursor ledger."""
    entries = []
    for line in text.splitlines():
        if 'run.completed' not in line or ('"provider":"cursor"' not in line and '"provider": "cursor"' not in line):
            continue
        stamp = _LOG_STAMP.match(line)
        marker = line.find('NTIVE:')
        if stamp is None or marker < 0:
            continue
        try:
            event = json.loads(line[marker + len('NTIVE:'):].strip())
        except ValueError:
            continue
        if event.get('provider') != 'cursor':
            continue
        payload = (event.get('event') or {}).get('payload') if isinstance(event.get('event'), dict) else None
        if not isinstance(payload, dict) or payload.get('type') != 'run.completed':
            continue
        result = payload.get('result') if isinstance(payload.get('result'), dict) else {}
        usage = result.get('usage') if isinstance(result.get('usage'), dict) else None
        if not usage:
            continue
        plain = _nonneg_int(usage.get('inputTokens'))
        output = _count(usage.get('outputTokens'))
        cached = _count(usage.get('cacheReadTokens'))
        creation = _count(usage.get('cacheWriteTokens'))
        if plain is None or None in (output, cached, creation):
            continue
        model = None
        model_info = result.get('model')
        if isinstance(model_info, dict) and isinstance(model_info.get('id'), str) and model_info.get('id'):
            model = model_info['id']
        elif isinstance(model_info, str) and model_info:
            model = model_info
        if not model:
            model = 'cursor-unknown'
        # Cursor's catalog slug "default" is Auto, not an unnamed model.
        # Price rules match Auto / cursor-auto / default to the Grok 4.7 rate.
        elif model.strip().lower() in ('default', 'auto', 'cursor-auto'):
            model = 'Auto'
        at = parse_iso(stamp.group(1))
        if at is None:
            continue
        duration = result.get('durationMs')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
            duration = None
        key = str(result.get('requestId') or result.get('id') or '')
        if not key:
            continue
        exit_code = 0 if result.get('status') == 'finished' else 1
        entries.append((at, model, plain + cached + creation, output, cached, creation, duration, key, exit_code))
    return entries


def zcode_db_rows(watermark_ms):
    """Completed model_usage rows finished after the watermark (ms epoch)."""
    if not ZCODE_DB.is_file():
        return
    try:
        db = sqlite3.connect('file:' + str(ZCODE_DB) + '?mode=ro', uri=True, timeout=2)
    except sqlite3.Error:
        return
    try:
        has_provider_id = 'provider_id' in {row[1] for row in db.execute('PRAGMA table_info(model_usage)')}
        provider_column = 'provider_id' if has_provider_id else 'NULL'
        cursor = db.execute(
            'SELECT id, model_id, started_at, completed_at, duration_ms, input_tokens, output_tokens,'
            f' cache_read_input_tokens, cache_creation_input_tokens, {provider_column} FROM model_usage'
            " WHERE status='completed' AND COALESCE(completed_at, started_at) > ?"
            ' ORDER BY COALESCE(completed_at, started_at)', (watermark_ms - ZCODE_DB_LOOKBACK_MS,))
        for row in cursor:
            row_id, model, started, completed, duration, input_total, output, read, creation, provider_id = row
            if not model or not isinstance(input_total, int) or input_total < 0:
                continue
            at = (completed or started) / 1000.0
            duration = float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0 else None
            marker = int(completed or started)
            yield at, model, input_total, output or 0, read or 0, creation or 0, duration, row_id, marker, provider_id
    except sqlite3.Error:
        return
    finally:
        db.close()


def _antigravity_model_of(gen_texts, step_index):
    """Model of the generation whose last_step_index first covers step_index.

    gen_texts are (last_step_index, raw_text) pairs sorted by last_step_index.
    Per-generation metadata carries its own model: a display name (Claude /
    GPT-OSS), a gemini-* id, or a MODEL_PLACEHOLDER enum with the display
    name next to it. Returns None when attribution is unknown."""
    for last_step, text in gen_texts:
        if last_step is None or step_index > last_step:
            continue
        display = _ANTIGRAVITY_GEN_DISPLAY.search(text)
        if display:
            name = display.group(1)
            return ANTIGRAVITY_DISPLAY_MODELS.get(name, name)
        found = _ANTIGRAVITY_GEN_MODEL.search(text)
        if found:
            return ANTIGRAVITY_MODEL_ALIASES.get(found.group(1), found.group(1))
        enum = _ANTIGRAVITY_MODEL_ENUM.search(text)
        return enum.group(1) if enum else None
    return None


def _pb_varint(data, pos):
    value = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            break
    return None, pos


def _pb_fields(data):
    """Yield (field_no, wire_type, value) for one protobuf message.

    Deliberately dependency-free and total: malformed tails simply end the
    iteration instead of raising, so a partial live DB can never break import."""
    pos = 0
    while pos < len(data):
        tag, pos = _pb_varint(data, pos)
        if tag is None:
            return
        field_no, wire = tag >> 3, tag & 7
        if field_no <= 0:
            return
        if wire == 0:
            value, pos = _pb_varint(data, pos)
            if value is None:
                return
            yield field_no, wire, value
        elif wire == 2:
            length, pos = _pb_varint(data, pos)
            if length is None or pos + length > len(data):
                return
            yield field_no, wire, bytes(data[pos:pos + length])
            pos += length
        elif wire == 1:
            if pos + 8 > len(data):
                return
            yield field_no, wire, bytes(data[pos:pos + 8])
            pos += 8
        elif wire == 5:
            if pos + 4 > len(data):
                return
            yield field_no, wire, bytes(data[pos:pos + 4])
            pos += 4
        else:
            return


def _pb_get(data, path):
    """All values at a nested field path; length-delimited levels only descend
    into sub-messages, varint leaves return ints."""
    current = [data]
    for depth, wanted in enumerate(path):
        following = []
        last = depth == len(path) - 1
        for blob in current:
            if not isinstance(blob, (bytes, bytearray)):
                continue
            for field_no, wire, value in _pb_fields(bytes(blob)):
                if field_no != wanted:
                    continue
                if last or wire == 2:
                    following.append(value)
        current = following
    return current


def _pb_text(value):
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode('utf-8')
        except UnicodeDecodeError:
            return None
    return value if isinstance(value, str) else None


def _antigravity_proto_model(data):
    """Per-generation model from protobuf gen_metadata (field 1.19 id, else the
    field 1.20 key/value pair 'model_enum'). Mirrors the text-path fallbacks."""
    model_id = _pb_text((_pb_get(data, (1, 19)) or [None])[0])
    if model_id:
        found = _ANTIGRAVITY_GEN_MODEL.search(model_id)
        if found:
            return ANTIGRAVITY_MODEL_ALIASES.get(found.group(1), found.group(1))
        return model_id
    for pair in _pb_get(data, (1, 20)):
        kv = {}
        for field_no, wire, value in _pb_fields(pair):
            if wire == 2 and field_no in (1, 2):
                kv[field_no] = _pb_text(value)
        if kv.get(1) == 'model_enum' and kv.get(2):
            return kv[2]
    return None


def _antigravity_proto_entries(path, db):
    """Yield usage rows from protobuf gen_metadata when the transcript-JSON
    export is absent (Antigravity >= the build that switched gen_metadata to
    protobuf; verified against the JSON rows of the same conversation DB):
    field 1.4 = usage (1: context-size enum, 2: plain input, 3: output,
    10: thinking; output total = 3 + 10). Field 1.9.10.1 is the total context
    size after the call; the protobuf build no longer stores the cache-read
    split, so cache read is estimated as max(0, context - plain input) and
    total input = plain + read = context size when known. Against the
    transcript-JSON rows of the same DB (input_tokens plain-only,
    cache_read_tokens separate) this estimate is within ~2% on same-model
    rows; context-compaction steps can make a single row noisy, but totals
    stop under-counting long conversations by an order of magnitude. The
    call is dated by the step whose metadata carries the same plain input
    (steps.metadata field 9.2 = this generation's field 1.4.2, field 1.1 =
    step start epoch); field 1.20 'last_step_index' attributes the step.
    Cache creation is not stored separately and stays 0."""
    try:
        step_sizes = {}
        for metadata, in db.execute('SELECT metadata FROM steps WHERE metadata IS NOT NULL'):
            if not isinstance(metadata, (bytes, bytearray)):
                continue
            starts = _pb_get(bytes(metadata), (1, 1))
            sizes = _pb_get(bytes(metadata), (9, 2))
            if starts and sizes and isinstance(starts[0], int) and isinstance(sizes[0], int):
                step_sizes.setdefault(sizes[0], starts[0])
        for (data,) in db.execute('SELECT data FROM gen_metadata ORDER BY idx'):
            if not isinstance(data, (bytes, bytearray)):
                continue
            data = bytes(data)
            usage = (_pb_get(data, (1, 4)) or [None])[0]
            if not isinstance(usage, (bytes, bytearray)):
                continue
            values = {}
            for field_no, wire, value in _pb_fields(bytes(usage)):
                if wire == 0:
                    values[field_no] = value
            # Signed varints arrive sign-extended (negative => huge uint64);
            # token counts are small positives, anything else is not a count.
            values = {k: v for k, v in values.items() if 0 <= v < 1 << 62}
            plain_input, plain_output = values.get(2), values.get(3)
            if not isinstance(plain_input, int) or plain_input < 0:
                continue
            if not isinstance(plain_output, int) or plain_output < 0:
                continue
            cumulative = (_pb_get(data, (1, 9, 10, 1)) or [None])[0]
            if not isinstance(cumulative, int) or cumulative < 0:
                cumulative = None
            read = max(0, cumulative - plain_input) if cumulative is not None else 0
            total_input = plain_input + read
            thinking = values.get(10)
            thinking = thinking if isinstance(thinking, int) and thinking >= 0 else 0
            kv = {}
            for pair in _pb_get(data, (1, 20)):
                pair_kv = {}
                for field_no, wire, value in _pb_fields(pair):
                    if wire == 2 and field_no in (1, 2):
                        pair_kv[field_no] = _pb_text(value)
                if isinstance(pair_kv.get(1), str):
                    kv[pair_kv[1]] = pair_kv.get(2)
            try:
                last_step = int(kv.get('last_step_index'))
            except (TypeError, ValueError):
                continue
            at = step_sizes.get(plain_input)
            if at is None:
                continue
            model = _antigravity_proto_model(data) or 'antigravity-unknown'
            yield (float(at), model, total_input, plain_output + thinking, read, 0,
                   None, f'{path.stem}|p{last_step}|{at}')
    except sqlite3.Error:
        return


def antigravity_entries(path):
    """(at, model, input, output, cached, creation, duration, key) tuples from
    one Antigravity conversation DB. Real per-call tokens live in transcript
    JSON embedded in steps.step_payload (PLANNER_RESPONSE entries); the model
    is attributed from gen_metadata. Read-only: the live DB is copied to a
    temp file and opened immutable, so the running app is never disturbed."""
    try:
        handle, temp_name = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        shutil.copyfile(path, temp_name)
    except OSError:
        return
    try:
        try:
            db = sqlite3.connect('file:' + temp_name + '?mode=ro&immutable=1', uri=True, timeout=2)
        except sqlite3.Error:
            return
        try:
            gen_texts = []
            for (data,) in db.execute('SELECT data FROM gen_metadata ORDER BY idx'):
                if not isinstance(data, (bytes, bytearray)):
                    continue
                text = bytes(data).decode('utf-8', errors='ignore')
                match = _ANTIGRAVITY_LAST_STEP.search(text)
                gen_texts.append((int(match.group(1)) if match else None, text))
            gen_texts.sort(key=lambda item: (item[0] is None, item[0] or 0))
            decoder = json.JSONDecoder()
            seen = set()
            produced = 0
            for (payload,) in db.execute(
                    "SELECT step_payload FROM steps WHERE step_payload LIKE '%input_tokens%'"):
                if not isinstance(payload, (bytes, bytearray)):
                    continue
                text = bytes(payload).decode('utf-8', errors='ignore')
                position = 0
                while True:
                    start = text.find('{"step_index"', position)
                    if start < 0:
                        break
                    try:
                        entry, end = decoder.raw_decode(text[start:])
                    except ValueError:
                        position = start + 5
                        continue
                    position = start + end
                    if not isinstance(entry, dict) or entry.get('type') != 'PLANNER_RESPONSE':
                        continue
                    if entry.get('status') not in (None, 'DONE'):
                        continue
                    plain = entry.get('input_tokens')
                    if not isinstance(plain, int) or isinstance(plain, bool) or plain < 0:
                        continue
                    output = entry.get('output_tokens')
                    read = entry.get('cache_read_tokens')
                    creation = entry.get('cache_creation_tokens', entry.get('cache_write_tokens'))
                    step_index = entry.get('step_index')
                    at = parse_iso(entry.get('created_at') or '')
                    if at is None or not isinstance(step_index, int):
                        continue
                    dedup = (step_index, at, plain)
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    model = _antigravity_model_of(gen_texts, step_index) or 'antigravity-unknown'
                    produced += 1
                    yield (at, model, plain + (read or 0) + (creation or 0),
                           output if isinstance(output, int) and output >= 0 else 0,
                           read if isinstance(read, int) and read >= 0 else 0,
                           creation if isinstance(creation, int) and creation >= 0 else 0,
                           None, f'{path.stem}|{step_index}|{entry.get("created_at")}')
            if not produced:
                # Newer Antigravity builds no longer embed transcript JSON;
                # the same per-call usage lives in protobuf gen_metadata.
                yield from _antigravity_proto_entries(path, db)
        except sqlite3.Error:
            return
        finally:
            db.close()
    finally:
        try:
            os.unlink(temp_name)
        except OSError:
            pass


def backfill_zcode_provider_ids(connection):
    """Update only provider_id on already-imported ZCode rows; never rebuild usage."""
    if not ZCODE_DB.is_file():
        return False
    try:
        db = sqlite3.connect('file:' + str(ZCODE_DB) + '?mode=ro', uri=True, timeout=2)
    except sqlite3.Error:
        return False
    connection.execute('SAVEPOINT zcode_provider_backfill')
    try:
        columns = {row[1] for row in db.execute('PRAGMA table_info(model_usage)')}
        if 'provider_id' not in columns:
            connection.execute('ROLLBACK TO zcode_provider_backfill')
            connection.execute('RELEASE zcode_provider_backfill')
            return False
        for row_id, provider_id in db.execute(
                "SELECT id,provider_id FROM model_usage WHERE status='completed' AND provider_id IS NOT NULL"):
            stable_id = 'imp-zcode-' + hashlib.sha1(('zdb|' + row_id).encode()).hexdigest()[:24]
            connection.execute(
                "UPDATE turns SET provider_id=? WHERE id=? AND platform='zcode'",
                (provider_id, stable_id))
        connection.execute('RELEASE zcode_provider_backfill')
        return True
    except sqlite3.Error:
        connection.execute('ROLLBACK TO zcode_provider_backfill')
        connection.execute('RELEASE zcode_provider_backfill')
        return False
    finally:
        db.close()


def router_db_rows():
    """Read the local router's request metadata without opening a write handle."""
    if not ROUTER_DB.is_file():
        return
    try:
        db = sqlite3.connect(ROUTER_DB.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    except sqlite3.Error:
        print('usage-import: router database unavailable', file=sys.stderr)
        return
    try:
        columns = {r[1] for r in db.execute('PRAGMA table_info(requests)')}
        extra = ','.join(name if name in columns else 'NULL' for name in
                         ('cached_tokens', 'cache_creation_tokens', 'kiro_credits', 'context_usage_percent'))
        rows = db.execute(
            'SELECT id, ts, requested_model, resolved_model, status, latency_ms,'
            ' prompt_tokens, completion_tokens,' + extra + ' FROM requests ORDER BY ts, id')
        for request_id, ts, requested, resolved, status, latency, input_total, output, cached, creation, credits, context in rows:
            model = resolved or requested
            if (request_id is None or not isinstance(ts, (int, float)) or
                    isinstance(ts, bool) or not isinstance(model, str) or not model or
                    not isinstance(status, int) or isinstance(status, bool)):
                continue
            if not isinstance(input_total, int) or isinstance(input_total, bool) or input_total < 0:
                input_total = None
            if not isinstance(output, int) or isinstance(output, bool) or output < 0:
                output = None
            if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency < 0:
                latency = None
            yield (str(request_id), ts / 1000.0, model, input_total, output,
                   0 if status < 400 else 1, latency, int(ts), cached, creation, credits, context)
    except sqlite3.Error:
        print('usage-import: router database schema or query failed', file=sys.stderr)
    finally:
        db.close()


def import_router_rows(connection):
    """Import router requests, consuming at most one matching non-router row each."""
    non_router = {}
    unmeasured = {}
    legacy_plain = {}
    for row_id, at, model, input_total, output, cached, creation in connection.execute(
            "SELECT id,at,model,actual_input,actual_output,cached,cache_creation FROM turns "
            "WHERE sent=1 AND platform<>'router' AND provider_id IN (?,?) "
            "AND COALESCE(exit_code,0)=0 AND at IS NOT NULL AND model IS NOT NULL",
            ROUTER_PROVIDER_IDS):
        key = (model.casefold(), input_total, output)
        non_router.setdefault(key, []).append((at, row_id))
        if not cached and not creation:
            legacy_plain.setdefault(key, []).append((at, row_id))
        # ZCode records absent upstream usage as 0/0. Only pair these by
        # completion time when the router also confirms missing usage.
        if input_total in (None, 0) and output in (None, 0):
            unmeasured.setdefault(model.casefold(), []).append((at, row_id))
    consumed = set()
    imported = skipped = 0
    for request_id, at, model, input_total, output, exit_code, duration, ts_ms, cached, creation, credits, context in router_db_rows() or ():
        record_id = f'imp-router-{request_id}-{ts_ms}'
        key = (model.casefold(), input_total, output)
        missing_usage = input_total is None and output is None
        candidates = (unmeasured.get(model.casefold(), ()) if missing_usage
                      else non_router.get(key, ()) if input_total is not None else ())
        if input_total is not None and (cached or creation):
            # Older clients only kept Backboard's fresh input count. The raw
            # router record now carries the complete cache breakdown.
            plain_key = (model.casefold(), input_total - (cached or 0) - (creation or 0), output)
            candidates = list(candidates) + legacy_plain.get(plain_key, [])
        window = 1 if missing_usage else 600
        if exit_code:
            candidates = ()  # A failed retry is distinct from a completed client call.
        match = min(
            ((abs(other_at - at), other_at, other_id)
             for other_at, other_id in candidates
             if other_id not in consumed and abs(other_at - at) <= window),
            default=None)
        if match is not None:
            consumed.add(match[2])
            if missing_usage:
                connection.execute(
                    'UPDATE turns SET actual_input=NULL,actual_output=NULL WHERE id=?', (match[2],))
            elif cached is not None or creation is not None:
                connection.execute('UPDATE turns SET actual_input=?,actual_output=?,cached=?,cache_creation=? WHERE id=?',
                                   (input_total, output, cached or 0, creation, match[2]))
            connection.execute('UPDATE turns SET kiro_credits=?,context_usage_percent=? WHERE id=?',
                               (credits, context, match[2]))
            connection.execute('DELETE FROM turns WHERE id=? AND platform=?', (record_id, 'router'))
            skipped += 1
            continue
        connection.execute(
            'INSERT OR REPLACE INTO turns '
            '(id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,'
            'cached,exit_code,ready,jev_actual_input,jev_actual_output,model,cache_creation,duration_ms,kiro_credits,context_usage_percent) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (record_id, at, 'router', 1, None, None, 0, input_total, output, cached or 0,
             exit_code, 1, None, None, model, creation, duration, credits, context))
        imported += 1
    return imported, skipped


def reclass_deepai_codex(connection, offsets):
    """Move already-imported DeepAI Code Codex rows off the Codex platform.

    Incremental tails do not re-read session headers, so rows imported before
    route detection stay on Codex until this one-shot pass. The row id is
    unchanged, so the same request is not inserted a second time.
    """
    if offsets.get(DEEPAI_CODEX_RECLASS_KEY) is True:
        return 0
    if not CODEX_SESSIONS.is_dir():
        offsets[DEEPAI_CODEX_RECLASS_KEY] = True
        return 0
    updated = 0
    failed = False
    for path in CODEX_SESSIONS.rglob('rollout-*.jsonl'):
        route = peek_codex_route(path)
        route_key = 'codex-bill:' + str(path)
        if route is None:
            failed = True
            continue
        offsets[route_key] = route
        if not codex_file_may_bill_deepai(route):
            continue
        try:
            text = path.read_text(errors='replace')
        except OSError:
            failed = True
            continue
        entries, model, route = codex_routed_entries(text, known_route=route)
        offsets[route_key] = route
        if model:
            offsets['codex-model:' + str(path)] = model
        for entry in entries:
            _at, _model, _input_total, _output, _cached, _creation, _duration, response_key, platform, provider_id = entry
            if platform != 'deepai' or provider_id != 'codex':
                continue
            record_id = 'imp-codex-' + hashlib.sha1(str(response_key).encode()).hexdigest()[:24]
            row = connection.execute('SELECT platform, provider_id FROM turns WHERE id=?', (record_id,)).fetchone()
            if row is None or (row[0] == 'deepai' and row[1] == 'codex'):
                continue
            connection.execute("UPDATE turns SET platform='deepai', provider_id='codex' WHERE id=?", (record_id,))
            updated += 1
    if not failed:
        offsets[DEEPAI_CODEX_RECLASS_KEY] = True
    return updated


def _run():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path = STATE / 'usage-import-state.json'
    try:
        offsets = json.loads(state_path.read_text())
    except (OSError, ValueError):
        offsets = {}
    connection = open_ledger()
    try:
        if offsets.get(ZCODE_PROVIDER_BACKFILL_KEY) is not True and backfill_zcode_provider_ids(connection):
            offsets[ZCODE_PROVIDER_BACKFILL_KEY] = True
        fingerprints = existing_fingerprints(connection)
        imported = 0
        skipped = 0

        def record(row_id, platform, at, model, input_total, output, cached, creation, duration, dedup_all=False, provider_id=None, account=None, exit_code=0):
            nonlocal imported, skipped
            if is_duplicate(fingerprints, platform, model, at, input_total, output, row_id, dedup_all, provider_id):
                skipped += 1
                return
            if provider_id is None:
                previous = connection.execute('SELECT provider_id FROM turns WHERE id=?', (row_id,)).fetchone()
                if previous and previous[0] is not None:
                    provider_id = previous[0]
            # Keep the first stamp: a re-parsed row must not move to whichever
            # account happens to be signed in during the re-import.
            previous = connection.execute('SELECT account FROM turns WHERE id=?', (row_id,)).fetchone()
            if previous and previous[0] is not None:
                account = previous[0]
            connection.execute('INSERT OR REPLACE INTO turns (id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,cached,exit_code,ready,jev_actual_input,jev_actual_output,model,cache_creation,duration_ms,provider_id,account) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                row_id, at, platform, 1, None, None, 0, input_total, output, cached, exit_code, 1, None, None, model, creation or None, duration, provider_id, account))
            imported += 1

        sources = (
            # Subagent transcripts are nested one level deeper than session files;
            # row ids are content-derived, so a message duplicated across both
            # files collapses into one ledger row.
            (chain(CLAUDE_PROJECTS.glob('*/*.jsonl'), CLAUDE_PROJECTS.glob('*/*/subagents/*.jsonl')), claude_entries, 'imp-claude-', 'claude', None),
            # Antigravity conversation DBs are rescanned whole each run; row ids
            # derive from conversation + step + created_at, so re-scans replace
            # in place instead of duplicating.
            (chain.from_iterable((root / 'conversations').glob('*.db') for root in ANTIGRAVITY_ROOTS),
             antigravity_entries, 'imp-antigravity-', 'antigravity', None),
        )
        accounts = {'claude': claude_account(), 'codex': codex_account()}
        # Stamp only recent rows: a re-parsed old log must not inherit whichever
        # account is signed in today. Older rows stay NULL and are never counted
        # in per-account stats.
        stamp_floor = time.time()-48*3600
        for paths, parser, prefix, platform, model_key_prefix in sources:
            for path in paths:
                model_key = model_key_prefix + str(path) if model_key_prefix else None
                if platform == 'antigravity':
                    for at, model, input_total, output, cached, creation, duration, key in parser(path):
                        record_id = prefix + hashlib.sha1(key.encode()).hexdigest()[:24]
                        record(record_id, platform, at, model, input_total, output, cached, creation, duration)
                    continue
                for text in iter_new_text(path, offsets):
                    if model_key:
                        entries, last_model = parser(text, offsets.get(model_key))
                        if last_model:
                            offsets[model_key] = last_model
                    else:
                        entries = parser(text)
                    for at, model, input_total, output, cached, creation, duration, key in entries:
                        record_id = prefix + hashlib.sha1(key.encode()).hexdigest()[:24]
                        record(record_id, platform, at, model, input_total, output, cached, creation, duration,
                               account=accounts.get(platform) if at is not None and at >= stamp_floor else None)
        if CODEX_SESSIONS.is_dir():
            for path in CODEX_SESSIONS.rglob('rollout-*.jsonl'):
                route_key = 'codex-bill:' + str(path)
                model_key = 'codex-model:' + str(path)
                known_route = offsets.get(route_key)
                if not isinstance(known_route, dict):
                    known_route = peek_codex_route(path) or {}
                    offsets[route_key] = known_route
                for text in iter_new_text(path, offsets):
                    entries, last_model, known_route = codex_routed_entries(text, offsets.get(model_key), known_route)
                    offsets[route_key] = known_route
                    if last_model:
                        offsets[model_key] = last_model
                    for at, model, input_total, output, cached, creation, duration, key, platform, provider_id in entries:
                        record_id = 'imp-codex-' + hashlib.sha1(key.encode()).hexdigest()[:24]
                        account = accounts.get('codex') if platform == 'codex' and at is not None and at >= stamp_floor else None
                        record(record_id, platform, at, model, input_total, output, cached, creation, duration,
                               provider_id=provider_id, account=account)
        reclass_deepai_codex(connection, offsets)
        if DEEPAI_PI_ROOT.is_dir():
            for path in DEEPAI_PI_ROOT.rglob('*.jsonl'):
                for text in iter_new_text(path, offsets):
                    for at, model, input_total, output, cached, creation, duration, key in deepai_direct_entries(text):
                        record_id = 'imp-deepai-direct-' + hashlib.sha1(key.encode()).hexdigest()[:24]
                        record(record_id, 'deepai', at, model, input_total, output, cached, creation, duration, provider_id='direct')
        if DEEPAI_PROVIDER_LOGS.is_dir():
            # Rows imported while the slug was still stored as "default".
            connection.execute(
                "UPDATE turns SET model='Auto' WHERE platform='deepai' AND provider_id='cursor' "
                "AND lower(model) IN ('default','auto','cursor-auto')")
            for path in DEEPAI_PROVIDER_LOGS.glob('*.log'):
                for text in iter_new_text(path, offsets):
                    for at, model, input_total, output, cached, creation, duration, key, exit_code in deepai_cursor_entries(text):
                        record_id = 'imp-deepai-cursor-' + hashlib.sha1(key.encode()).hexdigest()[:24]
                        record(record_id, 'deepai', at, model, input_total, output, cached, creation, duration,
                               provider_id='cursor', exit_code=exit_code)
        max_marker = offsets.get(ZCODE_DB_KEY, 0)
        for at, model, input_total, output, cached, creation, duration, row_id, marker, provider_id in zcode_db_rows(offsets.get(ZCODE_DB_KEY, 0)):
            # dedup against every layer: these requests may already exist under the
            # retired model-io source's row ids or a watch row's.
            record('imp-zcode-' + hashlib.sha1(('zdb|' + row_id).encode()).hexdigest()[:24], 'zcode', at, model, input_total, output, cached, creation, duration, dedup_all=True, provider_id=provider_id)
            if marker > max_marker:
                max_marker = marker
        offsets[ZCODE_DB_KEY] = max_marker
        router_imported, router_skipped = import_router_rows(connection)
        imported += router_imported
        skipped += router_skipped
        connection.commit()
    finally:
        connection.close()
    state_path.write_text(json.dumps(offsets))
    os.chmod(state_path, 0o600)
    (STATE / 'tokens.sqlite3').chmod(0o600)
    return imported, skipped


def _write_import_status(status):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = STATE / ('usage-import-status.json.' + str(os.getpid()) + '.tmp')
    try:
        with open(temp, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump(status, file)
        temp.replace(STATE / 'usage-import-status.json')
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def run():
    started = time.time()
    try:
        previous = json.loads((STATE / 'usage-import-status.json').read_text())
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    status = {key: previous.get(key) if isinstance(previous.get(key), (int, float)) and
              not isinstance(previous.get(key), bool) and previous[key] >= 0 else None
              for key in ('last_completed', 'imported', 'skipped')}
    status.update(last_started=started, error=None, next_due=started + 5)
    _write_import_status(status)
    try:
        imported, skipped = _run()
    except Exception as error:
        category = ('database_busy' if isinstance(error, sqlite3.Error) and
                    ('locked' in str(error).lower() or 'busy' in str(error).lower()) else
                    'database_error' if isinstance(error, sqlite3.Error) else
                    'io_error' if isinstance(error, OSError) else 'import_error')
        status['error'] = category
        try:
            _write_import_status(status)
        except OSError:
            print('usage-import: status_write_failed', file=sys.stderr)
        raise
    status.update(last_completed=time.time(), imported=imported, skipped=skipped)
    # launchd StartInterval is an estimate, not a guaranteed appointment.
    status['next_due'] = started + 5
    _write_import_status(status)
    return imported, skipped


def install():
    target = STATE / 'usage-import.py'
    target.write_text(Path(__file__).read_text())
    os.chmod(target, 0o600)
    plist_dir = Path.home() / 'Library/LaunchAgents'
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / 'local.context-gate.usage-import.plist'
    plist.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
	<key>Label</key><string>local.context-gate.usage-import</string>
	<key>ProgramArguments</key><array>
		<string>/usr/bin/python3</string><string>{target}</string>
	</array>
	<key>StartInterval</key><integer>5</integer>
	<key>RunAtLoad</key><true/>
	<key>StandardErrorPath</key><string>{STATE}/usage-import.err.log</string>
</dict></plist>''')
    print('installed:', target, '+', plist)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true', help='copy self to STATE and write the LaunchAgent timer')
    args = parser.parse_args()
    if args.install:
        install()
        return 0
    imported, skipped = run()
    print(json.dumps({'imported': imported, 'duplicate_skipped': skipped}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
