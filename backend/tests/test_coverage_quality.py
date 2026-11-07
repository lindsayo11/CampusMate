from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from app.coverage_quality import summarize, error_category
from app.notice_watch import embedded_pdfs


def test_metrics_use_application_dates_and_count_historical_content_separately():
    now=datetime(2026,10,2,tzinfo=UTC)
    monitors=[{'source_code':'A','topic':'employment','enabled':True,'index_healthy':True,
        'details_discovered':10,'details_collected':7,'freshness':'stale','region':'CN-AH',
        'error_categories':{'network':2}}]
    sources=[{'source_code':'A','items':7,'notices':4,'dated_items':3,'dated_notices':2,
        'availability':{'open':1,'expired':1,'needs_confirmation':2,'reference':3}},
        {'source_code':'B','items':5,'notices':0,'dated_notices':0,'availability':{'reference':5}}]
    result=summarize(monitors,sources,SimpleNamespace(observed_at=now-timedelta(minutes=5),state='ok'),now)
    assert result['detail_success_rate']==70 and result['deadline_completeness']==50
    assert result['unmonitored_items']==5 and result['stale_sources']==1
    assert result['worker']['status']=='stale' and result['error_categories']=={'network':2}
    assert sum(t['public_items'] for t in result['topics'])==7
    assert result['availability']['reference']==8
    empty=summarize([],[],now=now)
    assert empty['deadline_completeness'] is None and empty['detail_success_rate'] is None


def test_error_categories_and_official_pdf_viewer_file():
    assert error_category('来源 robots.txt 不允许采集')=='access_denied'
    assert error_category('无法确认官方 robots 规则（网络异常）')=='network'
    assert error_category('PDF 无可提取文本，需要人工 OCR')=='ocr_required'
    assert embedded_pdfs('<iframe src="/viewer.html?file=/notice.pdf"></iframe>',
        'https://official.example/article')==['https://official.example/notice.pdf']
    assert embedded_pdfs('<iframe src="/viewer.html?file=https://external.example/notice.pdf"></iframe>',
        'https://official.example/article')==[]
    assert embedded_pdfs('<script>var images=[];showVsbpdfIframe("/virtual_attach_file.vsb?afc=public", "100%");</script>',
        'https://official.example/article')==['https://official.example/virtual_attach_file.vsb?afc=public']
    assert embedded_pdfs('<script>showVsbpdfIframe("https://external.example/a.pdf", "100%");</script>',
        'https://official.example/article')==[]


def test_private_lists_and_staff_selection_are_not_student_notices():
    from app.adapters.notice_text import matches_topic, notice_title
    from bs4 import BeautifulSoup
    import pytest
    assert not matches_topic('2027年推免资格名单公示','postgraduate')
    assert not matches_topic('关于研究生指导教师遴选及招生资格审核的通知','postgraduate')
    with pytest.raises(ValueError):notice_title(BeautifulSoup('<h1>2027年推免资格名单公示</h1>','html.parser'))
