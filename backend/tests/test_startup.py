from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.startup_engine import calculations, build_draft, TITLES
from app.startup_schemas import Brief


def new_project(c,h=None,**changes):
    data={'name':'项目-'+str(uuid4()),'summary':'为小团队提供真实客户访谈与付费验证工具','customers':'小团队负责人',
        'problem':'难以追踪付费实验结果','solution':'结构化记录访谈和订单','traction':'已访谈3位潜在客户，未获得付费订单'}
    data.update(changes)
    r=c.post('/v1/startup/projects',headers=h or {},json=data)
    assert r.status_code==201,r.text
    return r.json()


def test_project_access_revision_and_delete():
    h={'x-user-id':str(uuid4())};other={'x-user-id':str(uuid4())}
    with TestClient(app) as c:
        p=new_project(c,h);url='/v1/startup/projects/'+p['id']
        assert c.get(url,headers=other).status_code==404
        assert not c.get('/v1/startup/projects',headers=other).json()
        update={**p['brief'],'name':'更改后的项目','expected_revision':1}
        changed=c.put(url,headers=h,json=update)
        assert changed.status_code==200 and changed.json()['revision']==2
        assert c.put(url,headers=h,json=update).status_code==409
        assert c.delete(url,headers=other).status_code==404
        assert c.delete(url,headers=h).status_code==200
        assert c.get(url,headers=h).status_code==404


def test_all_document_kinds_are_grounded_and_versioned():
    h={'x-user-id':str(uuid4())};other={'x-user-id':str(uuid4())}
    with TestClient(app) as c:
        p=new_project(c,h);url='/v1/startup/projects/'+p['id']
        for kind in TITLES:
            r=c.post(url+'/draft',headers=h,json={'kind':kind,'expected_revision':1})
            assert r.status_code==200,r.text
            draft=r.json()
            assert draft['mode']=='structured_template' and '待填写' in draft['markdown']
            assert p['brief']['name'] in draft['markdown']
            assert c.get(url+'/documents',headers=h).json()==[] if kind==list(TITLES)[0] else True
            save=c.post(url+'/documents',headers=h,json={'kind':kind,'expected_revision':1,'markdown':draft['markdown']})
            assert save.status_code==201,save.text
            artifact=save.json();did=artifact['id']
            assert artifact['version']==1
            assert c.get(url+'/documents/'+did,headers=other).status_code==404
            assert c.get(url+'/documents/'+did+'/export',headers=other).status_code==404
            exported=c.get(url+'/documents/'+did+'/export',headers=h)
            assert exported.text==draft['markdown']
            assert 'private' in exported.headers['cache-control']
            assert c.post(url+'/documents',headers=h,json={'kind':kind,'expected_revision':1,'markdown':'旧版本覆盖'}).status_code==409
        assert len(c.get(url+'/documents',headers=h).json())==14
        bp=c.post(url+'/draft',headers=h,json={'kind':'bp','expected_revision':1}).json()['markdown']
        assert '未获得付费订单' in bp
        assert '市场规模【待核验】' in bp


def test_financial_and_cap_table_arithmetic():
    b=Brief(name='示例',founders=[{'name':'创始人','percent':70},{'name':'合伙人','percent':30}],
        finance={'price':100,'monthly_units':100,'variable_cost':40,'fixed_cost':9000,'cash':18000,
            'pre_money':1000000,'investment':250000,'new_pool_pct':10})
    result=calculations(b);e=result['economics'];cap=result['cap_table']
    assert e['monthly_revenue']==10000 and e['monthly_operating_result']==-3000
    assert e['monthly_burn']==3000 and e['runway_months']==6 and e['break_even_units']==150
    assert e['contribution_margin_pct']==60
    assert [row['after_pct'] for row in cap['rows']]==[50.4,21.6,8,20]
    assert sum(Decimal(str(row['after_pct'])) for row in cap['rows'])==100
    assert cap['post_money']==1250000
    assert len(e['projections'])==15
    assert next(p['revenue'] for p in e['projections'] if p['scenario']=='基准' and p['year']==1)==120000
    for kind in ('bp','finance'):
        text=build_draft(b,kind)['markdown']
        assert '基准 · 第 5 年：收入 120000.0；成本 156000.0；经营结果 -36000.0' in text
        assert '销量下降20% · 第 1 年：收入 96000.0；成本 146400.0；经营结果 -50400.0' in text


def test_financial_zero_negative_and_missing_cases():
    e=calculations(Brief(name='空白'))['economics']
    assert len(e['missing_fields'])==5
    e=calculations(Brief(name='不亏损',finance={'price':10,'monthly_units':10,'variable_cost':2,'fixed_cost':0,'cash':0}))['economics']
    assert e['runway_months'] is None and e['monthly_burn']==0
    e=calculations(Brief(name='负贡献',finance={'price':0,'monthly_units':10,'variable_cost':2,'fixed_cost':100,'cash':0}))['economics']
    assert e['break_even_units'] is None and e['contribution_margin_pct'] is None and e['runway_months']==0
    cap=calculations(Brief(name='缺估值',founders=[{'name':'A','percent':100}],finance={'investment':10}))['cap_table']
    assert cap['missing_fields']==['pre_money'] and not cap['rows']


@pytest.mark.parametrize('bad',[
    {'founders':[{'name':'A','percent':50}]},
    {'founders':[{'name':'A','percent':50},{'name':'A','percent':50}]},
    {'finance':{'price':-1}}, {'finance':{'new_pool_pct':60}}, {'finance':{'price':'NaN'}},
    {'finance':{'price':'0.000000000000000000000000000000000001'}},
    {'completed_steps':['s99']}, {'user_id':'admin'}])
def test_invalid_inputs_are_rejected(bad):
    with TestClient(app) as c:
        assert c.post('/v1/startup/projects',json={'name':'不合法',**bad}).status_code==422


def test_document_save_concurrency_and_stale_project():
    h={'x-user-id':str(uuid4())}
    with TestClient(app) as c:
        p=new_project(c,h);url='/v1/startup/projects/'+p['id']
        body={'kind':'bp','expected_revision':1,'expected_document_version':0,'markdown':'真实草稿内容'}
        with ThreadPoolExecutor(2) as pool:
            responses=list(pool.map(lambda _:c.post(url+'/documents',headers=h,json=body),range(2)))
        assert sorted(r.status_code for r in responses)==[201,409]
        assert len(c.get(url+'/documents',headers=h).json())==1
        c.put(url,headers=h,json={**p['brief'],'expected_revision':1,'summary':'新资料'})
        assert c.post(url+'/draft',headers=h,json={'kind':'bp','expected_revision':1}).status_code==409
        assert c.post(url+'/documents',headers=h,json={**body,'expected_document_version':1}).status_code==409


def test_agent_documents_confirmation_and_project_change():
    h={'x-user-id':str(uuid4())};other={'x-user-id':str(uuid4())}
    with TestClient(app) as c:
        no_selection=c.post('/v1/development-agent/chat',headers=h,json={'query':'请写一份BP'}).json()
        assert no_selection['tool']=='startup' and no_selection['result']['workspace_url']=='/startup'
        p=new_project(c,h)
        req={'query':'请帮这个项目设计股权模式','startup_project_id':p['id']}
        r=c.post('/v1/development-agent/chat',headers=h,json=req).json()
        assert r['tool']=='startup_document' and r['arguments']['kind']=='equity'
        assert c.get('/v1/startup/projects/'+p['id']+'/documents',headers=h).json()==[]
        url='/v1/development-agent/actions/'+r['action_id']+'/confirm'
        assert c.post(url,headers=other).status_code==404
        first=c.post(url,headers=h)
        assert first.status_code==200 and first.json()['result']['startup_document']['version']==1
        assert c.post(url,headers=h).json()==first.json()
        r=c.post('/v1/development-agent/chat',headers=h,json={'query':'为它起草用户协议','conversation_id':r['conversation_id']}).json()
        assert r['arguments']['kind']=='user_agreement'
        c.put('/v1/startup/projects/'+p['id'],headers=h,json={**p['brief'],'expected_revision':1,'entity_name':'新主体'})
        assert c.post('/v1/development-agent/actions/'+r['action_id']+'/confirm',headers=h).status_code==409
        assert len(c.get('/v1/startup/projects/'+p['id']+'/documents',headers=h).json())==1
        assert c.post('/v1/development-agent/chat',headers=other,json=req).status_code==404


def test_model_draft_is_opt_in_falls_back_and_labels_output(monkeypatch):
    with TestClient(app) as c:
        p=new_project(c);url='/v1/startup/projects/'+p['id']+'/draft'
        monkeypatch.setattr(settings,'development_dify_api_base','https://dify.test/v1')
        monkeypatch.setattr(settings,'development_dify_app_key','test')
        def broken(*args,**kwargs):raise httpx.ConnectError('offline')
        monkeypatch.setattr('app.startup_generation.httpx.post',broken)
        r=c.post(url,json={'kind':'bp','expected_revision':1}).json()
        assert r['mode']=='structured_template' and 'model_notice' not in r
        r=c.post(url,json={'kind':'bp','expected_revision':1,'model_assist':True}).json()
        assert r['mode']=='structured_template' and '暂不可用' in r['model_notice']
        def good(url,**kwargs):
            inputs=kwargs['json']['inputs']
            assert inputs['phase']=='startup_draft' and p['brief']['solution'] in inputs['request']
            return httpx.Response(200,json={'data':{'status':'succeeded','outputs':{'markdown':'## 项目概述\n\n这是基于已有客户访谈资料提出的草稿，未形成付费验证结论。'}}},request=httpx.Request('POST',url))
        monkeypatch.setattr('app.startup_generation.httpx.post',good)
        r=c.post(url,json={'kind':'bp','expected_revision':1,'model_assist':True}).json()
        assert r['mode']=='model_assisted' and '未完成事实、法律或投资审查' in r['markdown']
        assert c.get('/v1/startup/projects/'+p['id']+'/documents').json()==[]


def test_ten_stage_progress_and_other_jurisdiction():
    with TestClient(app) as c:
        p=new_project(c,jurisdiction='HK',completed_steps=['s01','s02'])
        a=c.get('/v1/startup/projects/'+p['id']+'/analysis').json()
        assert a['progress_percent']==20 and len(a['roadmap'])==10
        assert sum(step['done'] for step in a['roadmap'])==2
        draft=c.post('/v1/startup/projects/'+p['id']+'/draft',json={'kind':'ipo','expected_revision':1}).json()
        assert '不视为当地适用规则' in draft['markdown']
        assert '不判断是否具备上市资格' in draft['markdown']
