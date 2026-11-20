from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch, Mock

from console import app
from console.usability_ui import GUIDES, TERMS, JS


class UsabilityTests(unittest.TestCase):
    def test_all_pages_have_specific_help_and_keep_technical_terms(self):
        self.assertEqual(len(GUIDES),16)
        for _, (title, purpose, concepts) in GUIDES.items():
            self.assertTrue(title);self.assertTrue(purpose)
            for term in concepts:self.assertIn(term,TERMS)
        self.assertIn('push / pull',TERMS);self.assertIn('P50 / P95',TERMS)
        self.assertEqual(app.PAGE.count('id="page-title"'),1)
        self.assertNotIn('id="page-guide"',app.PAGE)
        self.assertNotIn('这页怎么看</button>',app.PAGE)
        self.assertIn('updatePageGuide(v)',app.PAGE)

    def test_refresh_action_is_stable_and_status_has_its_own_line(self):
        self.assertIn('class="refresh-control"',app.PAGE)
        self.assertIn('max-width:84px',app.PAGE)
        self.assertIn('id="refresh-note" class="refresh-note"',app.PAGE)
        self.assertIn('white-space:normal;overflow-wrap:anywhere',app.PAGE)
        self.assertIn('note.title=message',app.PAGE)
        self.assertIn('aria-live="polite"',app.PAGE)

    def test_diagnostics_collapsed_and_user_content_is_not_rewritten(self):
        self.assertEqual(app.PAGE.count('class="ux-advanced" data-view="sys"'),2)
        self.assertEqual(app.PAGE.count('class="ux-advanced" data-view="center"'),5)
        self.assertIn('id="audit"',app.PAGE);self.assertIn('id="log-service"',app.PAGE)
        self.assertNotIn('MutationObserver',JS)
        self.assertIn('思考档位',app.PAGE)
        self.assertNotIn('重置锚点',app.PAGE)

    def test_secondary_destinations_stay_with_their_parent(self):
        from console.usability_ui import NAV_GROUPS,NAV_CHILDREN
        primary=[v for _,views in NAV_GROUPS for v in views]
        self.assertEqual(len(primary),11)
        secondary=[v for views in NAV_CHILDREN.values() for v in views]
        self.assertEqual(set(primary+secondary),set(GUIDES))
        self.assertEqual(len(primary+secondary),len(GUIDES))
        self.assertEqual(NAV_CHILDREN['center'],('wb','gt'))
        self.assertIn('req',NAV_CHILDREN['bill'])
        footer=app.PAGE.split('<div class="nav-footer">')[1].split('</nav>')[0]
        self.assertNotIn('class="nav-item',footer)

    def test_relocate_checks_registration_and_reports_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'registry.json').write_text(json.dumps({'repos':[{'name':'sample-project'}]}))
            with patch.object(app,'git_sync_home',return_value=tmp),patch.object(app.subprocess,'run',return_value=Mock(returncode=0)) as run:
                self.assertTrue(app.git_sync_relocate({'name':'sample-project','path':'/project'})['ok'])
                self.assertEqual(run.call_args.args[0][-3:],['sample-project','path','/project'])
                with self.assertRaises(ValueError):app.git_sync_relocate({'name':'unknown','path':'/project'})
                with self.assertRaises(ValueError):app.git_sync_relocate({'name':'--help','path':'/project'})


if __name__=='__main__':unittest.main()
