#!/usr/bin/env python3
"""Local token ledger. Estimates and measured provider usage never mixed."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
import os
STATE = Path(os.environ.get('CONTEXT_GATE_STATE','~/.local/state/context-gate')).expanduser()


def measured_usage(platform, event):
    if not isinstance(event, dict):
        return None
    if platform == 'claude' and event.get('type') != 'result':
        return None
    if platform in ('gpt', 'codex') and event.get('type') != 'turn.completed':
        return None
    if platform == 'openai' and event.get('type') == 'response.completed':
        event = event.get('response', {})
    usage = event.get('usage')
    if platform == 'anthropic' and event.get('type') == 'message_start':
        usage = event.get('message', {}).get('usage')
    if not isinstance(usage, dict):
        return None
    for name,value in usage.items():
        if name in ('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens','inputTokens','outputTokens','prompt_tokens','completion_tokens') and value is not None:
            if isinstance(value,bool) or not isinstance(value,int) or value<0:return None
    if platform=='anthropic' and event.get('type')=='message_start' and usage.get('input_tokens') is None:return None
    usage={k:(0 if v is None else v) for k,v in usage.items()}
    if platform == 'claude':
        input_tokens = sum(usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
        cached = usage.get('cache_read_input_tokens', 0)
        creation = usage.get('cache_creation_input_tokens', 0)
    elif platform in ('gpt', 'codex'):
        input_tokens = usage.get('input_tokens', 0)
        cached = usage.get('cached_input_tokens', 0)
        creation = 0
    elif platform == 'openai':
        input_tokens = usage.get('input_tokens', usage.get('prompt_tokens', 0))
        cached = (usage.get('input_tokens_details') or usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
        creation = 0
    elif platform == 'anthropic':
        input_tokens = sum(usage.get(k, 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
        cached = usage.get('cache_read_input_tokens', 0)
        creation = usage.get('cache_creation_input_tokens', 0)
    else:
        input_tokens = usage.get('inputTokens', 0)
        cached = usage.get('cacheReadTokens', 0)
        creation = usage.get('cacheCreationTokens', 0)
    output = usage.get('output_tokens', usage.get('outputTokens', usage.get('completion_tokens', 0)))
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (input_tokens, cached, output, creation)):
        return None
    return {'input_tokens': input_tokens, 'cached_input_tokens': cached, 'output_tokens': output, 'cache_creation_input_tokens': creation}


class UsageCollector:
    def __init__(self, platform):
        self.platform = platform
        self.buffer = ''
        self.usage = None
        self.model = None
        self.completed = False
        self.has_error = False

    def feed(self, text):
        self.buffer += text
        if '\ndata: [DONE]' in self.buffer:self.completed=True
        decoder = json.JSONDecoder()
        while True:
            start = self.buffer.find('{')
            if start < 0:
                self.buffer = self.buffer[-48:]  # Retain a split SSE [DONE] marker.
                return
            self.buffer = self.buffer[start:]
            try:
                event, end = decoder.raw_decode(self.buffer)
            except ValueError:
                if len(self.buffer) > 8 * 1024 * 1024:
                    self.buffer = ''
                return
            self.buffer = self.buffer[end:]
            if event.get('type') in ('message_stop','response.completed','turn.completed'):
                self.completed=True
            if event.get('type')=='error' or isinstance(event.get('error'),dict):self.has_error=True
            model = event.get('model') or event.get('model_id')
            for container in ('response','message'):
                value = event.get(container)
                if isinstance(value, dict):
                    model = model or value.get('model') or value.get('model_id')
            # ZCode answers arrive as plain-string 'response' values; only accept model-ish strings.
            if isinstance(model, str) and 0 < len(model) <= 120:
                self.model = model
            usage = measured_usage(self.platform, event)
            if usage is not None:
                if self.platform=='anthropic' and event.get('type')=='message_delta' and self.usage is None:
                    continue
                if self.usage is None:
                    self.usage = usage
                elif self.platform in ('gpt', 'codex'):
                    self.usage = {k: self.usage[k] + usage[k] for k in usage}
                elif self.platform == 'anthropic':
                    self.usage = {k: max(self.usage[k], usage[k]) for k in usage}
                else:
                    self.usage = usage


def save(record_id, platform, metrics, sent, usage=None, state_dir=STATE, exit_code=None, ready=None, timing=None, model=None, duration_ms=None):
    folder = Path(state_dir)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = folder / 'tokens.sqlite3'
    with sqlite3.connect(db) as connection:
        # Lock before checking schema: concurrent first calls must not both
        # observe missing columns and attempt the same migration.
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER)')
        cols = {r[1] for r in connection.execute('PRAGMA table_info(turns)')}
        if 'ready' not in cols:
            connection.execute('ALTER TABLE turns ADD COLUMN ready INTEGER')
            connection.execute('UPDATE turns SET ready=sent WHERE ready IS NULL')
        for name, kind in (('jev_actual_input', 'INTEGER'), ('jev_actual_output', 'INTEGER'), ('model', 'TEXT'), ('cache_creation', 'INTEGER'), ('duration_ms', 'REAL')):
            if name not in cols:
                connection.execute('ALTER TABLE turns ADD COLUMN '+name+' '+kind)
        usage = usage or {}
        if duration_ms is None and timing is not None:
            duration_ms = timing.get('total_ms')
        previous=connection.execute('SELECT at FROM turns WHERE id=?',(record_id,)).fetchone()
        connection.execute('INSERT OR REPLACE INTO turns (id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,cached,exit_code,ready,jev_actual_input,jev_actual_output,model,cache_creation,duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            record_id, previous[0] if previous else time.time(), platform, int(sent), metrics['baseline_tokens_estimated'],
            metrics['final_tokens_estimated'], metrics.get('jev_input_tokens_estimated', 0),
            usage.get('input_tokens'), usage.get('output_tokens'), usage.get('cached_input_tokens'), exit_code, int(sent if ready is None else ready), metrics.get('jev_input_tokens_actual'), metrics.get('jev_output_tokens_actual'), model, usage.get('cache_creation_input_tokens'), duration_ms))
        if timing is not None:
            connection.execute('CREATE TABLE IF NOT EXISTS request_timings (id TEXT PRIMARY KEY, endpoint TEXT, prepare_ms REAL, upstream_headers_ms REAL, first_response_byte_ms REAL, upstream_total_ms REAL, total_ms REAL, upstream_status INTEGER, stream_completed INTEGER)')
            connection.execute('INSERT OR REPLACE INTO request_timings VALUES (?,?,?,?,?,?,?,?,?)',(
                record_id,timing.get('endpoint'),timing.get('prepare_ms'),timing.get('upstream_headers_ms'),
                timing.get('first_response_byte_ms'),timing.get('upstream_total_ms'),timing.get('total_ms'),
                timing.get('upstream_status'),timing.get('stream_completed')))
    db.chmod(0o600)


def save_comparison(comparison_id, platform, baseline_input, filtered_input, state_dir=STATE):
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (baseline_input, filtered_input)):
        raise ValueError('A/B 必须使用平台实测输入 token')
    folder=Path(state_dir);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=folder/'tokens.sqlite3'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE IF NOT EXISTS comparisons (id TEXT PRIMARY KEY, platform TEXT, baseline_input INTEGER, filtered_input INTEGER)')
        c.execute('INSERT OR REPLACE INTO comparisons VALUES (?,?,?,?)',(comparison_id,platform,baseline_input,filtered_input))
    db.chmod(0o600)


def totals(state_dir=STATE):
    db = Path(state_dir) / 'tokens.sqlite3'
    if not db.exists():
        return {'sent_turns': 0, 'blocked_turns': 0}
    with sqlite3.connect(db) as c:
        cols={r[1] for r in c.execute('PRAGMA table_info(turns)')}
        optional=[name if name in cols else ('sent' if name=='ready' else 'NULL') for name in ('ready','jev_actual_input','jev_actual_output')]
        rows=c.execute('SELECT sent,before_est,after_est,jev_est,actual_input,actual_output,'+','.join(optional)+' FROM turns').fetchall() if cols else []
        has_ab=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='comparisons'").fetchone()
        pairs=c.execute('SELECT baseline_input,filtered_input FROM comparisons').fetchall() if has_ab else []
    sent = [r for r in rows if r[0]]
    # Imported rows carry NULL estimates (no gate involvement); coalesce so the
    # estimated totals only reflect traffic that actually went through the gate.
    before = sum(r[1] or 0 for r in sent)
    after = sum(r[2] or 0 for r in sent)
    jev = sum(r[3] or 0 for r in sent)
    measured = [r for r in sent if r[4] is not None]
    return {'sent_turns': len(sent), 'blocked_turns': sum(not r[6] for r in rows),
            'prepared_not_dispatched_turns': sum(bool(r[6]) and not r[0] for r in rows),
            'prepared_before_tokens_estimated': sum(r[1] or 0 for r in rows),
            'prepared_after_tokens_estimated': sum(r[2] or 0 for r in rows),
            'before_tokens_estimated': before, 'after_pack_tokens_estimated': after,
            'saved_pack_tokens_estimated': before - after,
            'saved_pack_pct_estimated': round(100 * (before - after) / max(1, before), 2),
            'jev_input_tokens_requested_estimated': jev,
            'net_saved_including_jev_estimated': before - after - jev,
            'provider_measured_turns': len(measured),
            'provider_actual_input_tokens': sum(r[4] for r in measured),
            'provider_actual_output_tokens': sum(r[5] or 0 for r in measured),
            'jev_actual_input_tokens': sum(r[7] or 0 for r in rows),
            'jev_actual_output_tokens': sum(r[8] or 0 for r in rows),
            'jev_usage_reported_turns': sum(r[7] is not None for r in rows),
            'actual_savings': sum(a-b for a,b in pairs) if pairs else None,
            'actual_ab_pairs': len(pairs),
            'actual_ab_baseline_input': sum(a for a,b in pairs),
            'actual_ab_filtered_input': sum(b for a,b in pairs),
            'actual_savings_note': '仅累计已记录的同任务 A/B 实测对照；未计 Jev 开销，不推算未对照任务的真实节省。'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='查看 Context Gate 累计 token 用量与估计节省')
    p.add_argument('--state-dir', default=str(STATE))
    a = p.parse_args()
    print(json.dumps(totals(a.state_dir), ensure_ascii=False, indent=2))
