import base64
import json
import io
import zipfile
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from console_import import Imports,LIMIT,extract


def package(parts):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)
    return stream.getvalue()


def workbook(sheet):
    return package({'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="r1"/><sheet name="Hidden" state="hidden" sheetId="2" r:id="r2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="/xl/worksheets/sheet2.xml"/></Relationships>',
        'xl/sharedStrings.xml':'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><r><t>Rich</t></r><r><t> text</t></r></si></sst>',
        'xl/worksheets/sheet1.xml':sheet,
        'xl/worksheets/sheet2.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="31"><c r="C31" t="inlineStr"><is><t>&lt;script&gt;literal&lt;/script&gt;</t></is></c></row></sheetData></worksheet>'})


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Imports(self.temp.name)

    def add(self,name,text):
        return self.store.add({'name':name,'data':base64.b64encode(text.encode()).decode()})

    def add_raw(self,name,raw):
        return self.store.add({'name':name,'data':base64.b64encode(raw).decode()})

    def test_word_body_table_tabs_breaks_and_original_preserved(self):
        raw=package({'word/document.xml':'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t><w:tab/><w:t>world</w:t><w:br/><w:t>next</w:t></w:r><w:del><w:r><w:t>deleted</w:t></w:r></w:del></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>', 'word/header1.xml':'ignored'})
        item=self.add_raw('note.docx',raw);page=self.store.preview(item['id'])
        self.assertEqual('Hello\tworld\nnext\ncell',page['content'])
        self.assertEqual(1,item['summary']['tables']);self.assertEqual(2,item['summary']['paragraphs'])
        self.assertTrue(item['summary']['notes']);self.assertEqual(raw,(self.store.path(item['id'])/'original').read_bytes())

    def test_excel_all_sheets_sparse_coordinates_formula_cache_and_pagination(self):
        sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="b"><v>0</v></c><c r="D1"><f>1+1</f><v>2</v></c><c r="E1"><f t="shared" si="0"/></c></row>'+''.join('<row r="%s"><c r="A%s"><v>%s</v></c></row>'%(i,i,i) for i in range(2,32))+'</sheetData></worksheet>'
        raw=workbook(sheet);item=self.add_raw('book.xlsx',raw);first=self.store.preview(item['id']);last=self.store.preview(item['id'],25)
        self.assertEqual(['Data','Hidden'],item['summary']['sheets']);self.assertEqual(2,item['summary']['formulas'])
        self.assertEqual(1,item['summary']['missing_formula_results'])
        self.assertEqual(['Data','A1','Rich text',''],first['content'][1])
        self.assertEqual('FALSE',first['content'][2][2]);self.assertEqual(['2','=1+1'],first['content'][3][2:])
        self.assertEqual(['Hidden','C31','<script>literal</script>',''],last['content'][-1])
        self.assertEqual(item['summary']['rows'],len(first['content'])+len(last['content']))
        peer=self.add_raw('other.xlsx',workbook(sheet.replace('<v>2</v>','<v>3</v>',1)))
        result=self.store.compare({'left':item['id'],'right':peer['id']})
        self.assertEqual(1,result['changed_cells']);self.assertEqual([2],result['left']['changed_columns'][3])

    def test_office_rejects_entities_zip_expansion_missing_parts_and_invalid_indices(self):
        cases=[('a.docx',b'not a zip'),('a.docx',package({'word/document.xml':'<!DOCTYPE x [<!ENTITY a "x">]><x/>'})),
               ('a.docx',package({'word/document.xml':'x'*2_000_001})),('a.xlsx',package({'bomb':'x'*8_000_001})),
               ('a.docx',package({'word/document.xml':'<x/>','word/vbaProject.bin':'macro'})),
               ('a.xlsx',workbook('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>99</v></c></row></sheetData></worksheet>'))]
        for name,raw in cases:
            with self.subTest(name=name),self.assertRaises(ValueError):self.add_raw(name,raw)
        self.assertEqual([],self.store.list())

    def test_csv_quoted_newline_ragged_rows_and_complete_pagination(self):
        text='name,value\n"line\none",2\nshort\n'+''.join('a,\n' for _ in range(30))
        item=self.add('data.csv',text);s=item['summary']
        self.assertEqual(33,s['rows']);self.assertEqual(1,s['ragged_rows']);self.assertEqual(30,s['empty_cells'])
        first=self.store.preview(item['id']);second=self.store.preview(item['id'],first['next_offset'])
        self.assertEqual('line\none',first['content'][1][0]);self.assertEqual(33,len(first['content'])+len(second['content']))
        self.assertIsNone(second['next_offset'])
        self.assertEqual(text.encode(),(self.store.path(item['id'])/'original').read_bytes())
        self.assertEqual(0o600,(self.store.path(item['id'])/'original').stat().st_mode&0o777)

    def test_remove_batch_deletes_only_library_records(self):
        keep=self.add('keep.txt','keep');a=self.add('a.txt','a');b=self.add('b.txt','b');c=self.add('c.txt','c')
        source=Path(self.temp.name)/'a.txt';source.write_text('a')
        (self.store.path(b['id'])/'original').unlink()
        result=self.store.remove({'ids':[a['id'],b['id'],a['id'],'0'*36]})
        self.assertEqual([a['id'],b['id']],[x['id'] for x in result['removed']]);self.assertEqual(['0'*36],result['missing'])
        self.assertEqual({'removed':[{'id':c['id'],'name':'c.txt'}],'missing':[]},self.store.remove({'id':c['id']}))
        self.assertEqual([keep],self.store.list());self.assertEqual('a',source.read_text())
        for bad in [{'id':a['id']},{'ids':['../x']},{'ids':[]},{'ids':'x'},{'id':None}]:
            with self.assertRaises(ValueError):self.store.remove(bad)
        self.assertEqual('keep',self.store.preview(keep['id'])['content'])

    def test_text_json_bom_and_tamper(self):
        item=self.add('note.md','\ufeff# Title\n<script>data</script>\n'+'x'*17000)
        preview=self.store.preview(item['id']);self.assertEqual(['# Title'],preview['summary']['headings'])
        self.assertEqual(16000,preview['next_offset'])
        self.assertEqual(item,Imports(self.temp.name).list()[0])
        (self.store.path(item['id'])/'original').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'变化'):self.store.preview(item['id'])
        data=self.add('data.json','{"a":[1,2],"b":true}')
        self.assertEqual({'structure':'对象','items':2},data['summary'])

    def test_compare_all_rows_with_independent_pages_and_format_difference(self):
        left=self.add('left.csv','name,value\n'+''.join('x,1\n' for _ in range(30)))
        right=self.add('right.tsv','name\tvalue\n'+''.join('x\t1\n' for _ in range(29))+'x\t2\n')
        body={'left':left['id'],'right':right['id'],'right_offset':25}
        result=self.store.compare(body)
        self.assertFalse(result['equal']);self.assertEqual(1,result['changed_positions']);self.assertEqual(1,result['changed_cells'])
        self.assertEqual(0,result['left']['offset']);self.assertEqual(25,result['right']['offset'])
        self.assertEqual([1],result['right']['changed_columns'][5])
        equivalent=self.add('same.tsv','name\tvalue\n'+''.join('x\t1\n' for _ in range(30)))
        result=self.store.compare({'left':left['id'],'right':equivalent['id']})
        self.assertFalse(result['equal']);self.assertTrue(result['content_equal']);self.assertEqual(0,result['changed_cells'])
        redacted=self.add('redacted.csv','token=abc123,value\n')
        with patch('console_import.public',return_value=[['masked','value']]):
            same=self.store.compare({'left':redacted['id'],'right':redacted['id']})
        self.assertEqual([[]],same['left']['changed_columns']);self.assertEqual([False],same['left']['changed_rows'])
        (self.store.path(right['id'])/'original').write_text('tamper')
        with self.assertRaisesRegex(ValueError,'变化'):self.store.compare(body)

    def test_compare_text_lines_and_invalid_offsets(self):
        a=self.add('a.txt','one\ntwo\n');b=self.add('b.txt','one\nchanged\nnew\n')
        result=self.store.compare({'left':a['id'],'right':b['id']})
        self.assertEqual(2,result['changed_positions']);self.assertIsNone(result['changed_cells'])
        self.assertEqual('text_lines',result['comparison_unit'])
        with self.assertRaises(ValueError):self.store.compare({'left':a['id'],'right':b['id'],'left_offset':999})
        with self.assertRaises(ValueError):self.store.compare({'left':'../file','right':b['id']})

    def test_reject_unsupported_traversal_oversize_and_invalid_content(self):
        for name in ('../note.txt','bad\\note.txt','sheet.xlsx','.env','nul\x00.txt'):
            with self.assertRaises(ValueError):self.add(name,'text')
        with self.assertRaises(ValueError):self.add('big.txt','x'*(LIMIT+1))
        for name,data in [('bad.txt','%%%'),('nul.txt',base64.b64encode(b'\x00').decode()),('bad.json',base64.b64encode(b'{').decode())]:
            with self.assertRaises(ValueError):self.store.add({'name':name,'data':data})
        self.assertEqual([],self.store.list())
        with self.assertRaises(ValueError):self.store.preview('../file')


if __name__=='__main__':unittest.main()
