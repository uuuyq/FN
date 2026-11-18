import hashlib
import json
import os
import secrets
import time
from typing import Annotated

from argon2.exceptions import VerificationError
from fastapi import Depends, Header, Request, Response
from pydantic import Field, StringConstraints
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.database import write_transaction
from ...models import User, UserSession, RequestReceipt
from ...schemas import Login, Register, Schema
from ...services import fail
from .limiter import AuthLimiter


class AccountUpdate(Schema):
    current_password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=1024)
    username: str | None = Field(default=None, min_length=1, max_length=100)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] | None = Field(default=None, min_length=12, max_length=1024)

RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]

def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    limiter = AuthLimiter()
    app.state.auth_limiter = limiter

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
        return {'id': user.id, 'username': user.username, 'csrf_token': csrf, 'onboarding_dismissed': user.onboarding_dismissed}

    @app.post('/api/auth/register')
    def create_account(body: Register, request: Request, response: Response):
        check_origin(request)
        limiter.check(request, 'username:' + body.username)
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
        limiter.check(request, 'username:' + body.username)
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.username == body.username))
            user_id = user.id if user else None
            expected_hash = user.password_hash if user else dummy_hash
        verify_password(expected_hash, body.password)
        with write_transaction(engine) as db:
            user = db.get(User, user_id) if user_id else None
            if not user or user.password_hash != expected_hash or user.username != body.username:
                fail(401, 'invalid_credentials')
            return signed_in(db, user, request, response)

    def verify_password(hashed, password):
        try:
            password_hasher.verify(hashed, password)
        except VerificationError:
            fail(401, 'invalid_credentials')

    @app.put('/api/auth/account')
    def account(body: AccountUpdate, request: Request, response: Response, x_request_id: RequestId, user_id=Depends(identity)):
        with Session(engine) as db:
            user = db.get(User, user_id)
            username, expected_hash = user.username, user.password_hash
        limiter.check(request, 'username:' + username)
        verify_password(expected_hash, body.current_password)
        new_hash = password_hasher.hash(body.password) if body.password is not None else None
        # Account requests contain credentials. Use a salted, expensive verifier
        # rather than the generic fast request fingerprint. All Argon2 work stays
        # outside the SQLite write transaction.
        payload = json.dumps(['PUT /api/auth/account', body.model_dump()], sort_keys=True, ensure_ascii=False)
        fingerprint = password_hasher.hash(payload)
        while True:
            with Session(engine) as db:
                receipt = db.get(RequestReceipt, (user_id, x_request_id))
                previous = receipt.fingerprint if receipt else None
            if previous:
                if not previous.startswith('$argon2'):
                    fail(409, 'request_id_reused')
                try:
                    password_hasher.verify(previous, payload)
                except VerificationError:
                    fail(409, 'request_id_reused')
            with write_transaction(engine) as db:
                user = db.get(User, user_id)
                if user.password_hash != expected_hash:
                    fail(401, 'invalid_credentials')
                receipt = db.get(RequestReceipt, (user_id, x_request_id))
                if receipt:
                    if receipt.fingerprint != previous:
                        # A concurrent request committed first. Verify its receipt
                        # outside the transaction before returning its result.
                        continue
                    result = receipt.result
                else:
                    if body.username is not None:
                        if db.scalar(select(User.id).where(User.username == body.username, User.id != user_id)):
                            fail(409, 'username_taken')
                        user.username = body.username
                    if new_hash is not None:
                        user.password_hash = new_hash
                        db.execute(update(UserSession).where(UserSession.user_id == user_id).values(revoked=True))
                    result = {'id': user.id, 'username': user.username, 'login_required': new_hash is not None}
                    db.add(RequestReceipt(user_id=user_id, request_id=x_request_id,
                                          fingerprint=fingerprint, result=result))
                break
        if result.get('login_required'):
            response.delete_cookie('fitplan_session')
        return result

    @app.get('/api/auth/me')
    def me(request: Request, user_id=Depends(identity)):
        with Session(engine) as db:
            user = db.get(User, user_id)
            session = db.get(UserSession, hashlib.sha256(request.cookies['fitplan_session'].encode()).hexdigest())
            return {'id': user.id, 'username': user.username, 'csrf_token': session.csrf, 'onboarding_dismissed': user.onboarding_dismissed}

    @app.post('/api/auth/onboarding/dismiss')
    def dismiss_onboarding(request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            db.get(User, user_id).onboarding_dismissed = True
            return {'onboarding_dismissed': True}
        return mutate(request, user_id, x_request_id, {}, action)

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, user_id=Depends(identity)):
        with write_transaction(engine) as db:
            db.get(UserSession, hashlib.sha256(request.cookies['fitplan_session'].encode()).hexdigest()).revoked = True
        response.delete_cookie('fitplan_session')
        return {'logged_out': True}

