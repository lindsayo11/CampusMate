"""Read bounded OLE documents without opening Office or trusting cached formula values."""
import io
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from .parsers import MAX_TEXT, ParseError


def compound(data):
    import olefile
    if not olefile.isOleFile(io.BytesIO(data)):
        raise ParseError('旧 Office 文件不是有效的 OLE 文档')
    try:document = olefile.OleFileIO(io.BytesIO(data), raise_defects=olefile.DEFECT_INCORRECT)
    except (olefile.OleFileError,OSError) as exc:raise ParseError('旧 Office 容器结构无效，需人工核对') from exc
    names = document.listdir()
    if len(names) > 1000 or sum(document.get_size(n) for n in names) > 20*1024*1024:
        document.close()
        raise ParseError('旧 Office 容器超过限制')
    if any(re.search(r'vba|macro|objectpool|encryptedpackage', '/'.join(n), re.I) for n in names):
        document.close()
        raise ParseError('旧 Office 包含宏、嵌入对象或加密内容，需人工处理')
    return document


def word(data):
    with compound(data) as ole:
        if not ole.exists('WordDocument'):
            raise ParseError('附件不是有效的 DOC 文件')
        header = ole.openstream('WordDocument').read(32)
        if len(header) < 12 or struct.unpack_from('<H', header, 10)[0] & 0x8100:
            raise ParseError('不支持加密 DOC')
    executable = shutil.which('antiword')
    compatibility = False
    incomplete = False
    if executable:
        with tempfile.TemporaryDirectory(prefix='campusmate-doc-') as root:
            path=Path(root)/'source.doc';path.write_bytes(data)
            result=subprocess.run([executable,'-m','UTF-8.txt',str(path)],capture_output=True,timeout=20)
            # WPS and fast-saved Word files can be valid OLE documents that
            # antiword cannot read. catdoc is a static text reader too.
            fallback=shutil.which('catdoc')
            if result.returncode and fallback:
                result=subprocess.run([fallback,'-d','utf-8',str(path)],capture_output=True,timeout=20)
                compatibility=True
                incomplete=bool(result.stderr.strip())
    elif shutil.which('textutil'):
        # macOS's text reader; no Word process, script or macro is invoked.
        result=subprocess.run(['textutil','-format','doc','-convert','txt','-stdin','-stdout'],
            input=data,capture_output=True,timeout=20)
    else:
        raise ParseError('DOC 文本引擎未安装')
    if result.returncode or len(result.stdout)>MAX_TEXT*4:
        raise ParseError('DOC 文本提取失败或超过限制')
    lines=[line.strip() for line in result.stdout.decode('utf-8').replace('\x00','').splitlines() if line.strip()]
    if not lines or len(lines)>5000:raise ParseError('DOC 文本为空或超过 5000 个文本行')
    text='\n'.join(f'[文本行 {i}] {line}' for i,line in enumerate(lines,1))
    if compatibility:
        warning='；文件有快速保存或兼容性提示，提取可能不完整' if incomplete else ''
        text='[DOC 兼容提取'+warning+'，请以归档原件核对]\n'+text
    return text


def spreadsheet(data):
    import xlrd
    with compound(data) as ole:
        name = 'Workbook' if ole.exists('Workbook') else 'Book' if ole.exists('Book') else None
        if not name:raise ParseError('附件不是有效的 XLS 文件')
        stream=ole.openstream(name).read()
    # Read BIFF record boundaries, not byte substrings inside values. xlrd only
    # exposes cached formula results; identify formula cells from the real BIFF
    # records and replace them with a review marker, never the cached value.
    cursor=0;bounds=[];formula_records=[]
    while cursor+4<=len(stream):
        offset=cursor;code,length=struct.unpack_from('<HH',stream,cursor);cursor+=4
        if cursor+length>len(stream):raise ParseError('XLS BIFF 记录截断')
        if code==0x002F:raise ParseError('不支持加密 XLS')
        if code in {0x0006,0x0206,0x0406}:
            if length<6:raise ParseError('XLS 公式记录截断')
            formula_records.append((offset,*struct.unpack_from('<HH',stream,cursor)))
        if code==0x0085 and length>=6 and stream[cursor+5] in {1,6}:
            raise ParseError('XLS 含宏工作表，需人工处理')
        if code==0x0085 and length>=6 and stream[cursor+5]==0:bounds.append(struct.unpack_from('<I',stream,cursor)[0])
        cursor+=length
    book=xlrd.open_workbook(file_contents=data,on_demand=True,ragged_rows=True,logfile=io.StringIO())
    try:
        if book.nsheets>20:raise ParseError('XLS 超过 20 个工作表')
        if formula_records and len(bounds)!=book.nsheets:raise ParseError('XLS 公式无法定位到工作表，需人工核对')
        formulas=set()
        for offset,row,column in formula_records:
            candidates=[(index,start) for index,start in enumerate(bounds) if start<=offset]
            if not candidates:raise ParseError('XLS 公式缺少工作表位置')
            index=max(candidates,key=lambda pair:pair[1])[0];formulas.add((index,row,column))
        parts=[];rows=0
        for sheet_index,sheet in enumerate(book.sheets()):
            if sheet.ncols>100 or rows+sheet.nrows>5000:raise ParseError('XLS 超过 5000 行或 100 列')
            parts.append(f'[工作表：{sheet.name}]');rows+=sheet.nrows
            for index in range(sheet.nrows):
                values=[]
                for column,cell in enumerate(sheet.row(index)):
                    if (sheet_index,index,column) in formulas:value='[公式，需人工核对]'
                    elif cell.ctype==xlrd.XL_CELL_DATE:
                        value=xlrd.xldate_as_datetime(cell.value,book.datemode).isoformat()
                    elif cell.ctype==xlrd.XL_CELL_NUMBER and float(cell.value).is_integer():value=str(int(cell.value))
                    elif cell.ctype in {xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK}:value=''
                    else:value=str(cell.value)
                    values.append(value)
                line=' | '.join(values).strip(' |')
                if line:parts.append(f'[行 {index+1}] '+line)
                if sum(map(len,parts))>MAX_TEXT:raise ParseError('XLS 文本超过限制')
        return '\n'.join(parts)
    finally:book.release_resources()
