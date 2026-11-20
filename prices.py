#!/usr/bin/env python3
"""Market price rules for the console. USD per 1M tokens; estimates, not billing."""
import json
import os
from pathlib import Path

STATE = Path(os.environ.get('CONTEXT_GATE_STATE', '~/.local/state/context-gate')).expanduser()
CONFIG_NAME = 'prices.json'
ROUTER_FREE_PRICE = {'match':'local-model-router-free','input':0.0,'output':0.0,'cache_read':0.0,'cache_write':0.0}
# Cost display modes (console toggle, persisted in MODE_NAME):
#  - 'actual':   what the owner pays today; free tiers, free keys, local
#                deploys and every Local Model Router request count as $0.
#                When no owner rule matches, a verified list price is used
#                so a known model is not left unpriced.
#  - 'official': every request valued at the model's official public list
#                price, including requests that were free in practice. $0
#                "free to me" rules are ignored (unless tagged official_free,
#                i.e. the vendor itself lists the price as $0); models with no
#                official price stay unpriced (tokens only), never $0.
MODE_ACTUAL = 'actual'
MODE_OFFICIAL = 'official'
MODES = (MODE_ACTUAL, MODE_OFFICIAL)
MODE_NAME = 'cost-mode.json'

# Public list prices per 1M tokens (USD). Rules match by case-insensitive
# substring (covers prefixes like 'claude-sonnet' and suffixes like ':free'),
# first hit wins. Unknown models stay unpriced and are excluded from
# money sums instead of getting a guessed price.
# cache_write applies to tokens the provider bills at cache-creation rates
# (Anthropic reports them; defaults to 1.25x input when omitted).
DEFAULT_RULES = [
    # Official model pages checked 2026-10-31. Standard text rates, USD/1M.
    {'match': 'gpt-6.1-terra', 'input': 1, 'output': 5, 'cache_read': 0.05, 'cache_write': 1.25,
     'long_context_threshold': 272000, 'long_input_multiplier': 2, 'long_output_multiplier': 1.5,
     'source': 'https://developers.openai.com/api/docs/models/gpt-6.1-terra', 'verified_at': '2026-10-31'},
    # GPT-5.6 Terra standard rates, USD/1M. Above 272k tokens input and cache
    # double and output rises 1.5x, same shape as GPT-6.1 Terra.
    {'match': 'gpt-5.6-terra',
     'model_ids': ['gpt-5.6-terra'],
     'input': 2, 'output': 12, 'cache_read': 0.2, 'cache_write': 2.5,
     'long_context_threshold': 272000, 'long_input_multiplier': 2, 'long_output_multiplier': 1.5,
     'source': 'https://developers.openai.com/api/docs/pricing', 'verified_at': '2026-11-08'},
    {'match': 'gemini-3.8-flash', 'input': 0.75, 'output': 3.75, 'cache_read': 0.075, 'cache_write': 0.75,
     'exact_model': True,
     'effective_until': '2026-12-31', 'next_input': 1.5, 'next_output': 7.5, 'next_cache_read': 0.15,
     'source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash', 'verified_at': '2026-10-31'},
    # Gemini 4 Argon (Google official pricing page, checked 2026-11-03):
    # $2/$10, implicit-cache read $0.10 through 2026-11-30; doubles to
    # $4/$20, cache read $0.20 from 2026-12-01. Exact-model match (after the
    # console strips effort suffixes, so '-high' variants share this price).
    {'match': 'gemini-4-argon', 'input': 2, 'output': 10, 'cache_read': 0.1, 'cache_write': 2,
     # Antigravity's own model list names 'gemini-pro-orchestrator-g1-pro'
     # "Orchestrator (Argon)", so it bills as Argon.
     'model_ids': ['gemini-4-argon', 'gemini-argon', 'gemini-pro-orchestrator-g1-pro'],
     'effective_until': '2026-11-30', 'next_input': 4, 'next_output': 20, 'next_cache_read': 0.2,
     'source': 'https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon', 'verified_at': '2026-11-03'},
    # Gemini 4 Hydrogen (Google official pricing page, checked 2026-11-15):
    # flat $1.50/$7.50, implicit-cache read $0.075; no long-context tier and
    # no dated price change. Implicit caching only, so cache_write = input.
    {'match': 'gemini-4-hydrogen', 'input': 1.5, 'output': 7.5, 'cache_read': 0.075, 'cache_write': 1.5,
     # Owner confirmed 2026-11-15: Antigravity's 'gemini-flash-worker-agy'
     # runs on Hydrogen, so it bills as Hydrogen.
     'model_ids': ['gemini-4-hydrogen', 'gemini-hydrogen', 'gemini-flash-worker-agy'],
     'source': 'https://aistudio.google.com/docs/pricing#gemini-4-hydrogen', 'verified_at': '2026-11-15'},
    # Verified 2026-10-08 against the OpenAI pricing table (standard tier).
    # gpt-6-astra is the top tier; batch/fast/ultrafast tiers are not modeled.
    {'match': 'gpt-6-astra', 'input': 10, 'output': 50, 'cache_read': 1, 'cache_write': 12.5},
    {'match': 'gpt-6.1-sol', 'input': 2, 'output': 10, 'cache_read': 0.1, 'cache_write': 2.5},
    {'match': 'gpt-6-sol', 'input': 2, 'output': 10, 'cache_read': 0.2, 'cache_write': 2.5},
    # Verified 2026-10-02 against OpenAI's pricing docs and third-party trackers.
    {'match': 'gpt-6-luna', 'input': 0.1, 'output': 0.5, 'cache_read': 0.01, 'cache_write': 0.125},
    {'match': 'gpt-5.5', 'input': 5, 'output': 30, 'cache_read': 0.5},
    # Auto review became a free local feature: the Codex pricing page lists it
    # under "Local features" and the official 28-days-of-shipping X posts say
    # reviews are free (owner confirmed 2026-10-08). The old rule billed it at
    # GPT-5.6 Luna rates per the Codex changelog (2026-07-31).
    {'match': 'codex-auto-review', 'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'official_free': True},
    {'match': 'claude-opus-5-5', 'input': 4, 'output': 20, 'cache_read': 0.2},
    {'match': 'claude-opus-5', 'input': 5, 'output': 25, 'cache_read': 0.5},
    {'match': 'claude-opus-4', 'input': 15, 'output': 75, 'cache_read': 1.5},
    {'match': 'claude-sonnet-5-5', 'input': 2, 'output': 10, 'cache_read': 0.2},
    {'match': 'claude-sonnet-5', 'input': 2, 'output': 10, 'cache_read': 0.2},
    {'match': 'claude-sonnet-4', 'input': 3, 'output': 15, 'cache_read': 0.3},
    {'match': 'claude-3-7-sonnet', 'input': 3, 'output': 15, 'cache_read': 0.3},
    {'match': 'claude-3-5-sonnet', 'input': 3, 'output': 15, 'cache_read': 0.3},
    # Verified 2026-10-08 against the claude-api pricing table: prompts up to
    # 100K tokens. Longer prompts bill $0.50/$2.50 and are not modeled here.
    {'match': 'claude-haiku-5-5', 'input': 0.1, 'output': 0.5, 'cache_read': 0.01, 'cache_write': 0.125},
    {'match': 'claude-haiku-4', 'input': 1, 'output': 5, 'cache_read': 0.1},
    # Grok 4.7 list price (xAI / Bedrock global): $2 / $6, cache read $0.50.
    # Same numbers as the official rule, so 按付费设置 can price a named Grok call.
    {'match': 'grok-4.7', 'input': 2, 'output': 6, 'cache_read': 0.5, 'cache_write': 2.5},
    # Cursor's model slug "default" is the catalog entry Auto. This session was
    # told to continue on a Grok model; Auto has no separate token rate, so it
    # uses the verified Grok 4.7 list price above. Exact ids only.
    {'match': 'cursor-auto',
     'model_ids': ['auto', 'cursor-auto', 'default'],
     'input': 2, 'output': 6, 'cache_read': 0.5, 'cache_write': 2.5},
    {'match': 'claude-3-5-haiku', 'input': 0.8, 'output': 4, 'cache_read': 0.08},
    {'match': 'glm-5.3-flash', 'input': 0.15, 'output': 0.5, 'cache_read': 0.03},
    {'match': 'glm-5.3', 'input': 1.4, 'output': 4.4, 'cache_read': 0.26},
    {'match': 'glm-', 'input': 0.6, 'output': 2.2, 'cache_read': 0.11},
    # Free per owner confirmation 2026-10-08: DeepSeek-V4-Flash, qwen3-14b (local).
    {'match': 'deepseek-v4-flash', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': 'qwen3-14b', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': 'nemotron-3', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': 'qwen2.5-coder', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': 'kimi-k3', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': 'openrouter/free', 'input': 0, 'output': 0, 'cache_read': 0},
    {'match': ':free', 'input': 0, 'output': 0, 'cache_read': 0},
]

# Official-price references include vendor list prices and clearly labelled
# hosting-provider list prices for open models. These are estimates of the
# same usage at a public rate, never evidence of what the owner actually paid.
# New references were fetched 2026-10-31; no automatic price-fetch job is used.
# Ambiguous aliases, web-only models and models lacking verifiable per-token
# prices stay unpriced. Do not substitute a nearby model or another size.
OFFICIAL_RULES = [
    # Exact, explicitly verified model identities; provider prefixes and :free
    # do not change the model used for a public-price comparison.
    {'match': 'muse-wonder-1.0',
     'model_ids': ['muse-wonder-1.0', 'muse-wonder'],
     'input': 4,
     'output': 20,
     'cache_read': 0.2,
     'cache_write': 4,
     'source': 'https://dev.meta.ai/docs/pricing-rate-limits',
     'source_name': 'Meta',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31'},
    {'match': 'muse-spark-1.3-contributor',
     'model_ids': ['muse-spark-1.3-contributor', 'muse-spark-1.2-contributor'],
     'input': 0.1,
     'output': 0.2,
     'cache_read': 0.002,
     'cache_write': 0.1,
     'source': 'https://dev.meta.ai/docs/pricing-rate-limits',
     'source_name': 'Meta',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31',
     'price_note': 'contributor'},
    {'match': 'muse-spark-1.3',
     'model_ids': ['muse-spark-1.3', 'muse-spark-1.2', 'muse-spark-1.1'],
     'input': 1.25,
     'output': 4.25,
     'cache_read': 0.15,
     'cache_write': 1.25,
     'source': 'https://dev.meta.ai/docs/pricing-rate-limits',
     'source_name': 'Meta',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31'},
    {'match': 'deepseek-v4.1-flash',
     'model_ids': ['deepseek-v4.1-flash',
                   'deepseek-v4.1-flash-1017',
                   'deepseek-v4-flash',
                   'deepseek-v4-flash-vision-exp',
                   'deepseek-flash'],
     'input': 0.3,
     'output': 1.2,
     'cache_read': 0.006,
     'cache_write': 0.3,
     'source': 'https://api-docs.deepseek.com/quick_start/pricing/',
     'source_name': 'DeepSeek',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31',
     'price_note': 'peak_reference'},
    {'match': 'mercury-3',
     'model_ids': ['mercury-3'],
     'input': 0.2,
     'output': 0.7,
     'cache_read': 0.02,
     'cache_write': 0.2,
     'source': 'https://www.inceptionlabs.ai/blog/introducing-mercury-3',
     'source_name': 'Inception',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31',
     'price_note': 'standard_list'},
    {'match': 'qwen3.8-27b',
     'model_ids': ['qwen3.8-27b'],
     'input': 0.5,
     'output': 3,
     'cache_read': 0.1,
     'cache_write': 0.625,
     'source': 'https://www.qwencloud.com/models/qwen3.8-27b',
     'source_name': 'QwenCloud',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31',
     'price_note': 'implicit_cache'},
    {'match': 'qwen3.8-flash-next',
     'model_ids': ['qwen3.8-flash-next', 'qwen3.8-flash'],
     'input': 0.15,
     'output': 0.47,
     'cache_read': 0.016,
     'cache_write': 0.2,
     'source': 'https://www.qwencloud.com/models/qwen3.8-flash',
     'source_name': 'QwenCloud',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31',
     'price_note': 'qwen_flash_reference'},
    {'match': 'mimo-v2.6-flash',
     'model_ids': ['mimo-v2.6-flash'],
     'input': 0.14,
     'output': 0.28,
     'cache_read': 0.0028,
     'cache_write': 0.14,
     'source': 'https://openrouter.ai/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints',
     'source_name': 'Xiaomi via OpenRouter',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31'},
    {'match': 'step-5-preview',
     'model_ids': ['step-5-preview'],
     'input': 1,
     'output': 2.7,
     'cache_read': 0.1,
     'cache_write': 1,
     'source': 'https://openrouter.ai/api/v1/models/stepfun/step-5-preview/endpoints',
     'source_name': 'StepFun via OpenRouter',
     'price_basis': 'vendor',
     'verified_at': '2026-10-31'},
    {'match': 'nemotron-3-ultra-550b-a55b',
     'model_ids': ['nemotron-3-ultra-550b-a55b'],
     'input': 0.5,
     'output': 2.2,
     'cache_read': 0.1,
     'cache_write': 0.5,
     'source': 'https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b/endpoints',
     'source_name': 'DeepInfra via OpenRouter',
     'price_basis': 'provider',
     'verified_at': '2026-10-31'},
    {'match': 'nemotron-3-super-120b-a12b',
     'model_ids': ['nemotron-3-super-120b-a12b'],
     'input': 0.3,
     'output': 2.4,
     'cache_read': 0.15,
     'cache_write': 0.3,
     'source': 'https://openrouter.ai/api/v1/models/nvidia/nemotron-3-super-120b-a12b/endpoints',
     'source_name': 'Crusoe via OpenRouter',
     'price_basis': 'provider',
     'verified_at': '2026-10-31'},
    {'match': 'muse-glimmer-30b',
     'model_ids': ['muse-glimmer-30b'],
     'input': 0.3,
     'output': 1.2,
     'cache_read': 0.04,
     'cache_write': 0.3,
     'source': 'https://openrouter.ai/api/v1/models/meta/muse-glimmer-30b/endpoints',
     'source_name': 'DeepInfra via OpenRouter',
     'price_basis': 'provider',
     'verified_at': '2026-10-31'},
    {'match': 'qwen3-14b',
     'model_ids': ['qwen3-14b'],
     'input': 0.12,
     'output': 0.24,
     'cache_read': 0.12,
     'cache_write': 0.12,
     'source': 'https://openrouter.ai/api/v1/models/qwen/qwen3-14b/endpoints',
     'source_name': 'OpenRouter',
     'price_basis': 'provider',
     'verified_at': '2026-10-31',
     'price_note': 'no_cache_discount'},

    # Claude Fable 5.1 / 5: $10 in, $50 out, cache read $0.25 (Anthropic
    # model table, claude-api reference cached 2026-10-06; Bedrock global
    # identical, 5m cache write $12.50).
    {'match': 'claude-fable-5', 'input': 10, 'output': 50, 'cache_read': 0.25, 'cache_write': 12.5},
    # Kimi K3 (Bedrock global): $3 / $15, cache read $0.30, cache write $3.75.
    {'match': 'kimi-k3', 'input': 3, 'output': 15, 'cache_read': 0.3, 'cache_write': 3.75},
    # Grok 4.7 (Bedrock global): $2 / $6, cache read $0.50.
    {'match': 'grok-4.7', 'input': 2, 'output': 6, 'cache_read': 0.5, 'cache_write': 2.5},
    # Amazon Nova Micro (Bedrock in-region; first-party AWS model).
    {'match': 'nova-micro', 'input': 0.035, 'output': 0.14, 'cache_read': 0.00875, 'cache_write': 0.035},
    # gpt-oss-20b (Bedrock in-region; open-weight, no OpenAI API price).
    {'match': 'gpt-oss-20b', 'input': 0.07, 'output': 0.3},
    # gpt-oss-120b (open-weight, no OpenAI API price; hosting-provider list
    # price via OpenRouter endpoints, checked 2026-11-03: Amazon Bedrock /
    # Together / Groq all list $0.15 in, $0.60 out per 1M; cache read $0.075
    # where offered). The measured medium-effort id is the only ledger name.
    {'match': 'gpt-oss-120b',
     'model_ids': ['gpt-oss-120b', 'gpt-oss-120b-medium'],
     'input': 0.15,
     'output': 0.6,
     'cache_read': 0.075,
     'cache_write': 0.15,
     'source': 'https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints',
     'source_name': 'Amazon Bedrock / Together via OpenRouter',
     'price_basis': 'provider',
     'verified_at': '2026-11-03'},
    # DeepSeek V3.2 (Bedrock in-region).
    {'match': 'deepseek.v3.2', 'input': 0.62, 'output': 1.85},
    {'match': 'deepseek-v3.2', 'input': 0.62, 'output': 1.85},
]


def config_path(state_dir=STATE):
    return Path(state_dir) / CONFIG_NAME


def _user_document(state_dir):
    path = config_path(state_dir)
    if path.is_file():
        try:
            document = json.loads(path.read_text())
            return document if isinstance(document, dict) else {}
        except (OSError, ValueError):
            pass
    return {}


def _user_list(document, key):
    value = document.get(key)
    return [rule for rule in value if isinstance(rule, dict) and isinstance(rule.get('match'), str)] if isinstance(value, list) else []


def _validated(rules):
    valid = []
    def rate(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and 0 <= value < float('inf'))
    for rule in rules:
        identities=rule.get('model_ids')
        if identities is not None:
            if not isinstance(identities,list) or not identities or any(not isinstance(name,str) or not name.strip() for name in identities):continue
            rule['model_ids']=[name.lower().strip() for name in identities]
        # A malformed override must not label an unknown model as free, nor
        # poison the entire stats JSON with NaN/Infinity.
        if (not rule['match'].strip() or not all(rate(rule.get(key)) for key in ('input', 'output'))
                or any(key in rule and not rate(rule[key]) for key in ('cache_read', 'cache_write'))):
            continue
        rule.setdefault('cache_read', round(rule['input'] * 0.1, 6))
        rule.setdefault('cache_write', round(rule['input'] * 1.25, 6))
        if all(rate(rule[key]) for key in ('input', 'output', 'cache_read', 'cache_write')):
            valid.append(rule)
    return valid


def is_free(rule):
    return rule is not None and rule['input'] == 0 and rule['output'] == 0


def load_rules(state_dir=STATE, mode=MODE_ACTUAL):
    """Price rules for one cost mode; first substring hit wins.

    actual:   user rules, then DEFAULT_RULES (unchanged behaviour).
    official: user `official_rules`, then every non-free user/built-in rule,
              then OFFICIAL_RULES. $0 rules survive only when tagged
              official_free (the vendor's own list price is $0), so a model
              that is merely free to the owner falls through to its official
              price or stays unpriced.
    """
    document = _user_document(state_dir)
    user = _user_list(document, 'rules')
    if mode != MODE_OFFICIAL:
        # Owner rules and built-in payment rates win. Verified list prices fill
        # the rest, so Muse, Mercury, GPT-OSS and the other catalogued models
        # are not left unpriced. A $0 owner rule still stays $0.
        listed = [dict(rule) for rule in OFFICIAL_RULES if not is_free(rule) or rule.get('official_free') is True]
        return _validated([dict(rule) for rule in user + DEFAULT_RULES] + listed)
    official = _validated([dict(rule) for rule in _user_list(document, 'official_rules')])
    rest = _validated([dict(rule) for rule in user + DEFAULT_RULES + OFFICIAL_RULES])
    return official + [rule for rule in rest if not is_free(rule) or rule.get('official_free') is True]


def normalize_mode(value):
    return value if value in MODES else MODE_ACTUAL


def mode_path(state_dir=STATE):
    return Path(state_dir) / MODE_NAME


def load_mode(state_dir=STATE):
    """Persisted console cost mode; anything unreadable means 'actual'."""
    try:
        document = json.loads(mode_path(state_dir).read_text())
    except (OSError, ValueError):
        return MODE_ACTUAL
    return normalize_mode(document.get('mode') if isinstance(document, dict) else None)


def save_mode(state_dir, mode):
    if mode not in MODES:
        raise ValueError('unknown cost mode')
    path = mode_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp')
    fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps({'mode': mode}).encode())
    finally:
        os.close(fd)
    os.replace(temp, path)
    return mode


def price_for(model, rules=None, state_dir=STATE, platform=None, mode=MODE_ACTUAL):
    # Backboard is a paid upstream even when reached through the local router.
    if platform == 'router' and mode != MODE_OFFICIAL and not str(model or '').lower().startswith('backboard/'):
        return ROUTER_FREE_PRICE
    if rules is None:
        rules = load_rules(state_dir, mode)
    name = str(model or '').lower()
    identity = name.rsplit('/', 1)[-1]
    if identity.endswith(':free'): identity = identity[:-len(':free')]
    if isinstance(rules, dict):
        return rules.get(name)
    for rule in rules:
        if rule.get('model_ids') is not None:
            if identity in rule['model_ids']: return rule
            continue
        if rule.get('exact_model'):
            import re
            canonical=re.sub(r'(?:-(?:thinking|low|mid|medium|high|xhigh|max))+$','',name)
            if canonical!=rule['match'].lower():continue
        if rule['match'].lower() in name:
            return rule
    return None


def row_cost(model, input_tokens, output_tokens, cached_tokens, rules=None, state_dir=STATE, cache_creation=None, platform=None, rule=None, mode=MODE_ACTUAL, at=None):
    """USD cost of one measured row, or None when the model has no price.

    input_tokens counts every billed input token INCLUDING cache-read and
    cache-creation tokens (the ledger convention for every platform); those
    two subsets are re-priced at their own rates and removed from the
    plain-input bucket first. Callers that already resolved the rule may pass
    it as `rule` to skip the lookup.
    """
    if rule is None:
        rule = price_for(model, rules, state_dir, platform=platform, mode=mode)
    if rule is None:
        return None
    rule = dict(rule)
    if rule.get('effective_until') and at is not None:
        import datetime
        try: day = datetime.datetime.fromtimestamp(float(at), datetime.timezone.utc).date().isoformat()
        except (ValueError, TypeError, OverflowError, OSError): day = None
        if day and day > rule['effective_until']:
            for name in ('input', 'output', 'cache_read'):
                if 'next_' + name in rule: rule[name] = rule['next_' + name]
    if rule.get('long_context_threshold') and (input_tokens or 0) > rule['long_context_threshold']:
        for name in ('input', 'cache_read', 'cache_write'): rule[name] *= rule.get('long_input_multiplier', 1)
        rule['output'] *= rule.get('long_output_multiplier', 1)
    cached = min(cached_tokens or 0, input_tokens or 0)
    creation = min(cache_creation or 0, (input_tokens or 0) - cached)
    plain = (input_tokens or 0) - cached - creation
    return (round(plain / 1e6 * rule['input']
                  + creation / 1e6 * rule['cache_write']
                  + cached / 1e6 * rule['cache_read']
                  + (output_tokens or 0) / 1e6 * rule['output'], 6))


def ensure_config(state_dir=STATE):
    path = config_path(state_dir)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {'note': 'USD per 1M tokens. Rules match by lowercase substring, first hit wins; user rules run before built-ins. Unpriced models are excluded from money sums. cache_write defaults to 1.25x input when omitted. Optional "official_rules" (same shape) are used only by the console\'s official-price mode, before everything else; $0 rules are ignored in that mode.',
               'rules': DEFAULT_RULES}
    import os
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps(payload, ensure_ascii=False, indent=2).encode())
    finally:
        os.close(fd)
    return path
