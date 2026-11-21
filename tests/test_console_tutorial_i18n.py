# -*- coding: utf-8 -*-
"""Tests for automatic system-language detection, 8-language i18n, and onboarding tutorial."""
import json
import shutil
import subprocess
import unittest

from console.app import PAGE
from console.tutorial_ui import SUPPORTED_LANGS, LANG_OPTIONS, TOUR_UI, MAIN_TOUR, PAGE_TOURS
from console.usability_ui import GUIDES


class TutorialAndI18nTests(unittest.TestCase):
    def test_all_eight_languages_registered_in_selector_and_tours(self):
        self.assertEqual(SUPPORTED_LANGS, ('zh', 'zh-TW', 'en', 'ja', 'ko', 'es', 'fr', 'de'))
        for code, label in LANG_OPTIONS:
            self.assertIn(f'<option value="{code}">{label}</option>', PAGE)
            self.assertIn(code, TOUR_UI)
            self.assertIn(code, MAIN_TOUR)
            self.assertGreaterEqual(len(MAIN_TOUR[code]), 5)

    def test_every_console_view_has_first_visit_page_tour(self):
        self.assertEqual(set(PAGE_TOURS.keys()), set(GUIDES.keys()))
        for view, langs in PAGE_TOURS.items():
            self.assertIn('zh', langs, f'Missing zh page tour for {view}')
            self.assertIn('en', langs, f'Missing en page tour for {view}')
            self.assertTrue(langs['zh'], f'Empty zh page tour for {view}')
            self.assertTrue(langs['en'], f'Empty en page tour for {view}')

    def test_tutorial_controls_and_hooks_present(self):
        self.assertIn('id="tour-open"', PAGE)
        self.assertIn('id="tour-auto-chk"', PAGE)
        self.assertIn('id="tour-replay-main"', PAGE)
        self.assertIn('id="tour-reset-pages"', PAGE)
        self.assertIn('maybeStartPageTour(v)', PAGE)
        self.assertIn('bootOnboarding()', PAGE)

    def test_system_language_auto_detection_js(self):
        node = shutil.which('node') or '/opt/homebrew/bin/node'
        if not shutil.which(node):
            self.skipTest('Node unavailable')
        init = PAGE[PAGE.index("let LANG="):PAGE.index('const LOCALE=')]
        script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
function detect(local, shell, navLangs) {
  const ctx = {
    localStorage: { getItem: () => local },
    window: { __contextGateLanguage: shell },
    navigator: navLangs ? { languages: navLangs, language: navLangs[0] } : undefined,
  };
  return JSON.parse(JSON.stringify(vm.runInNewContext(SOURCE + '\n({LANG, LANG_AUTO})', ctx)));
}
assert.deepEqual(detect(null, undefined, ['zh-CN']), { LANG: 'zh', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['zh-Hant-TW']), { LANG: 'zh-TW', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['en-US']), { LANG: 'en', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['ja-JP']), { LANG: 'ja', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['ko-KR']), { LANG: 'ko', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['es-MX']), { LANG: 'es', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['fr-CA']), { LANG: 'fr', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['de-DE']), { LANG: 'de', LANG_AUTO: true });
assert.deepEqual(detect(null, undefined, ['pt-BR']), { LANG: 'en', LANG_AUTO: true });
assert.deepEqual(detect('ja', 'en', ['zh-CN']), { LANG: 'ja', LANG_AUTO: false });
assert.deepEqual(detect(null, 'ko', ['zh-CN']), { LANG: 'ko', LANG_AUTO: false });
'''.replace('SOURCE', json.dumps(init))
        res = subprocess.run([node], input=script, text=True, capture_output=True, timeout=15)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == '__main__':
    unittest.main()
