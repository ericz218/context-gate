import unittest,tempfile
from pathlib import Path
from context_gate import Config,build_pack
class Reviewer:
 def __init__(self):self.pools=[]
 def ask(self,provider,state,questions):
  if "candidates" in state:self.pools.append([x["path"] for x in state["candidates"]])
  return {"answers":{k:{"choice":"no" if k.startswith("missing_") or k in ("conflict","cross_module") else "yes","confidence":.99} for k in questions}}
class NegationTests(unittest.TestCase):
 def test_readonly_negations_do_not_retrieve_edit_dependencies(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/"price.py").write_text("def price(): return 1\n");(root/"test_price.py").write_text("from price import price\n")
   memory=root/"memory.md";memory.write_text("[CORE_MEMORY_START]\nCORE\n[CORE_MEMORY_END]")
   for phrase in ["禁止修改","不要修改","不得修改","不能修改","不允许修改","不修改"]:
    with self.subTest(phrase=phrase):
     r=Reviewer();build_pack(root,"只读解释 price.py，"+phrase,[memory],Config(force_gate=True,cache_dir=str(root/"cache")),r)
     self.assertEqual(r.pools[0],["price.py"])
 def test_positive_edit_request_still_keeps_related_tests(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/"price.py").write_text("def price(): return 1\n");(root/"test_price.py").write_text("from price import price\n")
   memory=root/"memory.md";memory.write_text("[CORE_MEMORY_START]\nCORE\n[CORE_MEMORY_END]")
   r=Reviewer();build_pack(root,"只读检查 price.py 后修改它",[memory],Config(force_gate=True,cache_dir=str(root/"cache")),r)
   self.assertIn("test_price.py",r.pools[0])
