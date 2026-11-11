import hashlib
import os
import secrets
import time

from argon2.exceptions import VerificationError
from fastapi import Depends, Header, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.database import write_transaction
from ...models import User, UserSession
from ...schemas import Login, Register, Schema
from pydantic import Field
from typing import Annotated
from pydantic import StringConstraints

class AccountUpdate(Schema):
    current_password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, min_length=1, max_length=100)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] | None = Field(default=None, min_length=12, max_length=1024)

from ...services import fail
from typing import Annotated


RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]

def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    def check_origin(request):
        origin = request.headers.get('origin')
        if origin and origin != os.getenv('APP_ORIGIN', str(request.base_url).rstrip('/')):
            fail(403, 'origin_rejected')

    def signed_in(db, user, request, response):
        old = db.get(UserSession, hashlib.sha256(request.cookies.get('fitplan_session', '').encode()).hexdigest())
        if old:
            old.revoked = True
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.add(UserSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, csrf=csrf, expires=int(time.time()) + 604800))
        response.set_cookie('fitplan_session', token, httponly=True, secure=secure, samesite='lax', max_age=604800)
        return {'id': user.id, 'username': user.username, 'csrf_token': csrf}

    @app.post('/api/auth/register')
    def create_account(body: Register, request: Request, response: Response):
        check_origin(request)
        hashed = password_hasher.hash(body.password)
        with write_transaction(engine) as db:
            if db.scalar(select(User.id).where(User.username == body.username)):
                fail(409, 'username_taken')
            user = User(username=body.username, password_hash=hashed)
            db.add(user)
            db.flush()
            return signed_in(db, user, request, response)

    @app.post('/api/auth/login')
    def login(body: Login, request: Request, response: Response):
        check_origin(request)
        with write_transaction(engine) as db:
            user = db.scalar(select(User).where(User.username == body.username))
            try:
                password_hasher.verify(user.password_hash if user else dummy_hash, body.password)
            except VerificationError:
                fail(401, 'invalid_credentials')
            if not user:
                fail(401, 'invalid_credentials')
            return signed_in(db, user, request, response)

    @app.put('/api/auth/account')
    def account(body: AccountUpdate, request: Request, response: Response, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            user = db.get(User, user_id)
            try:
                password_hasher.verify(user.password_hash, body.current_password)
            except VerificationError:
                fail(401, 'invalid_credentials')
            if body.username is not None:
                if db.scalar(select(User.id).where(User.username == body.username, User.id != user_id)):
                    fail(409, 'username_taken')
                user.username = body.username
            if body.password is not None:
                user.password_hash = password_hasher.hash(body.password)
                db.execute(update(UserSession).where(UserSession.user_id == user_id).values(revoked=True))
            return {'id': user.id, 'username': user.username, 'login_required': body.password is not None}
        result = mutate(request, user_id, x_request_id, body, action)
        if result.get('login_required'):
            response.delete_cookie('fitplan_session')
        return result

    @app.get('/api/auth/me')
    def me(request: Request, user_id=Depends(identity)):
        with Session(engine) as db:
            user = db.get(User, user_id)
            session = db.get(UserSession, hashlib.sha256(request.cookies['fitplan_session'].encode()).hexdigest())
            return {'id': user.id, 'username': user.username, 'csrf_token': session.csrf}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, user_id=Depends(identity)):
        with write_transaction(engine) as db:
            db.get(UserSession, hashlib.sha256(request.cookies['fitplan_session'].encode()).hexdigest()).revoked = True
        response.delete_cookie('fitplan_session')
        return {'logged_out': True}

