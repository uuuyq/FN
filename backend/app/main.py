import hashlib
import os
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from .errors import error_detail
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .core.database import make_engine, write_transaction
from .models import UserSession
from .services import fail, idempotent
from typing import Annotated


def create_app(engine=None):
    engine = engine or make_engine()
    app = FastAPI(title='FNote', version='0.1.0')
    app.state.engine = engine
    secure = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
    password_hasher = PasswordHasher()
    dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))

    @app.exception_handler(HTTPException)
    async def http_error(_, error):
        detail = error.detail if isinstance(error.detail, dict) else {}
        code = detail.get('code', {404: 'not_found', 401: 'unauthenticated', 403: 'origin_rejected'}.get(error.status_code, 'internal_error'))
        return JSONResponse(status_code=error.status_code,
                            content={'detail': error_detail(code, **{k: v for k, v in detail.items() if k not in ('code', 'message')})},
                            headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        # Preserve field locations without echoing passwords, input values or exception contexts.
        fields = [{'loc': list(item['loc']), 'type': item['type']} for item in error.errors()]
        return JSONResponse(status_code=422, content={'detail': error_detail('validation_error', errors=fields)})

    @app.exception_handler(Exception)
    async def unexpected_error(_, error):
        return JSONResponse(status_code=500, content={'detail': error_detail('internal_error')})

    @app.exception_handler(OperationalError)
    async def busy(_, error):
        if 'locked' in str(error).lower() or 'busy' in str(error).lower():
            return JSONResponse(status_code=503, content={'detail': error_detail('database_busy', retryable=True)}, headers={'Retry-After': '1'})
        return JSONResponse(status_code=500, content={'detail': error_detail('database_error')})

    @app.exception_handler(IntegrityError)
    async def constraint(_, error):
        return JSONResponse(status_code=409, content={'detail': error_detail('constraint_conflict')})

    @app.middleware('http')
    async def limits(request, call_next):
        # Count actual bytes as well as Content-Length, including chunked requests.
        total = 0
        chunks = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > 1048576:
                return JSONResponse(status_code=413, content={'detail': error_detail('request_too_large')})
            chunks.append(chunk)
        request._body = b''.join(chunks)
        return await call_next(request)

    def identity(request: Request):
        token = request.cookies.get('fnote_session', '')
        with Session(engine) as db:
            session = db.get(UserSession, hashlib.sha256(token.encode()).hexdigest())
            if not session or session.revoked or session.expires <= int(time.time()):
                fail(401, 'unauthenticated')
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
                    fail(403, 'csrf_failed')
            return session.user_id

    def mutate(request, user_id, request_id, body, action):
        with write_transaction(engine) as db:
            return idempotent(db, user_id, request_id, request.method + ' ' + request.url.path, body.model_dump(mode='json') if body else {}, lambda: action(db))

    RequestId = Annotated[str, Header(alias='X-Request-ID', min_length=8, max_length=100)]

    @app.get('/api/health')
    def health():
        with engine.connect() as db:
            db.exec_driver_sql('SELECT 1 FROM users LIMIT 1')
        return {'status': 'ok', 'sqlite_version': sqlite3.sqlite_version}

    from .modules.auth.router import register as auth
    from .modules.profile.router import register as profile
    from .modules.catalog.router import register as catalog
    from .modules.workouts.router import register as workouts
    from .agent.router import register as conversations
    for register in (auth, profile, catalog, workouts, conversations):
        register(app, engine, identity, mutate, secure, password_hasher, dummy_hash)

    # Optional production frontend: same origin, no dev server or SSE proxy.
    if os.getenv('FRONTEND_DIST'):
        from pathlib import Path
        from fastapi.responses import FileResponse
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        root = Path(os.environ['FRONTEND_DIST']).resolve(strict=True)
        if not (root / 'index.html').is_file():
            raise RuntimeError('Build the frontend before starting local deployment')
        allowed_hosts = ['127.0.0.1', 'localhost']
        origin_host = urlsplit(os.getenv('APP_ORIGIN', '')).hostname
        if origin_host:
            allowed_hosts.append(origin_host)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

        @app.middleware('http')
        async def local_headers(request, call_next):
            response = await call_next(request)
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Referrer-Policy'] = 'same-origin'
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
            return response

        @app.get('/{path:path}', include_in_schema=False)
        def frontend(path: str):
            if path == 'api' or path.startswith('api/'):
                fail(404, 'not_found')
            candidate = (root / path).resolve()
            if not candidate.is_relative_to(root):
                fail(404, 'not_found')
            if candidate.is_file():
                return FileResponse(candidate)
            if '.' in Path(path).name:
                fail(404, 'not_found')
            return FileResponse(root / 'index.html', headers={'Cache-Control': 'no-store'})

    return app
