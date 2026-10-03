from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.task_alerts import TaskAlert, deliver_task_alerts


def setup(c):
    owner,member=[{'X-User-Id':str(uuid4())} for _ in range(2)]
    team=c.post('/v1/teams',headers=owner,json={'title':'任务提醒测试'}).json()
    c.get('/v1/profile',headers=member)
    base=f'/v1/teams/{team["id"]}'
    c.post(base+'/invitations',headers=owner,json={'target':member['X-User-Id']})
    c.post(f'/v1/invitations/{team["id"]}/decision',headers=member,json={'action':'accept'})
    payload={'title':'准备报名材料','assignee':member['X-User-Id'],'due_at':(datetime.now(UTC)+timedelta(hours=2)).isoformat()}
    task=c.post(base+'/tasks',headers=owner,json=payload).json()
    return owner,member,base,task,payload


def test_task_alert_delivery_idempotency_and_read_permission():
    with TestClient(app) as c:
        owner,member,base,task,_=setup(c)
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:deliver_task_alerts(),range(2)))
        notices=c.get('/v1/task-alerts',headers=member).json()['items']
        assert len(notices)==1 and notices[0]['task_id']==task['id']
        assert not notices[0]['overdue']
        assert c.get('/v1/task-alerts',headers=owner).json()['items']==[]
        path=f'/v1/task-alerts/{notices[0]["id"]}/read'
        assert c.post(path,headers=owner).status_code==404
        assert c.post(path,headers=member).status_code==200
        assert c.post(path,headers=member).status_code==200
        assert c.get('/v1/task-alerts',headers=member).json()['items'][0]['read_at']
        c.post(base+'/leave',headers=member)
        assert c.get('/v1/task-alerts',headers=member).json()['items']==[]
        assert c.post(path,headers=member).status_code==404


def test_task_reschedule_transfer_complete_and_dissolve():
    with TestClient(app) as c:
        owner,member,base,task,payload=setup(c)
        deliver_task_alerts()
        path=base+f'/tasks/{task["id"]}'
        payload['due_at']=(datetime.now(UTC)+timedelta(days=3)).isoformat()
        task=c.put(path,headers=owner,json={**payload,'version':task['version']}).json()
        deliver_task_alerts()
        assert c.get('/v1/task-alerts',headers=member).json()['items']==[]
        payload['due_at']=(datetime.now(UTC)-timedelta(hours=1)).isoformat()
        payload['assignee']=owner['X-User-Id']
        task=c.put(path,headers=owner,json={**payload,'version':task['version']}).json()
        deliver_task_alerts()
        notices=c.get('/v1/task-alerts',headers=owner).json()['items']
        assert len(notices)==1 and notices[0]['overdue']
        assert c.get('/v1/task-alerts',headers=member).json()['items']==[]
        task=c.post(path+'/status',headers=owner,json={'status':'done','version':task['version']}).json()
        assert c.get('/v1/task-alerts',headers=owner).json()['items']==[]
        c.post(base+'/dissolve',headers=owner);deliver_task_alerts()
        assert c.get('/v1/task-alerts',headers=owner).json()['items']==[]
        with SessionLocal() as db:assert db.query(TaskAlert).filter_by(task_id=task['id']).count()==2
