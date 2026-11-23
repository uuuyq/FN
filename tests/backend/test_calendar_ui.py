from helpers import write, make_workout, setup, send
from sqlalchemy.orm import Session
from app.models import Workout


def test_calendar_complete_month_and_isolation(env):
    engine, (a,b) = env
    _, w = make_workout(a)
    with Session(engine) as db:
        original=db.get(Workout,w['id'])
        for i in range(205):
            db.add(Workout(user_id=original.user_id, actual_date='2026-01-02', notes=''))
        db.commit()
    result=a.get('/api/workouts/calendar?month=2026-01').json()
    assert result['training_days']==1
    assert result['days']==[{'date':'2026-01-02','count':206,'parts':['胸']}]
    assert b.get('/api/workouts/calendar?month=2026-01').json()['days']==[]
    assert a.get('/api/workouts/calendar?month=2026-13').status_code==422
    assert a.get('/api/workouts/calendar?month=2024-02').status_code==200
    write(a,f"/workouts/{w['id']}",{'version':w['version']}, "DELETE")
    assert a.get('/api/workouts/calendar?month=2026-01').json()['days'][0]['count']==205


def test_account_password_and_username(env):
    _,(a,b)=env
    write(a,'/auth/account',{'current_password':'wrong','username':'new'},'PUT',status=401)
    write(a,'/auth/account',{'current_password':'test-password-123','username':'bob'},'PUT',status=409)
    r=write(a,'/auth/account',{'current_password':'test-password-123','username':'alice-new'},'PUT')
    assert r['username']=='alice-new'
    write(a,'/auth/account',{'current_password':'test-password-123','password':'a-new-password-123'},'PUT')
    assert a.get('/api/auth/me').status_code==401
    assert a.post('/api/auth/login',json={'username':'alice-new','password':'a-new-password-123'}).status_code==200
    assert b.get('/api/auth/me').status_code==200


def test_conversation_rename_delete_isolated_and_preserves_training(env):
    _,(a,b)=env
    _,w=make_workout(a)
    cid,_=setup(a,lambda ctx:{'kind':'reply','text':'你好'})
    turn=send(a,cid)
    write(b,'/conversations/'+cid,{'title':'别人的名字'},'PATCH',status=404)
    write(a,'/conversations/'+cid,{'title':'  我的训练  '},'PATCH')
    assert a.get('/api/conversations/'+cid).json()['title']=='我的训练'
    write(a,'/conversations/'+cid,{'title':'   '},'PATCH',status=422)
    write(b,'/conversations/'+cid,{},'DELETE',status=404)
    write(a,'/conversations/'+cid,{},'DELETE')
    write(a,'/conversations/'+cid,{},'DELETE')
    assert cid not in [r['id'] for r in a.get('/api/conversations').json()['items']]
    assert a.get('/api/conversations/'+cid).status_code==404
    assert a.get('/api/turns/'+turn['id']).status_code==404
    write(a,'/conversations/'+cid,{'title':'恢复'},'PATCH',status=404)
    assert a.get('/api/workouts/'+w['id']).status_code==200


