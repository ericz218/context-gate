import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import usage_import as imp
class Regressions(unittest.TestCase):
 def test_partial_line_is_retried_and_utf8_not_split(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'rollout.jsonl';offsets={}
   complete=b'{"type":"turn_context","payload":{"model":"gpt-6.1-sol"}}\n'
   pending=json.dumps({'timestamp':'2026-10-13T16:00:00.000Z','type':'token_usage_record','payload':{'response_id':'r1','usage':{'input_tokens':20,'output_tokens':4}}}).encode()+b'\n'
   p.write_bytes(complete+pending[:50]);text=''.join(imp.iter_new_text(p,offsets))
   self.assertEqual(offsets[str(p)],len(complete));self.assertEqual(imp.codex_entries(text)[0],[])
   with p.open('ab') as f:f.write(pending[50:])
   rows,model=imp.codex_entries(''.join(imp.iter_new_text(p,offsets)),'gpt-6.1-sol')
   self.assertEqual(len(rows),1);self.assertEqual(rows[0][2:4],(20,4))
   self.assertEqual(list(imp.iter_new_text(p,offsets)),[])
   p.write_bytes(b'\xc3');self.assertEqual(list(imp.iter_new_text(p,offsets)),[])
   with p.open('ab') as f:f.write(b'\xa9\n')
   self.assertEqual(list(imp.iter_new_text(p,offsets)),['é\n'])
 def test_status_is_fresh_success_with_no_account_or_tokens(self):
  with tempfile.TemporaryDirectory() as tmp:
   state=Path(tmp)
   with patch.multiple(imp,STATE=state,CLAUDE_PROJECTS=state/'missing-claude',CODEX_SESSIONS=state/'missing-codex',ZCODE_DB=state/'missing-zcode',ROUTER_DB=state/'missing-router',ANTIGRAVITY_ROOTS=(state/'missing-antigravity',),DEEPAI_PI_ROOT=state/'missing-deepai-pi',DEEPAI_PROVIDER_LOGS=state/'missing-deepai-logs'),patch.object(imp,'claude_account',return_value=None),patch.object(imp,'codex_account',return_value=None):
    self.assertEqual(imp.run(),(0,0))
   d=json.loads((state/'usage-import-status.json').read_text())
   self.assertGreater(d['last_completed'],0);self.assertEqual(d['imported'],0)
   self.assertEqual(d['next_due'],d['last_started']+5);self.assertNotIn('account',d)
   self.assertEqual((state/'usage-import-status.json').stat().st_mode&0o777,0o600)
 def test_previous_success_is_preserved_during_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   state=Path(tmp);(state/'usage-import-status.json').write_text(json.dumps({'last_completed':10,'imported':3,'skipped':2,'private':'omit'}))
   def fail():
    d=json.loads((state/'usage-import-status.json').read_text())
    self.assertEqual((d['last_completed'],d['imported'],d['skipped']),(10,3,2));self.assertNotIn('private',d)
    raise OSError('simulated')
   with patch.object(imp,'STATE',state),patch.object(imp,'_run',side_effect=fail):
    with self.assertRaises(OSError):imp.run()
   d=json.loads((state/'usage-import-status.json').read_text());self.assertEqual(d['last_completed'],10);self.assertEqual(d['error'],'io_error')
 def test_status_failure_does_not_mask_original_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   original=imp.sqlite3.OperationalError('database locked')
   with patch.object(imp,'STATE',Path(tmp)),patch.object(imp,'_write_import_status',side_effect=[None,OSError('status write')]),patch.object(imp,'_run',side_effect=original):
    with self.assertRaises(imp.sqlite3.OperationalError) as caught:imp.run()
    self.assertIs(caught.exception,original)
 def test_marker_write_failure_is_not_success(self):
  with tempfile.TemporaryDirectory() as tmp:
   state=Path(tmp);orig=Path.write_text
   def write(path,*args,**kw):
    if path.name=='usage-import-state.json':raise OSError('marker fail')
    return orig(path,*args,**kw)
   with patch.multiple(imp,STATE=state,CLAUDE_PROJECTS=state/'missing-claude',CODEX_SESSIONS=state/'missing-codex',ZCODE_DB=state/'missing-zcode',ROUTER_DB=state/'missing-router',ANTIGRAVITY_ROOTS=(state/'missing-antigravity',),DEEPAI_PI_ROOT=state/'missing-deepai-pi',DEEPAI_PROVIDER_LOGS=state/'missing-deepai-logs'),patch.object(imp,'claude_account',return_value=None),patch.object(imp,'codex_account',return_value=None),patch.object(Path,'write_text',write):
    with self.assertRaises(OSError):imp.run()
   d=json.loads((state/'usage-import-status.json').read_text());self.assertEqual(d['error'],'io_error');self.assertIsNone(d['last_completed'])
 def test_failure_exposes_safe_category_and_propagates(self):
  with tempfile.TemporaryDirectory() as tmp:
   with patch.object(imp,'STATE',Path(tmp)),patch.object(imp,'_run',side_effect=imp.sqlite3.OperationalError('database locked private text')):
    with self.assertRaises(imp.sqlite3.OperationalError):imp.run()
    d=json.loads((Path(tmp)/'usage-import-status.json').read_text())
    self.assertEqual(d['error'],'database_busy');self.assertIsNone(d['last_completed'])
    self.assertNotIn('private',json.dumps(d))
if __name__=='__main__':unittest.main()
