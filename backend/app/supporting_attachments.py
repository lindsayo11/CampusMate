"""Archive first-party office attachments of a parsed parent; no invented opportunity rows."""
import json
import re

from bs4 import BeautifulSoup
from sqlalchemy import select

from .adapters.index_discovery import official_url
from .adapters.notice_text import document_base
from .intake import record_document_version, _persist_evidence
from .intake_models import NoticeResource, DocumentVersion
from .parsers import ParseError, extract_isolated


def office_links(content, base, config=None):
    if config and config.get('json_detail'):
        from .adapters.base import RawArtifact
        from .adapters.public_json_notice import PublicJSONNoticeAdapter
        parsed=PublicJSONNoticeAdapter(config['topic'],config['json_detail']).parse(
            RawArtifact(content,base,base,'application/json'))
        return [row['url'] for row in parsed.records[0]['attachments']
            if re.search(r'\.(?:docx?|xlsx?|pdf)(?:\?|$|\b)',row['url']+' '+row['title'],re.I)][:8]
    soup=BeautifulSoup(content,'html.parser')
    base=document_base(soup,base)
    found=[]
    for node in soup.select('a[href]'):
        label=node.get_text(' ',strip=True)
        if re.search(r'名单|公示|拟录取',label):
            continue
        url=official_url(node['href'],base)
        if url and re.search(r'\.(?:docx?|xlsx?|pdf)(?:\?|$|\b)',url+' '+label,re.I) and url not in found:
            found.append(url)
    return found[:8]


def image_links(content, base, config=None):
    """Only first-party images inside an explicit article container, never page chrome."""
    if config and config.get('json_detail'):return []
    from .adapters.notice_text import ARTICLE_SELECTORS
    soup=BeautifulSoup(content,'html.parser');base=document_base(soup,base)
    selectors=[config['article_selector']] if config and config.get('article_selector') else ARTICLE_SELECTORS
    article=next((node for selector in selectors if (node:=soup.select_one(selector)) is not None),None)
    if article is None:return []
    found=[]
    for node in article.select('img[src], img[data-src]')[:40]:
        hint=' '.join(str(node.get(k,'')) for k in ('alt','class','src','data-src'))
        if re.search(r'logo|icon|banner|qrcode|二维码|微信|分享|广告|头像',hint,re.I):continue
        dimensions=[int(v) for k in ('width','height') if re.fullmatch(r'\d{1,5}',v:=str(node.get(k,'')))]
        if dimensions and min(dimensions)<120:continue
        url=official_url(node.get('data-src') or node.get('src'),base)
        if url and re.search(r'\.(?:png|jpe?g|webp)(?:\?|$)',url,re.I) and url not in found:found.append(url)
    return found[:4]


def supporting_links(content,base,config=None):
    return office_links(content,base,config)+image_links(content,base,config)


def attachment_format(content):
    if content.startswith(b'%PDF'):return 'pdf'
    if content.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff')) or content[:4]==b'RIFF' and content[8:12]==b'WEBP':return 'image'
    import zipfile,io
    if content.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        from .legacy_office import compound
        with compound(content) as ole:
            if ole.exists('WordDocument'):return 'doc'
            if ole.exists('Workbook') or ole.exists('Book'):return 'xls'
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:names=set(z.namelist())
        if 'word/document.xml' in names:return 'docx'
        if 'xl/workbook.xml' in names:return 'xlsx_attachment'
    except zipfile.BadZipFile:pass
    raise ParseError('附件没有返回支持的 PDF、Office 或正文图片')


def ingest_office_attachment(db,source,endpoint,raw,parent_url):
    parent=db.scalar(select(NoticeResource).where(NoticeResource.endpoint_id==endpoint.id,
        NoticeResource.url==parent_url,NoticeResource.document_id.is_not(None)))
    document=db.get(DocumentVersion,parent.document_id) if parent else None
    if not document or document.deleted_at:
        raise ParseError('附件缺少已解析的官方父文档')
    if raw.content.lstrip().lower().startswith((b'<!doctype html',b'<html')):
        from .adapters.education import reject_login_page
        reject_login_page(BeautifulSoup(raw.content,'html.parser'))
        raise ParseError('附件下载返回网页，需要核对官方文件链接')
    format=attachment_format(raw.content)
    parsed=extract_isolated(raw.content,format)
    proofs=[]
    sheet=''
    for line in parsed.text.splitlines():
        if line.startswith('[工作表：'):
            sheet=line[len('[工作表：'):-1]
        match=re.match(r'\[(段落|行|文本行) (\d+)\] (.*)',line)
        if match:
            location=(f'part=word/document.xml;paragraph={match[2]}' if format=='docx' else
                      f'stream=WordDocument;text-line={match[2]}' if format=='doc' else f'sheet={sheet};row={match[2]}')
            proofs.append({'record_key':'attachment','field':'body','evidence_location':location,
                'quote_or_normalized_fact':match[3],'extractor':'parser','evidence_type':'office'})
    if format=='pdf':
        pages=re.split(r'\[第 (\d+) 页\]\n',parsed.text)
        proofs.extend({'record_key':'attachment','field':'body','evidence_location':f'page={pages[i]}',
            'quote_or_normalized_fact':pages[i+1],'extractor':'parser','evidence_type':'pdf'} for i in range(1,len(pages),2))
    proofs.extend({'record_key':'attachment','field':'body',
        'evidence_location':f"page={p['page']};line={p['line']};box={','.join(map(str,p['box']))};confidence={p['confidence']}",
        'quote_or_normalized_fact':p['text'],'extractor':'ocr','evidence_type':'ocr'} for p in parsed.evidence)
    if not proofs:raise ParseError('附件没有可定位的文本或 OCR 证据')
    payload={'kind':'supporting_attachment','parent_document_id':document.id,'parent_url':parent_url,
             'format':format,'body':parsed.text}
    doc,changed=record_document_version(db,endpoint,raw,json.dumps(payload,ensure_ascii=False))
    if changed:_persist_evidence(db,source,doc,proofs)
    # No DevelopmentItem/Position/eligibility is created from an attachment alone.
    return {'changed':changed,'document_version_id':doc.id}
