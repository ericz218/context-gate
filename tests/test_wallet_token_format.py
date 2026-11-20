"""Wallet token labels are locale-independent; badge follows the system language."""
import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('wallet_ui_format', ROOT / 'console/wallet_ui.py')
wallet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wallet)


class WalletTokenFormat(unittest.TestCase):
    def test_token_suffixes_and_estimate_badge_in_both_languages(self):
        if not shutil.which('node'):
            self.skipTest('Node is required')
        # Export closures only from this in-memory test copy, not the product module.
        js = wallet.JS.replace('window.loadWallet=loadWallet;',
            'window.test={compact,state,resultView};')
        harness = "const assert=require('assert');const window={};const document={};let LANG='zh';"
        harness += 'const EN=' + json.dumps(wallet.EN) + ';'
        harness += "const T=s=>LANG==='en'?(EN[s]??s):s;const LOCALE=()=>LANG==='en'?'en-US':'zh-CN';"
        checks = """
const x=window.test;
for(const lang of ['zh','en']){
 LANG=lang;x.state.settings.numberFormat='compact';
 for(const [value,label] of [[9107000,'9.107M'],[17200000000,'17.2B'],[1200,'1.2K']]){
  assert.equal(x.compact(value),label);
 }
 const html=x.resultView({totalTokens:17200000000,inputTokens:9107000,outputTokens:1200});
 assert(html.includes('<span class="tag prepared">'+(lang==='zh'?'估算':'Estimate')+'</span>'));
 assert(html.includes('17.2B'));assert(!html.includes('>ESTIMATE<'));
 x.state.settings.numberFormat='full';assert.equal(x.compact(9107000),'9,107,000');
}
"""
        result = subprocess.run(['node','-'], input=harness+js+checks, text=True,
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
