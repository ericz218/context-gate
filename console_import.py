"""Local text/table import. Originals stay in private state; no inference."""
import base64
import binascii
import csv
import hashlib
import io
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from control_center import write_json,audit
from console_search import public
from console_office import office
from console_pdf import pdf

LIMIT=512000
TYPES={'.txt','.md','.csv','.tsv','.json','.docx','.xlsx','.pdf'}


def extract(raw,suffix):
    if suffix in ('.docx','.xlsx'):return office(raw,suffix)
    if suffix=='.pdf':return pdf(raw)
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:raise ValueError('请使用UTF-8编码的文字或表格文件') from None
    if '\x00' in text:raise ValueError('文件含二进制内容')
    if suffix in ('.csv','.tsv'):
        try:rows=list(csv.reader(io.StringIO(text,newline=''),delimiter='\t' if suffix=='.tsv' else ',',strict=True))
        except csv.Error:raise ValueError('表格格式无效或单个单元格过大') from None
        width=max((len(row) for row in rows),default=0)
        summary={'rows':len(rows),'columns':width,'ragged_rows':sum(len(row)!=width for row in rows),
                 'empty_cells':sum(cell=='' for row in rows for cell in row)}
        return text,rows,summary
    if suffix=='.json':
        try:value=json.loads(text)
        except (ValueError,RecursionError):raise ValueError('JSON格式无效或嵌套过深') from None
        summary={'structure':'对象' if isinstance(value,dict) else '数组' if isinstance(value,list) else '单值',
                 'items':len(value) if isinstance(value,(dict,list)) else 1}
    else:
        headings=[line.strip() for line in text.splitlines() if re.match(r'^#{1,6}\s+\S',line)]
        summary={'characters':len(text),'lines':len(text.splitlines()),'heading_count':len(headings),
                 'headings':headings[:20],'more_headings':len(headings)>20}
    return text,None,summary


class Imports:
    def __init__(self,state):
        self.folder=Path(state).resolve()/'imports';self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)

    def path(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9-]{36}',identifier):raise ValueError('文件编号无效')
        return self.folder/identifier

    def list(self):
        items=[]
        for path in self.folder.glob('*/metadata.json'):
            try:items.append(json.loads(path.read_text()))
            except (ValueError,OSError):continue
        return sorted(items,key=lambda x:x['name'])

    def add(self,body):
        name=body.get('name');encoded=body.get('data')
        if not isinstance(name,str) or not 1<=len(name)<=200 or Path(name).name!=name or '\\' in name or any(ord(c)<32 for c in name):raise ValueError('文件名无效')
        suffix=Path(name).suffix.lower()
        if suffix not in TYPES:raise ValueError('目前支持TXT、Markdown、CSV、TSV、JSON、DOCX、XLSX和PDF')
        if not isinstance(encoded,str) or len(encoded)>((LIMIT+2)//3)*4:raise ValueError('文件每份最多512KB')
        try:raw=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):raise ValueError('上传内容无效') from None
        if len(raw)>LIMIT:raise ValueError('文件每份最多512KB')
        _,_,summary=extract(raw,suffix)
        identifier=str(uuid.uuid4());folder=self.path(identifier);folder.mkdir(mode=0o700)
        file=folder/'original';fd=os.open(file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        item={'id':identifier,'name':name,'suffix':suffix,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'summary':public(summary)}
        write_json(folder/'metadata.json',item)
        audit(self.folder.parent,'import_file',{'platform':'user','id':identifier},file_id=identifier,bytes=len(raw))
        return item

    def remove(self,body):
        # 只删导入库内的记录目录（保存的副本与元数据）；副本已不在时等于只删记录。用户电脑上的源文件从不触碰。
        ids=body.get('ids') if 'ids' in body else [body.get('id')]
        if not isinstance(ids,list) or not 1<=len(ids)<=500:raise ValueError('请选择要删除的导入文件')
        removed=[];missing=[]
        for identifier in dict.fromkeys(str(x) for x in ids):
            folder=self.path(identifier)
            try:item=json.loads((folder/'metadata.json').read_text())
            except (ValueError,OSError):missing.append(identifier);continue
            shutil.rmtree(folder)
            audit(self.folder.parent,'import_delete',{'platform':'user','id':identifier},file_id=identifier,bytes=item.get('bytes',0))
            removed.append({'id':identifier,'name':item.get('name','')})
        if not removed:raise ValueError('没有找到这份导入文件')
        return {'removed':removed,'missing':missing}

    def load(self,identifier):
        folder=self.path(identifier);item=json.loads((folder/'metadata.json').read_text())
        with (folder/'original').open('rb') as stream:raw=stream.read(LIMIT+1)
        if len(raw)>LIMIT or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('导入原件已变化，请重新导入')
        text,rows,_=extract(raw,item['suffix'])
        return item,text,rows

    @staticmethod
    def page(item,text,rows,offset=0):
        if type(offset) is not int or offset<0:raise ValueError('翻页位置无效')
        value=rows if rows is not None else text;size=25 if rows is not None else 16000
        if offset>len(value):raise ValueError('翻页位置超出内容')
        return {**item,'unit':'rows' if rows is not None else 'characters','offset':offset,'total':len(value),
                'content':public(value[offset:offset+size]),'next_offset':offset+size if len(value)>offset+size else None}

    def preview(self,identifier,offset=0):
        return self.page(*self.load(identifier),offset)

    def compare(self,body):
        left=self.load(body.get('left'));right=self.load(body.get('right'))
        tables=left[2] is not None and right[2] is not None
        a,b=(left[2],right[2]) if tables else (left[1].splitlines(),right[1].splitlines())
        changed=sum(x!=y for x,y in zip_longest(a,b))
        cells=sum(sum(x!=y for x,y in zip_longest(l or [],r or [])) for l,r in zip_longest(a,b)) if tables else None
        pages={'left':self.page(*left,body.get('left_offset',0)),
               'right':self.page(*right,body.get('right_offset',0))}
        if tables:
            for side,other in [('left',b),('right',a)]:
                page=pages[side];page['changed_columns']=[];page['changed_rows']=[]
                for i,row in enumerate(page['content'],page['offset']):
                    row=(a if side=='left' else b)[i]
                    peer=other[i] if i<len(other) else None
                    page['changed_rows'].append(row!=peer)
                    page['changed_columns'].append([j for j,value in enumerate(row) if peer is None or j>=len(peer) or value!=peer[j]])
        return {**pages,
                'equal':left[0]['sha256']==right[0]['sha256'],
                'content_equal':a==b if tables else left[1]==right[1],
                'comparison_unit':'table_rows' if tables else 'text_lines',
                'changed_positions':changed,'changed_cells':cells}
