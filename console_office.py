"""Bounded, read-only OOXML text extraction using the standard library."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P='{http://schemas.openxmlformats.org/package/2006/relationships}'
XML_LIMIT=2_000_000


def xml(package,name):
    try:
        with package.open(name) as stream:raw=stream.read(XML_LIMIT+1)
    except (KeyError,RuntimeError,NotImplementedError,zipfile.BadZipFile):raise ValueError('Office文件缺少有效的内容部件') from None
    if len(raw)>XML_LIMIT:raise ValueError('Office内容部件超过2MB解析限制')
    # Also reject UTF-16 declarations rather than allowing a byte-pattern bypass.
    if b'\x00' in raw or re.search(br'<!\s*(DOCTYPE|ENTITY)',raw,re.I):raise ValueError('Office XML含不支持的编码或实体声明')
    try:return ET.fromstring(raw)
    except (ET.ParseError,RecursionError):raise ValueError('Office XML内容无效') from None


def office(raw,suffix):
    try:package=zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:raise ValueError('请导入有效的DOCX或XLSX文件；旧版DOC/XLS不支持') from None
    with package:
        entries=package.infolist();names=[x.filename for x in entries]
        if len(entries)>256 or sum(x.file_size for x in entries)>8_000_000:
            raise ValueError('Office文件展开后超过8MB或256个部件限制')
        if len(names)!=len(set(names)) or any(x.flag_bits&1 for x in entries):
            raise ValueError('Office文件含重复部件或加密内容')
        if any('vbaProject' in name for name in names):raise ValueError('不支持含宏的Office文件')
        if suffix=='.docx':return word(package)
        return excel(package)


def word(package):
    root=xml(package,'word/document.xml');body=root.find(W+'body')
    if body is None:raise ValueError('Word正文不存在或格式不支持')
    if body.find('.//'+W+'altChunk') is not None:raise ValueError('Word包含外部嵌入正文，请先转换成普通正文')
    paragraphs=[]
    visible=[];pending=[body]
    while pending:
        node=pending.pop()
        if node.tag==W+'del':continue
        if node.tag==W+'p':visible.append(node)
        pending.extend(reversed(list(node)))
    for paragraph in visible:
        parts=[]
        pending=list(reversed(list(paragraph)))
        while pending:
            node=pending.pop()
            if node.tag in (W+'p',W+'del'):continue
            if node.tag==W+'t':parts.append(node.text or '')
            elif node.tag==W+'tab':parts.append('\t')
            elif node.tag in (W+'br',W+'cr'):parts.append('\n')
            pending.extend(reversed(list(node)))
        paragraphs.append(''.join(parts))
    text='\n'.join(paragraphs)
    if len(text)>XML_LIMIT:raise ValueError('Word提取文字超过2百万字符限制')
    return text,None,{'characters':len(text),'lines':len(text.splitlines()),'paragraphs':len(paragraphs),
                      'tables':len(list(body.iter(W+'tbl'))),'heading_count':0,'headings':[],
                      'notes':['仅提取正文段落和表格文字，保留制表符与换行；表格按段落展开。',
                               '不保留排版、图片、页眉页脚、脚注或批注；修订删除文字不纳入正文。']}


def excel(package):
    workbook=xml(package,'xl/workbook.xml');rels=xml(package,'xl/_rels/workbook.xml.rels')
    targets={}
    for rel in rels.findall(P+'Relationship'):
        if rel.get('TargetMode')=='External':continue
        target=rel.get('Target','')
        # Resolve package-relative targets without touching the filesystem.
        name=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        if '..' in name.split('/') or '\\' in name:raise ValueError('Excel部件路径无效')
        targets[rel.get('Id')]=name
    strings=[]
    if 'xl/sharedStrings.xml' in package.namelist():
        strings=[''.join(t.text or '' for t in item if t.tag==S+'t') if item.find(S+'r') is None
                 else ''.join(t.text or '' for run in item.findall(S+'r') for t in run.findall(S+'t'))
                 for item in xml(package,'xl/sharedStrings.xml').findall(S+'si')]
    rows=[['工作表','单元格','保存的值','公式（不计算）']];sheet_names=[];formulas=0;missing=0
    for sheet in workbook.findall(S+'sheets/'+S+'sheet'):
        name=sheet.get('name','');sheet_names.append(name)
        target=targets.get(sheet.get(R+'id'))
        if not target:raise ValueError('Excel工作表关联无效')
        root=xml(package,target)
        if root.tag!=S+'worksheet':raise ValueError('只支持普通Excel工作表，图表工作表请另行导出')
        seen=set();cells=[]
        for cell in root.findall(S+'sheetData/'+S+'row/'+S+'c'):
            address=cell.get('r','');match=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]{0,6})',address)
            if not match or address in seen:raise ValueError('Excel单元格坐标无效或重复')
            col=0
            for char in match[1]:col=col*26+ord(char)-64
            row=int(match[2])
            if col>16384 or row>1048576:raise ValueError('Excel单元格坐标超出范围')
            seen.add(address);kind=cell.get('t','n');value=cell.findtext(S+'v',default='')
            if kind=='s':
                if not value.isdecimal() or int(value)>=len(strings):raise ValueError('Excel共享文字索引无效')
                value=strings[int(value)]
            elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.findall(S+'is//'+S+'t'))
            elif kind=='b':
                if value not in ('0','1'):raise ValueError('Excel布尔值无效')
                value='TRUE' if value=='1' else 'FALSE'
            elif kind not in ('n','str','e','d'):raise ValueError('Excel单元格类型不支持')
            formula=cell.find(S+'f');formula_text=''
            if formula is not None:
                formulas+=1;missing+=cell.find(S+'v') is None or value==''
                formula_text='='+formula.text if formula.text else '[共享/数组公式引用；未展开]'
                if formula.attrib:formula_text+=' ['+' '.join(k+'='+v for k,v in sorted(formula.attrib.items()))+']'
            cells.append((row,col,[name,address,value,formula_text]))
            if len(rows)+len(cells)>50001:raise ValueError('Excel超过5万个已存单元格限制')
        rows.extend(item[2] for item in sorted(cells))
    if not sheet_names:raise ValueError('Excel没有普通工作表')
    text='\n'.join('\t'.join(row) for row in rows)
    if len(text)>XML_LIMIT:raise ValueError('Excel提取内容超过2百万字符限制')
    return text,rows,{'rows':len(rows),'columns':4,'ragged_rows':0,'empty_cells':sum(c=='' for r in rows for c in r),
                      'sheets':sheet_names,'cells':len(rows)-1,'formulas':formulas,'missing_formula_results':missing,
                      'notes':['读取全部工作表（含隐藏表），按工作表、坐标列出已存单元格；未存空白格不展开。',
                               '值按原始保存内容显示，日期可能为序号；不还原样式、合并格、图表或批注。',
                               '公式仅展示文字和保存结果，结果可能过期或缺失；不计算公式、不访问外部链接。']}
