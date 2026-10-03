"""Add replayable assistant examples only to the dedicated retained demo database."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.agent_state import Conversation

if not settings.demo_mode or 'retained-demo' not in settings.database_url:
    raise SystemExit('Requires dedicated retained-demo database and DEMO_MODE=true')
if settings.development_dify_app_key:
    raise SystemExit('Clear development model configuration for deterministic demo seeding')
with TestClient(app) as c:
    for i,goal in enumerate(['考研','就业','保研','考公','创业'],1):
        user=f'demo-five-people-20260929-student-{i}'
        title=f'模拟路演：我的{goal}发展方向'
        with SessionLocal() as db:
            if db.scalar(select(Conversation).where(Conversation.user_id==user,Conversation.title==title)):
                continue
        headers={'x-user-id':user}
        r=c.post('/v1/development-agent/chat',headers=headers,json={'query':title,'intent':'paths'})
        assert r.status_code==200,r.text
        cid=r.json()['conversation_id']
        r=c.post('/v1/development-agent/chat',headers=headers,json={
            'query':f'继续为{goal}生成准备计划（模拟路演）','intent':'plan','conversation_id':cid})
        assert r.status_code==200,r.text
        r=c.post('/v1/development-agent/actions/'+r.json()['action_id']+'/confirm',headers=headers)
        assert r.status_code==200,r.text
    print('Retained 5 assistant example conversations; confirmed plans preserved')
