"""Focused draft revision regression; no browser or production database."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('draft_backend',ROOT/'console_wallet.py')
backend=importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class CalculatorDraft(unittest.TestCase):
    def test_reset_blocks_old_saves_without_touching_accounting_or_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            app=backend.Wallets(Path(temp)/'state',Path(temp)/'missing.json')
            app.create_wallet({'name':'Keep','provider':'Test','initialCredit':'20'})
            with app.connect() as c:
                before={table:[tuple(row) for row in c.execute('SELECT * FROM '+table)] for table in ('wallets','ledger','audit')}
            defaults=app.settings()['defaultBudget']
            draft={'version':1,'calc':{'budget':'55'},'mode':'money','result':{'totalTokens':'9107000'}}
            app.update_settings({'calculatorDraft':draft,'calculatorDraftRevision':200})
            app.update_settings({'calculatorDraft':None,'calculatorDraftRevision':201})
            app.update_settings({'calculatorDraft':draft,'calculatorDraftRevision':200})
            self.assertIsNone(app.settings()['calculatorDraft'])
            self.assertEqual(app.settings()['calculatorDraftRevision'],201)
            self.assertEqual(app.settings()['defaultBudget'],defaults)
            with app.connect() as c:
                after={table:[tuple(row) for row in c.execute('SELECT * FROM '+table)] for table in before}
            self.assertEqual(before,after)
            for revision in (True,-1,1.2,9007199254740992):
                with self.assertRaises(backend.DomainError):
                    app.update_settings({'calculatorDraft':draft,'calculatorDraftRevision':revision})
            for bad in ({'version':2,'calc':{}},{'version':1,'calc':[]},[]):
                with self.assertRaises(backend.DomainError):
                    app.update_settings({'calculatorDraft':bad,'calculatorDraftRevision':202})


if __name__=='__main__':unittest.main()
