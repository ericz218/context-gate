import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from console_memory import MemoryLibrary


class MemoryExportTests(unittest.TestCase):
    def documents(self, tmp):
        out = Path(tmp)/'阅读'; out.mkdir()
        (out/'详细').mkdir(); (out/'详细/空文件夹').mkdir()
        (out/'历史生成/旧版').mkdir(parents=True)
        (out/'原始记录').mkdir()
        docs = {'目录.md':'# 全量目录\n完整目录', '大纲.md':'# 大纲\n人话内容',
                '详细/主题.md':'# 主题\n<details><summary>完整正文</summary>\n\n原文不能丢\n\n</details>',
                '历史生成/旧版/旧文档.md':'历史内容原样保留', 'catalog.json':'{"schema_version":2}',
                '原始记录/当前快照.json':json.dumps([{'value':'当前原文'},{'value':'归档原文','archived':True}],ensure_ascii=False)}
        for name, content in docs.items(): (out/name).write_text(content,encoding='utf-8')
        (out/'.DS_Store').write_bytes(b'finder metadata')
        return MemoryLibrary(out=out,root=tmp), docs

    def test_complete_on_demand_exports_and_no_recursion(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib, docs = self.documents(tmp)
            self.assertFalse((lib.out/'导出').exists())
            for kind in ('txt','md'):
                path = lib.export(kind); text = path.read_text()
                for fact in ('完整目录','人话内容','原文不能丢','历史内容原样保留','当前原文','归档原文'):
                    self.assertIn(fact,text)
                self.assertEqual(path.suffix,'.'+kind)
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
                if kind == 'txt': self.assertNotIn('<details>',text)
            for kind in ('human','raw'):
                path = lib.export(kind)
                with zipfile.ZipFile(path) as archive:
                    prefix = 'AI记忆-'+('人话版' if kind == 'human' else '原始版')+'/'
                    names = archive.namelist()
                    expected = docs if kind == 'human' else {'原始记录/当前快照.json':docs['原始记录/当前快照.json']}
                    for name, content in expected.items(): self.assertEqual(archive.read(prefix+name),content.encode())
                    self.assertFalse(any('导出/' in name or '.DS_Store' in name for name in names))
                    if kind == 'human': self.assertIn(prefix+'详细/空文件夹/',names)
                    else: self.assertEqual(set(names),{prefix+'原始记录/',prefix+'原始记录/当前快照.json'})
            self.assertEqual(len(list((lib.out/'导出').iterdir())),4)

    def test_sync_lock_rejects_export_without_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib,_ = self.documents(tmp)
            with (Path(tmp)/'humanize_sync.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(ValueError,'正在同步'): lib.export('raw')
            self.assertFalse((lib.out/'导出').exists())

    def test_invalid_kind_missing_snapshot_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib,_ = self.documents(tmp)
            with self.assertRaises(ValueError): lib.export('../bad')
            (lib.out/'详细/link.md').symlink_to(lib.out/'目录.md')
            with self.assertRaisesRegex(ValueError,'链接'): lib.export('human')
            (lib.out/'详细/link.md').unlink()
            (lib.out/'原始记录/当前快照.json').unlink()
            with self.assertRaisesRegex(ValueError,'原始快照'): lib.export('raw')
            self.assertFalse((lib.out/'导出').exists())

    def test_changed_document_is_not_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib,_ = self.documents(tmp)
            original = lib._export_files
            calls = 0
            def changed(kind):
                nonlocal calls
                calls += 1
                if calls == 2: (lib.out/'详细/主题.md').write_text('发生变化')
                return original(kind)
            with patch.object(lib,'_export_files',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'发生变化'): lib.export('human')
            self.assertFalse((lib.out/'导出').exists())


if __name__ == '__main__': unittest.main()
