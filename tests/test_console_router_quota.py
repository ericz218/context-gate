"""Tests for configured per-key and aggregate router quota queries."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import shutil
import subprocess
import unittest
import urllib.request
from unittest import mock

import console_router
from console_router import RouterManager
from console_router_quota import (
    attach_quota_support,
    query_all_quotas,
    query_provider_quotas,
    quota_profile,
    scrub_secrets,
)


class _QuotaUpstreamServer(ThreadingHTTPServer):
    daemon_threads = True


class _FakeRouter:
    def __init__(self, snapshot_data, keys_by_provider, secrets_by_key):
        self._snapshot = snapshot_data
        self._keys = keys_by_provider
        self._secrets = secrets_by_key
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, command, args=None):
        args = args or {}
        if command == 'snapshot':
            return self._snapshot
        if command == 'list_provider_keys':
            return list(self._keys.get(args.get('providerId'), []))
        if command == 'reveal_provider_key':
            kid = args.get('id')
            val = self._secrets.get(kid)
            if isinstance(val, Exception):
                raise val
            return val
        raise AssertionError(f'unexpected router command: {command}')


class QuotaProfileTests(unittest.TestCase):
    def test_supported_and_unsupported_providers_match_audit(self):
        supported = [
            {'id': 15, 'name': 'Backboard', 'baseUrl': 'http://127.0.0.1:18192/v1'},
            {'id': 16, 'name': 'CloudBackboard', 'baseUrl': 'https://app.backboard.io/v1'},
            {'id': 1, 'name': 'AMD TokenFactory', 'baseUrl': 'https://developer.amd.com.cn/radeon/api/v1'},
            {'id': 14, 'name': 'Kiro', 'baseUrl': 'https://q.us-east-1.amazonaws.com'},
            {'id': 17, 'name': 'Kiro EU', 'baseUrl': 'https://q.eu-central-1.amazonaws.com/'},
        ]
        unsupported = [
            {'id': 10, 'name': '示例中转', 'baseUrl': 'https://relay.example.com/v1'},
            {'id': 8, 'name': 'APIMaster', 'baseUrl': 'https://apimaster.ai/v1'},
            {'id': 11, 'name': 'Agent Router', 'baseUrl': 'https://agentrouter.org/v1'},
            {'id': 9, 'name': 'Mercury', 'baseUrl': 'https://api.inceptionlabs.ai/v1'},
            {'id': 4, 'name': 'NVIDIA', 'baseUrl': 'https://integrate.api.nvidia.com/v1'},
            {'id': 7, 'name': 'MetaMuse', 'baseUrl': 'https://api.meta.ai/v1'},
            {'id': 6, 'name': 'AWS', 'baseUrl': 'https://bedrock-runtime.us-east-2.amazonaws.com/openai/v1'},
            {'id': 2, 'name': 'Ollama Local', 'baseUrl': 'http://127.0.0.1:11434/v1'},
            {'id': 12, 'name': 'Gemini Web', 'baseUrl': 'http://127.0.0.1:18190/v1'},
            {'id': 13, 'name': 'GPT Codex', 'baseUrl': 'http://127.0.0.1:18191/v1'},
            # Host / URL lookalikes must be rejected cleanly.
            {'id': 90, 'name': 'OtherLocalShim', 'baseUrl': 'http://127.0.0.1:18192/v1'},
            {'id': 91, 'name': 'BackboardCreds', 'baseUrl': 'https://user:pass@app.backboard.io/v1'},
            {'id': 92, 'name': 'AmdEvil', 'baseUrl': 'https://developer.amd.com.cn.evil.test/radeon/api/v1'},
            {'id': 93, 'name': 'KiroPort', 'baseUrl': 'https://q.us-east-1.amazonaws.com:8443'},
            {'id': 94, 'name': 'BadUrl', 'baseUrl': 'not a url'},
        ]

        for p in supported:
            self.assertIsNotNone(quota_profile(p), p)
        for p in unsupported:
            self.assertIsNone(quota_profile(p), p)

        snap = attach_quota_support({'connected': True, 'providers': supported + unsupported})
        by_id = {p['id']: p for p in snap['providers']}
        self.assertTrue(by_id[15]['quotaSupported'])
        self.assertEqual(by_id[15]['quotaUnit'], 'USD')
        self.assertEqual(by_id[1]['quotaKind'], 'daily')
        self.assertEqual(by_id[14]['quotaUnit'], 'credits')
        for p in unsupported:
            self.assertFalse(by_id[p['id']]['quotaSupported'])
            self.assertIsNone(by_id[p['id']]['quotaKind'])


class QuotaQueryTests(unittest.TestCase):
    def setUp(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _send_json(self, code, payload):
                body = json.dumps(payload).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/backboard/balance':
                    key = self.headers.get('X-API-Key')
                    if key == 'espr_bb_ok_1':
                        return self._send_json(200, {
                            'balance_usd': 1.25,
                            'paid_credit_usd': 0.75,
                            'subscription_credits_usd': 0.50,
                            'nash_credit_usd': 0.0,
                            'free_credit_usd': 10.0,
                            'client_id': 101,
                        })
                    if key == 'espr_bb_dup_1':
                        return self._send_json(200, {
                            'balance_usd': 1.25,
                            'paid_credit_usd': 0.75,
                            'subscription_credits_usd': 0.50,
                            'free_credit_usd': 10.0,
                            'client_id': 101,
                        })
                    if key == 'espr_bb_disabled_alive':
                        return self._send_json(200, {
                            'balance_usd': 2.0,
                            'paid_credit_usd': 2.0,
                            'free_credit_usd': 5.0,
                            'client_id': 102,
                        })
                    if key == 'espr_bb_zero':
                        return self._send_json(200, {
                            'balance_usd': 0.0,
                            'paid_credit_usd': 0.0,
                            'free_credit_usd': 5.0,
                            'client_id': 103,
                        })
                    return self._send_json(401, {'detail': f'Invalid API key {key}'})

                if self.path == '/amd/usage':
                    auth = self.headers.get('Authorization', '')
                    if auth == 'Bearer rc-amd-1':
                        return self._send_json(200, {
                            'organization_id': 'oneclick-org-1',
                            'daily_cost_limit_usd': 1.0,
                            'daily_cost_used_usd': 0.25,
                            'daily_cost_remaining_usd': 0.75,
                            'all_time': {'cost': 3.5},
                        })
                    if auth == 'Bearer rc-amd-2':
                        return self._send_json(200, {
                            'organization_id': 'oneclick-org-2',
                            'daily_cost_limit_usd': 1.0,
                            'daily_cost_used_usd': 0.0,
                            'daily_cost_remaining_usd': 1.0,
                            'all_time': {'cost': 0.0},
                        })
                    return self._send_json(403, {'detail': 'forbidden'})

                if self.path.startswith('/kiro/getUsageLimits'):
                    auth = self.headers.get('Authorization', '')
                    tt = self.headers.get('TokenType', '')
                    if auth == 'Bearer ksk_kiro_1' and tt == 'API_KEY':
                        return self._send_json(200, {
                            'subscriptionInfo': {'subscriptionTitle': 'KIRO PRO'},
                            'userInfo': {'userId': 'u-kiro-1'},
                            'usageBreakdownList': [{
                                'usageLimitWithPrecision': 598.0,
                                'currentUsageWithPrecision': 126.67,
                                'bonuses': [
                                    {'status': 'ACTIVE', 'usageLimit': 500.0, 'currentUsage': 0.0},
                                    {'status': 'EXPIRED', 'usageLimit': 999.0, 'currentUsage': 0.0},
                                ],
                            }],
                        })
                    if auth == 'Bearer ksk_kiro_exhausted' and tt == 'API_KEY':
                        return self._send_json(200, {
                            'subscriptionInfo': {'subscriptionTitle': 'KIRO PRO'},
                            'userInfo': {'userId': 'u-kiro-2'},
                            'usageBreakdownList': [{
                                'usageLimitWithPrecision': 500.0,
                                'currentUsageWithPrecision': 500.0,
                                'bonuses': [
                                    {'status': 'ACTIVE', 'usageLimit': 500.0, 'currentUsage': 0.0},
                                ],
                            }],
                        })
                    return self._send_json(401, {'message': 'unauthorized'})

                return self._send_json(404, {'error': 'not found'})

        self.server = _QuotaUpstreamServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = mock.MagicMock()
        import threading
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

        self.urls = {
            'backboard': f'http://127.0.0.1:{self.port}/backboard/balance',
            'amd_tokenfactory': f'http://127.0.0.1:{self.port}/amd/usage',
            'kiro': f'http://127.0.0.1:{self.port}/kiro/getUsageLimits',
        }
        self.snapshot = {
            'providers': [
                {'id': 15, 'name': 'Backboard', 'baseUrl': 'http://127.0.0.1:18192/v1', 'enabled': True},
                {'id': 1, 'name': 'AMD TokenFactory', 'baseUrl': 'https://developer.amd.com.cn/radeon/api/v1', 'enabled': True},
                {'id': 14, 'name': 'Kiro', 'baseUrl': 'https://q.us-east-1.amazonaws.com', 'enabled': True},
                {'id': 10, 'name': '示例中转', 'baseUrl': 'https://relay.example.com/v1', 'enabled': True},
            ]
        }
        self.keys = {
            15: [
                {'id': 101, 'label': 'bb-primary', 'enabled': True, 'priority': 0, 'hasSecret': True},
                {'id': 102, 'label': 'bb-dup', 'enabled': True, 'priority': 1, 'hasSecret': True},
                {'id': 103, 'label': 'bb-disabled-alive', 'enabled': False, 'priority': 2, 'hasSecret': True},
                {'id': 104, 'label': 'bb-zero', 'enabled': True, 'priority': 3, 'hasSecret': True},
                {'id': 105, 'label': 'bb-bad', 'enabled': False, 'priority': 4, 'hasSecret': True},
                {'id': 106, 'label': 'bb-missing', 'enabled': True, 'priority': 5, 'hasSecret': False},
                {'id': 107, 'label': 'bb-empty', 'enabled': False, 'priority': 6, 'hasSecret': True},
                {'id': 108, 'label': 'bb-kc-err', 'enabled': False, 'priority': 7, 'hasSecret': True},
            ],
            1: [
                {'id': 201, 'label': 'amd-1', 'enabled': True, 'priority': 0, 'hasSecret': True},
                {'id': 202, 'label': 'amd-2', 'enabled': True, 'priority': 1, 'hasSecret': True},
            ],
            14: [
                {'id': 301, 'label': 'kiro-pro', 'enabled': True, 'priority': 0, 'hasSecret': True},
            ],
        }
        self.secrets = {
            101: 'espr_bb_ok_1',
            102: 'espr_bb_dup_1',
            103: 'espr_bb_disabled_alive',
            104: 'espr_bb_zero',
            105: 'espr_bb_inactive_secret',
            107: '   ',
            108: ValueError('Keychain failed for espr_VerySecretKey123'),
            201: 'rc-amd-1',
            202: 'rc-amd-2',
            301: 'ksk_kiro_1',
        }
        self.router = _FakeRouter(self.snapshot, self.keys, self.secrets)

    def test_provider_quota_dedup_and_secret_scrubbing(self):
        report = query_provider_quotas(self.router, 15, include_disabled=True, balance_urls=self.urls)
        self.assertEqual(report['unit'], 'USD')
        self.assertEqual(report['totalKeys'], 8)
        self.assertEqual(report['checkedKeys'], 8)
        self.assertEqual(report['enabledChecked'], 4)
        self.assertEqual(report['duplicateAccounts'], 1)
        # Only client:101 ($1.25) counts toward enabledTotal; client:103 is $0; client:102 ($2.00) is disabled.
        self.assertAlmostEqual(report['enabledTotal'], 1.25)
        self.assertAlmostEqual(report['allAliveTotal'], 3.25)
        # Extra free on unique enabled ok accounts: client:101 ($10) + client:103 ($5) = $15.0 (dup #102 excluded)
        self.assertAlmostEqual(report['extraFreeTotal'], 15.0)
        # usableCount counts non-duplicate? Wait: enabled rows with ok and remaining > 0 -> #101 and #102
        self.assertEqual(report['usableCount'], 2)

        by_id = {k['id']: k for k in report['keys']}
        self.assertTrue(by_id[102]['duplicateAccount'])
        self.assertEqual(by_id[105]['status'], 401)
        self.assertNotIn('espr_bb_inactive_secret', by_id[105]['message'])
        self.assertEqual(by_id[106]['message'], '待补密钥')
        self.assertEqual(by_id[107]['message'], '密钥为空')
        self.assertIn('[REDACTED]', by_id[108]['message'])
        self.assertNotIn('espr_VerySecretKey123', by_id[108]['message'])

    def test_all_quotas_combines_totals_distinct_by_unit_and_skips_unsupported(self):
        result = query_all_quotas(self.router, include_disabled=False, balance_urls=self.urls)
        t = result['totals']
        self.assertAlmostEqual(t['usdBalance'], 1.25)
        self.assertAlmostEqual(t['usdDaily'], 1.75)
        self.assertAlmostEqual(t['usdAvailable'], 3.0)
        self.assertAlmostEqual(t['kiroCredits'], 971.33)
        self.assertAlmostEqual(t['extraFreeUsd'], 15.0)
        self.assertEqual(t['supportedProviders'], 3)
        self.assertEqual(t['unsupportedProviders'], 1)
        self.assertEqual(result['unsupportedProviders'], [{'id': 10, 'name': '示例中转'}])

    def test_unsupported_provider_raises_value_error(self):
        with self.assertRaises(ValueError):
            query_provider_quotas(self.router, 10, balance_urls=self.urls)

    def test_scrub_secrets_redacts_prefixes_and_bearer(self):
        text = scrub_secrets('Authorization: Bearer rc-abcdef123456 failed for ksk_1234567890')
        self.assertNotIn('rc-abcdef123456', text)
        self.assertNotIn('ksk_1234567890', text)
        self.assertIn('[REDACTED]', text)

    def test_kiro_base_quota_only_excludes_bonus_when_base_positive(self):
        self.snapshot['providers'][2]['baseQuotaOnly'] = True
        report = query_provider_quotas(self.router, 14, include_disabled=True, balance_urls=self.urls)
        self.assertTrue(report['baseQuotaOnly'])
        self.assertAlmostEqual(report['enabledTotal'], 471.33)
        self.assertAlmostEqual(report['extraBonusCredits'], 500.0)
        self.assertEqual(report['usableCount'], 1)
        self.assertEqual(report['pausedCount'], 0)
        key = report['keys'][0]
        self.assertTrue(key['enabled'])
        self.assertFalse(key['paused'])
        self.assertAlmostEqual(key['baseRemaining'], 471.33)
        self.assertAlmostEqual(key['bonusRemaining'], 500.0)

        totals = query_all_quotas(self.router, include_disabled=False, balance_urls=self.urls)['totals']
        self.assertAlmostEqual(totals['kiroCredits'], 471.33)
        self.assertAlmostEqual(totals['extraBonusCredits'], 500.0)

    def test_kiro_base_quota_only_pauses_without_disabling_when_base_exhausted(self):
        self.snapshot['providers'][2]['baseQuotaOnly'] = True
        self.secrets[301] = 'ksk_kiro_exhausted'
        report = query_provider_quotas(self.router, 14, include_disabled=True, balance_urls=self.urls)
        self.assertAlmostEqual(report['enabledTotal'], 0.0)
        self.assertAlmostEqual(report['extraBonusCredits'], 500.0)
        self.assertEqual(report['usableCount'], 0)
        self.assertEqual(report['pausedCount'], 1)
        key = report['keys'][0]
        self.assertTrue(key['enabled'])
        self.assertTrue(key['paused'])
        self.assertEqual(key['pauseReason'], 'base_quota_exhausted')


class RouterManagerAndUIIntegrationTests(unittest.TestCase):
    def test_snapshot_attaches_support_and_action_dispatches(self):
        router = RouterManager()
        snap = {'providers': [{'id': 1, 'name': 'AMD TokenFactory', 'baseUrl': 'https://developer.amd.com.cn/radeon/api/v1'}]}
        with mock.patch.object(router, 'call', return_value=snap):
            out = router.snapshot()
        self.assertTrue(out['connected'])
        self.assertTrue(out['providers'][0]['quotaSupported'])

        with self.assertRaises(ValueError):
            router.action({'command': 'query_all_quotas', 'args': 'bad'})

        with mock.patch('console_router_quota.query_all_quotas', return_value={'ok': True}) as qall:
            res = router.action({'command': 'query_all_quotas', 'args': {'includeDisabled': True}})
        self.assertEqual(res, {'result': {'ok': True}})
        qall.assert_called_once_with(router, include_disabled=True)

        with mock.patch('console_router_quota.query_provider_quotas', return_value={'providerId': 15}) as qone:
            res2 = router.action({'command': 'query_provider_quotas', 'args': {'providerId': 15, 'includeDisabled': False}})
        self.assertEqual(res2, {'result': {'providerId': 15}})
        qone.assert_called_once_with(router, 15, include_disabled=False)

    def test_cli_outputs_json_and_handles_unknown_provider(self):
        fake_report = {
            'checkedAt': 1000,
            'includeDisabled': False,
            'providers': [],
            'unsupportedProviders': [{'id': 10, 'name': '示例中转'}],
            'totals': {
                'usdAvailable': 1.5, 'usdBalance': 0.5, 'usdDaily': 1.0,
                'kiroCredits': 10.0, 'extraFreeUsd': 0.0,
                'supportedProviders': 2, 'unsupportedProviders': 1,
                'checkedKeys': 2, 'usableKeys': 2,
            },
        }
        buf = io.StringIO()
        with mock.patch('console_router.RouterManager.query_all_quotas', return_value=fake_report):
            with mock.patch('sys.stdout', buf):
                rc = console_router._cli(['quota', '--json'])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())['totals']['usdAvailable'], 1.5)

    def test_ui_renders_quota_controls_and_preserves_panel_across_polling(self):
        if not shutil.which('node'):
            self.skipTest('Node is needed for browser logic checks')
        from console.router_ui import JS
        slice_js = JS[:JS.index('// 模型库：AWS Bedrock 注册表')]
        script = r'''
const assert=require('node:assert/strict');
const created={};
const el=id=>created[id]||(created[id]={id,value:'',innerHTML:'',textContent:'',checked:false,disabled:false,hidden:false,dataset:{},classList:{toggle(){},add(){},remove(){}},addEventListener(){},removeEventListener(){},focus(){},querySelector(){return null;},querySelectorAll(){return[];},contains(){return false;}});
const $=id=>el(id);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const T=s=>s,LOCALE=()=>'zh-CN',num=n=>String(n),nsp=(a,b,c)=>String(c),ddSync=()=>{};
async function centerApi(path,body){if(body?.command==='list_provider_keys'){if(body?.args?.providerId===14)return {result:[{id:301,label:'k-kiro',enabled:true,hasSecret:true,paused:true,pauseReason:'base_quota_exhausted',baseRemaining:0,bonusRemaining:500}]};return {result:[{id:1,label:'k1',enabled:true,hasSecret:true}]};}return {result:{}};}
const matchMedia=()=>({matches:false,addEventListener(){}}),localStorage={getItem:()=>null,setItem(){}},document={activeElement:null};
function dialogClose(){}function dialogOpen(){}function dialogCancelAnimation(){}
function syncRouterFilters(){}function loadCapabilities(){}function loadBedrock(){}function reconcile(){}
''' + slice_js + r'''
(async()=>{
 routerTab='providers';
 routerData={
  connected:true,
  dashboard:{server:{},usage:{today:{},byModel:[],byProvider:[]}},
  aliases:[],models:[],logs:[],settings:{},info:{},
  providers:[
   {id:15,name:'Backboard',baseUrl:'http://127.0.0.1:18192/v1',note:'',keyCount:2,keyStrategy:'priority',enabled:true,quotaSupported:true},
   {id:14,name:'Kiro',baseUrl:'https://q.us-east-1.amazonaws.com',note:'',keyCount:1,keyStrategy:'priority',enabled:true,baseQuotaOnly:true,pausedKeyCount:1,enabledKeyCount:1,quotaSupported:true},
   {id:10,name:'示例中转',baseUrl:'https://relay.example.com/v1',note:'',keyCount:1,keyStrategy:'priority',enabled:true,quotaSupported:false}
  ]
 };
 renderRouterContent(true);
 const html1=el('router-content').innerHTML;
 assert.ok(html1.includes('data-router-action="quota-all"'));
 assert.ok(html1.includes('data-router-action="quota-provider" data-router-id="15"'));
 assert.ok(!html1.includes('data-router-action="quota-provider" data-router-id="10"'));
 assert.ok(html1.includes('data-router-base-only="14"'));
 assert.ok(!html1.includes('data-router-base-only="10"'));
 assert.ok(html1.includes('已暂停（基础额度用完） 1/1'));
 routerQuota={
  checkedAt:1700000000000,
  totals:{usdAvailable:12.5,usdBalance:1.5,usdDaily:11,kiroCredits:471.33,extraBonusCredits:500,extraFreeUsd:20,supportedProviders:3,unsupportedProviders:10,checkedKeys:35,usableKeys:15},
  providers:[{providerId:14,providerName:'Kiro',unit:'credits',enabledTotal:0,allAliveTotal:0,extraBonusCredits:500,usableCount:0,enabledChecked:1,pausedCount:1,duplicateAccounts:0,keys:[{id:301,label:'k-kiro',enabled:true,paused:true,pauseReason:'base_quota_exhausted',remaining:0,unit:'credits',ok:true,duplicateAccount:false,message:'基础额度已用完（已暂停，赠送 500.00 未启用）',latencyMs:95}]}],
  unsupportedProviders:[{id:10,name:'示例中转'}]
 };
 routerData.providers[0].keyCount=3;
 renderRouterContent(false);
 const html2=el('router-content').innerHTML;
 assert.ok(html2.includes('id="router-quota-panel"'));
 assert.ok(html2.includes('$12.5000'));
 assert.ok(html2.includes('赠送未启用 500.00'));
 assert.ok(html2.includes('1 把已暂停'));
 await routerKeys(14);
 assert.ok(el('router-form').innerHTML.includes('id="router-keys-base-only"'));
 assert.ok(el('router-form').innerHTML.includes('后台已暂停（基础额度用完）'));
 await routerKeys(15);
 assert.ok(el('router-form').innerHTML.includes('id="router-keys-quota"'));
 assert.ok(el('router-form').innerHTML.includes('id="router-keys-quota-top"'));
 assert.ok(el('router-form').innerHTML.includes('id="router-form-status-top"'));
 assert.ok(!el('router-form').innerHTML.includes('id="router-keys-base-only"'));
 await routerKeys(10);
 assert.ok(!el('router-form').innerHTML.includes('id="router-keys-quota"'));
 assert.ok(!el('router-form').innerHTML.includes('id="router-keys-quota-top"'));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        res = subprocess.run(['node'], input=script, text=True, capture_output=True, timeout=15)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == '__main__':
    unittest.main()
