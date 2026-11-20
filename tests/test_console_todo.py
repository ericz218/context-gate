import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from console.app import PAGE, make_server
from console_todo import Todos, parse_line, MAX_TEXT


class ParseTests(unittest.TestCase):
    def test_accepted_line_shapes(self):
        cases = {
            '- [ ] 写周报': ('写周报', False),
            '- [x] 写周报': ('写周报', True),
            '* [X] 写周报': ('写周报', True),
            '[x] 写周报': ('写周报', True),
            '- 写周报': ('写周报', False),
            '1. 写周报': ('写周报', False),
            '2) 写周报': ('写周报', False),
            '• 写周报': ('写周报', False),
            '☐ 写周报': ('写周报', False),
            '✅ 写周报': ('写周报', True),
            '~~写周报~~': ('写周报', True),
            '- [ ] ~~写周报~~': ('写周报', True),
            'x 2026-10-30 写周报': ('写周报', True),
            'x 2026-10-30 2026-10-01 写周报': ('写周报', True),
            '   写周报   的   续集 ': ('写周报 的 续集', False),
        }
        for line, want in cases.items():
            self.assertEqual(parse_line(line), want, line)

    def test_plain_words_are_not_misread(self):
        # 只有 "x" 加日期才算 todo.txt 完成；普通以 x 开头的词、负数和连字符开头的内容保持原样。
        self.assertEqual(parse_line('x 光检查预约'), ('x 光检查预约', False))
        self.assertEqual(parse_line('-5度时关水阀'), ('-5度时关水阀', False))
        self.assertEqual(parse_line('2026年报税'), ('2026年报税', False))

    def test_blank_and_marker_only_lines_are_skipped(self):
        for line in ('', '   ', '-', '- ', '- [ ]', '- [x]  ', '~~', '~~~~', '---', '***'):
            self.assertIsNone(parse_line(line), repr(line))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Todos(self.temp.name)

    def texts(self):
        return [(x['text'], x['done']) for x in self.store.list()['items']]

    def test_batch_import_keeps_order_marks_done_and_skips_duplicates(self):
        text = '- [ ] 甲\n- [x] 乙\n\n~~丙~~\n- [ ] 甲\n  丁\n- [ ] ' + 'x' * (MAX_TEXT + 1)
        result = self.store.import_text({'text': text})
        self.assertEqual(result['imported'], {'added': 4, 'done': 2, 'duplicates': 1, 'too_long': 1})
        self.assertEqual(self.texts(), [('甲', False), ('乙', True), ('丙', True), ('丁', False)])
        self.assertEqual((result['open'], result['done']), (2, 2))
        again = self.store.import_text({'text': '- [ ] 乙\n- [ ] 戊'})
        self.assertEqual(again['imported']['duplicates'], 1)
        self.assertEqual(self.texts()[-1], ('戊', False))

    def test_duplicates_ignore_case_and_extra_spaces(self):
        self.store.add({'text': 'Rotate  Token'})
        with self.assertRaises(ValueError):
            self.store.add({'text': 'rotate token'})
        self.assertEqual(self.store.import_text({'text': '- rotate TOKEN'})['imported']['added'], 0)

    def test_nothing_new_does_not_rewrite_the_file(self):
        self.store.add({'text': '甲'})
        before = self.store.file.stat().st_mtime_ns
        self.store.import_text({'text': '- [ ] 甲'})
        self.assertEqual(self.store.file.stat().st_mtime_ns, before)

    def test_strike_through_and_undo_with_done_time(self):
        a = self.store.add({'text': '甲'})['added']['id']
        b = self.store.add({'text': '乙'})['added']['id']
        result = self.store.set_done({'ids': [a, b], 'done': True})
        self.assertEqual(result['changed'], 2)
        item = next(x for x in result['items'] if x['id'] == a)
        self.assertTrue(item['done'] and item['done_at'])
        self.assertEqual(self.store.set_done({'ids': [a], 'done': True})['changed'], 0)
        undone = self.store.set_done({'ids': [a], 'done': False})
        item = next(x for x in undone['items'] if x['id'] == a)
        self.assertFalse(item['done']);self.assertIsNone(item['done_at'])
        with self.assertRaises(ValueError):
            self.store.set_done({'ids': [a], 'done': 'yes'})

    def test_edit_delete_and_clear_done(self):
        a = self.store.add({'text': '甲'})['added']['id']
        b = self.store.add({'text': '乙'})['added']['id']
        self.store.edit({'id': a, 'text': '  甲   改  '})
        self.assertEqual(self.texts()[0][0], '甲 改')
        with self.assertRaises(ValueError):
            self.store.edit({'id': a, 'text': '乙'})
        with self.assertRaises(ValueError):
            self.store.edit({'id': 'missing', 'text': '丙'})
        self.store.set_done({'ids': [b], 'done': True})
        self.assertEqual(self.store.clear_done({})['removed'], 1)
        self.assertEqual(self.texts(), [('甲 改', False)])
        self.assertEqual(self.store.remove({'ids': [a]})['removed'], 1)
        with self.assertRaises(ValueError):
            self.store.remove({'ids': [a]})

    def test_add_rejects_empty_multiline_and_overlong(self):
        for bad in ('', '   ', '甲\n乙', 'x' * (MAX_TEXT + 1), None, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.store.add({'text': bad})

    def test_export_round_trips_through_import(self):
        self.store.import_text({'text': '- [ ] 甲\n- [x] 乙\n~~丙~~'})
        markdown = self.store.export()['markdown']
        self.assertEqual(markdown, '- [ ] 甲\n- [x] 乙\n- [x] 丙\n')
        other = Todos(tempfile.mkdtemp())
        other.import_text({'text': markdown})
        self.assertEqual([(x['text'], x['done']) for x in other.list()['items']], self.texts())

    def test_data_survives_reload_and_private_file_mode(self):
        self.store.import_text({'text': '- [x] 甲'})
        self.assertEqual(self.store.file.stat().st_mode & 0o777, 0o600)
        self.assertEqual([(x['text'], x['done']) for x in Todos(self.temp.name).list()['items']], [('甲', True)])

    def test_corrupt_file_is_reported_not_overwritten(self):
        self.store.file.write_text('{broken')
        with self.assertRaises(ValueError):
            self.store.list()
        with self.assertRaises(ValueError):
            self.store.add({'text': '甲'})
        self.assertEqual(self.store.file.read_text(), '{broken')

    def test_import_limits(self):
        with self.assertRaises(ValueError):
            self.store.import_text({'text': '   '})
        with self.assertRaises(ValueError):
            self.store.import_text({'text': '甲\n' * 2001})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = make_server(0, self.temp.name, launch_schedules=False)
        threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True).start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close()))
        self.base = 'http://127.0.0.1:%d/%s' % (self.server.server_port, self.server.local_token)

    def call(self, path, body=None):
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_full_flow_over_http(self):
        self.assertEqual(self.call('/v1/todos'), (200, {'items': [], 'open': 0, 'done': 0}))
        # 超过默认 30KB 的请求体上限，验证批量导入路由单独放宽后仍能成功。
        big = ''.join('条目%d ' % i + '填' * 300 + '\n' for i in range(200))
        self.assertGreater(len(big.encode()), 100000)
        status, data = self.call('/v1/todos/import', {'text': '- [ ] 甲\n- [x] 乙\n丙\n' + big})
        self.assertEqual((status, data['imported']['added']), (200, 203))
        ids = [x['id'] for x in data['items']]
        status, data = self.call('/v1/todos/done', {'ids': ids[:1], 'done': True})
        self.assertEqual((status, data['done']), (200, 2))
        status, data = self.call('/v1/todos/edit', {'id': ids[2], 'text': '丙改'})
        self.assertEqual(status, 200)
        status, data = self.call('/v1/todos/add', {'text': '丙改'})
        self.assertEqual((status, data['error']), (400, '已有相同的待办'))
        status, data = self.call('/v1/todos/delete', {'ids': ids[:1]})
        self.assertEqual((status, data['removed']), (200, 1))
        self.assertEqual(self.call('/v1/todos/clear_done', {})[1]['removed'], 1)
        markdown = self.call('/v1/todos/export')[1]['markdown']
        self.assertTrue(markdown.startswith('- [ ] 丙改\n'))
        self.assertEqual(markdown.count('\n'), 201)
        self.assertEqual(self.call('/v1/todos/nope', {})[0], 404)

    def test_requires_local_token(self):
        request = urllib.request.Request(self.base.rsplit('/', 1)[0] + '/wrong/v1/todos')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 403)


class PageTests(unittest.TestCase):
    def test_page_has_todo_view_nav_and_strikethrough_style(self):
        self.assertIn('data-v="todo"', PAGE)
        self.assertIn('id="todo-page"', PAGE)
        self.assertEqual(PAGE.count('VIEWS.todo=["todo"];'), 1)
        self.assertLess(PAGE.index('const VIEWS={'), PAGE.index('VIEWS.todo=["todo"];'))
        self.assertIn("if(v==='todo')loadTodo();", PAGE)
        self.assertIn('text-decoration:line-through', PAGE)

    def test_mini_window_mode_opens_todo_and_hides_console_chrome(self):
        # 原生浮窗用 ?mini=todo 加载同一页面：启动后直接进待办，隐藏侧栏和顶栏。
        self.assertIn("applyView(todoMini?'todo':'overview')", PAGE)
        self.assertNotIn("applyView('overview');\n    uiWired=true;", PAGE)
        self.assertIn("get('mini')==='todo'", PAGE)
        self.assertIn('body.todo-mini #sidenav', PAGE)
        self.assertIn('messageHandlers.todoPanel', PAGE)


if __name__ == '__main__':
    unittest.main()
