#!/usr/bin/env python3
"""Model Wallet accounting for the Context Gate console (Python standard library + SQLite).

Migrated from the isolated prototype proto/backend.py and proto/pricing.py; calculation and
ledger behaviour are unchanged. Deliberate differences from the prototype:
- No HTTP server, static files, Host/Origin/CSRF checks: console/app.py owns transport and auth.
- Routes are served by Wallets.handle(method, subpath, query, body) -> (http_status, dict).
- Own database only: <state_dir>/model-wallet.sqlite3. No other database is opened.
- Default catalog: console/wallet_catalog.json beside this module.
"""
import json, sqlite3, uuid
from urllib.parse import unquote
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent/'console'/'wallet_catalog.json'
# Embedded verbatim from proto/schema.sql.
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, data TEXT NOT NULL, custom INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS model_settings(user_id TEXT NOT NULL, model_id TEXT NOT NULL REFERENCES models(id), data TEXT NOT NULL, PRIMARY KEY(user_id,model_id));
CREATE TABLE IF NOT EXISTS endpoints(id TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES models(id), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS price_versions(id TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES models(id), endpoint_id TEXT NOT NULL, service_tier TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS price_model ON price_versions(model_id,endpoint_id,service_tier,created_at);
CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY, model_id TEXT NOT NULL, old_version TEXT, new_version TEXT NOT NULL, changed_at TEXT NOT NULL, source TEXT);
CREATE TABLE IF NOT EXISTS settings(user_id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wallets(id TEXT PRIMARY KEY,user_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provider_wallet_mapping(user_id TEXT NOT NULL,provider TEXT NOT NULL,wallet_provider TEXT NOT NULL,PRIMARY KEY(user_id,provider));
CREATE TABLE IF NOT EXISTS reservations(user_id TEXT NOT NULL,request_id TEXT NOT NULL,wallet_id TEXT NOT NULL REFERENCES wallets(id),state TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(user_id,request_id));
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,wallet_id TEXT NOT NULL REFERENCES wallets(id),request_id TEXT,type TEXT NOT NULL, data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,request_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,request_id));
CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,action TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(user_id TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(user_id,key));
CREATE TABLE IF NOT EXISTS undo(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,data TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""

# ---- pricing engine (verbatim from proto/pricing.py) ----

class DomainError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def dec(value, name='number', nonnegative=True):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise DomainError('INVALID_INPUT', f'{name} must be a decimal')
    if not d.is_finite() or (nonnegative and d < 0) or abs(d) > Decimal('1e30'):
        raise DomainError('INVALID_INPUT', f'{name} is outside supported range')
    return d

def ratio(value, name):
    d = dec(value, name)
    if d > 1:
        raise DomainError('INVALID_RATIO', f'{name} must be between 0 and 1')
    return d

def wire(value):
    if isinstance(value, Decimal): return format(value, 'f')
    if isinstance(value, dict): return {k: wire(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [wire(v) for v in value]
    return value

USAGE_TYPES = {'uncachedInputTokens':'INPUT_TOKEN','outputTokens':'OUTPUT_TOKEN',
 'cacheReadTokens':'CACHE_READ','cacheWriteTokens':'CACHE_WRITE','reasoningTokens':'REASONING_TOKEN',
 'imageInputTokens':'IMAGE_INPUT','imageCount':'IMAGE','imageOutputCount':'IMAGE_OUTPUT',
 'audioInputTokens':'AUDIO_INPUT','audioOutputTokens':'AUDIO_OUTPUT','audioSeconds':'SECOND',
 'videoSeconds':'VIDEO_INPUT','videoOutputSeconds':'VIDEO_OUTPUT','embeddingTokens':'EMBEDDING',
 'requests':'REQUEST','seconds':'SECOND','minutes':'MINUTE'}

def normalize_usage(raw):
    if not isinstance(raw, dict) or not raw:
        raise DomainError('USAGE_UNKNOWN', 'Provider usage is unavailable; reservation remains pending')
    u = {k: dec(v,k) for k,v in raw.items() if k in set(USAGE_TYPES)|{'inputTokens','totalTokens'}}
    if not u: raise DomainError('USAGE_UNKNOWN','No recognized usage measurements')
    for k,v in u.items():
        if ('Tokens' in k or 'Count' in k or k=='requests') and v != v.to_integral_value():
            raise DomainError('INVALID_USAGE',f'{k} must be an integer')
    if 'inputTokens' not in u or 'outputTokens' not in u:
        raise DomainError('USAGE_UNKNOWN','Complete input and output usage are required for settlement')
    inp=u.get('inputTokens',Decimal(0)); read=u.get('cacheReadTokens',Decimal(0)); write=u.get('cacheWriteTokens',Decimal(0))
    if read+write > inp: raise DomainError('INVALID_USAGE','Cached input exceeds total input')
    reasoning=u.get('reasoningTokens',Decimal(0)); out=u.get('outputTokens',Decimal(0))
    if reasoning > out: raise DomainError('INVALID_USAGE','Reasoning tokens exceed total output')
    u['uncachedInputTokens']=inp-read-write
    u['totalTokens']=inp+out
    return u

def charge(prices, usage):
    """Prices: type -> {pricePerUnit,unit}; zero usage requires no price."""
    amounts={}; total=Decimal(0)
    for key,typ in USAGE_TYPES.items():
        quantity=dec(usage.get(key,0), key)
        if key=='outputTokens' and 'REASONING_TOKEN' in prices:
            quantity-=dec(usage.get('reasoningTokens',0))
        if key=='reasoningTokens' and typ not in prices: continue # already in output
        if quantity == 0: continue
        entry=prices.get(typ)
        if entry is None or entry.get('pricePerUnit') is None:
            raise DomainError('PRICE_UNAVAILABLE', f'{typ} price unavailable')
        unit=entry.get('unit','MILLION_TOKENS').upper().replace(' ','_')
        denominator={'MILLION_TOKENS':1000000,'1M_TOKENS':1000000,'USD/1M_TOKENS':1000000,
                     'PER_1M_TOKENS':1000000,'THOUSAND_TOKENS':1000,'1K_TOKENS':1000}.get(unit)
        if denominator is None:
            if unit in ('TOKEN','IMAGE','SECOND','MINUTE','REQUEST'): denominator=1
            else: raise DomainError('UNSUPPORTED_UNIT',f'Unsupported billing unit: {unit}')
        amount=quantity*dec(entry['pricePerUnit'])/Decimal(denominator)
        amounts[typ]=amounts.get(typ,Decimal(0))+amount; total+=amount
    return {'totalCost':total,'breakdown':amounts}

def calculate(prices, payload, model, rates):
    with localcontext() as ctx:
        ctx.prec=48
        currency=payload.get('currency','USD').upper()
        if currency not in ('USD','CAD','CNY'): raise DomainError('INVALID_CURRENCY','Use USD, CAD or CNY')
        if rates.get(currency) is None: raise DomainError('EXCHANGE_RATE_UNAVAILABLE',f'{currency} exchange rate unavailable')
        rate=dec(rates.get(currency), 'exchange rate')
        if rate<=0: raise DomainError('EXCHANGE_RATE_UNAVAILABLE',f'{currency} exchange rate unavailable')
        ir=ratio(payload.get('inputRatio','0.8'),'inputRatio'); outr=ratio(payload.get('outputRatio',1-ir),'outputRatio')
        if ir+outr!=1: raise DomainError('INVALID_RATIO','Input and output ratios must sum to 1')
        cr=ratio(payload.get('cacheRatio','0.9'),'cacheRatio'); cw=Decimal(0)
        if payload.get('cacheMode')=='advanced':
            cr=ratio(payload.get('cacheReadRatio',0),'cacheReadRatio'); cw=ratio(payload.get('cacheWriteRatio',0),'cacheWriteRatio')
            unc=ratio(payload.get('uncachedRatio',1-cr-cw),'uncachedRatio')
            if unc+cr+cw!=1: raise DomainError('INVALID_RATIO','Advanced input ratios must sum to 1')
        if model.get('supportsCache') is False: cr=cw=Decimal(0)
        if payload.get('mode')=='requests':
            request_in=dec(payload.get('averageInputTokens',payload.get('averageInputTokensPerRequest',60000)))
            request_out=dec(payload.get('averageOutputTokens',payload.get('averageOutputTokensPerRequest',8000)))
            if request_in+request_out==0: raise DomainError('INVALID_INPUT','Request must have nonzero tokens')
            ir=request_in/(request_in+request_out); outr=1-ir
        unit_usage={'uncachedInputTokens':ir*(1-cr-cw)*1000000,'cacheReadTokens':ir*cr*1000000,'cacheWriteTokens':ir*cw*1000000,'outputTokens':outr*1000000}
        effective=charge(prices,unit_usage)['totalCost']
        mode=payload.get('mode','money'); budget=dec(payload.get('budget',100),'budget')/rate
        request_cost=None; requests=None
        if mode=='money':
            if effective==0: raise DomainError('UNBOUNDED_TOKENS','Zero price cannot establish a finite token limit')
            total=budget/effective*1000000
        elif mode=='tokens': total=dec(payload.get('totalTokens',0),'totalTokens')
        elif mode=='requests':
            inp=dec(payload.get('averageInputTokens',payload.get('averageInputTokensPerRequest',60000)))
            out=dec(payload.get('averageOutputTokens',payload.get('averageOutputTokensPerRequest',8000)))
            if inp+out==0: raise DomainError('INVALID_INPUT','Request must have nonzero tokens')
            ir=inp/(inp+out); outr=1-ir
            request_cost=charge(prices,{'uncachedInputTokens':inp*(1-cr-cw),'cacheReadTokens':inp*cr,'cacheWriteTokens':inp*cw,'outputTokens':out})['totalCost']
            if request_cost==0: raise DomainError('UNBOUNDED_REQUESTS','Zero price cannot establish a finite request limit')
            requests=(budget/request_cost).to_integral_value(rounding='ROUND_FLOOR'); total=requests*(inp+out)
            effective=request_cost/(inp+out)*1000000
        else: raise DomainError('INVALID_MODE','Use money, tokens or requests')
        usage={'inputTokens':total*ir,'outputTokens':total*outr,'cacheReadTokens':total*ir*cr,'cacheWriteTokens':total*ir*cw,'uncachedInputTokens':total*ir*(1-cr-cw)}
        cost=charge(prices,usage); breakdown=cost['breakdown']
        try: no_cache=charge(prices,{'uncachedInputTokens':usage['inputTokens'],'outputTokens':usage['outputTokens']})['totalCost']
        except DomainError: no_cache=None
        savings=None if no_cache is None else no_cache-cost['totalCost']
        result=dict(usage,kind='ESTIMATE',modelId=model['id'],provider=model.get('apiProvider'),currency=currency,
            budgetUSD=budget,budget=budget*rate,totalTokens=total,effectiveCostPerMillion=effective,
            inputCost=breakdown.get('INPUT_TOKEN',Decimal(0)),outputCost=breakdown.get('OUTPUT_TOKEN',Decimal(0)),
            cacheCost=breakdown.get('CACHE_READ',Decimal(0))+breakdown.get('CACHE_WRITE',Decimal(0)),
            totalCost=cost['totalCost'],displayCost=cost['totalCost']*rate,costWithoutCache=no_cache,costWithCache=cost['totalCost'],
            cacheSavings=savings,savingsPercent=(savings/no_cache*100 if no_cache else None),costPerRequest=request_cost,estimatedRequests=requests,breakdown=breakdown)
    def round28(v):
        # Outside the 48-digit context: a unary plus rounds to the default 28 significant digits.
        if isinstance(v,Decimal): return +v
        if isinstance(v,dict): return {k:round28(x) for k,x in v.items()}
        return v
    return wire(round28(result))

USER='local'
def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def dumps(v): return json.dumps(wire(v),ensure_ascii=False,sort_keys=True,separators=(',',':'))
def loads(v): return json.loads(v)
def reject_secrets(v):
    if isinstance(v,dict):
        for k,x in v.items():
            compact=k.lower().replace('_','').replace('-','')
            if any(s in compact for s in ('apikey','authorization','credential','password','secret','accesstoken','refreshtoken')):
                raise DomainError('SECRETS_FORBIDDEN','Credentials are not accepted by this prototype')
            reject_secrets(x)
    elif isinstance(v,list):
        for x in v: reject_secrets(x)

def expiry(v):
    if v is None or v=='': return None
    try:
        if isinstance(v,(int,float)):return datetime.fromtimestamp(v,timezone.utc)
        result=datetime.fromisoformat(v.replace('Z','+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError): raise DomainError('INVALID_DATE','Invalid expiration date')

DEFAULTS={'defaultCurrency':'USD','defaultBudget':'100','defaultInputRatio':'0.8','defaultOutputRatio':'0.2','defaultCacheRatio':'0.9',
'exchangeRates':{'USD':'1','CAD':None,'CNY':None},'exchangeRateSource':'UNAVAILABLE','exchangeRateUpdatedAt':None,
'theme':'dark','numberFormat':'compact','walletStrategy':'MANUAL_PRIORITY','failMode':'FAIL_CLOSED',
'providerWalletMapping':{'AWS Bedrock':'AWS','Anthropic API':'Anthropic','OpenAI API':'OpenAI','Google Vertex':'Google Cloud','Azure OpenAI':'Azure'},
'recentModels':[],'alerts':{'creditsExpiringDays':30,'highDailySpend':None,'spendSpikeMultiplier':'2'},'costGuard':{'mode':'BLOCK','threshold':None},
'scheduledSync':{'enabled':False,'status':'UNSUPPORTED','reason':'No scheduler is connected'}}

class UnsupportedAdapter:
    def invokeModel(self,*args,**kwargs): raise DomainError('UNSUPPORTED','Real model invocation is disabled in the isolated prototype')
    def syncBalance(self,*args,**kwargs): return {'status':'UNSUPPORTED','connected':False,'balanceSource':'MANUAL','reason':'No authenticated official transport is connected'}
    def normalizeUsage(self,raw): return wire(normalize_usage(raw))
    def getPricing(self,*args): return {'status':'REGISTRY_ONLY'}

class AWSAdapter(UnsupportedAdapter):
    """Pure response normalizer for AWS Billing GetCredits; no credentials accessed."""
    source='https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_billing_GetCredits.html'
    def normalizeCredits(self, response):
        credits=response.get('credits',response.get('Credits',[])); rows=[]
        for c in credits:
            remaining=c.get('remainingAmount'); initial=c.get('initialAmount'); estimated=c.get('estimatedAmount')
            def amount(a):
                if isinstance(a,dict): return a.get('currencyAmount',a.get('amount',a.get('Amount')))
                return a
            value=amount(remaining) if remaining is not None else amount(estimated)
            rows.append({'currentBalance':str(dec(value)) if value is not None else None,'initialCredit':str(dec(amount(initial))) if initial is not None else None,
                'balanceSource':'LIVE_API' if remaining is not None else 'ESTIMATED','eligibleServices':c.get('applicableProductNames',[]),'currency':remaining.get('currencyCode','USD') if isinstance(remaining,dict) else 'USD','expiresAt':expiry(c.get('endDate')).isoformat() if c.get('endDate') is not None else None,'sourceUrl':self.source})
        return rows

class Wallets:
    def __init__(self,state_dir,catalog=None):
        self.db=str(Path(state_dir)/'model-wallet.sqlite3'); self.catalog_path=Path(catalog) if catalog else CATALOG_PATH
        Path(self.db).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA); c.execute('INSERT OR IGNORE INTO migrations VALUES(1,?)',(now(),))
            c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(USER,dumps(DEFAULTS)))
        if self.catalog_path.exists(): self.update_catalog(loads(self.catalog_path.read_text()))
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30,isolation_level=None); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=30000'); c.execute('PRAGMA journal_mode=WAL'); return c
    @contextmanager
    def transaction(self):
        c=self.connect(); c.execute('BEGIN IMMEDIATE')
        try: yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
    def audit(self,c,action,old=None,new=None):
        c.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(uid(),USER,action,dumps({'id':uid(),'action':action,'time':now(),'user':USER,'oldValue':old,'newValue':new}),now()))
    def settings(self,c=None):
        if c: return loads(c.execute('SELECT data FROM settings WHERE user_id=?',(USER,)).fetchone()[0])
        with self.connect() as c: return self.settings(c)
    def update_settings(self,p,c=None):
        reject_secrets(p)
        draft_keys={'calculatorDraft','calculatorDraftRevision'}
        if draft_keys.intersection(p):
            if set(p)!=draft_keys: raise DomainError('INVALID_INPUT','Calculator draft fields must be submitted together')
            revision=p['calculatorDraftRevision'];draft=p['calculatorDraft']
            if type(revision) is not int or not 0<=revision<=9007199254740991: raise DomainError('INVALID_INPUT','Invalid calculator draft revision')
            if draft is not None and (not isinstance(draft,dict) or type(draft.get('version')) is not int or draft['version']!=1 or not isinstance(draft.get('calc'),dict)): raise DomainError('INVALID_INPUT','Invalid calculator draft')
            if c is None:
                with self.transaction() as tx: return self.update_settings(p,tx)
            s=self.settings(c)
            if revision<=s.get('calculatorDraftRevision',0): return s
            s.update(p);c.execute('UPDATE settings SET data=? WHERE user_id=?',(dumps(s),USER));return s
        s=self.settings(c); s.update(p)
        if s['defaultCurrency'] not in ('USD','CAD','CNY'): raise DomainError('INVALID_CURRENCY','Unsupported currency')
        ir=ratio(s['defaultInputRatio'],'input'); out=ratio(s['defaultOutputRatio'],'output')
        if ir+out!=1: raise DomainError('INVALID_RATIO','Ratios must sum to 1')
        ratio(s['defaultCacheRatio'],'cache'); dec(s['defaultBudget'])
        if s['failMode'] not in ('FAIL_OPEN','FAIL_CLOSED'): raise DomainError('INVALID_INPUT','Invalid fail mode')
        if s['walletStrategy'] not in ('MANUAL_PRIORITY','SOONEST_EXPIRY_FIRST','USE_EXPIRING_CREDITS_FIRST','HIGHEST_BALANCE_FIRST'): raise DomainError('INVALID_INPUT','Invalid wallet strategy')
        if not isinstance(s.get('costGuard'),dict) or s['costGuard'].get('mode') not in ('BLOCK','REQUIRE_APPROVAL'): raise DomainError('INVALID_INPUT','Invalid cost guard mode')
        for k,v in s['exchangeRates'].items():
            if k not in ('USD','CAD','CNY') or (v is not None and dec(v)<=0): raise DomainError('INVALID_RATE','Rates must be positive USD conversion rates')
        s['exchangeRates']['USD']='1'
        if 'exchangeRates' in p: s.update(exchangeRateUpdatedAt=now(),exchangeRateSource='MANUAL_OVERRIDE')
        if c: c.execute('UPDATE settings SET data=? WHERE user_id=?',(dumps(s),USER)); return s
        with self.transaction() as tx:
            self.update_settings(p,tx); self.audit(tx,'Settings Changed',self.settings(),s)
        return s
    def model(self,id,c=None):
        if c:
            row=c.execute('SELECT data FROM models WHERE id=?',(id,)).fetchone()
            if not row: raise DomainError('MODEL_NOT_FOUND','Model does not exist')
            m=loads(row[0]); setting=c.execute('SELECT data FROM model_settings WHERE user_id=? AND model_id=?',(USER,id)).fetchone()
            m.update({'enabled':True,'hidden':False,'favorite':False,'featured':False,'default':False})
            if setting: m.update(loads(setting[0]))
            return m
        with self.connect() as c: return self.model(id,c)
    def update_catalog(self,data):
        reject_secrets(data)
        if not isinstance(data.get('models'),list): raise DomainError('INVALID_CATALOG','models must be an array')
        with self.transaction() as c:
            for m in data['models']:
                if not m.get('id'): raise DomainError('INVALID_MODEL','Model id is required')
                existing=c.execute('SELECT custom FROM models WHERE id=?',(m['id'],)).fetchone()
                if existing and existing[0]: raise DomainError('CATALOG_CONFLICT','Catalog cannot overwrite a custom model')
                m=dict(m,isBuiltIn=True,isCustom=False)
                for k in ('favorite','hidden','enabled','priceOverride','notes'): m.pop(k,None)
                c.execute('INSERT INTO models VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(m['id'],dumps(m)))
            for e in data.get('endpoints',[]):
                c.execute('INSERT INTO endpoints VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(e['id'],e['modelId'],dumps(e)))
            grouped={}
            for p in data.get('prices',[]):
                key=(p['modelId'],p.get('endpointId',p['modelId']),p.get('serviceTier','STANDARD')+'|'+p.get('pricingMode','STANDARD'))
                grouped.setdefault(key,{})[p['priceType']]=p
            # Compatibility for compact custom or legacy catalog entries.
            for m in data['models']:
                if not any(key[0]==m['id'] for key in grouped): grouped[(m['id'],m['id'],'STANDARD|STANDARD')]=self.inline_prices(m)
            for (mid,ep,tier),ps in grouped.items(): self.save_prices(c,mid,ep,tier,ps)
            for k,v in [('catalogVersion',data.get('catalogVersion','unknown')),('catalogUpdatedAt',data.get('catalogUpdatedAt',now()))]:
                c.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(k,dumps(v)))
            self.audit(c,'Catalog Updated',new={'version':data.get('catalogVersion'),'models':len(data['models'])})
        return self.catalog_meta()
    @staticmethod
    def inline_prices(m):
        return {t:{'pricePerUnit':m.get(k),'unit':'MILLION_TOKENS','currency':m.get('currency','USD'),'sourceUrl':m.get('officialPricingUrl')} for k,t in [('inputPrice','INPUT_TOKEN'),('outputPrice','OUTPUT_TOKEN'),('cacheReadPrice','CACHE_READ'),('cacheWritePrice','CACHE_WRITE')]}
    def save_prices(self,c,mid,ep,tier,ps):
        for p in ps.values():
            if p.get('pricePerUnit') is not None: dec(p['pricePerUnit'])
        serialized=dumps(ps); old=c.execute('SELECT id,data FROM price_versions WHERE model_id=? AND endpoint_id=? AND service_tier=? ORDER BY rowid DESC LIMIT 1',(mid,ep,tier)).fetchone()
        if old and old['data']==serialized: return old['id']
        version=uid(); c.execute('INSERT INTO price_versions VALUES(?,?,?,?,?,?)',(version,mid,ep,tier,serialized,now()))
        c.execute('INSERT INTO price_history(model_id,old_version,new_version,changed_at,source) VALUES(?,?,?,?,?)',(mid,old['id'] if old else None,version,now(),dumps([p.get('sourceUrl') for p in ps.values()])))
        self.audit(c,'Price Updated',old['id'] if old else None,version); return version
    def catalog_meta(self):
        with self.connect() as c: return {r['key']:loads(r['value']) for r in c.execute('SELECT * FROM metadata')}
    def pricing(self,mid,endpoint=None,tier='STANDARD',version=None,c=None,pricing_mode=None,prompt_tokens=None):
        if not c:
            with self.connect() as cx: return self.pricing(mid,endpoint,tier,version,cx,pricing_mode,prompt_tokens)
        m=self.model(mid,c)
        if version:
            row=c.execute('SELECT * FROM price_versions WHERE id=? AND model_id=?',(version,mid)).fetchone()
        else:
            rows=c.execute('SELECT * FROM price_versions WHERE model_id=? ORDER BY rowid DESC',(mid,)).fetchall()
            latest={}
            for r in rows:
                base,_,mode=r['service_tier'].partition('|');mode=mode or 'STANDARD'
                if base!=tier or (endpoint and r['endpoint_id']!=endpoint):continue
                latest.setdefault((r['endpoint_id'],mode),r)
            if not endpoint and latest:
                # Prefer catalog's first endpoint, never mix creator and hosting prices.
                first=c.execute('SELECT id FROM endpoints WHERE model_id=? ORDER BY rowid LIMIT 1',(mid,)).fetchone()
                ep=first[0] if first else next(iter(latest))[0]
                latest={k:r for k,r in latest.items() if k[0]==ep}
            matches=[]
            for (_,mode),r in latest.items():
                if pricing_mode and mode!=pricing_mode:continue
                entries=loads(r['data']);conditions=[x.get('conditions') or {} for x in entries.values()]
                valid=True; unresolved=False
                for cond in conditions:
                    if cond.get('contextBand') and prompt_tokens is None and not pricing_mode:unresolved=True
                    for key in ('inputTokensMinExclusive','inputTokensMaxInclusive'):
                        if key in cond:
                            if prompt_tokens is None:unresolved=not bool(pricing_mode)
                            elif key=='inputTokensMinExclusive' and dec(prompt_tokens)<=dec(cond[key]):valid=False
                            elif key=='inputTokensMaxInclusive' and dec(prompt_tokens)>dec(cond[key]):valid=False
                    if any(k in cond for k in ('resolution','pricingPeriod','cacheTtlSeconds')) and not pricing_mode:unresolved=True
                    if cond.get('contextBand') and prompt_tokens is not None and not any(k in cond for k in ('inputTokensMinExclusive','inputTokensMaxInclusive')) and not pricing_mode:unresolved=True
                if valid and not unresolved:matches.append((mode,r))
            if not matches:raise DomainError('PRICE_CONDITION_UNRESOLVED','Select an explicit pricing mode or provide prompt length for verified pricing thresholds')
            if pricing_mode:row=matches[0][1]
            else:
                standard=[r for mode,r in matches if mode=='STANDARD']
                if standard:row=standard[0]
                elif len(matches)==1:row=matches[0][1]
                else:raise DomainError('PRICE_CONDITION_UNRESOLVED','Multiple price modes match; select one explicitly')
        if not row: raise DomainError('PRICE_UNAVAILABLE','No price version for this endpoint and tier')
        ps=loads(row['data']); rates=self.settings(c)['exchangeRates']
        for p in ps.values():
            curr=p.get('currency','USD')
            if curr!='USD' and p.get('pricePerUnit') is not None:
                if rates.get(curr) is None: raise DomainError('EXCHANGE_RATE_UNAVAILABLE',f'{curr} conversion rate unavailable')
                p['originalPrice']=p['pricePerUnit'];p['originalCurrency']=curr;p['currency']='USD'
                with localcontext() as x:x.prec=48;p['pricePerUnit']=str(dec(p['originalPrice'])/dec(rates[curr]))
        if not version and m.get('priceOverride'):
            for k,t in [('inputPrice','INPUT_TOKEN'),('outputPrice','OUTPUT_TOKEN'),('cacheReadPrice','CACHE_READ'),('cacheWritePrice','CACHE_WRITE')]:
                if k in m['priceOverride']: ps[t]={'pricePerUnit':m['priceOverride'][k],'unit':'MILLION_TOKENS','currency':'USD','source':'CUSTOM_OVERRIDE'}
            # Persist override snapshot so reservations survive later override changes.
            ver=self.save_prices(c,mid,row['endpoint_id'],'OVERRIDE',ps)
        else: ver=row['id']
        return {'prices':ps,'priceVersion':ver,'endpointId':row['endpoint_id'],'serviceTier':tier,'pricingMode':row['service_tier'].partition('|')[2] or 'STANDARD'}
    def models(self,q=None):
        q=q or {}; s=self.settings()
        with self.connect() as c: allm=[self.model(r[0],c) for r in c.execute('SELECT id FROM models')]
        counts={}
        for m in allm: counts[m.get('apiProvider','Unknown')]=counts.get(m.get('apiProvider','Unknown'),0)+1
        def values(k): return q.get(k,[]).split(',') if isinstance(q.get(k),str) else q.get(k,[])
        result=[]
        for m in allm:
            if not q.get('includeHidden') and m['hidden']: continue
            if not q.get('statuses') and m.get('status') in ('DEPRECATED','RETIRED') and not (q.get('includeDeprecated') and m['status']=='DEPRECATED'): continue
            if values('providers') and m.get('apiProvider') not in values('providers'): continue
            if values('statuses') and m.get('status') not in values('statuses'): continue
            cats=m.get('category',m.get('categories',[])); cats=[cats] if isinstance(cats,str) else cats or []
            if values('categories') and not set(values('categories')).intersection(cats): continue
            if values('capabilities') and not all(m.get(k if k.startswith('supports') else 'supports'+k[0].upper()+k[1:]) for k in values('capabilities')): continue
            if q.get('search') and q['search'].lower() not in ' '.join(str(m.get(k,'')) for k in ('name','displayName','id','creator','apiProvider','family')).lower(): continue
            if q.get('enabled') and not m['enabled']: continue
            if q.get('favorites') and not m['favorite']: continue
            if q.get('minContext') and (m.get('contextWindow') is None or dec(m['contextWindow'])<dec(q['minContext'])): continue
            if q.get('inputMax') and (m.get('inputPrice') is None or dec(m['inputPrice'])>dec(q['inputMax'])): continue
            if q.get('outputMax') and (m.get('outputPrice') is None or dec(m['outputPrice'])>dec(q['outputMax'])): continue
            if q.get('price')=='unknown' and m.get('inputPrice') is not None and m.get('outputPrice') is not None: continue
            if q.get('price')=='free' and not (m.get('inputPrice') is not None and m.get('outputPrice') is not None and dec(m['inputPrice'])==0 and dec(m['outputPrice'])==0): continue
            result.append(m)
        sort=q.get('sort','name'); key={'provider':'apiProvider','creator':'creator','context':'contextWindow','output':'maxOutputTokens','inputPrice':'inputPrice','outputPrice':'outputPrice','verified':'priceLastVerifiedAt','newest':'releaseDate','cache':'cacheReadPrice'}.get(sort,'displayName')
        if key in ('contextWindow','maxOutputTokens','inputPrice','outputPrice','cacheReadPrice'): result.sort(key=lambda m:(m.get(key) is None,dec(m.get(key) or 0)),reverse=sort in ('context','output'))
        else: result.sort(key=lambda m:str(m.get(key) or m.get('name','')).lower(),reverse=sort in ('verified','newest'))
        return {'models':result,'providerCounts':counts,'recent':s['recentModels']}
    def patch_model(self,mid,p,c=None):
        reject_secrets(p)
        allowed={'enabled','hidden','favorite','featured','default','notes','priceOverride'}
        if not set(p)<=allowed: raise DomainError('INVALID_INPUT','Only model settings are editable; duplicate built-in to customize')
        for k in ('enabled','hidden','favorite','featured','default'):
            if k in p and not isinstance(p[k],bool): raise DomainError('INVALID_INPUT',f'{k} must be boolean')
        if p.get('priceOverride'):
            for v in p['priceOverride'].values():
                if v is not None: dec(v)
        if not c:
            with self.transaction() as cx: return self.patch_model(mid,p,cx)
        old=self.model(mid,c); row=c.execute('SELECT data FROM model_settings WHERE user_id=? AND model_id=?',(USER,mid)).fetchone();setting=loads(row[0]) if row else {};setting.update(p)
        c.execute('INSERT OR REPLACE INTO model_settings VALUES(?,?,?)',(USER,mid,dumps(setting)));self.audit(c,'Model Changed',old,p);return self.model(mid,c)
    def custom(self,p,duplicate=None):
        reject_secrets(p)
        m=self.model(duplicate) if duplicate else {};m.update(p);m['id']='custom-'+uid();m.update(isBuiltIn=False,isCustom=True,status='CURRENT')
        if not m.get('name'): raise DomainError('INVALID_MODEL','Model name is required')
        m.setdefault('displayName',m['name']);m.setdefault('apiProvider',m.get('provider','Custom'));m.setdefault('creator','Custom')
        ps=self.inline_prices(m)
        with self.transaction() as c:
            c.execute('INSERT INTO models VALUES(?,?,1)',(m['id'],dumps(m)));self.save_prices(c,m['id'],m['id'],'STANDARD',ps);self.audit(c,'Custom Model Created',new=m)
        return self.model(m['id'])
    def bulk(self,p):
        actions={'enable':{'enabled':True},'disable':{'enabled':False},'hide':{'hidden':True},'unhide':{'hidden':False},'favorite':{'favorite':True},'unfavorite':{'favorite':False},'delete':{'hidden':True}}
        if p.get('action') not in actions: raise DomainError('INVALID_ACTION','Unknown bulk action')
        ids=p.get('ids',[])
        if not isinstance(ids,list) or not ids: raise DomainError('INVALID_INPUT','Choose models')
        with self.transaction() as c:
            old=[{'id':mid,'settings':{k:self.model(mid,c).get(k) for k in ('enabled','favorite','hidden','notes','priceOverride')}} for mid in ids]
            for mid in ids:self.patch_model(mid,actions[p['action']],c)
            undo=uid();c.execute('INSERT INTO undo VALUES(?,?,?,?)',(undo,USER,dumps(old),(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()))
        return {'models':[self.model(mid) for mid in ids],'undoId':undo}
    def undo(self,id):
        with self.transaction() as c:
            row=c.execute('SELECT * FROM undo WHERE id=? AND user_id=?',(id,USER)).fetchone()
            if not row or expiry(row['expires_at'])<datetime.now(timezone.utc): raise DomainError('UNDO_EXPIRED','Undo expired')
            for r in loads(row['data']): self.patch_model(r['id'],r['settings'],c)
            c.execute('DELETE FROM undo WHERE id=?',(id,))
        return {'restored':True}
    def calculate(self,p):
        if p.get('customModel'):
            m=dict(p['customModel'],id='transient',apiProvider=p['customModel'].get('apiProvider','Custom'));ps=self.inline_prices(m);ver='TRANSIENT'
            for entry in ps.values():
                if entry.get('currency','USD')!='USD' and entry.get('pricePerUnit') is not None:
                    with localcontext() as x:x.prec=48;entry['pricePerUnit']=str(dec(entry['pricePerUnit'])/self.rate(entry['currency']))
                    entry['currency']='USD'
        else:
            m=self.model(p['modelId']);priced=self.pricing(m['id'],p.get('endpointId'),p.get('serviceTier','STANDARD'),pricing_mode=p.get('pricingMode'),prompt_tokens=p.get('promptTokens',p.get('averageInputTokens') if p.get('mode')=='requests' else None));ps=priced['prices'];ver=priced['priceVersion']
        result=calculate(ps,p,m,self.settings()['exchangeRates']);result['priceVersion']=ver
        if m['id']!='transient':
            s=self.settings();recent=[m['id']]+[x for x in s['recentModels'] if x!=m['id']];self.update_settings({'recentModels':recent[:10]})
        return result
    def wallet(self,id,c=None):
        if not c:
            with self.connect() as cx:return self.wallet(id,cx)
        row=c.execute('SELECT data FROM wallets WHERE id=? AND user_id=?',(id,USER)).fetchone()
        if not row: raise DomainError('WALLET_NOT_FOUND','Wallet does not exist')
        w=loads(row[0]);w['availableBalance']=str(dec(w['currentBalance'],nonnegative=False)-dec(w['reservedBalance']));w['debt']=str(max(dec(0),-dec(w['currentBalance'],nonnegative=False)));return w
    def wallets(self):
        with self.connect() as c:return {'wallets':[self.wallet(r[0],c) for r in c.execute('SELECT id FROM wallets WHERE user_id=?',(USER,))]}
    def create_wallet(self,p):
        reject_secrets(p);kind=p.get('type','MANUAL')
        if kind not in ('MANUAL','CONNECTED'):raise DomainError('INVALID_INPUT','Wallet type must be MANUAL or CONNECTED')
        currency=p.get('currency','USD')
        if currency not in ('USD','CAD','CNY'):raise DomainError('INVALID_CURRENCY','Unsupported currency')
        initial=str(dec(p.get('initialCredit',p.get('currentBalance',0))));balance=str(dec(p.get('currentBalance',initial)));expiry(p.get('expiresAt'))
        w=dict(p,id=uid(),walletId=None,userId=USER,type=kind,initialCredit=initial,currentBalance=balance,reservedBalance='0',currency=currency,balanceSource='MANUAL' if kind=='MANUAL' else 'ESTIMATED',connectionStatus='UNCONNECTED',lastSyncedAt=None)
        w['walletId']=w['id'];w.setdefault('name','Local wallet');w.setdefault('provider','Custom');w.setdefault('priority',1);w.setdefault('lowBalanceThreshold','10');w.setdefault('eligibleProviders',[]);w.setdefault('eligibleModels',[]);w.setdefault('eligibleServices',[]);w.setdefault('restrictions','');w.setdefault('limits',{})
        self.wallet_fields(w)
        with self.transaction() as c:
            c.execute('INSERT INTO wallets VALUES(?,?,?)',(w['id'],USER,dumps(w)));self.ledger(c,w,None,'CREDIT',dec(balance),dec(0),dec(balance),{});self.audit(c,'Wallet Created',new=w)
        return self.wallet(w['id'])
    def wallet_fields(self,w):
        pr=w.get('priority')
        if isinstance(pr,bool) or not isinstance(pr,(int,float)) or not pr>=0: raise DomainError('INVALID_INPUT','priority must be a non-negative number')
        if w.get('lowBalanceThreshold') is not None: dec(w['lowBalanceThreshold'],'lowBalanceThreshold')
        if not isinstance(w.get('limits'),dict): raise DomainError('INVALID_INPUT','limits must be an object')
        for k,v in w['limits'].items():
            if v is not None: dec(v,k)
    def patch_wallet(self,id,p):
        reject_secrets(p);forbidden={'currentBalance','reservedBalance','availableBalance','id','walletId','balanceSource','userId','initialCredit','currency','type'}
        if not set(p)<={'name','provider','priority','lowBalanceThreshold','expiresAt','notes','eligibleProviders','eligibleModels','eligibleServices','restrictions','limits'}:raise DomainError('INVALID_INPUT','Use balance adjustment; financial identity fields cannot be edited')
        expiry(p.get('expiresAt'))
        with self.transaction() as c:
            old=self.wallet(id,c);w=dict(old,**p);self.wallet_fields(w);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),id));self.audit(c,'Wallet Changed',old,w)
        return self.wallet(id)
    def ledger(self,c,w,r,typ,amount,before,after,extra):
        entry=dict(extra,id=uid(),walletId=w['id'],requestId=r.get('requestId') if r else None,type=typ,amount=str(amount),balanceBefore=str(before),balanceAfter=str(after),currency=w['currency'],createdAt=now())
        if r:
            for k in ('agentId','sessionId','gateId','modelId','provider','priceVersion'):entry[k]=r.get(k)
        c.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?)',(entry['id'],USER,w['id'],entry['requestId'],typ,dumps(entry),entry['createdAt']))
        return entry
    def rate(self,currency,c=None):
        value=self.settings(c)['exchangeRates'].get(currency)
        if value is None:raise DomainError('EXCHANGE_RATE_UNAVAILABLE',f'Configure USD/{currency} rate before using this wallet')
        return dec(value)
    def adjust(self,id,p):
        amount=dec(p.get('amount'),nonnegative=False)
        with self.transaction() as c:
            w=self.wallet(id,c);before=dec(w['currentBalance'],nonnegative=False);after=before+amount
            if after<dec(w['reservedBalance']):raise DomainError('RESERVED_BALANCE','Adjustment would invalidate pending reservations')
            w['currentBalance']=str(after);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),id));self.ledger(c,w,None,'ADJUSTMENT',amount,before,after,{'reason':p.get('reason','')});self.audit(c,'Balance Adjusted',str(before),str(after))
        return self.wallet(id)
    def eligible(self,w,provider,mid,service=None):
        if expiry(w.get('expiresAt')) and expiry(w['expiresAt'])<=datetime.now(timezone.utc):return False
        mapped=self.settings()['providerWalletMapping'].get(provider,provider)
        if w['provider'] not in (mapped,provider) and provider not in w.get('eligibleProviders',[]):return False
        if w.get('eligibleProviders') and provider not in w['eligibleProviders'] and mapped not in w['eligibleProviders']:return False
        if w.get('eligibleModels') and mid not in w['eligibleModels']:return False
        if w.get('eligibleServices') and service not in w['eligibleServices']:return False
        return True
    def limit_check(self,c,w,cost):
        limits=w.get('limits',{});t=datetime.now(timezone.utc)
        if limits.get('perRequest') is not None and cost>dec(limits['perRequest']):raise DomainError('SPEND_LIMIT','Per-request spend limit exceeded')
        rows=c.execute('SELECT data,created_at FROM ledger WHERE wallet_id=? AND type="USAGE"',(w['id'],)).fetchall()
        pending=sum((dec(loads(r[0])['reservedAmount']) for r in c.execute('SELECT data FROM reservations WHERE wallet_id=? AND state IN ("RESERVED","USAGE_UNKNOWN")',(w['id'],))),dec(0))
        for k,days in [('daily',1),('weekly',7),('monthly',30)]:
            if limits.get(k) is None:continue
            spent=sum((dec(loads(r['data'])['amount']) for r in rows if expiry(r['created_at'])>=t-timedelta(days=days)),dec(0))
            if spent+pending+cost>dec(limits[k]):raise DomainError('SPEND_LIMIT',f'{k} spend limit exceeded')
    def check_budget(self,p,c=None):
        if not c:
            with self.connect() as cx:return self.check_budget(p,cx)
        m=self.model(p['modelId'],c)
        if not m['enabled'] or m.get('status') not in ('CURRENT','NEW','PREVIOUS'):raise DomainError('MODEL_DISABLED','Model is not eligible for automatic routing')
        priced=self.pricing(m['id'],p.get('endpointId'),p.get('serviceTier','STANDARD'),c=c,pricing_mode=p.get('pricingMode'),prompt_tokens=p.get('estimatedInputTokens',0))
        provider=m.get('apiProvider',m.get('provider'))
        erow=c.execute('SELECT data FROM endpoints WHERE id=?',(priced['endpointId'],)).fetchone()
        if erow:provider=loads(erow[0]).get('provider',provider)
        for cap in p.get('requiredCapabilities',[]):
            key=cap if cap.startswith('supports') else 'supports'+cap[0].upper()+cap[1:]
            if not m.get(key):raise DomainError('CAPABILITY_UNAVAILABLE',f'Required capability {cap} unavailable')
        inp=dec(p.get('estimatedInputTokens',0));out=dec(p.get('estimatedOutputTokens',0));cache=ratio(p.get('estimatedCacheRatio',0),'cache')
        if m.get('supportsCache') is False:cache=dec(0)
        if m.get('contextWindow') is not None and inp+out>dec(m['contextWindow']):raise DomainError('CONTEXT_EXCEEDED','Input and output exceed context window')
        if m.get('maxInputTokens') is not None and inp>dec(m['maxInputTokens']):raise DomainError('CONTEXT_EXCEEDED','Input exceeds model limit')
        if m.get('maxOutputTokens') is not None and out>dec(m['maxOutputTokens']):raise DomainError('OUTPUT_EXCEEDED','Output exceeds model limit')
        cost=charge(priced['prices'],{'uncachedInputTokens':inp*(1-cache),'cacheReadTokens':inp*cache,'outputTokens':out})['totalCost']
        guard=self.settings(c).get('costGuard',{})
        if guard.get('threshold') is not None and cost>dec(guard['threshold']):
            if guard.get('mode')=='BLOCK':raise DomainError('COST_GUARD','Request exceeds cost guard')
            if guard.get('mode')=='REQUIRE_APPROVAL' and not p.get('approved'):raise DomainError('APPROVAL_REQUIRED','Request exceeds approval threshold')
        ws=[self.wallet(r[0],c) for r in c.execute('SELECT id FROM wallets WHERE user_id=?',(USER,))]
        if p.get('walletId'):ws=[w for w in ws if w['id']==p['walletId']]
        ws=[w for w in ws if self.eligible(w,provider,m['id'],p.get('service'))]
        strategy=p.get('walletStrategy',self.settings(c)['walletStrategy'])
        if strategy in ('SOONEST_EXPIRY_FIRST','USE_EXPIRING_CREDITS_FIRST'):ws.sort(key=lambda w:(w.get('expiresAt') or '9999',w.get('priority',1)))
        elif strategy=='HIGHEST_BALANCE_FIRST':ws.sort(key=lambda w:dec(w['availableBalance'],nonnegative=False)/self.rate(w['currency'],c),reverse=True)
        else:ws.sort(key=lambda w:w.get('priority',1))
        rejected=[]
        for w in ws:
            amount=cost*self.rate(w['currency'],c)
            try:self.limit_check(c,w,amount)
            except DomainError as e:rejected.append({'walletId':w['id'],'reason':e.code});continue
            if amount<=dec(w['availableBalance'],nonnegative=False):return wire(dict(priced,allowed=True,walletId=w['id'],estimatedCost=cost,reservedAmount=amount,availableBalance=w['availableBalance'],currency=w['currency'],provider=provider,modelId=m['id'],lowBalance=w.get('lowBalanceThreshold') is not None and dec(w['availableBalance'],nonnegative=False)-amount<dec(w['lowBalanceThreshold']),warnings=['COST_GUARD_WARNING'] if guard.get('threshold') and cost>dec(guard['threshold']) else []))
            rejected.append({'walletId':w['id'],'reason':'INSUFFICIENT_BALANCE'})
        return wire({'allowed':False,'reason':'INSUFFICIENT_BALANCE' if ws else 'NO_ELIGIBLE_WALLET','estimatedCost':cost,'rejected':rejected})
    def idem(self,c,key,p,fn):
        payload=dumps(p);row=c.execute('SELECT payload,response FROM idempotency WHERE user_id=? AND key=?',(USER,key)).fetchone()
        if row:
            if row['payload']!=payload:raise DomainError('IDEMPOTENCY_CONFLICT','Same idempotency key used with different payload')
            return loads(row['response'])
        response=fn();c.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(USER,key,payload,dumps(response)));return response
    def reserve(self,p):
        if not p.get('requestId'):raise DomainError('INVALID_INPUT','requestId is required')
        with self.transaction() as c:
            def perform():
                quote=self.check_budget(p,c)
                if not quote['allowed']:raise DomainError(quote['reason'],'No eligible wallet can reserve this request')
                w=self.wallet(quote['walletId'],c);amount=dec(quote['reservedAmount']);before=dec(w['currentBalance'],nonnegative=False)
                r=dict(p,**quote,state='RESERVED',createdAt=now(),exchangeRate=str(self.rate(w['currency'],c)))
                w['reservedBalance']=str(dec(w['reservedBalance'])+amount);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),w['id']))
                c.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(USER,p['requestId'],w['id'],'RESERVED',dumps(r)))
                self.ledger(c,w,r,'RESERVATION',amount,before,before,{});self.audit(c,'Reservation',new=r)
                return r
            return self.idem(c,'reserve:'+p['requestId'],p,perform)
    def reservation(self,c,id):
        row=c.execute('SELECT * FROM reservations WHERE user_id=? AND request_id=?',(USER,id)).fetchone()
        if not row:raise DomainError('RESERVATION_NOT_FOUND','Reservation does not exist')
        return loads(row['data'])
    def settle(self,p):
        request=p.get('requestId')
        if not request:raise DomainError('INVALID_INPUT','requestId is required')
        if not p.get('usage'):
            with self.transaction() as c:
                r=self.reservation(c,request)
                if r['state'] not in ('RESERVED','USAGE_UNKNOWN'):raise DomainError('INVALID_STATE','Reservation already completed')
                r['state']='USAGE_UNKNOWN';c.execute('UPDATE reservations SET state=?,data=? WHERE user_id=? AND request_id=?',('USAGE_UNKNOWN',dumps(r),USER,request));self.audit(c,'Usage Unknown',new={'requestId':request})
            return {'requestId':request,'state':'USAGE_UNKNOWN','charged':False,'reason':'No provider usage; reservation retained for reconciliation'}
        usage=normalize_usage(p['usage'])
        with self.transaction() as c:
            def perform():
                r=self.reservation(c,request)
                if r['state'] not in ('RESERVED','USAGE_UNKNOWN'):raise DomainError('INVALID_STATE','Reservation already completed')
                result=charge(r['prices'],usage);usd=result['totalCost'];amount=usd*dec(r['exchangeRate']);reserved=dec(r['reservedAmount']);w=self.wallet(r['walletId'],c);before=dec(w['currentBalance'],nonnegative=False);after=before-amount
                w['currentBalance']=str(after);w['reservedBalance']=str(dec(w['reservedBalance'])-reserved);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),w['id']))
                r.update(state='SETTLED',actualCost=str(usd),chargedAmount=str(amount),usage=wire(usage),settledAt=now());c.execute('UPDATE reservations SET state=?,data=? WHERE user_id=? AND request_id=?',('SETTLED',dumps(r),USER,request))
                self.ledger(c,w,r,'RELEASE',reserved,before,before,{'reason':'Settlement releases complete hold'});self.ledger(c,w,r,'USAGE',amount,before,after,{'usageData':wire(usage),'breakdown':wire(result['breakdown'])})
                baseline=None
                try:baseline=charge(r['prices'],{'uncachedInputTokens':usage['inputTokens'],'outputTokens':usage['outputTokens']})['totalCost']
                except DomainError:pass
                record=dict(r,**wire(usage),id=uid(),cacheSavings=str(baseline-usd) if baseline is not None else None,kind='SIMULATED' if p.get('simulated') or r.get('simulated') else 'ACTUAL',streaming=bool(p.get('streaming')),latency=p.get('latency'),debt=wire(max(dec(0),-after)))
                c.execute('INSERT INTO usage VALUES(?,?,?,?,?)',(record['id'],USER,request,dumps(record),now()));self.audit(c,'Settlement',new=record)
                return record
            return self.idem(c,'settle:'+request,p,perform)
    def release(self,p):
        with self.transaction() as c:
            def perform():
                r=self.reservation(c,p['requestId'])
                if r['state'] not in ('RESERVED','USAGE_UNKNOWN'):raise DomainError('INVALID_STATE','Reservation already completed')
                w=self.wallet(r['walletId'],c);amount=dec(r['reservedAmount']);w['reservedBalance']=str(dec(w['reservedBalance'])-amount);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),w['id']))
                r['state']='RELEASED';c.execute('UPDATE reservations SET state=?,data=? WHERE user_id=? AND request_id=?',('RELEASED',dumps(r),USER,p['requestId']))
                self.ledger(c,w,r,'RELEASE',amount,dec(w['currentBalance'],nonnegative=False),dec(w['currentBalance'],nonnegative=False),{'reason':p.get('reason','Request failed')});self.audit(c,'Release',new=r);return r
            return self.idem(c,'release:'+p['requestId'],p,perform)
    def refund(self,p):
        if not p.get('refundId'):raise DomainError('INVALID_INPUT','refundId required for refund idempotency')
        with self.transaction() as c:
            def perform():
                r=self.reservation(c,p['requestId'])
                if r['state']!='SETTLED':raise DomainError('INVALID_STATE','Only settled requests can be refunded')
                already=sum((dec(loads(row[0])['amount']) for row in c.execute('SELECT data FROM ledger WHERE user_id=? AND request_id=? AND type="REFUND"',(USER,p['requestId']))),dec(0));remaining=dec(r['chargedAmount'])-already;amount=dec(p.get('amount',remaining))
                if amount>remaining:raise DomainError('REFUND_EXCEEDED','Refund exceeds settled amount')
                w=self.wallet(r['walletId'],c);before=dec(w['currentBalance'],nonnegative=False);after=before+amount;w['currentBalance']=str(after);c.execute('UPDATE wallets SET data=? WHERE id=?',(dumps(w),w['id']))
                entry=self.ledger(c,w,r,'REFUND',amount,before,after,{'refundId':p['refundId']});self.audit(c,'Refund',new=entry);return entry
            return self.idem(c,'refund:'+p['refundId'],p,perform)
    def route(self,p):
        ids=p.get('modelIds') or [m['id'] for m in self.models({'enabled':True})['models']];candidates=[];rejected=[]
        for mid in ids:
            try:
                q=self.check_budget(dict(p,modelId=mid))
                if q['allowed']:
                    m=self.model(mid);q.update(quality=p.get('qualityScores',{}).get(mid),latency=p.get('latencies',{}).get(mid));candidates.append(q)
                else:rejected.append({'modelId':mid,'reason':q['reason']})
            except DomainError as e:rejected.append({'modelId':mid,'reason':e.code})
        strategy=p.get('strategy','CHEAPEST_FIRST')
        if strategy=='QUALITY_FIRST':candidates.sort(key=lambda q:(q['quality'] is None,-dec(q['quality'] or 0),dec(q['estimatedCost'])))
        elif strategy=='EXPIRING_CREDITS_FIRST':candidates.sort(key=lambda q:(self.wallet(q['walletId']).get('expiresAt') or '9999',dec(q['estimatedCost'])))
        elif strategy=='WALLET_BALANCE_AWARE':candidates.sort(key=lambda q:(q['lowBalance'],-dec(q['availableBalance'],nonnegative=False)/self.rate(q['currency']),dec(q['estimatedCost'])))
        elif strategy=='BALANCED':candidates.sort(key=lambda q:(q['lowBalance'],dec(q['estimatedCost'])/(1+dec(q['quality'] or 0))))
        elif strategy=='CUSTOM':candidates.sort(key=lambda q:ids.index(q['modelId']))
        else:candidates.sort(key=lambda q:dec(q['estimatedCost']))
        selected=candidates[0] if candidates else None
        with self.transaction() as c:self.audit(c,'ContextGate Routing',new={'strategy':strategy,'selected':selected and selected['modelId'],'simulation':True})
        return {'simulation':True,'strategy':strategy,'selected':selected,'candidates':candidates,'rejected':rejected,'qualitySource':'USER_SUPPLIED_OR_UNAVAILABLE'}
    def rows(self,table,q=None):
        if table not in ('usage','ledger','audit','reservations'):raise DomainError('INVALID_INPUT','Unknown data collection')
        with self.connect() as c:rows=[loads(r[0]) for r in c.execute(f'SELECT data FROM {table} WHERE user_id=? ORDER BY rowid DESC',(USER,))]
        for k,v in (q or {}).items():
            if k in ('walletId','agentId','sessionId','gateId','modelId','provider','requestId','kind'):rows=[r for r in rows if str(r.get(k))==str(v)]
        return rows
    def dashboard(self):
        usage=self.rows('usage');wallets=self.wallets()['wallets'];t=datetime.now(timezone.utc);totals={}
        def period(days):return [u for u in usage if expiry(u['createdAt'])>=(t.replace(hour=0,minute=0,second=0,microsecond=0) if days==1 else t-timedelta(days=days))]
        for label,days in [('today',1),('7d',7),('30d',30)]:
            rows=period(days);totals[label]={'cost':str(sum((dec(r.get('actualCost',0)) for r in rows),dec(0))),'tokens':str(sum((dec(r.get('totalTokens',0)) for r in rows),dec(0))),'requests':len(rows)}
        groups={}
        for key in ('provider','modelId','agentId','gateId','walletId','sessionId'):
            buckets={}
            for u in usage:
                val=u.get(key) or 'Unspecified';b=buckets.setdefault(val,{'cost':dec(0),'requests':0,'tokens':dec(0),'inputTokens':dec(0),'outputTokens':dec(0),'cacheReadTokens':dec(0)})
                b['cost']+=dec(u.get('actualCost',0));b['requests']+=1
                for k,uk in [('tokens','totalTokens'),('inputTokens','inputTokens'),('outputTokens','outputTokens'),('cacheReadTokens','cacheReadTokens')]:b[k]+=dec(u.get(uk,0))
            groups[key]=[wire(dict(id=k,**v,avgCost=v['cost']/v['requests'],cacheHitRate=v['cacheReadTokens']/v['inputTokens'] if v['inputTokens'] else None)) for k,v in sorted(buckets.items(),key=lambda x:x[1]['cost'],reverse=True)]
        balance=dec(0);unknown=[]
        for w in wallets:
            try:balance+=dec(w['availableBalance'],nonnegative=False)/self.rate(w['currency'])
            except DomainError:unknown.append(w['id'])
        daily=dec(totals['30d']['cost'])/30
        return wire({'periods':totals,'totalWalletBalanceUSD':balance,'walletsMissingExchangeRate':unknown,'groups':groups,'creditsExpiringSoon':[w for w in wallets if expiry(w.get('expiresAt')) and expiry(w['expiresAt'])<t+timedelta(days=30)],'estimatedDaysRemaining':balance/daily if daily>0 else None,'cacheSavings':sum((dec(u.get('cacheSavings',0)) for u in usage if u.get('cacheSavings') is not None),dec(0)),'cacheSavingsStatus':'PRICING_SNAPSHOT_BASELINE','simulationIncluded':any(u.get('kind')=='SIMULATED' for u in usage)})
    def export(self):
        with self.connect() as c:
            settings=[{'modelId':r['model_id'],'data':loads(r['data'])} for r in c.execute('SELECT * FROM model_settings WHERE user_id=?',(USER,))]
            custom=[loads(r[0]) for r in c.execute('SELECT data FROM models WHERE custom=1')]
        return {'schemaVersion':1,'exportedAt':now(),'customModels':custom,'modelSettings':settings,'settings':self.settings(),'walletConfig':[{k:v for k,v in w.items() if k not in ('reservedBalance','availableBalance','currentBalance','debt')} for w in self.wallets()['wallets']],'usage':self.rows('usage'),'transactions':self.rows('ledger')}
    def import_data(self,p):
        data=p.get('data',p);reject_secrets(data)
        if data.get('schemaVersion')!=1:raise DomainError('INVALID_IMPORT','Unsupported schemaVersion')
        # Validate before mutation. Financial records are exported for analysis, never replayed as balances.
        for m in data.get('customModels',[]):
            if not m.get('name'):raise DomainError('INVALID_MODEL','Custom model name required')
            for ps in self.inline_prices(m).values():
                if ps['pricePerUnit'] is not None:dec(ps['pricePerUnit'])
        for x in data.get('modelSettings',[]):
            if x['modelId'] not in {m.get('id') for m in data.get('customModels',[])}:self.model(x['modelId'])
        with self.transaction() as c:
            if 'settings' in data:self.update_settings({k:v for k,v in data['settings'].items() if k not in ('calculatorDraft','calculatorDraftRevision')},c)
            for m in data.get('customModels',[]):
                mid=m.get('id','custom-'+uid());old=c.execute('SELECT custom FROM models WHERE id=?',(mid,)).fetchone()
                if old and not old[0]:raise DomainError('IMPORT_CONFLICT','Custom import cannot overwrite built-in')
                m=dict(m,id=mid,isCustom=True,isBuiltIn=False);c.execute('INSERT OR REPLACE INTO models VALUES(?,?,1)',(mid,dumps(m)));self.save_prices(c,mid,mid,'STANDARD',self.inline_prices(m))
            for x in data.get('modelSettings',[]):self.patch_model(x['modelId'],x['data'],c)
            self.audit(c,'Settings Imported',new={'customModels':len(data.get('customModels',[]))})
        return {'imported':True,'walletConfigImported':False,'reason':'Wallet balances and financial ledgers require deliberate creation; export is not a financial replay'}
    def reset(self,p):
        if p.get('confirmation')!='RESET':raise DomainError('CONFIRMATION_REQUIRED','Type RESET to confirm reset')
        target=p.get('target')
        if target=='builtins':
            if not self.catalog_path.exists():raise DomainError('CATALOG_UNAVAILABLE','Bundled catalog is missing')
            return self.update_catalog(loads(self.catalog_path.read_text()))
        with self.transaction() as c:
            if target in ('models','all'):c.execute('DELETE FROM model_settings WHERE user_id=?',(USER,))
            if target in ('calculator','all'):
                requested=p.get('calculatorDraftRevision',0)
                if type(requested) is not int or not 0<=requested<=9007199254740991: raise DomainError('INVALID_INPUT','Invalid calculator draft revision')
                previous=self.settings(c).get('calculatorDraftRevision',0)
                revision=max(requested,previous+1,int(datetime.now(timezone.utc).timestamp()*1000))
                if revision>9007199254740991: raise DomainError('INVALID_INPUT','Calculator draft revision exhausted')
                reset_settings=dict(DEFAULTS,calculatorDraft=None,calculatorDraftRevision=revision)
                c.execute('UPDATE settings SET data=? WHERE user_id=?',(dumps(reset_settings),USER))
            if target=='all':
                for table in ('idempotency','undo','usage','ledger','reservations','wallets','audit'):c.execute(f'DELETE FROM {table} WHERE user_id=?',(USER,))
                # Preserve historical built-in price versions, remove custom catalog on explicit full reset.
                ids=[r[0] for r in c.execute('SELECT id FROM models WHERE custom=1')]
                for mid in ids:
                    c.execute('DELETE FROM price_versions WHERE model_id=?',(mid,));c.execute('DELETE FROM price_history WHERE model_id=?',(mid,));c.execute('DELETE FROM endpoints WHERE model_id=?',(mid,));c.execute('DELETE FROM models WHERE id=?',(mid,))
            if target not in ('models','calculator','all'):raise DomainError('INVALID_INPUT','Unknown reset target')
            self.audit(c,'Local Data Reset',new={'target':target})
        return {'reset':target}

    def handle(self,method,subpath,query,body):
        """Serve one /v1/wallet request. Returns (http_status, json-safe dict).

        method: 'GET' | 'POST' | 'PATCH'. subpath: prototype path after '/api', e.g. '/wallets/<id>/adjust'.
        query: dict of single values. body: dict (the console has already parsed the JSON object).
        Routes, status mapping and the {"error": {"code", "message"}} envelope follow proto/backend.py.
        """
        try:
            if method not in ('GET','POST','PATCH'):raise DomainError('NOT_FOUND','Endpoint does not exist')
            if not isinstance(body,dict):raise DomainError('INVALID_INPUT','JSON object required')
            if len(dumps(body).encode())>2_000_000:raise DomainError('BODY_TOO_LARGE','Request exceeds 2 MB')
            reject_secrets(body)
            return 200,wire(self._serve(method,str(subpath),dict(query or {}),body))
        except DomainError as e:
            status=403 if e.code.startswith('FORBIDDEN') else 404 if e.code.endswith('NOT_FOUND') else 409 if e.code in ('IDEMPOTENCY_CONFLICT','INVALID_STATE') else 400
            return status,{'error':{'code':e.code,'message':e.message}}
        except (KeyError,TypeError,ValueError):return 400,{'error':{'code':'INVALID_INPUT','message':'Required field is missing or malformed'}}
        except Exception:return 500,{'error':{'code':'INTERNAL_ERROR','message':'Operation failed; no partial transaction was committed'}}
    def _serve(self,method,path,query,body):
        parts=path.strip('/').split('/')
        if method=='GET':
            if path=='/bootstrap':return dict(self.catalog_meta(),models=self.models({'includeHidden':True,'includeDeprecated':True})['models'],providers=list(self.models()['providerCounts']),providerCounts=self.models()['providerCounts'],settings=self.settings(),wallets=self.wallets()['wallets'],dashboard=self.dashboard(),adapters={'AWS':{'status':'UNCONNECTED','balanceApi':'GetCredits'},'others':{'status':'UNSUPPORTED'}},integration={'mode':'ISOLATED_SIMULATION','productionConnected':False})
            if path in ('/models','/catalog'):return dict(self.models(query),**self.catalog_meta())
            if len(parts)>=2 and parts[0]=='models':
                m=self.model(unquote('/'.join(parts[1:])))
                with self.connect() as c:
                    m['endpoints']=[loads(r[0]) for r in c.execute('SELECT data FROM endpoints WHERE model_id=?',(m['id'],))]
                    m['priceHistory']=[dict(r) for r in c.execute('SELECT * FROM price_history WHERE model_id=?',(m['id'],))]
                    m['prices']=[dict(r,data=loads(r['data'])) for r in c.execute('SELECT * FROM price_versions WHERE model_id=?',(m['id'],))]
                return m
            if path=='/wallets':return self.wallets()
            if len(parts)==2 and parts[0]=='wallets':return self.wallet(parts[1])
            if path=='/settings':return self.settings()
            if path in ('/costs','/dashboard'):return self.dashboard()
            if path in ('/usage','/ledger','/audit','/reservations'):
                key={'ledger':'transactions','usage':'usage','audit':'audit','reservations':'reservations'}[parts[0]];return {key:self.rows(parts[0],query)}
            if path=='/pricing':
                if query.get('modelId'):return self.pricing(query['modelId'],query.get('endpointId'),query.get('serviceTier','STANDARD'),query.get('priceVersion'),pricing_mode=query.get('pricingMode'))
                with self.connect() as c:return {'prices':[dict(r,data=loads(r['data'])) for r in c.execute('SELECT * FROM price_versions')]}
            if path=='/export':return self.export()
        if method=='PATCH':
            if path=='/settings':return self.update_settings(body)
            if len(parts)>=2 and parts[0]=='models':return self.patch_model(unquote('/'.join(parts[1:])),body)
            if len(parts)==2 and parts[0]=='wallets':return self.patch_wallet(parts[1],body)
        if method=='POST':
            if path=='/calculate':return self.calculate(body)
            if path=='/compare':
                ids=body.get('modelIds',[])
                if not isinstance(ids,list) or not 2<=len(ids)<=10:raise DomainError('INVALID_INPUT','Compare requires 2–10 models')
                results=[]
                for mid in ids:
                    try:results.append(self.calculate(dict(body,modelId=mid)))
                    except DomainError as e:results.append({'modelId':mid,'error':{'code':e.code,'message':e.message}})
                return {'results':results}
            if path=='/models':return self.custom(body)
            if path=='/models/bulk':return self.bulk(body)
            if path=='/models/undo':return self.undo(body['undoId'])
            if len(parts)>=3 and parts[0]=='models' and parts[-1]=='duplicate':return self.custom(body,unquote('/'.join(parts[1:-1])))
            if path=='/wallets':return self.create_wallet(body)
            if len(parts)==3 and parts[0]=='wallets':
                if parts[2]=='adjust':return self.adjust(parts[1],body)
                if parts[2]=='sync':
                    w=self.wallet(parts[1]);result=(AWSAdapter() if w['provider']=='AWS' else UnsupportedAdapter()).syncBalance()
                    with self.transaction() as c:self.audit(c,'Wallet Sync',new={'walletId':w['id'],'result':result})
                    return dict(result,wallet=w)
            if path=='/wallets/check-budget':return self.check_budget(body)
            if path=='/wallets/reserve':return self.reserve(body)
            if path=='/wallets/settle':return self.settle(body)
            if path=='/wallets/release':return self.release(body)
            if path=='/wallets/refund':return self.refund(body)
            if path=='/route':return self.route(body)
            if path=='/invoke':
                decision=self.route(body)
                if not decision['selected']:return decision
                selected=decision['selected'];reserve=self.reserve(dict(body,modelId=selected['modelId'],walletId=selected['walletId'],endpointId=selected['endpointId'],simulated=True))
                if body.get('failed') and not body.get('usage'):return {'simulation':True,'reservation':reserve,'result':self.release({'requestId':body['requestId'],'reason':'Simulated provider failure'})}
                return {'simulation':True,'reservation':reserve,'result':self.settle({'requestId':body['requestId'],'usage':body.get('usage'),'simulated':True,'streaming':body.get('streaming',False)})}
            if path=='/import':return self.import_data(body)
            if path=='/reset':return self.reset(body)
            if path in ('/catalog/update','/pricing/update'):
                if body:raise DomainError('INVALID_INPUT','Update only imports the bundled verified catalog; arbitrary source URLs are forbidden')
                if not self.catalog_path.exists():raise DomainError('CATALOG_UNAVAILABLE','Bundled catalog is missing')
                return self.update_catalog(loads(self.catalog_path.read_text()))
            if path=='/exchange-rates/refresh':return {'status':'UNSUPPORTED','reason':'No authenticated or verified live FX transport is connected; configure manual override','cached':self.settings()['exchangeRates'],'updatedAt':self.settings()['exchangeRateUpdatedAt']}
        raise DomainError('NOT_FOUND','Endpoint does not exist')
    def close(self):
        """No long-lived connection is kept between calls; present so the console closes every service uniformly."""
        return None

class WalletSDK:
    """In-process ContextGate integration contract. Uses one accounting service."""
    def __init__(self,console):self.console=console
    def getBalance(self,walletId):return self.console.wallet(walletId)
    def checkBudget(self,payload):return self.console.check_budget(payload)
    def reserve(self,payload):return self.console.reserve(payload)
    def settle(self,payload):return self.console.settle(payload)
    def release(self,payload):return self.console.release(payload)
    def getPricing(self,modelId,**kwargs):return self.console.pricing(modelId,**kwargs)
