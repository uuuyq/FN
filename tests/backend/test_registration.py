from sqlalchemy import select
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from app.models import User


def test_registration_validation_duplicate_and_automatic_session(env):
    engine,(a,b)=env
    body={'username':' new-user ','password':'synthetic-password-123','password_confirmation':'synthetic-password-123'}
    assert a.post('/api/auth/register',json={**body,'password_confirmation':'mismatched-password'}).status_code==422
    assert a.post('/api/auth/register',json={**body,'password':'short','password_confirmation':'short'}).status_code==422
    assert a.post('/api/auth/register',json=body,headers={'Origin':'https://evil.invalid'}).status_code==403
    result=a.post('/api/auth/register',json=body)
    assert result.status_code==200 and result.json()['username']=='new-user'
    assert a.get('/api/auth/me').json()['id']==result.json()['id']
    assert result.json()['onboarding_dismissed'] is False
    assert 'HttpOnly' in result.headers['set-cookie']
    assert b.post('/api/auth/register',json=body).json()['detail']['code']=='username_taken'
    with Session(engine) as db:
        rows=list(db.scalars(select(User).where(User.username=='new-user')))
        assert len(rows)==1 and PasswordHasher().verify(rows[0].password_hash,body['password'])
    a.headers['X-CSRF-Token']=result.json()['csrf_token']
    assert a.post('/api/auth/logout').status_code==200
    assert a.post('/api/auth/login',json={'username':'new-user','password':body['password']}).status_code==200
