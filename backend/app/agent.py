"""Dify selects tools; CampusMate validates facts and owns confirmed transactions."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from .auth import actor_id
from .config import settings
from .database import get_db
from .governance import audit
from .models import AgentAction, Opportunity
from .schemas import EligibilityCheckIn, ReminderIn, TrackerWriteIn
from .social import Connect, connect_user, match_candidates

router = APIRouter(prefix='/v1/agent')
Tool = Literal['opportunity_search', 'eligibility_check', 'team_match', 'tracker_write', 'deadline_remind', 'message_connect']
WRITE_TOOLS = {'tracker_write', 'deadline_remind', 'message_connect'}


class ChatIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000)
    opportunity_id: str | None = Field(default=None, max_length=40)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['job', 'contest', 'civil_service', 'volunteer', 'club', 'graduate'] | None = None
    q: str | None = Field(default=None, max_length=80)


class MatchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    skills: list[str] = Field(default_factory=list, max_length=20)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Tool
    arguments: dict


ARG_TYPES = {'opportunity_search': SearchArgs, 'eligibility_check': EligibilityCheckIn,
             'team_match': MatchArgs, 'tracker_write': TrackerWriteIn,
             'deadline_remind': ReminderIn, 'message_connect': Connect}


def validate_decision(raw):
    decision = Decision.model_validate(raw)
    schema = ARG_TYPES[decision.tool]
    if set(decision.arguments) - set(schema.model_fields):
        raise ValueError('Unknown tool argument')
    args = schema.model_validate(decision.arguments)
    return Decision(tool=decision.tool, arguments=args.model_dump())


def route_query(body, user):
    if settings.dify_api_base and settings.dify_app_key:
        try:
            response = httpx.post(settings.dify_api_base.rstrip('/')+'/workflows/run',
                headers={'Authorization':'Bearer '+settings.dify_app_key}, timeout=20,
                json={'inputs':{'query':body.query, 'opportunity_id':body.opportunity_id or ''},
                      'response_mode':'blocking', 'user':hashlib.sha256(user.encode()).hexdigest()})
            response.raise_for_status()
            data=response.json()['data']
            if data['status'] != 'succeeded':
                raise ValueError('Workflow failed')
            decision=data['outputs']['decision']
            if isinstance(decision,str):
                decision=json.loads(decision)
            return validate_decision(decision), 'dify'
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # Never silently downgrade a model-requested write or invent a result.
            raise HTTPException(502, '智能服务暂不可用或输出不符合约定，请使用机会列表和操作按钮')
    q=body.query
    if body.opportunity_id:
        if '提醒' in q:
            return validate_decision({'tool':'deadline_remind','arguments':{'opportunity_id':body.opportunity_id}}), 'rules'
        if '看板' in q or '收藏' in q:
            return validate_decision({'tool':'tracker_write','arguments':{'opportunity_id':body.opportunity_id}}), 'rules'
        if '能报' in q or '资格' in q:
            return validate_decision({'tool':'eligibility_check','arguments':{'opportunity_id':body.opportunity_id}}), 'rules'
    kinds=[('实习','job'),('就业','job'),('岗位','job'),('竞赛','contest'),('考公','civil_service'),('志愿','volunteer'),('社团','club'),('升学','graduate')]
    kind=next((kind for word,kind in kinds if word in q),None)
    return validate_decision({'tool':'opportunity_search','arguments':{'type':kind,'q':None if kind else q[:80]}}), 'rules'


def run_tool(decision, user, db):
    from .main import create_reminder, eligibility_check, list_opportunities, write_tracker
    args=ARG_TYPES[decision.tool].model_validate(decision.arguments)
    if decision.tool in {'eligibility_check','tracker_write','deadline_remind'}:
        opportunity=db.get(Opportunity,args.opportunity_id)
        if not opportunity or opportunity.status != 'published':
            raise HTTPException(404,'机会不存在或已下线')
    if decision.tool=='opportunity_search':
        result=list_opportunities(args.type,args.q,db)
        result.items=result.items[:5]
    elif decision.tool=='eligibility_check':
        result=eligibility_check(args,user,db)
    elif decision.tool=='team_match':
        result=match_candidates(args.skills,user,db)
    elif decision.tool=='tracker_write':
        result=write_tracker(args,user,db,commit=False)
    elif decision.tool=='deadline_remind':
        result=create_reminder(args,user,db,commit=False)
    else:
        result=connect_user(args,user,db,commit=False)
    return jsonable_encoder(result)


@router.post('/chat')
def chat(body: ChatIn, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    decision,mode=route_query(body,user)
    if decision.tool in WRITE_TOOLS:
        action=AgentAction(id=str(uuid4()),user_id=user,tool=decision.tool,
                           arguments=json.dumps(decision.arguments,ensure_ascii=False),
                           expires_at=datetime.now(UTC)+timedelta(minutes=10))
        db.add(action)
        audit(db,user,'agent_propose','action:'+action.id,{'tool':decision.tool})
        db.commit()
        return {'mode':mode,'status':'confirmation_required','tool':decision.tool,
                'action_id':action.id,'arguments':decision.arguments,
                'message':'请核对操作参数并确认；尚未执行。'}
    result=run_tool(decision,user,db)
    from .knowledge import SearchIn, search_documents, tokens
    references = []
    if decision.tool in {'opportunity_search', 'eligibility_check'} and tokens(body.query[:200]):
        references = search_documents(SearchIn(query=body.query[:200], opportunity_id=body.opportunity_id), db)['items']
    audit(db,user,'agent_read','tool:'+decision.tool)
    db.commit()
    return {'mode':mode,'status':'completed','tool':decision.tool,'result':result,'references':references,
            'message':'以下结果来自业务数据库与确定性工具。'}


@router.post('/actions/{action_id}/confirm')
def confirm(action_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    claimed=db.execute(update(AgentAction).where(AgentAction.id==action_id,AgentAction.user_id==user).values(status=AgentAction.status))
    if not claimed.rowcount:
        raise HTTPException(404,'操作不存在')
    row=db.get(AgentAction,action_id,populate_existing=True)
    if row.status=='completed':
        return json.loads(row.result_json)
    if row.status!='pending':
        raise HTTPException(409,'操作已取消')
    expiry=row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
    if expiry<=datetime.now(UTC):
        raise HTTPException(409,'确认已过期，请重新发起')
    decision=validate_decision({'tool':row.tool,'arguments':json.loads(row.arguments)})
    result=run_tool(decision,user,db)
    response={'status':'completed','tool':row.tool,'result':result,'message':'操作已完成。'}
    row.status='completed'
    row.result_json=json.dumps(response,ensure_ascii=False)
    audit(db,user,'agent_confirm','action:'+row.id,{'tool':row.tool})
    db.commit()
    return response


@router.post('/actions/{action_id}/cancel')
def cancel(action_id: str, user: str = Depends(actor_id), db: Session = Depends(get_db)):
    changed=db.execute(update(AgentAction).where(AgentAction.id==action_id,AgentAction.user_id==user,AgentAction.status=='pending').values(status='cancelled'))
    if not changed.rowcount:
        raise HTTPException(409,'操作不存在或已处理')
    db.commit()
    return {'status':'cancelled'}
