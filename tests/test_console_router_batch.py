import shutil
import subprocess
import unittest

from console.router_ui import JS


class RouterBatchTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the page parser')
    def test_six_modes_and_rejected_input(self):
        parser = JS[JS.index('function routerParseKeys('):JS.index('function routerBatchKeys(')]
        checks = r'''
const assert = require('node:assert/strict');
const keys = [{id:7,label:'old1'}, {id:3,label:'old2'}];
for (const op of ['create','replace']) {
  const ids = op === 'replace' ? [{id:7}, {id:3}] : [{}, {}];
  assert.deepEqual(routerParseKeys('  key-a\r\n\r\nkey-b\n','keys',op,keys), ids.map((id,i)=>({...id,secret:['key-a','key-b'][i]})));
  assert.deepEqual(routerParseKeys('\uFEFF账号 A\n账号 B','notes',op,keys), ids.map((id,i)=>({...id,label:['账号 A','账号 B'][i]})));
  assert.deepEqual(routerParseKeys('账号 A\nkey-a\n账号 B\nkey-b\n','combined',op,keys), ids.map((id,i)=>({...id,label:['账号 A','账号 B'][i],secret:['key-a','key-b'][i]})));
}
assert.deepEqual(routerParseKeys('\nkey-a','combined','create',[]), [{label:'',secret:'key-a'}]);
assert.equal(routerParseKeys('😀'.repeat(200),'notes','create',[])[0].label.length,400);
assert.deepEqual(
  routerParseKeys('k21\nk22\nk23','keys','create',Array(20).fill(keys[0])),
  [{secret:'k21'}, {secret:'k22'}, {secret:'k23'}]
);
const snapshot=[{id:7,providerId:15,priority:1,label:'old1',enabled:true,hasSecret:true},{id:3,providerId:15,priority:2,label:'old2',enabled:false,hasSecret:true}];
assert.equal(routerBatchConflict('create',snapshot,[]),false);
assert.equal(routerBatchConflict('create',snapshot,[{...snapshot[0],enabled:false}]),false);
assert.equal(routerBatchConflict('replace',snapshot,[{...snapshot[0],enabled:false},snapshot[1]]),false);
assert.equal(routerBatchConflict('replace',snapshot,[{...snapshot[0],label:'edited'},snapshot[1]]),true);
assert.equal(routerBatchConflict('replace',snapshot,[snapshot[1],snapshot[0]]),true);
assert.equal(routerBatchConflict('replace',snapshot,[snapshot[0]]),true);
assert.equal(routerBatchConflict('replace',snapshot,[{...snapshot[0],hasSecret:false},snapshot[1]]),true);
for (const [text,mode,op,targets] of [
 ['','keys','create',[]], ['note\nkey\nnote','combined','create',[]],
 ['a key','keys','create',[]], ['a'.repeat(2001),'keys','create',[]],
 ['😀'.repeat(201),'notes','create',[]], ['one','notes','replace',keys],
 ['one\ntwo\nthree','keys','replace',keys],
 ['note\n\nother\nkey','combined','create',[]], ['key','oops','create',[]],
 ['key','keys','oops',[]], ['a'.repeat(1000001),'notes','create',[]]
]) assert.throws(()=>routerParseKeys(text,mode,op,targets));
console.log('Six batch combinations and validation passed');
'''
        result = subprocess.run(['node'], input=parser + checks, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the page parser')
    def test_batch_create_ignores_concurrent_key_updates_and_replace_keeps_guard(self):
        section = JS[JS.index('function routerParseKeys('):JS.index("\n$('router-form').addEventListener")]
        checks = r'''
const assert = require('node:assert/strict');
const makeEl = () => ({
  textContent: '', innerHTML: '', value: '', disabled: false, dataset: {},
  classList: { remove() {}, add() {} },
  attributes: {},
  setAttribute(k, v) { this.attributes[k] = v; },
  addEventListener() {}, removeEventListener() {},
  querySelectorAll() { return []; },
  replaceChildren() {}, focus() {}, offsetWidth: 0,
  elements: {},
});
const nodes = {
  'router-form': Object.assign(makeEl(), { elements: { mode: { value: 'keys' }, operation: { value: 'create' } } }),
  'router-dialog': makeEl(),
  'router-form-title': makeEl(),
  'router-batch-text': makeEl(),
  'router-form-error': makeEl(),
  'router-batch-save': makeEl(),
  'router-batch-help': makeEl(),
  'router-batch-count': makeEl(),
  'router-batch-preview': makeEl(),
  'router-batch-back': makeEl(),
};
const $ = id => nodes[id] || (nodes[id] = makeEl());
const T = s => s, esc = s => String(s), routerTable = () => '<table></table>';
const routerData = { providers: [{ id: 15, name: 'Backboard' }] };
let routerBusy = false;
const calls = [], doneMsgs = [];
const initial = [
  { id: 49, providerId: 15, priority: 1, label: 'a', enabled: true, hasSecret: true },
  { id: 50, providerId: 15, priority: 2, label: 'b', enabled: true, hasSecret: true },
];
let liveKeys = [
  { id: 49, providerId: 15, priority: 1, label: 'a', enabled: false, hasSecret: true },
  { id: 50, providerId: 15, priority: 2, label: 'b', enabled: false, hasSecret: true },
  { id: 51, providerId: 15, priority: 3, label: 'c', enabled: true, hasSecret: true },
];
async function routerCall(cmd, args) {
  calls.push([cmd, args]);
  if (cmd === 'list_provider_keys') return JSON.parse(JSON.stringify(liveKeys));
  return { ok: true };
}
async function routerKeysDone(pid, msg) { doneMsgs.push([pid, msg]); }
function routerKeys() {}
(async () => {
  routerBatchKeys(15, JSON.parse(JSON.stringify(initial)));
  nodes['router-batch-text'].value = 'k1\nk2\nk3\nk4\nk5\nk6\nk7\nk8';
  await nodes['router-form'].onsubmit({ preventDefault() {} });
  assert.equal(nodes['router-form-error'].textContent, '');
  assert.equal(calls.filter(c => c[0] === 'upsert_provider_key').length, 8);
  assert.equal(calls.filter(c => c[0] === 'list_provider_keys').length, 0);
  assert.deepEqual(doneMsgs, [[15, '批量处理完成 · 8 / 8']]);

  calls.length = 0; doneMsgs.length = 0;
  liveKeys = [{ ...initial[0], enabled: false }, initial[1]];
  nodes['router-form'].elements.operation.value = 'replace';
  routerBatchKeys(15, JSON.parse(JSON.stringify(initial)));
  nodes['router-batch-text'].value = 'rk1\nrk2';
  await nodes['router-form'].onsubmit({ preventDefault() {} });
  assert.equal(nodes['router-form-error'].textContent, '');
  assert.equal(calls.filter(c => c[0] === 'upsert_provider_key').length, 2);

  calls.length = 0; doneMsgs.length = 0;
  liveKeys = [{ ...initial[0], label: 'changed-concurrently' }, initial[1]];
  routerBatchKeys(15, JSON.parse(JSON.stringify(initial)));
  nodes['router-batch-text'].value = 'rk1\nrk2';
  await nodes['router-form'].onsubmit({ preventDefault() {} });
  assert.match(nodes['router-form-error'].textContent, /已有条目发生变化/);
  assert.equal(calls.filter(c => c[0] === 'upsert_provider_key').length, 0);
})().catch(e => { console.error(e); process.exitCode = 1; });
'''
        result = subprocess.run(['node'], input=section + checks, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
