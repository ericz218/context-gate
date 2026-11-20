"""Optional PDF reader, isolated from the console with time/output limits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

LIMIT=2_000_000


def pdf(raw):
    if not raw.startswith(b'%PDF-'):raise ValueError('PDF文件头无效')
    python=Path(sys.executable) if importlib.util.find_spec('pypdf') else Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
    if not python.is_file():raise ValueError('本机缺少PDF解析运行环境；原件尚未导入')
    with tempfile.TemporaryFile() as output:
        try:
            result=subprocess.run([str(python),'-I',str(Path(__file__).resolve()),'--read'],input=raw,
                                  stdout=output,stderr=subprocess.DEVNULL,timeout=12,
                                  env={'PATH':os.defpath,'PYTHONNOUSERSITE':'1'})
        except (OSError,subprocess.TimeoutExpired):raise ValueError('PDF解析不可用或超过12秒限制') from None
        output.seek(0);data=output.read(4*LIMIT+1)
    if len(data)>4*LIMIT:raise ValueError('PDF提取内容超过限制')
    if result.returncode:raise ValueError('PDF无法读取、已加密或超过解析限制；未保存原件')
    try:value=json.loads(data)
    except (ValueError,UnicodeError):raise ValueError('PDF解析结果无效') from None
    return value['text'],None,value['summary']


def worker():
    import io
    import resource
    from pypdf import PdfReader
    resource.setrlimit(resource.RLIMIT_CPU,(8,8))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*LIMIT,4*LIMIT))
    try:resource.setrlimit(resource.RLIMIT_AS,(1_000_000_000,1_000_000_000))
    except (ValueError,OSError):pass  # Not supported on every macOS runtime.
    raw=sys.stdin.buffer.read(512001)
    if len(raw)>512000:raise ValueError('oversize')
    reader=PdfReader(io.BytesIO(raw),strict=True)
    if reader.is_encrypted or not 1<=len(reader.pages)<=200:raise ValueError('encrypted/oversize')
    pages=[];empty=[];size=0
    for i,page in enumerate(reader.pages,1):
        contents=page.get_contents()
        if contents is not None and len(contents.get_data())>8_000_000:raise ValueError('expanded page oversize')
        text=page.extract_text() or ''
        if not text.strip():empty.append(i)
        text='【第%s页】\n%s'%(i,text);size+=len(text.encode('utf-8'))
        if size>LIMIT:raise ValueError('extracted text oversize')
        pages.append(text)
    text='\n\n'.join(pages)
    summary={'characters':len(text),'lines':len(text.splitlines()),'pages':len(pages),'empty_pages':empty,
             'notes':['仅提取PDF文字，保留页码；不还原版面、图片、表格结构、表单或批注。',
                      '不执行PDF脚本或访问链接；尚未提供OCR。文字提取顺序可能不同于视觉阅读顺序。']}
    if empty:summary['notes'].append('以下页没有可提取文字，可能是扫描件或空白页：'+','.join(map(str,empty)))
    sys.stdout.write(json.dumps({'text':text,'summary':summary},ensure_ascii=False))


if __name__=='__main__':
    try:worker()
    except Exception:sys.exit(1)
