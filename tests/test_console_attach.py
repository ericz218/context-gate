import base64,tempfile,unittest
from pathlib import Path
import console_attach
from group_chat import Groups

class AttachTests(unittest.TestCase):
    def test_attachment_saved_inside_group_project_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir()
            groups=Groups(Path(tmp)/'state')
            gid='g'*8+'-test'
            with groups.connect() as db:
                db.execute('INSERT INTO groups(id,name,root) VALUES(?,?,?)',(gid,'t',str(root)))
            b64=lambda raw:base64.b64encode(raw).decode()
            out=console_attach.save(groups,{'group':gid,'name':'../../图 片.png','data':b64(b'\x89PNG data')})
            path=Path(out['path'])
            self.assertTrue(path.resolve().is_relative_to(root.resolve()))
            self.assertEqual(path.read_bytes(),b'\x89PNG data')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotIn('/',out['name']);self.assertTrue(out['name'].endswith('.png'))
            for bad in [{'group':'missing','name':'a.txt','data':b64(b'x')},
                        {'group':gid,'name':'a.txt','data':'not base64!'},
                        {'group':gid,'name':'a.txt','data':''},
                        {'group':gid,'name':'...','data':b64(b'x')},
                        {'group':gid,'name':'id_rsa','data':b64(b'x')},
                        {'group':gid,'name':'big.bin','data':b64(b'x'*(console_attach.LIMIT+1))}]:
                with self.subTest(bad=bad['name'],group=bad['group']),self.assertRaises(ValueError):console_attach.save(groups,bad)
            # 附件目录被换成指向项目外的链接时拒绝写入
            outside=Path(tmp)/'outside';outside.mkdir()
            other=Path(tmp)/'project2';other.mkdir();(other/console_attach.FOLDER).symlink_to(outside)
            with groups.connect() as db:
                db.execute('INSERT INTO groups(id,name,root) VALUES(?,?,?)',('h'*8+'-test','t2',str(other)))
            with self.assertRaises(ValueError):console_attach.save(groups,{'group':'h'*8+'-test','name':'a.txt','data':b64(b'x')})
            self.assertEqual(list(outside.iterdir()),[])
            # 系统选择框：逐个校验，坏文件报错不影响好文件；取消不报错
            from unittest.mock import Mock,patch
            good=Path(tmp)/'pic.png';good.write_bytes(b'img');secret=Path(tmp)/'id_rsa';secret.write_bytes(b'k')
            run=lambda code,out='',err='':patch('console_attach.subprocess.run',return_value=Mock(returncode=code,stdout=out,stderr=err))
            with run(0,'%s\n%s\n%s\n'%(good,secret,Path(tmp)/'missing.txt')):picked=console_attach.pick(groups,{'group':gid})
            self.assertEqual([f['name'] for f in picked['files']],['pic.png']);self.assertEqual(len(picked['errors']),2)
            self.assertEqual(Path(picked['files'][0]['path']).read_bytes(),b'img')
            with run(1,err='User canceled. (-128)'):self.assertTrue(console_attach.pick(groups,{'group':gid})['cancelled'])
            with run(1,err='boom'),self.assertRaises(ValueError):console_attach.pick(groups,{'group':gid})
            with self.assertRaises(ValueError):console_attach.pick(groups,{'group':'missing'})
