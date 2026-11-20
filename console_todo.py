"""Local to-do list. Text typed or pasted by the user only; no inference, no model calls."""
import json
from pathlib import Path
import re
import threading
import time
import uuid

from control_center import write_json,audit

MAX_TEXT=500
MAX_ITEMS=5000
MAX_IMPORT_CHARS=200000
MAX_IMPORT_LINES=2000
MAX_IDS=500

BULLET=re.compile(r'^(?:[-*+•·]|\d{1,3}[.)、])(?:\s+|$)')
BOX=re.compile(r'^(?:\[([ xX✓✔])\]|([☐□])|([☑✅✓✔]))\s*')
STRUCK=re.compile(r'^~~(.+)~~$')
# todo.txt marks completion with a lowercase "x" plus a date; a bare "x " could just be the word.
TODO_TXT_DONE=re.compile(r'^x\s+\d{4}-\d{2}-\d{2}\s+(?:\d{4}-\d{2}-\d{2}\s+)?')


def parse_line(line):
    """One pasted line -> (text, done), or None for a blank or marker-only line. Accepts Markdown task lists,
    numbered/bulleted lists, todo.txt completions and ~~struck~~ text."""
    s=line.strip()
    if not s:return None
    s=BULLET.sub('',s,count=1);done=False
    box=BOX.match(s)
    if box:
        done=box.group(1) not in (None,' ') or box.group(3) is not None;s=s[box.end():]
    else:
        txt=TODO_TXT_DONE.match(s)
        if txt:done=True;s=s[txt.end():]
    struck=STRUCK.match(s.strip())
    if struck:done=True;s=struck.group(1)
    s=' '.join(s.split())
    # Lines with no letter/digit/CJK at all (separators like "---", stray markers) are not tasks.
    return (s,done) if re.search(r'\w',s) else None


def clean(text):
    if not isinstance(text,str):raise ValueError('待办内容无效')
    text=' '.join(text.split())
    if not text:raise ValueError('待办内容不能为空')
    if len(text)>MAX_TEXT:raise ValueError('单条待办最多%d字'%MAX_TEXT)
    return text


def key(text):
    return text.casefold()


class Todos:
    def __init__(self,state):
        self.state=Path(state).resolve();self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.file=self.state/'todos.json';self.lock=threading.Lock()

    def load(self):
        try:data=json.loads(self.file.read_text())
        except FileNotFoundError:return []
        except (ValueError,OSError):raise ValueError('待办数据文件无法读取，请检查 todos.json') from None
        items=data.get('items') if isinstance(data,dict) else None
        if not isinstance(items,list):raise ValueError('待办数据文件格式无效，请检查 todos.json')
        return items

    def save(self,items):
        write_json(self.file,{'version':1,'items':items})

    @staticmethod
    def make(text,done):
        now=time.time()
        return {'id':uuid.uuid4().hex[:12],'text':text,'done':done,'created':now,'done_at':now if done else None}

    @staticmethod
    def ids(body):
        ids=body.get('ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=MAX_IDS or not all(isinstance(x,str) for x in ids):raise ValueError('请选择待办')
        return set(ids)

    def snapshot(self,items=None):
        items=self.load() if items is None else items
        done=sum(bool(x['done']) for x in items)
        return {'items':items,'open':len(items)-done,'done':done}

    def list(self):
        with self.lock:return self.snapshot()

    def add(self,body):
        text=body.get('text')
        if isinstance(text,str) and ('\n' in text.strip() or '\r' in text.strip()):raise ValueError('一次添加一条；多条请用批量导入')
        text=clean(text)
        with self.lock:
            items=self.load()
            if len(items)>=MAX_ITEMS:raise ValueError('待办已满（最多%d条），请先清除已完成'%MAX_ITEMS)
            if key(text) in {key(x['text']) for x in items}:raise ValueError('已有相同的待办')
            item=self.make(text,False);items.append(item);self.save(items)
            audit(self.state,'todo_add',{'platform':'user'},id=item['id'])
        return {'added':item,**self.snapshot(items)}

    def import_text(self,body):
        text=body.get('text')
        if not isinstance(text,str) or not text.strip():raise ValueError('请粘贴要导入的内容')
        if len(text)>MAX_IMPORT_CHARS:raise ValueError('一次最多导入%d字'%MAX_IMPORT_CHARS)
        lines=text.splitlines()
        if len(lines)>MAX_IMPORT_LINES:raise ValueError('一次最多导入%d行'%MAX_IMPORT_LINES)
        with self.lock:
            items=self.load();seen={key(x['text']) for x in items}
            added=done=duplicates=too_long=0
            for line in lines:
                parsed=parse_line(line)
                if parsed is None:continue
                value,finished=parsed
                if len(value)>MAX_TEXT:too_long+=1;continue
                if key(value) in seen:duplicates+=1;continue
                if len(items)>=MAX_ITEMS:raise ValueError('待办已满（最多%d条），本次没有导入，请先清除已完成'%MAX_ITEMS)
                seen.add(key(value));items.append(self.make(value,finished));added+=1;done+=finished
            if added:
                self.save(items)
                audit(self.state,'todo_import',{'platform':'user'},added=added,done=done)
        return {'imported':{'added':added,'done':done,'duplicates':duplicates,'too_long':too_long},**self.snapshot(items)}

    def set_done(self,body):
        ids=self.ids(body);done=body.get('done')
        if type(done) is not bool:raise ValueError('完成状态无效')
        with self.lock:
            items=self.load();changed=0;now=time.time()
            for item in items:
                if item['id'] in ids and bool(item['done'])!=done:
                    item['done']=done;item['done_at']=now if done else None;changed+=1
            if changed:self.save(items);audit(self.state,'todo_done' if done else 'todo_undone',{'platform':'user'},count=changed)
        return {'changed':changed,**self.snapshot(items)}

    def edit(self,body):
        identifier=body.get('id');text=clean(body.get('text'))
        with self.lock:
            items=self.load()
            target=next((x for x in items if x['id']==identifier),None)
            if target is None:raise ValueError('没有找到这条待办')
            if any(x is not target and key(x['text'])==key(text) for x in items):raise ValueError('已有相同的待办')
            if target['text']!=text:target['text']=text;self.save(items)
        return self.snapshot(items)

    def remove(self,body):
        ids=self.ids(body)
        with self.lock:
            items=self.load();kept=[x for x in items if x['id'] not in ids];removed=len(items)-len(kept)
            if not removed:raise ValueError('没有找到这条待办')
            self.save(kept);audit(self.state,'todo_delete',{'platform':'user'},count=removed)
        return {'removed':removed,**self.snapshot(kept)}

    def clear_done(self,body):
        with self.lock:
            items=self.load();kept=[x for x in items if not x['done']];removed=len(items)-len(kept)
            if removed:self.save(kept);audit(self.state,'todo_clear_done',{'platform':'user'},count=removed)
        return {'removed':removed,**self.snapshot(kept)}

    def export(self):
        with self.lock:items=self.load()
        return {'markdown':''.join('- [%s] %s\n'%('x' if x['done'] else ' ',x['text']) for x in items),'count':len(items)}
