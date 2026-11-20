import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sync_engine',ROOT/'tools/git_sync_engine.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


class EngineOptionTests(unittest.TestCase):
    def test_follow_work_branch_syncs_commits_without_staging_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            subprocess.run(['git','init','-q','-b','art/current',str(p)],check=True)
            subprocess.run(['git','-C',str(p),'config','user.name','Test'],check=True)
            subprocess.run(['git','-C',str(p),'config','user.email','test@example.invalid'],check=True)
            (p/'work.txt').write_text('saved')
            subprocess.run(['git','-C',str(p),'add','.'],check=True)
            subprocess.run(['git','-C',str(p),'commit','-qm','baseline'],check=True)
            (p/'work.txt').write_text('unfinished change')
            entry=engine.new_entry(str(p),'sample-project',branch='old',status='ok',mode='sync',push=True,follow_branch=True,auto_commit=False)
            sync=engine.RepoSync(entry,None)
            with patch.object(sync,'fetch') as fetch,patch.object(sync,'integrate_upstream',return_value=True),patch.object(sync,'push_branch') as push,patch.object(sync,'autocommit') as commit,patch.object(sync,'log'):
                sync.run()
                fetch.assert_called_once();push.assert_called_once();commit.assert_not_called()
            self.assertEqual(entry['branch'],'art/current')
            self.assertEqual(entry['pending_changes'],1)
            self.assertEqual((p/'work.txt').read_text(),'unfinished change')
            self.assertEqual(subprocess.run(['git','-C',str(p),'diff','--cached','--name-only'],capture_output=True,text=True,check=True).stdout,'')

    def test_relocation_refuses_another_github_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);home=root/'sync';home.mkdir();repo=root/'repo';repo.mkdir()
            subprocess.run(['git','init','-q',str(repo)],check=True)
            subprocess.run(['git','-C',str(repo),'remote','add','origin','https://github.com/example-user/another-project.git'],check=True)
            registry={'repos':[{'name':'sample-project','path':'/previous','remote_url':'https://github.com/example-user/sample-project.git','remote':'origin','status':'paused'}]}
            path=home/'registry.json';path.write_text(json.dumps(registry))
            env={**os.environ,'GITSYNC_HOME':str(home)}
            run=subprocess.run(['python3',str(ROOT/'tools/git_sync_engine.py'),'set','sample-project','path',str(repo)],env=env,capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(json.loads(path.read_text())['repos'][0]['path'],'/previous')


if __name__=='__main__':unittest.main()
