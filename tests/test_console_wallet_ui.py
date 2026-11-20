"""Self-contained checks for the model wallet console module (no dependency on app.py assembly)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from console.wallet_ui import CSS, HTML, JS, EN

ALLOWED_PREFIXES = ('.mw-', '#mw-', '[data-view=wallet]', '[data-view="wallet"]')


def strip_js(src):
    """Return code with comments, string/template/regex literals blanked, for structural checks."""
    out = []
    n = len(src)
    i = 0
    brace = 0
    tpl_stack = []
    prev = ''

    def scan_tpl(j):
        while j < n:
            ch = src[j]
            if ch == '\\':
                j += 2
                continue
            if ch == '`':
                return j + 1, False
            if ch == '$' and j + 1 < n and src[j + 1] == '{':
                return j + 2, True
            j += 1
        return n, False

    while i < n:
        c = src[i]
        if c == '/' and src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and src.startswith('/*', i):
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in '\'"':
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == '\\' else 1
            i = j + 1
            out.append('""')
            prev = '"'
            continue
        if c == '`':
            j, opened = scan_tpl(i + 1)
            if opened:
                tpl_stack.append(brace)
                brace += 1
            out.append('""')
            prev = '"'
            i = j
            continue
        if c == '}' and tpl_stack and brace - 1 == tpl_stack[-1]:
            tpl_stack.pop()
            brace -= 1
            j, opened = scan_tpl(i + 1)
            if opened:
                tpl_stack.append(brace)
                brace += 1
            out.append('""')
            prev = '"'
            i = j
            continue
        if c == '/':
            tail = ''.join(out).rstrip()[-6:]
            if prev == '' or prev in '(,=:[!&|?{};+-*%<>~^' or re.search(r'(return|typeof|case)$', tail):
                j = i + 1
                in_class = False
                while j < n:
                    ch = src[j]
                    if ch == '\\':
                        j += 2
                        continue
                    if ch == '[':
                        in_class = True
                    elif ch == ']':
                        in_class = False
                    elif ch == '/' and not in_class:
                        break
                    elif ch == '\n':
                        break
                    j += 1
                j += 1
                while j < n and src[j].isalpha():
                    j += 1
                out.append('""')
                prev = '"'
                i = j
                continue
        if c == '{':
            brace += 1
        elif c == '}':
            brace -= 1
        out.append(c)
        if not c.isspace():
            prev = c
        i += 1
    return ''.join(out)


def css_problems(css):
    """Every selector must be scoped to the wallet page; keyframes must be named mw-*."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    problems = []

    def skip_block(i):
        depth = 1
        while i < len(css) and depth:
            if css[i] == '{':
                depth += 1
            elif css[i] == '}':
                depth -= 1
            i += 1
        return i

    def parse(i, wrapped):
        buf = ''
        while i < len(css):
            ch = css[i]
            if ch == '{':
                head = buf.strip()
                buf = ''
                if head.startswith('@'):
                    kind = head.split()[0].split('(')[0]
                    if kind in ('@media', '@supports'):
                        i = parse(i + 1, True)
                    elif kind == '@keyframes' and len(head.split()) > 1 and head.split()[1].startswith('mw-'):
                        i = skip_block(i + 1)
                    else:
                        problems.append(head)
                        i = skip_block(i + 1)
                else:
                    for sel in head.split(','):
                        s = sel.strip()
                        if not s.startswith(ALLOWED_PREFIXES):
                            problems.append(s)
                    i = skip_block(i + 1)
            elif ch == '}':
                return i + 1 if wrapped else i
            else:
                buf += ch
                i += 1
        return i

    parse(0, False)
    return problems


class WalletUIModule(unittest.TestCase):
    def node(self, script, *args, stdin=None):
        if not shutil.which('node'):
            self.skipTest('node is required for browser-logic checks')
        return subprocess.run(['node', *args], input=script, text=True, capture_output=True, timeout=20)

    def test_exports_have_expected_types(self):
        self.assertIsInstance(CSS, str)
        self.assertIsInstance(HTML, str)
        self.assertIsInstance(JS, str)
        self.assertIsInstance(EN, dict)
        self.assertIn('data-view="wallet"', HTML)
        self.assertIn('id="mw-root"', HTML)
        self.assertIn('class="pagehead" data-view="wallet"', HTML)

    def test_html_ids_are_namespaced_and_unique(self):
        ids = re.findall(r'\sid="([^"]+)"', HTML)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(x.startswith('mw-') for x in ids), ids)
        self.assertNotIn('data-view="', JS, 'JS must not create data-view nodes (console applyView would toggle them)')

    def test_js_parses(self):
        result = self.node(JS, '--check')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_js_has_one_iife_and_no_top_level_declarations(self):
        code = strip_js(JS.strip())
        self.assertTrue(code.startswith('(function(){'), code[:40])
        self.assertTrue(code.endswith('})();'), code[-40:])
        depth_brace = 0
        depth_paren = 0
        leaks = []
        for m in re.finditer(r'[{}()]|\b(function|const|let|var|class)\b', code):
            tok = m.group(0)
            if tok == '{':
                depth_brace += 1
            elif tok == '}':
                depth_brace -= 1
            elif tok == '(':
                depth_paren += 1
            elif tok == ')':
                depth_paren -= 1
            elif depth_brace == 0 and depth_paren == 0:
                leaks.append(tok)
        self.assertEqual(leaks, [], 'declarations outside the IIFE')

    def test_only_loadWallet_is_exposed_globally(self):
        harness = (
            "const vm=require('vm');let src='';"
            "process.stdin.on('data',d=>src+=d);"
            "process.stdin.on('end',()=>{const names=['window','document','console','setTimeout','clearTimeout'];"
            "const ctx={window:{},document:{},console,setTimeout,clearTimeout};vm.createContext(ctx);"
            "vm.runInContext(src,ctx);"
            "process.stdout.write(JSON.stringify({window:Object.keys(ctx.window),"
            "global:Object.keys(ctx).filter(k=>!names.includes(k))}));});"
        )
        result = self.node(JS, '-e', harness)
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        exposed = json.loads(result.stdout)
        self.assertEqual(exposed['window'], ['loadWallet'])
        self.assertEqual(exposed['global'], [])

    def test_css_selectors_are_scoped_to_wallet_page(self):
        self.assertEqual(css_problems(CSS), [])

    def test_css_has_no_literal_colours(self):
        self.assertIsNone(re.search(r'#[0-9a-fA-F]{3,8}\b', CSS))
        self.assertNotIn('rgb(', CSS)
        self.assertNotIn('hsl(', CSS)
        for name in ('red', 'white', 'black', 'gray', 'grey', 'blue', 'green'):
            self.assertIsNone(re.search(r'(?<![\w-])' + name + r'(?![\w-])', CSS), name)

    def test_every_chinese_t_key_has_english(self):
        keys = set()
        for m in re.finditer(r"""T\((['"])((?:(?!\1)[^\\\n]|\\.)*)\1\)""", JS):
            keys.add(m.group(2))
        cjk = [k for k in keys if re.search(r'[一-鿿]', k)]
        self.assertTrue(cjk)
        missing = [k for k in cjk if not str(EN.get(k, '')).strip()]
        self.assertEqual(missing, [])

    def test_api_calls_use_wallet_prefix_and_post_patch_convention(self):
        self.assertEqual(JS.count('fetch('), 1, 'all requests go through api()')
        self.assertIn("'v1/wallet/'+path", JS)
        self.assertIn("'?_method=PATCH'", JS)
        literals = re.findall(r"api\('([^']*)'", JS)
        self.assertTrue(literals)
        self.assertTrue(all(not x.startswith('/') for x in literals), literals)
        self.assertGreater(len(re.findall(r"api\([^)]*'PATCH'", JS)), 0)

    def test_forbidden_patterns_absent(self):
        code = JS
        allowed = (
            "document.addEventListener('visibilitychange',()=>{if(document.hidden){readCalc();queueDraft(true)}});",
            "window.addEventListener('pagehide',pageDraft);",
        )
        for listener in allowed:
            self.assertEqual(code.count(listener), 1)
            code = code.replace(listener, '')
        self.assertNotIn('localStorage', JS)
        self.assertNotIn('location.hash', JS)
        self.assertNotIn('dataset.theme', JS)
        self.assertNotIn('documentElement', JS)
        self.assertNotIn('document.addEventListener', code)
        self.assertNotIn('window.addEventListener', code)


if __name__ == '__main__':
    unittest.main()
