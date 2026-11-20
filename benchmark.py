#!/usr/bin/env python3
"""Synthetic retrieval benchmark. Fake/live review labels are mandatory."""
import argparse
import json
from pathlib import Path
import statistics
import tempfile
from context_gate import Config, DecisionClient, build_pack


class SyntheticReviewer:
    def ask(self, provider, state, questions):
        return {'answers': {k: {'choice': 'no' if k.startswith('missing_') or k in ('cross_module', 'conflict') else 'yes',
                               'confidence': .96} for k in questions}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='context-gate-bench-') as folder:
        base = Path(folder)
        repo = base / 'repo'
        repo.mkdir()
        for i in range(500):
            (repo / ('unrelated_%04d.py' % i)).write_text('# inert unrelated fixture\n' + 'OTHER_DATA = "abcdefghijklmnop0123456789"\n' * 100)
        (repo / 'price.py').write_text('from decimal import Decimal\n\ndef price(values):\n    return sum(values, Decimal("0")).quantize(Decimal("0.01"))\n')
        (repo / 'test_price.py').write_text('from price import price\nfrom decimal import Decimal\n\ndef test_rounding():\n    assert price([Decimal("1.005")]) == Decimal("1.00")\n')
        memory = base / 'memory.md'
        memory.write_text('[CORE_MEMORY_START]\nGoal: round prices using Decimal. Preserve price API.\n[CORE_MEMORY_END]')
        config = Config(cache_dir=str(base / 'cache'), force_gate=True)
        client = DecisionClient(config) if args.live else SyntheticReviewer()
        samples = []
        for _ in range(1 if args.live else 5):
            result = build_pack(repo, 'Fix price rounding; preserve existing behavior', [memory], config, client)
            samples.append({'mode': result['mode'], 'ready_to_send': result['ready_to_send'], **result['metrics']})
        report = {'fixture': '502-file synthetic repository; intentionally unrelated filler; not representative task accuracy',
                  'review_backend': 'real_jev_laya_secondary_or_jev' if args.live else 'fake_no_network',
                  'cold': samples[0], 'warm_samples': samples[1:],
                  'warm_median_ms': statistics.median(s['total_ms'] for s in samples[1:]) if len(samples) > 1 else None,
                  'limitations': ['Estimated token counts', 'No final-model TTFT or accuracy measurement',
                                  'Synthetic reduction does not establish the 85–95% production target']}
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
