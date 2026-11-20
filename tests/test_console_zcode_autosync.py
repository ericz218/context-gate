import copy
import http.client
import json
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import console_zcode_sync as z

EMPTY = {'schemaVersion': 1, 'config': {'providerConfigRules': {'providerRules': []}, 'modelConfigRules': {'providerModelRules': [], 'manualProviderModelRules': []}}}
OPTION_SPECS = {'reasoningLevel': {'map': {'low': 1, 'high': 3}}}
FULL_PROPERTIES = {'contextWindow': 1000, 'inputFormat': {'supportsImage': True}, 'supportsToolCall': True}


def make_doc(rules=(), smart=(), manual=()):
    d = copy.deepcopy(EMPTY)
    d['config']['providerConfigRules']['providerRules'] = copy.deepcopy(list(rules))
    d['config']['modelConfigRules'] = {'providerModelRules': copy.deepcopy(list(smart)),
                                       'manualProviderModelRules': copy.deepcopy(list(manual))}
    return d


def router_rule(ids=(), optionSpecs=None):
    cfg = {'api': {'type': 'openai-compatible', 'baseUrl': z.BASE_URL}, 'access': {'opaque': 'FAKE-PRESERVE'},
           'personalModelIds': list(ids), 'modelOrder': list(ids)}
    if optionSpecs is not None:
        cfg['optionSpecs'] = copy.deepcopy(optionSpecs)
    return {'providerId': z.PROVIDER_ID, 'config': cfg}


def unrelated_doc():
    return make_doc(rules=[{'providerId': 'unrelated', 'config': {'access': {'opaque': 'UNCHANGED'}}}])


class FakeRouter:
    def __init__(self, models=('alias',), registry=None, call_error=False):
        self.models = list(models)
        self.registry = registry
        self.call_error = call_error

    def snapshot(self):
        rows = [{'modelId': m, 'upstreamModel': 'up-' + m, 'enabled': True, 'providerEnabled': True, 'displayName': m}
                for m in self.models]
        rows.append({'modelId': 'disabled', 'enabled': False, 'providerEnabled': True})
        return {'connected': True, 'models': rows}

    def call(self, command, args=None):
        if self.call_error:
            raise RuntimeError('boom')
        return self.registry


class ActionRouter(FakeRouter):
    def __init__(self, models=('alias',)):
        super().__init__(models)
        self.commands = []

    def action(self, body):
        self.commands.append(body.get('command'))
        return {'result': {'ok': True}}


class AutoSyncBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.default = self.home / '.zcode/v2/provider_config.json'
        self.second = self.home / 'zcode-account2/.zcode/v2/provider_config.json'

    def write(self, path, document):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))

    def load(self, path):
        return json.loads(path.read_text())

    def model_rules(self, path, mid):
        rules = self.load(path)['config']['modelConfigRules']
        return [r for r in rules['providerModelRules'] + rules['manualProviderModelRules']
                if r.get('providerId') == z.PROVIDER_ID and r.get('modelId') == mid]


class MirrorTests(AutoSyncBase):
    def test_mirror_replaces_membership_and_disables_removed(self):
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': m, 'config': {'enabled': True}} for m in 'ABC']
        self.write(self.default, make_doc(rules=[router_rule('ABC')], smart=smart))
        result = z.sync(self.home, ['B', 'D'], ['default'], apply=True, mirror=True)
        self.assertTrue(result['results'][0]['ok'])
        cfg = z.lmr_rule(self.load(self.default))['config']
        self.assertEqual(cfg['personalModelIds'], ['B', 'D'])
        self.assertEqual(cfg['modelOrder'], ['B', 'D'])
        self.assertIs(self.model_rules(self.default, 'A')[0]['config']['enabled'], False)
        self.assertIs(self.model_rules(self.default, 'C')[0]['config']['enabled'], False)
        self.assertIs(self.model_rules(self.default, 'B')[0]['config']['enabled'], True)
        self.assertIs(self.model_rules(self.default, 'D')[0]['config']['enabled'], True)

    def test_mirror_leaves_other_providers_alone(self):
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': m, 'config': {'enabled': True}} for m in 'ABC']
        smart += [{'providerId': 'other', 'modelId': 'A', 'config': {'enabled': True}},
                  {'providerId': 'other', 'modelId': 'Z', 'config': {'enabled': True}}]
        rules = [router_rule('ABC'), {'providerId': 'other', 'config': {'access': {'opaque': 'UNCHANGED'}}}]
        self.write(self.default, make_doc(rules=rules, smart=smart))
        before = self.load(self.default)
        other_rules = [r for r in before['config']['providerConfigRules']['providerRules'] if r['providerId'] == 'other']
        other_models = [r for r in before['config']['modelConfigRules']['providerModelRules'] if r['providerId'] == 'other']
        z.sync(self.home, ['B'], ['default'], apply=True, mirror=True)
        after = self.load(self.default)
        self.assertEqual([r for r in after['config']['providerConfigRules']['providerRules'] if r['providerId'] == 'other'], other_rules)
        self.assertEqual([r for r in after['config']['modelConfigRules']['providerModelRules'] if r['providerId'] == 'other'], other_models)

    def test_non_mirror_only_adds(self):
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': m, 'config': {'enabled': True}} for m in 'ABC']
        self.write(self.default, make_doc(rules=[router_rule('ABC')], smart=smart))
        result = z.sync(self.home, ['B', 'D'], ['default'], apply=True)
        self.assertTrue(result['results'][0]['ok'])
        cfg = z.lmr_rule(self.load(self.default))['config']
        self.assertEqual(cfg['personalModelIds'], ['A', 'B', 'C', 'D'])
        self.assertEqual(cfg['modelOrder'], ['A', 'B', 'C', 'D'])
        self.assertIs(self.model_rules(self.default, 'A')[0]['config']['enabled'], True)
        self.assertIs(self.model_rules(self.default, 'C')[0]['config']['enabled'], True)

    def test_kiro_moves_to_claude_and_stays_there_on_auto_sync(self):
        opus, auto = 'kiro/claude-opus-5.5', 'kiro/auto'
        claude = router_rule(['chun/claude-opus-5.5'])
        claude['providerId'] = z.CLAUDE_PROVIDER_ID
        config = {'enabled': True, 'properties': copy.deepcopy(FULL_PROPERTIES)}
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': opus, 'config': config}]
        self.write(self.default, make_doc(rules=[router_rule(['domestic', opus]), claude], smart=smart))

        self.assertTrue(z.sync(self.home, [opus, auto], apply=True)['results'][0]['ok'])
        for aliases in ([opus, auto, 'domestic'], [opus, 'domestic']):
            router = FakeRouter(aliases)
            self.assertTrue(z.auto_sync(router, self.home)['ok'])
            doc = self.load(self.default)
            domestic, claude = doc['config']['providerConfigRules']['providerRules']
            expected_kiro = [mid for mid in aliases if mid.startswith('kiro/')]
            for field in ('personalModelIds', 'modelOrder'):
                self.assertEqual(domestic['config'][field], ['domestic'])
                self.assertEqual(claude['config'][field], ['chun/claude-opus-5.5'] + expected_kiro)
            self.assertEqual(self.model_rules(self.default, opus), [])
            rows = doc['config']['modelConfigRules']['providerModelRules']
            opus_rule = next(r for r in rows if r['modelId'] == opus)
            self.assertEqual(opus_rule, {'providerId': z.CLAUDE_PROVIDER_ID, 'modelId': opus, 'config': config})
            self.assertEqual(next(r for r in rows if r['modelId'] == auto)['config']['enabled'], auto in aliases)
            self.assertEqual(z.auto_sync(router, self.home)['changed'], 0)

    def test_mirror_empty_clears_models(self):
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': m, 'config': {'enabled': True}} for m in 'AB']
        self.write(self.default, make_doc(rules=[router_rule('AB')], smart=smart))
        result = z.sync(self.home, [], ['default'], apply=True, mirror=True)
        self.assertTrue(result['results'][0]['ok'])
        cfg = z.lmr_rule(self.load(self.default))['config']
        self.assertEqual(cfg['personalModelIds'], [])
        self.assertEqual(cfg['modelOrder'], [])
        self.assertTrue(all(r['config']['enabled'] is False for r in self.load(self.default)['config']['modelConfigRules']['providerModelRules']))

    def test_mirror_empty_without_router_rule_creates_nothing(self):
        doc = make_doc()
        self.assertEqual(z.merge(doc, [], None, mirror=True), doc)

    def test_backup_prune_keeps_newest_ten(self):
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        folder = self.default.parent
        # Non-matching names and a directory must survive pruning.
        extras = [folder / 'provider_config.json.lmr-backup-note',
                  folder / 'provider_config.json.lmr-backup-1',
                  folder / 'provider_config.json.bak',
                  folder / 'other.json.lmr-backup-5']
        extras[1].mkdir()
        for path in (extras[0], extras[2], extras[3]):
            path.write_text('keep')
        for i in range(12):
            result = z.sync(self.home, ['m%d' % i], ['default'], apply=True, mirror=True)
            self.assertTrue(result['results'][0]['changed'])
        backups = [p for p in folder.iterdir() if re.fullmatch(r'provider_config\.json\.lmr-backup-[0-9]+', p.name) and p.is_file()]
        self.assertEqual(len(backups), 10)
        for path in extras:
            self.assertTrue(path.exists(), path.name)


class AutoSyncTests(AutoSyncBase):
    def test_multiple_accounts_counts_and_idempotence(self):
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        self.write(self.second, unrelated_doc())
        router = FakeRouter(['alias'])
        self.assertEqual(z.auto_sync(router, self.home), {'ok': True, 'accounts': 2, 'changed': 2, 'failed': 0})
        self.assertEqual(z.lmr_rule(self.load(self.default))['config']['personalModelIds'], ['alias'])
        self.assertEqual(z.lmr_rule(self.load(self.second))['config']['personalModelIds'], ['alias'])
        self.assertEqual(z.auto_sync(router, self.home), {'ok': True, 'accounts': 2, 'changed': 0, 'failed': 0})

    def test_failed_account_is_counted(self):
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        self.second.parent.mkdir(parents=True)
        self.second.write_text('{broken')
        self.assertEqual(z.auto_sync(FakeRouter(['alias']), self.home), {'ok': False, 'accounts': 2, 'changed': 1, 'failed': 1})

    def test_no_accounts_returns_zero(self):
        self.assertEqual(z.auto_sync(FakeRouter(['alias']), self.home), {'ok': True, 'accounts': 0, 'changed': 0, 'failed': 0})

    def test_survives_registry_call_exception(self):
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        result = z.auto_sync(FakeRouter(['alias'], call_error=True), self.home)
        self.assertEqual(result, {'ok': True, 'accounts': 1, 'changed': 1, 'failed': 0})
        rule = self.model_rules(self.default, 'alias')[0]
        self.assertEqual(rule['config']['properties'], {'supportsToolCall': True})


class CapabilityTests(AutoSyncBase):
    def test_copies_capabilities_from_existing_model(self):
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': 'X', 'config': {'enabled': True,
                  'properties': copy.deepcopy(FULL_PROPERTIES), 'optionSpecs': copy.deepcopy(OPTION_SPECS)}}]
        self.write(self.default, make_doc(rules=[router_rule(['X'])], smart=smart))
        self.write(self.second, unrelated_doc())
        z.sync(self.home, ['X'], None, apply=True)
        rule = self.model_rules(self.second, 'X')[0]
        self.assertEqual(rule['config']['properties'], FULL_PROPERTIES)
        self.assertEqual(rule['config']['optionSpecs'], OPTION_SPECS)

    def test_new_model_gets_defaults(self):
        self.write(self.default, make_doc(rules=[router_rule(['X'], optionSpecs=OPTION_SPECS)]))
        z.sync(self.home, ['Y'], ['default'], apply=True, details={'Y': {'supportsImage': True}})
        cfg = self.model_rules(self.default, 'Y')[0]['config']
        self.assertEqual(cfg['properties'], {'supportsToolCall': True, 'inputFormat': {'supportsImage': True}})
        self.assertEqual(cfg['optionSpecs'], OPTION_SPECS)
        self.assertNotIn('contextWindow', cfg['properties'])

    def test_existing_properties_are_not_overwritten(self):
        custom = {'supportsToolCall': False, 'contextWindow': 777}
        smart = [{'providerId': z.PROVIDER_ID, 'modelId': 'X', 'config': {'enabled': True,
                  'properties': copy.deepcopy(custom), 'optionSpecs': {'custom': {'k': 1}}}}]
        self.write(self.default, make_doc(rules=[router_rule(['X'])], smart=smart))
        z.sync(self.home, ['X'], ['default'], apply=True, details={'X': {'supportsImage': True, 'contextWindow': 5000}})
        cfg = self.model_rules(self.default, 'X')[0]['config']
        self.assertEqual(cfg['properties'], custom)
        self.assertEqual(cfg['optionSpecs'], {'custom': {'k': 1}})

    def test_input_modalities_parsing(self):
        cases = [
            ('["TEXT","IMAGE"]', True),
            ('["TEXT"]', False),
            ('[]', None),
            ('not json', None),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.write(self.default, make_doc(rules=[router_rule(['old'])]))
                router = FakeRouter(['Z'], registry=[{'inferenceProfileId': 'up-Z', 'inputModalities': raw}])
                z.auto_sync(router, self.home)
                props = self.model_rules(self.default, 'Z')[0]['config']['properties']
                if expected is None:
                    self.assertNotIn('inputFormat', props)
                else:
                    self.assertIs(props['inputFormat']['supportsImage'], expected)

    def test_registry_wrapped_in_dict(self):
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        registry = {'models': [{'modelId': 'up-Z', 'inputModalities': ['TEXT', 'IMAGE'], 'contextWindow': 4096}]}
        z.auto_sync(FakeRouter(['Z'], registry=registry), self.home)
        props = self.model_rules(self.default, 'Z')[0]['config']['properties']
        self.assertEqual(props, {'supportsToolCall': True, 'inputFormat': {'supportsImage': True}, 'contextWindow': 4096})


class HTTPWiringTests(AutoSyncBase):
    def setUp(self):
        super().setUp()
        from console import app
        self.write(self.default, make_doc(rules=[router_rule(['old'])]))
        self.write(self.second, unrelated_doc())
        patcher = patch.object(app.Path, 'home', return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = app
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.local_token = 'TEST-LOCAL-BOUNDARY'
        self.server.router = ActionRouter(['alias'])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, body):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            headers = {'Origin': 'http://127.0.0.1:' + str(self.server.server_port), 'Connection': 'close',
                       'Content-Type': 'application/json'}
            conn.request('POST', '/' + self.server.local_token + '/v1/router/action', body=json.dumps(body), headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read().decode())
        finally:
            conn.close()

    def test_action_adds_zcode_sync_only_for_sync_commands(self):
        status, data = self.post({'command': 'set_bedrock_model_enabled', 'args': {'input': {'id': 1, 'enabled': True}}})
        self.assertEqual(status, 200)
        self.assertEqual(data['result'], {'ok': True})
        self.assertEqual(data['zcodeSync'], {'ok': True, 'accounts': 2, 'changed': 2, 'failed': 0})
        self.assertEqual(z.lmr_rule(self.load(self.default))['config']['personalModelIds'], ['alias'])
        before = self.default.read_bytes()
        status, data = self.post({'command': 'clear_logs', 'args': {}})
        self.assertEqual(status, 200)
        self.assertNotIn('zcodeSync', data)
        self.assertEqual(self.default.read_bytes(), before)

    def test_sync_failure_does_not_fail_action(self):
        with patch.object(self.app, 'zcode_auto_sync', side_effect=RuntimeError('boom')):
            status, data = self.post({'command': 'upsert_model', 'args': {}})
        self.assertEqual(status, 200)
        self.assertEqual(data['result'], {'ok': True})
        self.assertEqual(data['zcodeSync'], {'ok': False, 'accounts': 0, 'changed': 0, 'failed': 0})


if __name__ == '__main__':
    unittest.main()
