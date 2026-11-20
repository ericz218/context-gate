"""English startup coverage and safe separation of UI copy from user content."""
import ast
import json
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from console.app import PAGE
from console.git_ui import JS as GIT_JS
from console.usability_ui import GUIDES, TERMS


def dictionary_source():
    return PAGE[PAGE.index("let LANG="):PAGE.index('const T=s=>')]


def t_literals(page):
    """Include both branches of T(condition ? 'a' : 'b'), not only T('a')."""
    values=set()
    for match in re.finditer(r'\bT\(',page):
        start=match.end();i=start;depth=1;quote=None;escaped=False
        while i<len(page) and depth:
            c=page[i]
            if quote:
                if escaped:escaped=False
                elif c=='\\':escaped=True
                elif c==quote:quote=None
            elif c in "'\"`":quote=c
            elif c=='(':depth+=1
            elif c==')':depth-=1
            i+=1
        for literal in re.findall(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"",page[start:i-1]):
            try:values.add(ast.literal_eval(literal))
            except (ValueError,SyntaxError):pass
    return values


class StaticLabels(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.labels=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if not self.skip:
            self.labels.extend(v for k,v in attrs if k in ('placeholder','title','aria-label') and v)
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip-=1
    def handle_data(self,value):
        if not self.skip and value.strip():self.labels.append(value.strip())


class EnglishUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('node'):raise unittest.SkipTest('Node unavailable')
        result=subprocess.run(['node'],input=dictionary_source()+'\nprocess.stdout.write(JSON.stringify(EN));',text=True,capture_output=True,check=True)
        cls.english=json.loads(result.stdout)

    def run_js(self,source):
        result=subprocess.run(['node'],input=source,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_navigation_and_help_are_available_before_static_translation(self):
        for title,purpose,concepts in GUIDES.values():
            for value in (title,purpose,*concepts):
                if re.search('[一-鿿]',value):self.assertTrue(self.english.get(value),value)
        for name,explanation in TERMS.items():
            if re.search('[一-鿿]',name):self.assertIn(name,self.english)
            self.assertIn(explanation,self.english)
            self.assertIsNone(re.search('[一-鿿]',self.english[explanation]))

    def test_static_and_dynamic_interface_copy_have_english(self):
        labels=StaticLabels();labels.feed(PAGE)
        # The language picker uses the language's own name, as English does.
        static={s for s in labels.labels if re.search('[一-鿿]',s) and s!='中文'}
        dynamic={s for s in t_literals(PAGE) if re.search('[一-鿿]',s)}
        missing=sorted(s for s in static|dynamic if not self.english.get(s))
        self.assertEqual(missing,[])

    def test_first_paint_translates_new_navigation_and_modal_chrome_only(self):
        a=PAGE.index('function applyStaticLang(){');b=PAGE.index('\napplyStaticLang();',a)
        self.run_js(r'''
const assert=require('node:assert/strict');
const sent=[],localStorage={getItem:()=> 'en'};
const window={webkit:{messageHandlers:{language:{postMessage:v=>sent.push(v)}}}};
const node=(text,excluded=false)=>({nodeValue:text,parentElement:{closest:selector=>excluded&&selector.includes('#modal-body')}});
const nav=node('共享记忆'),group=node('管理'),close=node('关闭'),userContent=node('共享记忆',true);
const texts=[nav,group,close,userContent];
const field={value:'共享记忆',attrs:{placeholder:'搜索项目','aria-label':'搜索项目'},getAttribute(k){return this.attrs[k]},setAttribute(k,v){this.attrs[k]=v}};
const document={title:'',documentElement:{},body:{},
 createTreeWalker(root,type,filter){const visible=texts.filter(n=>filter.acceptNode(n)===1);let i=0;return {nextNode(){this.currentNode=visible[i++];return !!this.currentNode}}},
 querySelectorAll(selector){return selector.includes('placeholder')||selector==='[aria-label]'?[field]:[]}};
const NodeFilter={SHOW_TEXT:4,FILTER_ACCEPT:1,FILTER_REJECT:2};
''' + dictionary_source() + "const T=s=>LANG==='en'?(EN[s]??s):s;\n" + PAGE[a:b] + r'''
applyStaticLang();
assert.equal(nav.nodeValue,'Shared memory');assert.equal(group.nodeValue,'Manage');assert.equal(close.nodeValue,'Close');
assert.equal(field.attrs.placeholder,'Search projects');assert.equal(field.attrs['aria-label'],'Search projects');
assert.equal(field.value,'共享记忆');assert.equal(userContent.nodeValue,'共享记忆');
assert.equal(document.documentElement.lang,'en');assert.equal(document.title,'Context Gate Console');assert.deepEqual(sent,['en']);
''')

    def test_native_preference_survives_a_new_backend_origin(self):
        init=PAGE[PAGE.index("let LANG="):PAGE.index('const LOCALE=')]
        self.run_js("const assert=require('node:assert/strict'),vm=require('node:vm');\n"+r'''
function language(local,shell){const context={localStorage:{getItem:()=>local},window:{__contextGateLanguage:shell}};return vm.runInNewContext(SOURCE+'\nLANG',context)}
''' .replace('SOURCE',json.dumps(init))+r'''
assert.equal(language(null,'en'),'en');assert.equal(language('zh','en'),'zh');assert.equal(language('en','zh'),'en');assert.equal(language('invalid','en'),'zh');
''')

    def test_memory_category_labels_translate_without_renaming_user_content(self):
        from console.memory_ui import JS
        function=JS[JS.index('function memoryGroupTitle('):JS.index('function memoryMatches(')]
        self.run_js("const assert=require('node:assert/strict'),localStorage={getItem:()=> 'en'};\n"+dictionary_source()+"const T=s=>LANG==='en'?(EN[s]??s):s;\n"+function+r'''
const group={id:'rules',title:'使用与协作约定'};
assert.equal(memoryGroupTitle(group),'Collaboration rules');assert.equal(group.title,'使用与协作约定');
assert.equal(memoryGroupTitle({id:'project:abc',title:'项目 · 我的项目'}),'Project · 我的项目');
assert.equal(memoryGroupTitle({id:'custom',title:'使用与协作约定'}),'使用与协作约定');
assert.equal(memoryGroupTitle({id:'rules',title:'我的自定义标题'}),'我的自定义标题');
''')

    def test_sync_empty_states_are_english_but_project_names_are_preserved(self):
        js=GIT_JS[:GIT_JS.index("$('git-repos')?.addEventListener")]
        self.run_js(r'''
const assert=require('node:assert/strict'),localStorage={getItem:()=> 'en'};
const nodes=Object.fromEntries(['git-device','git-live-state','git-summary','git-repo','git-repos','git-events'].map(id=>[id,{value:'',innerHTML:''}]));
const $=id=>nodes[id],num=v=>String(v),reconcile=(el,html)=>el.innerHTML=html;
const esc=s=>String(s).replace(/</g,'&lt;');
''' + dictionary_source()+"const T=s=>LANG==='en'?(EN[s]??s):s;\n"+js+r'''
gitData={device:'Local Mac',summary:{ok:0},data_sync:{state:'ok',at:Date.now()/1000},repos:[{name:'共享记忆',status:'paused',branch:'main',mode:'sync'},{name:'3p-x',status:'disabled',mode:'none'},{name:'x--2',status:'disabled',mode:'none'},{name:'y',status:'disabled',has_remote:false}]};
renderGit();
const html=nodes['git-repos'].innerHTML;
assert.match(html,/共享记忆/);assert.match(html,/Paused/);assert.match(html,/My projects/);
assert.match(html,/Others' projects/);assert.match(html,/Backup copies/);assert.match(html,/Not on GitHub/);
assert.match(html,/No downloads yet/);assert.match(html,/Current branch/);
assert.ok(html.indexOf('共享记忆')<html.indexOf('3p-x')&&html.indexOf('3p-x')<html.indexOf('x--2'));
assert.match(nodes['git-live-state'].innerHTML,/Multi-device/);
''')


if __name__=='__main__':unittest.main()
