"""Local, bounded OCR with page/line boxes and confidence; no remote uploads."""
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import re
import warnings

from .parsers import ParseError


def recognize_bytes(data):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS=12_000_000
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'PNG','JPEG','WEBP'} or getattr(source,'n_frames',1)!=1:
                    raise ParseError('OCR 只接收单帧 PNG、JPEG、WEBP')
                if min(source.size)<120 or max(source.size)>16000:
                    raise ParseError('正文图片尺寸不足或超过限制')
                source.load()
                normalized=ImageOps.exif_transpose(source).convert('RGB')
                normalized.thumbnail((3000,5000))
                with tempfile.TemporaryDirectory(prefix='campusmate-image-') as root:
                    path=Path(root)/'image.png';normalized.save(path)
                    return recognize_image(path)
        except (Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
            raise ParseError('正文图片解压像素超过限制') from exc


def recognize_image(path, page=1):
    executable=shutil.which('tesseract')
    if not executable:
        raise ParseError('OCR 引擎未安装，需人工识别')
    result=subprocess.run([executable,str(path),'stdout','-l','chi_sim+eng','--psm','3','tsv'],
        capture_output=True,timeout=30,check=False,env={**os.environ,'OMP_THREAD_LIMIT':'1'})
    if result.returncode or len(result.stdout)>4*1024*1024:
        raise ParseError('OCR 失败或输出超限，需人工识别')
    lines={}
    for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')),delimiter='\t'):
        text=word.get('text','').strip()
        if not text or word.get('level')!='5':continue
        key=tuple(word[k] for k in ('block_num','par_num','line_num'))
        lines.setdefault(key,[]).append(word)
    proofs=[]
    for index,words in enumerate(lines.values(),1):
        quote=' '.join(w['text'] for w in words)
        quote=re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])','',quote)
        confidence=sum(float(w['conf']) for w in words)/len(words)
        left=min(int(w['left']) for w in words);top=min(int(w['top']) for w in words)
        right=max(int(w['left'])+int(w['width']) for w in words)
        bottom=max(int(w['top'])+int(w['height']) for w in words)
        proofs.append({'page':page,'line':index,'text':quote,'confidence':round(confidence,1),
            'box':[left,top,right-left,bottom-top]})
    if not proofs:raise ParseError('OCR 未识别到文本，需人工核对')
    return proofs


def recognize_pdf(data, pages):
    executable=shutil.which('pdftoppm')
    if not executable:raise ParseError('PDF 渲染引擎未安装，需人工 OCR')
    if len(pages)>8:raise ParseError('扫描 PDF 超过 8 页 OCR 上限，需人工分批处理')
    proofs=[]
    with tempfile.TemporaryDirectory(prefix='campusmate-ocr-') as directory:
        root=Path(directory);source=root/'source.pdf';source.write_bytes(data)
        for page in pages:
            prefix=root/f'page-{page}'
            # scale-to bounds the longest edge, including pathological PDF dimensions.
            result=subprocess.run([executable,'-f',str(page),'-l',str(page),'-singlefile',
                '-scale-to','2200','-png',str(source),str(prefix)],capture_output=True,timeout=15)
            image=prefix.with_suffix('.png')
            if result.returncode or not image.exists() or image.stat().st_size>12*1024*1024:
                raise ParseError('扫描 PDF 页面渲染失败或超限')
            proofs.extend(recognize_image(image,page))
    return proofs
