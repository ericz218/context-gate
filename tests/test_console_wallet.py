"""Model Wallet tests migrated from proto/tests (test_backend, test_acceptance, test_ledger_acceptance)
plus Context Gate integration: route table, token/Origin guard, database location and page assembly.
All data is synthetic. Every test uses a temporary directory and port 0."""
import hashlib, json, sqlite3, sys, tempfile, threading, unittest, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_wallet import Wallets, DomainError, AWSAdapter, UnsupportedAdapter, WalletSDK, CATALOG_PATH, calculate, charge, normalize_usage
from console.app import make_server


def fixture(mid='test',provider='Test',price='1',status='CURRENT',cache=True):
    return {'id':mid,'name':mid,'displayName':mid,'apiProvider':provider,'creator':'Creator','status':status,'category':['Coding','Text'],'supportsCache':cache,'supportsTools':True,'contextWindow':4000000,'inputPrice':price,'outputPrice':'5','cacheReadPrice':'0.1','cacheWritePrice':'1.25'}

class WalletBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Wallets(Path(self.temp.name)/'state',Path(self.temp.name)/'missing.json')
        self.app.update_catalog({'catalogVersion':'test-1','models':[fixture(),fixture('other','Other','0.5'),fixture('old',status='DEPRECATED'),fixture('unknown',price=None)]})
        self.wallet=self.app.create_wallet({'name':'Test wallet','provider':'Test','currentBalance':'10','initialCredit':'10'})
    def tearDown(self):self.temp.cleanup()
    def payload(self,**p):return dict({'requestId':'req','modelId':'test','estimatedInputTokens':1000000,'estimatedOutputTokens':0,'estimatedCacheRatio':0},**p)
    def error(self,code,fn,*args):
        with self.assertRaises(DomainError) as ctx:fn(*args)
        self.assertEqual(ctx.exception.code,code)
    def test_three_modes_and_unused_price(self):
        m=self.app.custom({'name':'Input only','inputPrice':'1','outputPrice':None,'supportsCache':False})
        r=self.app.calculate({'mode':'requests','modelId':m['id'],'averageInputTokens':'1000000','averageOutputTokens':'0','budget':'10'})
        self.assertEqual(r['estimatedRequests'],'10');self.assertEqual(r['costPerRequest'],'1')
        self.error('PRICE_UNAVAILABLE',self.app.calculate,{'modelId':m['id']})
        result=self.app.calculate({'mode':'tokens','customModel':fixture(),'totalTokens':'1000000'})
        self.assertEqual(Decimal(result['totalCost']),Decimal('1.152'))
    def test_currencies_transient_and_wallet_conversion(self):
        self.error('EXCHANGE_RATE_UNAVAILABLE',self.app.calculate,{'modelId':'test','currency':'CAD'})
        self.app.update_settings({'exchangeRates':{'USD':'1','CAD':'1.4','CNY':'7'}})
        r=self.app.calculate({'mode':'tokens','customModel':dict(fixture(),currency='CAD'),'totalTokens':'1000000','cacheRatio':0})
        self.assertEqual(Decimal(r['totalCost']),Decimal('1.8')/Decimal('1.4'))
        w=self.app.create_wallet({'provider':'Other','currency':'CAD','currentBalance':'1.4'})
        q=self.app.check_budget(self.payload(modelId='other',estimatedInputTokens=2000000));self.assertTrue(q['allowed']);self.assertEqual(q['reservedAmount'],'1.40')
    def test_registry_filters_bulk_favorites_recent(self):
        self.assertEqual(len(self.app.models({'providers':'Test','categories':'Coding','minContext':'1000000'})['models']),2)
        self.assertEqual(self.app.models({'price':'unknown'})['models'][0]['id'],'unknown')
        self.assertEqual(self.app.models({'inputMax':'0.6'})['models'][0]['id'],'other')
        self.app.patch_model('test',{'favorite':True});self.app.calculate({'modelId':'test'})
        self.assertEqual(self.app.models({'favorites':1})['models'][0]['id'],'test');self.assertEqual(self.app.settings()['recentModels'][0],'test')
        result=self.app.bulk({'ids':['test','other'],'action':'hide'});self.assertEqual(len(self.app.models()['models']),1)
        self.app.undo(result['undoId']);self.assertFalse(self.app.model('test')['hidden'])
        self.app.bulk({'ids':['test'],'action':'disable'});self.assertFalse(self.app.model('test')['enabled'])
    def test_catalog_update_preserves_settings_and_history(self):
        self.app.patch_model('test',{'favorite':True,'hidden':True,'enabled':False,'notes':'User notes','priceOverride':{'inputPrice':'0.2'}})
        custom = self.app.custom({'name':'User model','inputPrice':'3','outputPrice':'4'})
        self.app.update_catalog({'catalogVersion':'test-2','models':[fixture(price='2')]})
        self.assertEqual(self.app.model(custom['id'])['inputPrice'], '3')
        self.assertEqual(self.app.model('test')['priceOverride'], {'inputPrice':'0.2'})
        self.assertTrue(self.app.model('test')['hidden'])
        m=self.app.model('test');self.assertEqual(m['inputPrice'],'2');self.assertEqual(m['notes'],'User notes');self.assertFalse(m['enabled']);self.assertTrue(m['favorite'])
        with self.app.connect() as c:self.assertGreater(c.execute('SELECT COUNT(*) FROM price_history WHERE model_id="test"').fetchone()[0],1)
    def test_custom_duplicate_export_import(self):
        m=self.app.custom({'name':'Discount'},'test');self.app.patch_model(m['id'],{'favorite':True})
        data=self.app.export();new=Wallets(Path(self.temp.name)/'new-state',Path(self.temp.name)/'missing.json');new.update_catalog({'models':[fixture(),fixture('other','Other','0.5'),fixture('old',status='DEPRECATED'),fixture('unknown',price=None)]})
        result=new.import_data({'data':data});self.assertTrue(result['imported']);self.assertTrue(new.model(m['id'])['favorite'])
        self.error('SECRETS_FORBIDDEN',new.import_data,{'schemaVersion':1,'settings':{'apiKey':'not-a-key'}})
    def test_wallet_sources_and_connected_normalizer(self):
        w=self.app.create_wallet({'provider':'AWS','type':'CONNECTED','currentBalance':'25'});self.assertEqual(w['balanceSource'],'ESTIMATED');self.assertEqual(w['connectionStatus'],'UNCONNECTED')
        rows=AWSAdapter().normalizeCredits({'credits':[{'remainingAmount':{'currencyAmount':'12.3','currencyCode':'USD'},'initialAmount':{'currencyAmount':'100','currencyCode':'USD'},'endDate':2000000000,'applicableProductNames':['Amazon Bedrock']}]})
        self.assertEqual(rows[0]['currentBalance'],'12.3');self.assertEqual(rows[0]['balanceSource'],'LIVE_API');self.assertEqual(UnsupportedAdapter().syncBalance()['status'],'UNSUPPORTED')
        self.error('INVALID_INPUT',self.app.patch_wallet,w['id'],{'balanceSource':'LIVE_API'})
    def test_wallet_priority_expiring_and_fallback(self):
        self.app.patch_wallet(self.wallet['id'],{'priority':3})
        w=self.app.create_wallet({'provider':'Test','currentBalance':'2','priority':1,'expiresAt':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        self.assertEqual(self.app.check_budget(self.payload())['walletId'],w['id'])
        self.assertEqual(self.app.check_budget(self.payload(estimatedInputTokens=3000000))['walletId'],self.wallet['id'])
        self.app.patch_wallet(w['id'],{'priority':9});self.assertEqual(self.app.check_budget(self.payload(walletStrategy='SOONEST_EXPIRY_FIRST'))['walletId'],w['id'])
        self.app.patch_wallet(w['id'],{'eligibleModels':['other']});self.assertEqual(self.app.check_budget(self.payload())['walletId'],self.wallet['id'])
    def test_limits_include_pending_and_guard(self):
        self.app.patch_wallet(self.wallet['id'],{'limits':{'daily':'1.5','perRequest':'1'}});self.app.reserve(self.payload())
        self.error('INSUFFICIENT_BALANCE',self.app.reserve,self.payload(requestId='second'))
        self.app.update_settings({'costGuard':{'mode':'REQUIRE_APPROVAL','threshold':'0.1'}})
        self.error('APPROVAL_REQUIRED',self.app.check_budget,self.payload())
    def test_actual_overrun_debt_and_refund(self):
        self.app.reserve(self.payload())
        record=self.app.settle({'requestId':'req','usage':{'inputTokens':2000000,'outputTokens':2000000},'streaming':True,'simulated':True})
        self.assertEqual(record['actualCost'],'12');self.assertEqual(record['debt'],'2');self.assertEqual(record['kind'],'SIMULATED');self.assertEqual(self.app.wallet(self.wallet['id'])['reservedBalance'],'0')
        r=self.app.refund({'requestId':'req','refundId':'refund','amount':'3'});self.assertEqual(self.app.refund({'requestId':'req','refundId':'refund','amount':'3'}),r)
        self.error('IDEMPOTENCY_CONFLICT',self.app.refund,{'requestId':'req','refundId':'refund','amount':'4'})
        self.error('REFUND_EXCEEDED',self.app.refund,{'requestId':'req','refundId':'another','amount':'10'})
    def test_unknown_usage_retained_reconcile(self):
        self.app.reserve(self.payload());self.assertEqual(self.app.settle({'requestId':'req'})['state'],'USAGE_UNKNOWN')
        self.app.settle({'requestId':'req','usage':{'inputTokens':10,'outputTokens':2}});self.assertEqual(len(self.app.rows('usage')),1)
    def test_route_capabilities_provider_fallback(self):
        self.app.create_wallet({'provider':'Other','currentBalance':'2'})
        r=self.app.route(self.payload(modelIds=['old','unknown','test','other'],strategy='CHEAPEST_FIRST',requiredCapabilities=['Tools']))
        self.assertEqual(r['selected']['modelId'],'other');self.assertTrue(r['simulation']);self.assertEqual(len(r['rejected']),2)
        r=self.app.route(self.payload(modelIds=['test'],requiredCapabilities=['Vision']));self.assertIsNone(r['selected'])
    def test_pricing_bands_and_version_snapshot(self):
        m=fixture('band');prices=[]
        for mode,price,cond in [('SHORT_CONTEXT','1',{'inputTokensMaxInclusive':100000}),('LONG_CONTEXT','2',{'inputTokensMinExclusive':100000})]:
            for typ,value in [('INPUT_TOKEN',price),('OUTPUT_TOKEN','5')]:prices.append({'modelId':'band','endpointId':'band','priceType':typ,'pricePerUnit':value,'unit':'MILLION_TOKENS','pricingMode':mode,'conditions':cond})
        self.app.update_catalog({'models':[m],'prices':prices});self.error('PRICE_CONDITION_UNRESOLVED',self.app.calculate,{'modelId':'band','cacheRatio':0})
        r=self.app.calculate({'modelId':'band','cacheRatio':0,'pricingMode':'SHORT_CONTEXT','budget':'100'});self.assertEqual(r['effectiveCostPerMillion'],'1.8')
        q=self.app.check_budget(self.payload(modelId='band',estimatedInputTokens=100001));self.assertEqual(Decimal(q['estimatedCost']),Decimal('.200002'))
    def test_dashboard_audit_and_sdk(self):
        sdk=WalletSDK(self.app);sdk.reserve(self.payload());sdk.settle({'requestId':'req','usage':{'inputTokens':100,'outputTokens':10,'cacheReadTokens':90}})
        d=self.app.dashboard();self.assertEqual(d['periods']['today']['requests'],1);self.assertGreater(Decimal(d['cacheSavings']),0)
        self.assertIn('action',self.app.rows('audit')[0]);self.assertIn('agentId',d['groups']);self.assertEqual(sdk.getBalance(self.wallet['id'])['id'],self.wallet['id'])
    def test_strict_unit_and_usage(self):
        self.error('UNSUPPORTED_UNIT',charge,{'INPUT_TOKEN':{'unit':'BOGUS','pricePerUnit':'1'}},{'uncachedInputTokens':1})
        self.error('USAGE_UNKNOWN',normalize_usage,{'outputTokens':1})
        self.error('INVALID_USAGE',normalize_usage,{'inputTokens':1,'outputTokens':1,'reasoningTokens':2})
    def test_reset_requires_confirmation(self):
        self.error('CONFIRMATION_REQUIRED',self.app.reset,{'target':'all'})
        self.app.reset({'target':'all','confirmation':'RESET'});self.assertEqual(self.app.wallets()['wallets'],[])
    def test_b1_null_threshold_keeps_budget_working(self):
        self.app.patch_wallet(self.wallet['id'],{'lowBalanceThreshold':None})
        r=self.app.check_budget(self.payload());self.assertTrue(r['allowed']);self.assertFalse(r['lowBalance'])
        self.assertEqual(self.app.reserve(self.payload(requestId='b1'))['state'],'RESERVED')
    def test_b1_invalid_wallet_numbers_rejected_at_write(self):
        for bad in [{'priority':None},{'priority':'high'},{'priority':True},{'lowBalanceThreshold':'abc'},{'limits':{'daily':'abc'}},{'limits':{'perRequest':'-1'}},{'limits':'daily'}]:
            self.error('INVALID_INPUT',self.app.patch_wallet,self.wallet['id'],bad)
        for bad in [{'priority':None},{'lowBalanceThreshold':'abc'},{'limits':{'monthly':'x'}}]:
            self.error('INVALID_INPUT',self.app.create_wallet,dict({'provider':'Test','currentBalance':'2'},**bad))
        self.error('INVALID_INPUT',self.app.create_wallet,{'provider':'Test','currentBalance':None})
        w=self.app.create_wallet({'provider':'Test','currentBalance':'2','lowBalanceThreshold':None,'limits':{'daily':None}})
        self.assertTrue(self.app.check_budget(self.payload(walletId=w['id']))['allowed'])
    def test_b2_reset_builtins_without_catalog_is_domain_error(self):
        self.error('CATALOG_UNAVAILABLE',self.app.reset,{'target':'builtins','confirmation':'RESET'})
    def test_b3_settings_enum_values_validated(self):
        self.error('INVALID_INPUT',self.app.update_settings,{'costGuard':{'mode':'NOPE','threshold':None}})
        self.error('INVALID_INPUT',self.app.update_settings,{'walletStrategy':'CHEAPEST_FIRST'})
        self.app.update_settings({'walletStrategy':'HIGHEST_BALANCE_FIRST','costGuard':{'mode':'REQUIRE_APPROVAL','threshold':None}})
        self.assertEqual(self.app.settings()['walletStrategy'],'HIGHEST_BALANCE_FIRST')
        self.app.update_settings({'walletStrategy':'MANUAL_PRIORITY','costGuard':{'mode':'BLOCK','threshold':None}})

class WalletCalculatorAcceptance(unittest.TestCase):
    def setUp(self):
        self.prices = {k: {'pricePerUnit': v, 'unit': 'MILLION_TOKENS'} for k, v in
                       [('INPUT_TOKEN', '1'), ('OUTPUT_TOKEN', '5'),
                        ('CACHE_READ', '0.10'), ('CACHE_WRITE', '1.25')]}
        self.model = {'id': 'acceptance-fixture', 'supportsCache': True, 'apiProvider': 'test'}
        self.rates = {'USD': '1', 'CAD': '1.4', 'CNY': '7'}  # explicit test fixtures, not market FX

    def calc(self, **kwargs):
        return calculate(self.prices, kwargs, self.model, self.rates)

    def test_required_example(self):
        result = self.calc(mode='money', budget='100', inputRatio='.8', outputRatio='.2', cacheRatio='.9')
        self.assertEqual(Decimal(result['effectiveCostPerMillion']), Decimal('1.152'))
        self.assertLess(abs(Decimal(result['totalTokens'])-Decimal('86805555.55555556')), Decimal('.0001'))
        self.assertLess(abs(Decimal(result['totalCost'])-100), Decimal('1e-20'))

    def test_each_cache_ratio(self):
        for r in ['0', '.5', '.9', '1']:
            with self.subTest(cache=r):
                result = self.calc(mode='tokens', totalTokens='1000000', cacheRatio=r)
                expected = Decimal('.8')*((1-Decimal(r))+Decimal(r)*Decimal('.1'))+1
                self.assertEqual(Decimal(result['totalCost']), expected)

    def test_explicit_fx_equivalence(self):
        usd = self.calc(budget='100', currency='USD')
        for currency, budget in [('CAD','140'),('CNY','700')]:
            result = self.calc(budget=budget, currency=currency)
            self.assertEqual(result['totalTokens'], usd['totalTokens'])

    def test_cache_write_partition(self):
        result = self.calc(mode='tokens', totalTokens='1000000', cacheMode='advanced',
                           uncachedRatio='.2', cacheReadRatio='.5', cacheWriteRatio='.3')
        self.assertEqual(Decimal(result['totalCost']), Decimal('1.5'))

    def test_unused_unknown_prices(self):
        self.prices['OUTPUT_TOKEN']['pricePerUnit'] = None
        result = self.calc(mode='tokens', totalTokens='1000000', inputRatio='1', outputRatio='0')
        self.assertEqual(Decimal(result['totalCost']), Decimal('.19'))

    def test_used_unknown_price(self):
        self.prices['CACHE_READ']['pricePerUnit'] = None
        with self.assertRaises(DomainError):
            self.calc(mode='tokens', totalTokens='1000000')

    def test_no_cache_support(self):
        self.model['supportsCache'] = False
        result = self.calc(mode='tokens', totalTokens='1000000')
        self.assertEqual(Decimal(result['totalCost']), Decimal('1.8'))

    def test_invalid_values(self):
        for value in ['NaN', 'Infinity', '-1', '1e1000']:
            with self.subTest(value=value), self.assertRaises(DomainError):
                self.calc(budget=value)

    def test_usage_partition(self):
        usage = normalize_usage({'inputTokens':1000, 'cacheReadTokens':600,
                                 'cacheWriteTokens':100, 'outputTokens':200, 'reasoningTokens':100})
        self.assertEqual(usage['uncachedInputTokens'], 300)
        self.assertEqual(charge(self.prices, usage)['totalCost'], Decimal('.001485'))

    def test_invalid_usage_partition(self):
        with self.assertRaises(DomainError):
            normalize_usage({'inputTokens':100, 'cacheReadTokens':101, 'outputTokens':0})

class WalletLedgerAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.console = Wallets(Path(self.tmp.name)/'state', Path(self.tmp.name)/'absent.json')
        self.model = self.console.custom({'name':'Acceptance fixture', 'apiProvider':'Test',
            'inputPrice':'1','outputPrice':'5','cacheReadPrice':'.1','cacheWritePrice':'1.25',
            'supportsCache':True,'currency':'USD'})
        self.wallet = self.console.create_wallet({'name':'Test wallet','provider':'Test','currentBalance':'1'})

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, request='r1'):
        return {'requestId':request,'modelId':self.model['id'],'estimatedInputTokens':600000,
                'estimatedOutputTokens':0,'estimatedCacheRatio':0,'simulated':True}

    def test_concurrent_reservations(self):
        def reserve(i):
            try:
                self.console.reserve(self.payload(str(i)))
                return True
            except DomainError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            success = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(success),1)
        wallet = self.console.wallet(self.wallet['id'])
        self.assertEqual(Decimal(wallet['currentBalance']), 1)
        self.assertEqual(Decimal(wallet['availableBalance']), Decimal('.4'))

    def test_idempotent_reserve_and_release(self):
        p=self.payload()
        first=self.console.reserve(p)
        self.assertEqual(first,self.console.reserve(p))
        with self.assertRaises(DomainError):
            self.console.reserve(dict(p,estimatedInputTokens=1))
        self.console.release({'requestId':'r1'})
        self.console.release({'requestId':'r1'})
        self.assertEqual(Decimal(self.console.wallet(self.wallet['id'])['availableBalance']),1)

    def test_snapshot_settlement_and_refund(self):
        self.console.reserve(self.payload())
        self.console.patch_model(self.model['id'],{'priceOverride':{'inputPrice':'100'}})
        p={'requestId':'r1','usage':{'inputTokens':100000,'outputTokens':10000},'simulated':True}
        settled=self.console.settle(p)
        self.assertEqual(Decimal(settled['actualCost']),Decimal('.15'))
        self.assertEqual(settled['kind'],'SIMULATED')
        self.console.settle(p)
        self.assertEqual(Decimal(self.console.wallet(self.wallet['id'])['currentBalance']),Decimal('.85'))
        refund={'requestId':'r1','refundId':'rf1','amount':'.1'}
        self.console.refund(refund)
        self.console.refund(refund)
        with self.assertRaises(DomainError):
            self.console.refund({'requestId':'r1','refundId':'rf2','amount':'.1'})

    def test_unknown_usage_keeps_hold(self):
        self.console.reserve(self.payload())
        result=self.console.settle({'requestId':'r1'})
        self.assertEqual(result['state'],'USAGE_UNKNOWN')
        wallet=self.console.wallet(self.wallet['id'])
        self.assertEqual(Decimal(wallet['currentBalance']),1)
        self.assertEqual(Decimal(wallet['reservedBalance']),Decimal('.6'))

    def test_expired_wallet(self):
        self.console.patch_wallet(self.wallet['id'],{'expiresAt':'2000-01-01'})
        self.assertFalse(self.console.check_budget(self.payload())['allowed'])


class WalletRouteTests(unittest.TestCase):
    """Route table of proto/backend.py served through Wallets.handle()."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Wallets(Path(self.temp.name)/'state',Path(self.temp.name)/'missing.json')
        self.app.update_catalog({'catalogVersion':'route-1','models':[fixture(),fixture('other','Other','0.5'),fixture('old',status='DEPRECATED'),fixture('unknown',price=None)]})
        self.wallet=self.app.create_wallet({'name':'Route wallet','provider':'Test','currentBalance':'10','initialCredit':'10'})
    def tearDown(self):self.temp.cleanup()
    def payload(self,**p):return dict({'requestId':'req','modelId':'test','estimatedInputTokens':1000000,'estimatedOutputTokens':0,'estimatedCacheRatio':0},**p)
    def call(self,method,path,query=None,body=None,expect=200):
        status,data=self.app.handle(method,path,query or {},{} if body is None else body)
        self.assertEqual(status,expect,data)
        return data
    def test_route_get_read_endpoints(self):
        w=self.wallet['id']
        for path in ['/bootstrap','/models','/catalog','/models/test',f'/wallets',f'/wallets/{w}','/settings','/costs','/dashboard','/usage','/ledger','/audit','/reservations','/export']:
            with self.subTest(path=path):self.call('GET',path)
        self.assertEqual(len(self.call('GET','/bootstrap')['models']),4)
        self.assertIn('prices',self.call('GET','/pricing',{'modelId':'test'}))
        self.assertIn('prices',self.call('GET','/pricing'))
        self.assertIn('transactions',self.call('GET','/ledger'))
    def test_route_patch_endpoints(self):
        w=self.wallet['id']
        self.assertEqual(self.call('PATCH','/settings',body={'defaultBudget':'50'})['defaultBudget'],'50')
        self.assertTrue(self.call('PATCH','/models/test',body={'favorite':True})['favorite'])
        self.assertEqual(self.call('PATCH',f'/wallets/{w}',body={'name':'Renamed'})['name'],'Renamed')
    def test_route_model_ids_with_slash(self):
        # Catalog ids contain '/', e.g. anthropic/claude-fable-5-1; the encoded and decoded
        # path forms must both reach the same model.
        self.app.update_catalog({'catalogVersion':'test-slash','models':[fixture('anthropic/claude-fable-5-1')]})
        for path in ['/models/anthropic%2Fclaude-fable-5-1','/models/anthropic/claude-fable-5-1']:
            with self.subTest(path=path):
                self.assertEqual(self.call('GET',path)['id'],'anthropic/claude-fable-5-1')
                self.assertTrue(self.call('PATCH',path,body={'favorite':True})['favorite'])
        self.assertTrue(self.call('GET','/models/anthropic%2Fclaude-fable-5-1')['favorite'])
        self.assertTrue(self.call('POST','/models/anthropic%2Fclaude-fable-5-1/duplicate',body={'name':'Slash copy'})['isCustom'])
        status,_=self.app.handle('GET','/models/anthropic/claude-fable-5-1/extra',{},{})
        self.assertEqual(status,404)
    def test_route_post_registry_and_wallets(self):
        self.assertIn('totalCost',self.call('POST','/calculate',body={'modelId':'test','mode':'tokens','totalTokens':'1000'}))
        self.assertEqual(len(self.call('POST','/compare',body={'modelIds':['test','other']})['results']),2)
        self.assertTrue(self.call('POST','/models',body={'name':'Route custom','inputPrice':'1','outputPrice':'2'})['isCustom'])
        bulk=self.call('POST','/models/bulk',body={'action':'favorite','ids':['test']})
        self.assertEqual(self.call('POST','/models/undo',body={'undoId':bulk['undoId']}),{'restored':True})
        self.assertTrue(self.call('POST','/models/test/duplicate',body={'name':'Route copy'})['isCustom'])
        new=self.call('POST','/wallets',body={'provider':'Test','currentBalance':'5'})
        self.assertEqual(self.call('POST',f"/wallets/{new['id']}/adjust",body={'amount':'1','reason':'route test'})['currentBalance'],'6')
        self.assertEqual(self.call('POST',f"/wallets/{new['id']}/sync")['status'],'UNSUPPORTED')
        self.assertTrue(self.call('POST','/wallets/check-budget',body=self.payload())['allowed'])
    def test_route_post_ledger_endpoints(self):
        self.assertEqual(self.call('POST','/wallets/reserve',body=self.payload(requestId='route-1'))['state'],'RESERVED')
        self.assertEqual(self.call('POST','/wallets/settle',body={'requestId':'route-1','usage':{'inputTokens':10,'outputTokens':1}})['state'],'SETTLED')
        self.assertEqual(self.call('POST','/wallets/refund',body={'requestId':'route-1','refundId':'route-refund'})['type'],'REFUND')
        self.call('POST','/wallets/reserve',body=self.payload(requestId='route-2'))
        self.assertEqual(self.call('POST','/wallets/release',body={'requestId':'route-2'})['state'],'RELEASED')
        self.assertTrue(self.call('POST','/route',body=self.payload(modelIds=['test','other']))['simulation'])
    def test_route_post_admin_endpoints(self):
        self.assertTrue(self.call('POST','/import',body={'schemaVersion':1})['imported'])
        self.assertEqual(self.call('POST','/reset',body={'target':'calculator','confirmation':'RESET'}),{'reset':'calculator'})
        self.assertEqual(self.call('POST','/exchange-rates/refresh')['status'],'UNSUPPORTED')
        for path in ('/catalog/update','/pricing/update'):
            with self.subTest(path=path):
                status,data=self.app.handle('POST',path,{},{})
                self.assertEqual((status,data['error']['code']),(400,'CATALOG_UNAVAILABLE'))
                status,data=self.app.handle('POST',path,{},{'source':'https://example.invalid'})
                self.assertEqual((status,data['error']['code']),(400,'INVALID_INPUT'))
    def test_handle_api_security_and_simulation(self):
        # Rewritten from proto test_http_api_security_and_simulation: HTTP-only checks (Host/Origin/static files)
        # belong to Context Gate and are covered by WalletConsoleIntegrationTests.
        self.assertEqual(len(self.call('GET','/bootstrap')['models']),4)
        self.assertEqual(self.call('PATCH','/settings',body={'apiKey':'no'},expect=400)['error']['code'],'SECRETS_FORBIDDEN')
        r=self.call('POST','/invoke',body=self.payload(modelIds=['test'],usage={'inputTokens':1,'outputTokens':1},streaming=True));self.assertEqual(r['result']['kind'],'SIMULATED')
        self.assertEqual(self.call('GET','/ledger')['transactions'][0]['type'],'USAGE')
        self.assertEqual(self.call('POST','/exchange-rates/refresh')['status'],'UNSUPPORTED')
    def test_unknown_routes_and_static_paths_are_404(self):
        for method,path in [('GET','/nope'),('POST','/nope'),('PATCH','/nope'),('GET','/static/app.js'),('GET','/../console_wallet.py'),('GET','/%2e%2e/console_wallet.py'),('POST','/wallets/x/unknown'),('GET','/wallets/missing')]:
            with self.subTest(method=method,path=path):
                status,data=self.app.handle(method,path,{},{})
                self.assertEqual(status,404);self.assertTrue(data['error']['code'].endswith('NOT_FOUND'))
    def test_body_must_be_object_secrets_rejected_and_size_capped(self):
        status,data=self.app.handle('POST','/wallets',{},[])
        self.assertEqual((status,data['error']['code']),(400,'INVALID_INPUT'))
        status,data=self.app.handle('POST','/wallets',{},{'provider':'Test','apiKey':'x'})
        self.assertEqual((status,data['error']['code']),(400,'SECRETS_FORBIDDEN'))
        status,data=self.app.handle('POST','/wallets',{},{'note':'x'*2000001})
        self.assertEqual((status,data['error']['code']),(400,'BODY_TOO_LARGE'))
        status,data=self.app.handle('PUT','/wallets',{},{})
        self.assertEqual(status,404)
    def test_handle_maps_domain_errors_to_prototype_statuses(self):
        self.assertEqual(self.app.handle('GET','/models/none',{},{})[0],404)
        self.assertEqual(self.app.handle('POST','/wallets/reserve',{},{})[0],400)
        self.app.handle('POST','/wallets/reserve',{},self.payload(requestId='dup'))
        self.assertEqual(self.app.handle('POST','/wallets/refund',{},{'requestId':'dup','refundId':'x'})[1]['error']['code'],'INVALID_STATE')
        self.assertEqual(self.app.handle('POST','/wallets/refund',{},{'requestId':'dup','refundId':'x'})[0],409)


class WalletDefaultsTests(unittest.TestCase):
    def test_default_catalog_and_database_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Wallets(tmp)
            self.assertEqual(w.catalog_path,CATALOG_PATH)
            self.assertTrue(CATALOG_PATH.is_file())
            self.assertEqual({m['id'] for m in w.models({'includeHidden':True,'includeDeprecated':True})['models']}, {m['id'] for m in json.loads(CATALOG_PATH.read_text())['models']})
            self.assertEqual(w.db,str(Path(tmp)/'model-wallet.sqlite3'))
            self.assertIsNone(w.close())


class WalletConsoleIntegrationTests(unittest.TestCase):
    """Real Context Gate server (make_server, port 0): token, Origin, routing, database location."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=make_server(0,self.tmp.name,launch_schedules=False)
        threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
        self.root='http://127.0.0.1:'+str(self.server.server_port)+'/'+self.server.local_token
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(self.root+'/v1/wallet'+path,data,{'Content-Type':'application/json',**(headers or {})})
        with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
    def refused(self,url,body=None,headers=None):
        data=None if body is None else json.dumps(body).encode()
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(urllib.request.Request(url,data,{'Content-Type':'application/json',**(headers or {})}),timeout=5)
        return ctx.exception.code,json.loads(ctx.exception.read().decode())
    def test_bootstrap_serves_every_catalog_model(self):
        status,data=self.request('/bootstrap')
        catalog=json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
        self.assertEqual(status,200)
        self.assertEqual(len(data['models']),len(catalog['models']))
        self.assertEqual(data['integration'],{'mode':'ISOLATED_SIMULATION','productionConnected':False})
    def test_create_wallet_and_patch_settings_over_http(self):
        status,wallet=self.request('/wallets',{'name':'HTTP wallet','provider':'Test','currentBalance':'3'})
        self.assertEqual(status,200);self.assertEqual(wallet['availableBalance'],'3')
        self.assertEqual(self.request('/wallets/'+wallet['id'])[1]['id'],wallet['id'])
        self.assertEqual(self.request('/settings?_method=PATCH',{'theme':'light'})[1]['theme'],'light')
        self.assertEqual(self.request('/settings')[1]['theme'],'light')
    def test_token_origin_method_and_body_guards(self):
        self.assertEqual(self.refused('http://127.0.0.1:'+str(self.server.server_port)+'/wrong-token/v1/wallet/bootstrap')[0],403)
        self.assertEqual(self.refused(self.root+'/v1/wallet/bootstrap',headers={'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.request('/bootstrap',headers={'Origin':'http://127.0.0.1:'+str(self.server.server_port)})[0],200)
        code,data=self.refused(self.root+'/v1/wallet/settings?_method=GET',{'theme':'light'})
        self.assertEqual((code,data['error']['code']),(400,'INVALID_INPUT'))
        code,data=self.refused(self.root+'/v1/wallet/wallets',[])
        self.assertEqual(code,400)
        code,data=self.refused(self.root+'/v1/wallet/wallets',{'provider':'Test','apiKey':'x'})
        self.assertEqual((code,data['error']['code']),(400,'SECRETS_FORBIDDEN'))
        code,data=self.refused(self.root+'/v1/wallet/nope')
        self.assertEqual((code,data['error']['code']),(404,'NOT_FOUND'))
    def test_database_is_wallet_file_in_state_dir_and_others_untouched(self):
        sentinel=Path(self.tmp.name)/'sentinel.sqlite3'
        c=sqlite3.connect(sentinel);c.execute('CREATE TABLE t(x)');c.execute('INSERT INTO t VALUES(1)');c.commit();c.close()
        before=hashlib.sha256(sentinel.read_bytes()).hexdigest()
        self.request('/wallets',{'provider':'Test','currentBalance':'1'})
        self.assertEqual(self.server.wallets.db,str(Path(self.tmp.name)/'model-wallet.sqlite3'))
        self.assertTrue((Path(self.tmp.name)/'model-wallet.sqlite3').is_file())
        self.assertEqual(hashlib.sha256(sentinel.read_bytes()).hexdigest(),before)


class WalletPageAssemblyTests(unittest.TestCase):
    def test_nav_section_and_view_switch_are_wired_once(self):
        from console.app import PAGE
        self.assertEqual(PAGE.count('<button type="button" class="nav-item" data-v="wallet"'),1)
        self.assertEqual(PAGE.count('data-v="wallet"'),1)
        self.assertEqual(PAGE.count('data-view="wallet"'),2)  # pagehead + section, like other views
        self.assertEqual(PAGE.count("if(v==='wallet')loadWallet({automatic:true});"),1)
        self.assertIn('function loadWallet',PAGE)
        self.assertIn('const VIEWS={git:["git"],wallet:["wallet"],quota:',PAGE)
        self.assertLess(PAGE.index('data-v="wallet"'),PAGE.index('data-v="quota"'))


if __name__=='__main__':unittest.main()
