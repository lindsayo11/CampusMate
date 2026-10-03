"""Owned startup workspace, server-side arithmetic and versioned Markdown drafts."""
import json
from datetime import UTC, datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from .auth import actor_id
from .database import get_db
from .governance import audit
from .startup_models import StartupProject, StartupArtifact
from .startup_schemas import Brief, ProjectUpdate, DraftIn, ArtifactIn
from .startup_engine import TITLES, ROADMAP, FIELDS, SOURCES, calculations, build_draft, sources_for

router=APIRouter(prefix='/v1/startup')


def own_project(db,project_id,user):
    row=db.scalar(select(StartupProject).where(StartupProject.id==project_id,StartupProject.user_id==user))
    if not row:raise HTTPException(404,'创业项目不存在')
    return row


def brief_of(row):
    return Brief.model_validate_json(row.brief_json)


def project_out(row):
    return {'id':row.id,'brief':json.loads(row.brief_json),'revision':row.revision,
        'created_at':row.created_at,'updated_at':row.updated_at}


def lock_revision(db,project_id,user,revision):
    changed=db.execute(update(StartupProject).where(StartupProject.id==project_id,
        StartupProject.user_id==user,StartupProject.revision==revision).values(revision=StartupProject.revision))
    if not changed.rowcount:
        own_project(db,project_id,user)
        raise HTTPException(409,'项目资料已更新，请重新读取后生成或保存')


def save_artifact(db,user,project_id,kind,revision,markdown,expected_version):
    lock_revision(db,project_id,user,revision)
    version=db.scalar(select(func.max(StartupArtifact.version)).where(
        StartupArtifact.project_id==project_id,StartupArtifact.kind==kind)) or 0
    if version!=expected_version:raise HTTPException(409,'此文稿已有新版本，请重新读取后保存')
    row=StartupArtifact(id=str(uuid4()),project_id=project_id,kind=kind,version=version+1,
        project_revision=revision,title=TITLES[kind],markdown=markdown,
        sources_json=json.dumps(sources_for(kind),ensure_ascii=False),created_at=datetime.now(UTC))
    db.add(row);db.flush()
    audit(db,user,'startup_document_save','startup:'+project_id,{'kind':kind,'version':row.version})
    return row


def artifact_out(row,full=True):
    result={'id':row.id,'project_id':row.project_id,'kind':row.kind,'version':row.version,
        'project_revision':row.project_revision,'title':row.title,'created_at':row.created_at,
        'sources':json.loads(row.sources_json)}
    if full:result['markdown']=row.markdown
    return result


@router.get('/capabilities')
def capabilities(user:str=Depends(actor_id)):
    return {'document_kinds':[{'kind':k,'title':v} for k,v in TITLES.items()],
        'roadmap':[{'id':i,'title':t,'kind':k,'tasks':tasks} for i,t,k,tasks in ROADMAP],
        'fields':[{'group':g,'name':n,'label':l} for g,n,l in FIELDS],
        'sources':SOURCES,'default_mode':'structured_template'}


@router.get('/projects')
def projects(user:str=Depends(actor_id),db:Session=Depends(get_db),offset:int=Query(0,ge=0)):
    rows=db.scalars(select(StartupProject).where(StartupProject.user_id==user)
        .order_by(StartupProject.updated_at.desc(),StartupProject.id).offset(offset).limit(100)).all()
    return [{'id':r.id,'name':r.name,'revision':r.revision,'stage':brief_of(r).stage,'updated_at':r.updated_at} for r in rows]


@router.post('/projects',status_code=201)
def create_project(body:Brief,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    now=datetime.now(UTC)
    row=StartupProject(id=str(uuid4()),user_id=user,name=body.name,brief_json=body.model_dump_json(),revision=1,created_at=now,updated_at=now)
    db.add(row);audit(db,user,'startup_project_create','startup:'+row.id);db.commit()
    return project_out(row)


@router.get('/projects/{pid}')
def project(pid:str,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    return project_out(own_project(db,pid,user))


@router.put('/projects/{pid}')
def change_project(pid:str,body:ProjectUpdate,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    own_project(db,pid,user)
    brief=Brief.model_validate(body.model_dump(exclude={'expected_revision'}))
    changed=db.execute(update(StartupProject).where(StartupProject.id==pid,
        StartupProject.user_id==user,StartupProject.revision==body.expected_revision)
        .values(name=brief.name,brief_json=brief.model_dump_json(),revision=body.expected_revision+1,updated_at=datetime.now(UTC)))
    if not changed.rowcount:raise HTTPException(409,'资料已有新版本，请刷新后再编辑')
    audit(db,user,'startup_project_update','startup:'+pid);db.commit()
    return project_out(db.get(StartupProject,pid,populate_existing=True))


@router.delete('/projects/{pid}')
def remove_project(pid:str,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    row=own_project(db,pid,user)
    db.execute(delete(StartupArtifact).where(StartupArtifact.project_id==pid))
    db.delete(row);audit(db,user,'startup_project_delete','startup:'+pid);db.commit()
    return {'deleted':True}


@router.get('/projects/{pid}/analysis')
def analysis(pid:str,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    row=own_project(db,pid,user);brief=brief_of(row)
    return {**calculations(brief),'project_revision':row.revision,
        'roadmap':[{'id':i,'title':t,'kind':k,'tasks':tasks,'done':i in brief.completed_steps} for i,t,k,tasks in ROADMAP],
        'progress_percent':len(brief.completed_steps)*10}


@router.post('/projects/{pid}/draft')
def draft(pid:str,body:DraftIn,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    row=own_project(db,pid,user)
    if row.revision!=body.expected_revision:raise HTTPException(409,'资料已更新，请重新读取后生成')
    version=db.scalar(select(func.max(StartupArtifact.version)).where(StartupArtifact.project_id==pid,StartupArtifact.kind==body.kind)) or 0
    draft=build_draft(brief_of(row),body.kind)
    if body.model_assist:
        from .startup_generation import assist
        draft=assist(draft,brief_of(row),body.instruction,user)
    return {**draft,'project_id':pid,'project_revision':row.revision,'expected_document_version':version}


@router.get('/projects/{pid}/documents')
def documents(pid:str,user:str=Depends(actor_id),db:Session=Depends(get_db),offset:int=Query(0,ge=0)):
    own_project(db,pid,user)
    rows=db.scalars(select(StartupArtifact).where(StartupArtifact.project_id==pid)
        .order_by(StartupArtifact.created_at.desc(),StartupArtifact.id).offset(offset).limit(100)).all()
    return [artifact_out(r,full=False) for r in rows]


@router.post('/projects/{pid}/documents',status_code=201)
def save_document(pid:str,body:ArtifactIn,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    row=save_artifact(db,user,pid,body.kind,body.expected_revision,body.markdown,body.expected_document_version)
    db.commit();return artifact_out(row)


@router.get('/projects/{pid}/documents/{did}')
def document(pid:str,did:str,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    own_project(db,pid,user)
    row=db.scalar(select(StartupArtifact).where(StartupArtifact.project_id==pid,StartupArtifact.id==did))
    if not row:raise HTTPException(404,'文稿不存在')
    return artifact_out(row)


@router.get('/projects/{pid}/documents/{did}/export')
def export_document(pid:str,did:str,user:str=Depends(actor_id),db:Session=Depends(get_db)):
    data=document(pid,did,user,db)
    return Response(data['markdown'],media_type='text/markdown; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="{data["kind"]}-v{data["version"]}.md"',
        'Cache-Control':'private, no-store'})
