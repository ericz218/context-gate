# -*- coding: utf-8 -*-
"""Git 分类控制台测试（已合入 console/git_ui.py 与 console/app.py）。

覆盖：
- 事件分类 pull/push/commit/merge/conflict/blocked/skip/error/resolved/warning/info
- status/repo/limit 过滤参数（status 同时过滤 repos 与 events）
- 凭据 URL（含 token-only userinfo）与 Bearer 脱敏
- paused/disabled 不算 error；「不自动合并」警告、「冲突已解决」不误报
- 普通文案含『权限/密钥』不误判 error（error 判定只认错误前缀/完整短语）
- 符号链接日志文件不被带出解析
- 新 error 只通知一次；过滤视图下恢复 ok 也能清除指纹、复发再通知；通知失败不影响 API
- 页面 HTML/JS 含 data-v=git、Git 标题、ERROR 标记、/v1/git-sync 调用

通知一律由假函数代替，绝不真弹通知。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / 'console')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from console.git_ui import CSS, HTML, JS, EN  # noqa: E402
import console.app as app  # noqa: E402


def _day(offset):
    return '2026-10-%02d' % (28 + offset)


def make_home(tmp, day1=29, day2=30):
    home = Path(tmp) / 'git-home'
    (home / 'logs').mkdir(parents=True)
    (home / 'state').mkdir()
    registry = {'version': 1, 'created_at': '2026-10-28T00:00:00-04:00', 'repos': [
        {'name': 'alpha', 'status': 'ok', 'mode': 'sync', 'branch': 'main',
         'last_sync': '%sT01:00:00-04:00' % _day(day1), 'last_result': '无变化',
         'status_reason': '', 'warnings': [], 'conflict': None},
        {'name': 'beta', 'status': 'conflict', 'mode': 'sync', 'branch': 'main',
         'last_sync': '%sT02:00:00-04:00' % _day(day1),
         'last_result': '冲突未解决，自动合并已暂停（冲突分支 sync-conflict/beta/20261029-010203）',
         'status_reason': '拉取方向冲突：README.md',
         'conflict': {'kind': 'pull', 'branch': 'sync-conflict/beta/20261029-010203'}},
        {'name': 'gamma', 'status': 'blocked', 'mode': 'sync', 'branch': 'main',
         'last_sync': '%sT03:00:00-04:00' % _day(day1),
         'last_result': '阻止：gitleaks 在待提交内容里发现疑似密钥（1 处，文件：.env），已拦下不提交',
         'status_reason': 'gitleaks 在待提交内容里发现疑似密钥（1 处），已拦下不提交'},
        {'name': 'delta', 'status': 'paused', 'mode': 'sync', 'branch': 'main',
         'last_sync': '%sT04:00:00-04:00' % _day(day1), 'last_result': '已暂停',
         'status_reason': ''},
        {'name': 'epsilon', 'status': 'disabled', 'mode': 'none', 'branch': '',
         'last_sync': None, 'last_result': '', 'status_reason': '没有远程仓库'},
        {'name': 'zeta', 'status': 'ok', 'mode': 'sync', 'branch': 'main',
         'last_sync': '%sT05:00:00-04:00' % _day(day1),
         'last_result': '沙盒权限正常，密钥轮换已排期',
         'status_reason': ''},
    ]}
    (home / 'registry.json').write_text(json.dumps(registry, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
    lines = []

    def L(t, rid, repo, msg):
        lines.append('%s [%s] %s%s' % (t, rid, ('[%s] ' % repo) if repo else '', msg))

    t1 = '%sT00:00:10-04:00' % _day(day1)
    L(t1, 'a1a1a1a1a1', None, '==== 开始一轮同步（6 个仓库登记）')
    L(t1, 'a1a1a1a1a1', 'alpha', '自动提交 ab12cd34：2 个文件')
    L(t1, 'a1a1a1a1a1', 'alpha', '快进 origin/main → ef56ab78')
    L(t1, 'a1a1a1a1a1', 'alpha', '已推送 main cd90ef12')
    L(t1, 'a1a1a1a1a1', 'alpha', '结果：自动提交 ab12cd34（2 个文件）；快进 origin/main → ef56ab78；已推送 main cd90ef12（状态 ok）')
    L(t1, 'a1a1a1a1a1', 'beta', '冲突（拉取方向）origin/main：文件 README.md；冲突分支 sync-conflict/beta/20261029-010203（本机）')
    L(t1, 'a1a1a1a1a1', 'beta', '冲突 sync-conflict/beta/20261029-010203 已解决：用户在本机手动解决冲突并提交')
    L(t1, 'a1a1a1a1a1', 'gamma', '阻止：gitleaks 在待提交内容里发现疑似密钥（1 处），已拦下不提交')
    L(t1, 'a1a1a1a1a1', 'alpha', '结果：基线分支 main 有新提交，按规则不自动合并（状态 ok）')
    L(t1, 'a1a1a1a1a1', 'delta', '结果：已暂停（状态 paused）')
    L(t1, 'a1a1a1a1a1', 'epsilon', '跳过：路径不存在（外接卷未挂载？）')
    L(t1, 'a1a1a1a1a1', 'alpha', 'MemoryOS 补写出错：连接被拒绝')
    t2 = '%sT00:00:20-04:00' % _day(day2)
    L(t2, 'b2b2b2b2b2', None, '==== 本轮结束：disabled 1，paused 1，blocked 1，conflict 1，ok 1')
    L(t2, 'b2b2b2b2b2', 'alpha', '结果：无变化（状态 ok）')
    L(t2, 'b2b2b2b2b2', 'alpha', '出错：git fetch 失败(128)：fatal: couldn\'t find remote ref https://user:secret@github.com/example-user/alpha.git')
    L(t2, 'b2b2b2b2b2', 'alpha', '出错：git fetch 失败(128)：fatal: https://ghp_xxxonlytoken@github.com/example-user/alpha.git 无法访问')
    L(t2, 'b2b2b2b2b2', 'alpha', '结果：出错：git fetch 失败(128)：fatal: Authentication failed for Bearer ghp_BEARERTOKEN0123456789abcdef（状态 ok）')
    (home / 'logs' / ('git-sync-%s.log' % _day(day1))).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return home


class GitSyncClassificationTests(unittest.TestCase):

    def test_kinds_and_scrub(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp)
            events = app.parse_git_logs(str(home))
            kinds = [e['kind'] for e in events]
            for expect in ('commit', 'pull', 'push', 'conflict', 'blocked', 'skip',
                           'info', 'error', 'resolved', 'warning'):
                self.assertIn(expect, kinds, '缺少事件分类 %s: %r' % (expect, kinds))
            m = next(e for e in events if e['message'].startswith('出错：git fetch 失败') and 'github.com/example-user/alpha.git' in e['message'])
            self.assertNotIn('user:secret', m['message'])
            self.assertIn('https://[REDACTED]@github.com', m['message'])
            tok = next(e for e in events if '无法访问' in e['message'])
            self.assertNotIn('ghp_xxxonlytoken', tok['message'])
            self.assertIn('https://[REDACTED]@github.com', tok['message'])
            m2 = next(e for e in events if 'Bearer' in e['message'])
            self.assertNotIn('ghp_BEARERTOKEN0123456789abcdef', m2['message'])
            self.assertIn('Bearer [REDACTED]', m2['message'])
            for e in events:
                if e['message'].startswith('结果：无变化'):
                    self.assertEqual(e['kind'], 'skip')
            self.assertIn('conflict', [e['kind'] for e in events if '冲突（' in e['message']])
            self.assertIn('blocked', [e['kind'] for e in events if e['message'].startswith('阻止：')])

    def test_resolved_and_warning_not_errors(self):
        kind, result = app.classify_git_event('冲突 sync-conflict/beta/x 已解决：用户手动解决')
        self.assertEqual((kind, result), ('resolved', 'ok'))
        kind, result = app.classify_git_event('结果：基线分支 main 有新提交，按规则不自动合并（状态 ok）')
        self.assertEqual(kind, 'warning')
        kind, result = app.classify_git_event('MemoryOS 补写出错：连接被拒绝')
        self.assertEqual((kind, result), ('error', 'error'))
        kind, result = app.classify_git_event('冲突分支推送失败：network unreachable')
        self.assertNotEqual(kind, 'resolved')

    def test_unknown_is_info(self):
        for line in ('Some unexpected line', '==== 开始一轮同步（6 个仓库登记）'):
            kind, _result = app.classify_git_event(line)
            self.assertEqual(kind, 'info')

    def test_symlink_log_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp)
            outside = Path(tmp) / 'outside.log'
            outside.write_text('2026-10-29T00:00:00-04:00 [abc123] [alpha] 外部文件内容泄露测试行\n',
                               encoding='utf-8')
            (home / 'logs' / 'git-sync-evil.log').symlink_to(outside)
            events = app.parse_git_logs(str(home))
            self.assertFalse(any('外部文件' in e['message'] for e in events))


class GitSyncSnapshotTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = make_home(self._tmp.name)
        self._old_home = os.environ.get('GITSYNC_HOME')
        os.environ['GITSYNC_HOME'] = str(self.home)
        self._old_notify = app.git_notify_native
        self.addCleanup(self._restore)

    def _restore(self):
        app.git_notify_native = self._old_notify
        if self._old_home is None:
            os.environ.pop('GITSYNC_HOME', None)
        else:
            os.environ['GITSYNC_HOME'] = self._old_home

    def snap(self, **params):
        q = {k: [v] for k, v in params.items()}
        return app.git_sync_snapshot(self._tmp.name, q)

    def test_errors_and_paused_disabled(self):
        d = self.snap()
        by = {r['name']: r for r in d['repos']}
        self.assertTrue(by['beta']['is_error'])
        self.assertEqual(by['beta']['error_kind'], 'conflict')
        self.assertTrue(by['gamma']['is_error'])
        self.assertEqual(by['gamma']['error_kind'], 'blocked')
        self.assertFalse(by['delta']['is_error'])
        self.assertFalse(by['epsilon']['is_error'])
        self.assertFalse(by['alpha']['is_error'])
        self.assertFalse(by['zeta']['is_error'])  # 普通文案含权限/密钥不误报
        self.assertEqual(d['summary']['total'], 6)
        self.assertEqual(d['summary']['error'], 2)
        self.assertEqual(d['summary']['stopped'], 2)

    def test_error_judge_seeded_from_warning(self):
        self.assertFalse(app.git_error_judge('ok', '基线分支 main 有新提交，按规则不自动合并', '')[0])
        self.assertFalse(app.git_error_judge('ok', '已跳过：远程仓库权限设置为只读', '')[0])
        self.assertTrue(app.git_error_judge('ok', '出错：git fetch 失败(128)', '')[0])
        self.assertTrue(app.git_error_judge('ok', 'MemoryOS 补写出错：连接被拒绝', '')[0])
        self.assertFalse(app.git_error_judge('paused', '出错：旧错误', '')[0] is False or False)

    def test_filters(self):
        err = self.snap(status='error')
        self.assertEqual({r['name'] for r in err['repos']}, {'beta', 'gamma'})
        self.assertTrue(all(e['repo'] in {'beta', 'gamma'} or e['result'] in ('error', 'conflict', 'blocked')
                            for e in err['events']))
        self.assertTrue(any(e['kind'] == 'error' for e in err['events']))
        ok = self.snap(status='ok')
        self.assertEqual({r['name'] for r in ok['repos']}, {'alpha', 'zeta'})
        paused = self.snap(status='paused')
        self.assertEqual({r['name'] for r in paused['repos']}, {'delta'})
        disabled = self.snap(status='disabled')
        self.assertEqual({r['name'] for r in disabled['repos']}, {'epsilon'})
        one = self.snap(repo='beta')
        self.assertEqual([r['name'] for r in one['repos']], ['beta'])
        self.assertTrue(all(e['repo'] == 'beta' for e in one['events']))
        lim = self.snap(limit='1')
        self.assertEqual(len(lim['events']), 1)
        for bad in (dict(status='bogus'), dict(limit='0'), dict(limit='201'), dict(limit='x')):
            with self.assertRaises(ValueError):
                self.snap(**bad)

    def test_notify_once_then_recovery_renotify_all_view(self):
        calls = []
        app.git_notify_native = lambda repo, kind, summary: calls.append((repo, kind, summary)) or True
        d1 = self.snap()
        self.assertEqual(len(calls), 2)
        self.assertEqual({c[0] for c in calls}, {'beta', 'gamma'})
        self.assertTrue(all(n['notified'] for n in d1['notices']))
        self.snap()
        self.assertEqual(len(calls), 2)
        reg = json.loads((self.home / 'registry.json').read_text(encoding='utf-8'))
        for r in reg['repos']:
            if r['name'] == 'beta':
                r['status'] = 'ok'
                r['status_reason'] = ''
                r['last_result'] = '无变化'
        (self.home / 'registry.json').write_text(json.dumps(reg, ensure_ascii=False), encoding='utf-8')
        self.snap()
        self.assertEqual(len(calls), 2)
        for r in reg['repos']:
            if r['name'] == 'beta':
                r['status'] = 'conflict'
                r['status_reason'] = '拉取方向冲突：README.md'
        (self.home / 'registry.json').write_text(json.dumps(reg, ensure_ascii=False), encoding='utf-8')
        d3 = self.snap()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][0], 'beta')
        self.assertTrue(any(n['repo'] == 'beta' for n in d3['notices']))

    def test_notify_recovery_clearing_under_error_filter(self):
        """F2 回归：停留在 error 过滤视图时，恢复也要清除指纹，复发必须再通知。"""
        calls = []
        app.git_notify_native = lambda repo, kind, summary: calls.append(repo) or True
        self.snap(status='error')
        self.assertEqual(set(calls), {'beta', 'gamma'})
        self.assertEqual(len(calls), 2)
        reg = json.loads((self.home / 'registry.json').read_text(encoding='utf-8'))
        for r in reg['repos']:
            if r['name'] == 'beta':
                r['status'] = 'ok'
                r['status_reason'] = ''
                r['last_result'] = '无变化'
        (self.home / 'registry.json').write_text(json.dumps(reg, ensure_ascii=False), encoding='utf-8')
        self.snap(status='error')
        self.assertEqual(len(calls), 2)
        for r in reg['repos']:
            if r['name'] == 'beta':
                r['status'] = 'conflict'
                r['status_reason'] = '拉取方向冲突：README.md'
        (self.home / 'registry.json').write_text(json.dumps(reg, ensure_ascii=False), encoding='utf-8')
        self.snap(status='error')
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1], 'beta')

    def test_notify_failure_does_not_fail_api(self):
        app.git_notify_native = lambda repo, kind, summary: False
        d = self.snap()
        self.assertTrue(d['notices'])
        self.assertTrue(all(n['notified'] is False for n in d['notices']))
        self.assertTrue(all(n['error'] == 'osascript-failed' for n in d['notices']))
        calls = []
        app.git_notify_native = lambda repo, kind, summary: calls.append(repo) or True
        self.snap()
        self.assertEqual(calls, [])


class GitUiAssemblyTests(unittest.TestCase):

    def test_page_markers(self):
        self.assertIn('data-view="git"', HTML)
        self.assertIn('data-v="git"', app.PAGE)
        self.assertIn('id="git-device"', HTML)
        self.assertIn('id="page-title"', app.PAGE)
        self.assertIn('需要处理', JS)
        self.assertNotIn("T('ERROR')", JS)
        self.assertIn("r.last_push", JS)
        self.assertIn("r.last_pull", JS)
        self.assertIn("'git-sync?'", JS)
        self.assertIn('refreshView(view,options)', app.PAGE)
        self.assertIn('下载/pull', EN)
        self.assertIn('上传/push', EN)
        self.assertIn('git-bad', CSS)

    def test_injected_into_app_page(self):
        self.assertIn('data-v="git"', app.PAGE)
        self.assertIn('const VIEWS={git:["git"]', app.PAGE)
        self.assertIn("if(v==='git')loadGit();", app.PAGE)
        self.assertIn("case 'git':return loadGit();", app.PAGE)
        source = (ROOT / 'console' / 'app.py').read_text(encoding='utf-8')
        self.assertIn('/v1/git-sync', source)
        self.assertIn('def git_sync_snapshot', source)
        self.assertIn('def maybe_notify_git_errors', source)


class GitSyncActionTests(unittest.TestCase):
    """勾选同步、重试/暂停/恢复/标记已解决/打开文件夹，以及每种问题的原因+办法+按钮。"""

    def _home(self, tmp, repos):
        home = Path(tmp)
        (home / 'registry.json').write_text(json.dumps({'repos': repos}))
        return home

    def test_toggle_runs_enable_disable_and_validates(self):
        from unittest.mock import patch, Mock
        with tempfile.TemporaryDirectory() as tmp:
            self._home(tmp, [{'name': 'a', 'remote_url': 'git@github.com:x/a.git', 'path': tmp},
                             {'name': 'local', 'remote_url': '', 'path': tmp}])
            with patch.object(app, 'git_sync_home', return_value=tmp), \
                    patch.object(app.subprocess, 'run', return_value=Mock(returncode=0)) as run:
                self.assertTrue(app.git_sync_toggle({'name': 'a', 'on': True})['ok'])
                self.assertEqual(run.call_args.args[0][-3:], ['set', 'a', 'enable'])
                app.git_sync_toggle({'name': 'a', 'on': False})
                self.assertEqual(run.call_args.args[0][-3:], ['set', 'a', 'disable'])
                for bad in ({'name': 'a', 'on': 'yes'}, {'name': '--x', 'on': True},
                            {'name': 'nope', 'on': True}, {'name': 'local', 'on': True}):
                    with self.assertRaises(ValueError):
                        app.git_sync_toggle(bad)
                run.return_value = Mock(returncode=1, stderr='a 没有连接 GitHub', stdout='')
                with self.assertRaises(ValueError):
                    app.git_sync_toggle({'name': 'a', 'on': True})

    def test_retry_runs_in_background_and_commands_map(self):
        from unittest.mock import patch, Mock
        with tempfile.TemporaryDirectory() as tmp:
            self._home(tmp, [{'name': 'a', 'remote_url': 'u', 'path': tmp}])
            with patch.object(app, 'git_sync_home', return_value=tmp), \
                    patch.object(app.subprocess, 'Popen') as popen, \
                    patch.object(app.subprocess, 'run', return_value=Mock(returncode=0)) as run:
                self.assertTrue(app.git_sync_retry({'name': 'a'})['ok'])
                self.assertEqual(popen.call_args.args[0][-3:], ['run', '--only', 'a'])
                self.assertTrue(popen.call_args.kwargs.get('start_new_session'))
                for act in ('pause', 'resume', 'resolve'):
                    app.git_sync_command({'name': 'a'}, act)
                    self.assertEqual(run.call_args.args[0][-2:], [act, 'a'])
                with self.assertRaises(ValueError):
                    app.git_sync_command({'name': 'a'}, 'rm')
                app.git_sync_reveal({'name': 'a'})
                self.assertEqual(run.call_args.args[0][:2], ['open', '-R'])
                self.assertEqual(run.call_args.args[0][2], os.path.realpath(tmp))
                with self.assertRaises(ValueError):
                    app.git_sync_retry({'name': 'other'})

    def test_reveal_rejects_missing_path(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            self._home(tmp, [{'name': 'a', 'remote_url': 'u', 'path': tmp + '/gone'}])
            with patch.object(app, 'git_sync_home', return_value=tmp):
                with self.assertRaises(ValueError):
                    app.git_sync_reveal({'name': 'a'})

    def test_diagnose_known_causes(self):
        base = {'name': 'r', 'remote_url': 'u', 'status': 'blocked', 'mode': 'sync'}
        cases = {
            'secret': 'gitleaks 在待提交内容里发现疑似密钥（1 处，文件：.env），已拦下不提交',
            'bigfile': '文件超过 90MB 未提交：big.bin',
            'auth': '出错：remote: Permission denied; Authentication failed',
            'network': '出错：Could not resolve host: github.com',
            'missing': '路径不存在（外接卷未挂载？）',
            'fda': 'macOS 权限：同步器无权读取该目录（需给 GitSync.app 完全磁盘访问权限，见 README）',
            'detached': '当前不在任何分支上（分离 HEAD），本轮只拉取不提交',
            'busy': '仓库正被其他操作占用（index.lock），本轮跳过',
        }
        for cause, text in cases.items():
            h = app.git_diagnose(dict(base, status_reason=text))
            self.assertEqual(h['cause'], cause, text)
            self.assertTrue(h['reason'] and h['fix'] and 'pause' in h['actions'])
            self.assertIn(h['reason'], EN)
            for step in h['fix']:
                self.assertIn(step, EN)
        self.assertIn('locate', app.git_diagnose(dict(base, status_reason=cases['missing']))['actions'])
        c = app.git_diagnose({'name': 'r', 'remote_url': 'u', 'status': 'conflict',
                              'conflict': {'branch': 'sync-conflict/r/1'}})
        self.assertEqual((c['cause'], c['detail']), ('conflict', 'sync-conflict/r/1'))
        self.assertIn('resolve', c['actions'])
        self.assertEqual(app.git_diagnose({'name': 'r', 'remote_url': '', 'status': 'disabled'})['cause'], 'no_remote')
        self.assertIsNone(app.git_diagnose({'name': 'r', 'remote_url': 'u', 'status': 'ok', 'last_result': '无变化'}))
        self.assertIsNone(app.git_diagnose({'name': 'r', 'remote_url': 'u', 'status': 'disabled'}))

    def test_snapshot_lists_every_repo_with_help_and_branch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            home = make_home(tmp)
            with patch.object(app, 'git_sync_home', return_value=str(home)):
                d = app.git_sync_snapshot(tmp, {}, notify=False)
            names = {r['name'] for r in d['repos']}
            self.assertIn('epsilon', names)  # disabled 也要列出
            by = {r['name']: r for r in d['repos']}
            self.assertEqual(by['beta']['help']['cause'], 'conflict')
            self.assertEqual(by['gamma']['help']['cause'], 'secret')
            self.assertFalse(by['epsilon']['has_remote'])
            self.assertEqual(by['alpha']['branch'], 'main')

    def test_ui_has_toggle_actions_and_all_filter_default(self):
        self.assertNotIn('id="git-status"', HTML)
        self.assertIn('id="git-repo"', HTML)
        for needle in ("git-sync/toggle", "data-git-toggle", "data-git-act", "'git-sync/'+a.dataset.gitAct",
                       '未开启：只取回 GitHub 上的版本信息，不改本机文件', '没连接 GitHub', "T('原因')", "T('怎么办')",
                       '标记已解决', '打开文件夹', '重试', '当前分支'):
            self.assertIn(needle, JS)
        for needle in ("'需要处理'", "'我的项目'", "'别人的项目（只下载）'", "'备份副本'", "'没连 GitHub'",
                       "role=\"switch\"", "'自动同步 开'", "'已同步'", "'详细信息'"):
            self.assertIn(needle, JS)
        src = Path(app.__file__).read_text()
        for route in ('toggle', 'retry', 'pause', 'resume', 'resolve', 'reveal'):
            self.assertIn("'/v1/git-sync/%s'" % route, src)


if __name__ == '__main__':
    unittest.main()
