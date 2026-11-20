"""Draft regression checks. Codex-wallet-20261014-gpt6.1sol-low."""
import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wallet_ui_draft', ROOT / 'console/wallet_ui.py')
wallet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wallet)


class WalletUIRevision(unittest.TestCase):
    def node(self, script):
        if not shutil.which('node'):
            self.skipTest('Node is required')
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_english_values_and_existing_app_merge(self):
        # Exercise the real app's base dictionary and its non-overwriting wallet merge.
        app = (ROOT / 'console/app.py').read_text()
        base = app[app.index('const EN={'):app.index('const T=s=>')]
        self.assertFalse(any(re.search('[一-鿿]', v) for v in wallet.EN.values()))
        keys = set(re.findall(r"T\('([^']*)'\)", wallet.JS))
        chinese = sorted(k for k in keys if re.search('[一-鿿]', k))
        self.node(base + '\nconst walletEN=' + json.dumps(wallet.EN) + ';\n'
                  'for(const [k,v] of Object.entries(walletEN)){if(!(k in EN))EN[k]=v;}\n'
                  'for(const key of ' + json.dumps(chinese) + '){'
                  "if(!EN[key]||/[一-鿿]/u.test(EN[key]))throw Error('Missing or mixed English: '+key);}")

    def test_ime_search_keeps_input_and_defers_both_results(self):
        # Expose internals only in the in-memory test copy.
        js = wallet.JS.replace('window.loadWallet=loadWallet;',
            'window.test={onInput,onCompositionStart,onCompositionEnd,state};')
        harness = """
const assert=require('assert');const window={};const T=s=>s;const LOCALE=()=> 'zh-CN';
let modelWrites=0,pickerWrites=0,rootWrites=0;
const results={set innerHTML(v){modelWrites++}}, picker={set innerHTML(v){pickerWrites++}};
const root={set innerHTML(v){rootWrites++},querySelector(){return null}};
const document={querySelector(s){return {'#mw-model-results':results,'#mw-picker-results':picker,'#mw-root':root}[s]||null}};
"""
        checks = """
const x=window.test;
for(const [id,writes] of [['mw-model-search',()=>modelWrites],['mw-picker-search',()=>pickerWrites]]){
 const input={id,value:''};let before=writes();
 for(const value of ['中文','中文搜索']){
  x.onCompositionStart({target:input});input.value=value;
  x.onInput({target:input,isComposing:true});assert.equal(writes(),before);
  x.onCompositionEnd({target:input});assert.equal(writes(),++before);
  assert.equal(input.value,value);assert.equal(rootWrites,0);
 }
}
assert.equal(x.state.filters.search,'中文搜索');
"""
        self.node(harness + js + checks)

    def test_single_ledger_and_four_task_navigation(self):
        js = wallet.JS.replace('window.loadWallet=loadWallet;',
            'window.test={state,tabsHtml,usage};')
        harness = "const window={};const document={};const T=s=>s;const LOCALE=()=> 'zh-CN';"
        checks = """
const assert=require('assert'),x=window.test;
assert.equal((x.tabsHtml().match(/data-mw-tab=/g)||[]).length,4);
x.state.wallets=[{id:'w',name:'Wallet',currency:'USD'}];
x.state.usageRows={ledger:[{walletId:'w',requestId:'LEDGER_ONLY',type:'CREDIT',amount:'2'}],usage:[{walletId:'w',requestId:'USAGE_ONLY',kind:'SIMULATED'}],reservations:[{walletId:'w',requestId:'RESERVATION_ONLY'}]};
for(const [kind,marker] of [['ledger','LEDGER_ONLY'],['usage','USAGE_ONLY'],['reservations','RESERVATION_ONLY']]){
 x.state.usageFilter.record=kind;const html=x.usage();
 assert(html.includes(marker));assert.equal((html.match(/<table>/g)||[]).length,1);
 for(const other of ['LEDGER_ONLY','USAGE_ONLY','RESERVATION_ONLY'])if(other!==marker)assert(!html.includes(other));
}
"""
        self.node(harness + js + checks)

    def test_native_slider_and_task_layout_contract(self):
        self.assertIn('::-webkit-slider-runnable-track', wallet.CSS)
        self.assertIn('::-webkit-slider-thumb', wallet.CSS)
        self.assertIn('box-shadow:none;background:transparent;cursor:pointer;--mw-progress', wallet.CSS)
        self.assertNotIn('mw-more', wallet.JS)
        self.assertNotIn('mw-advanced-filters', wallet.JS)
        self.assertIn("page:'calculator'", wallet.JS)
        self.assertIn("sel('record-kind'", wallet.JS)
        self.assertIn('mw-model-filter-form', wallet.JS)
        self.assertIn("Translation:T('翻译')", wallet.JS)
        self.assertIn("['CURRENT','NEW','PREVIEW'].includes", wallet.JS)
        self.assertIn('技术详情与完整字段', wallet.JS)


if __name__ == '__main__':
    unittest.main()
