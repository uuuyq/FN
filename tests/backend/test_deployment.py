from fastapi.testclient import TestClient
from app.main import create_app


def test_local_static_spa_api_boundary_and_host_security(env,tmp_path,monkeypatch):
    engine,_=env
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<!doctype html><title>FNote</title>')
    (dist/'app.js').write_text('window.test=true')
    monkeypatch.setenv('FRONTEND_DIST',str(dist))
    monkeypatch.setenv('APP_ORIGIN','https://uuuf.online')
    with TestClient(create_app(engine),base_url='http://127.0.0.1') as c:
        for path in ['/','/history']:
            r=c.get(path);assert r.status_code==200 and 'FNote' in r.text
            assert r.headers['x-frame-options']=='DENY' and "connect-src 'self'" in r.headers['content-security-policy']
        assert c.get('/app.js').status_code==200
        assert c.get('/missing.js').status_code==404
        assert c.get('/api/not-real').status_code==404
        assert c.get('/%2e%2e/secret.txt').status_code==404
        assert c.get('/',headers={'Host':'evil.invalid'}).status_code==400
        assert c.get('/api/health',headers={'Host':'uuuf.online'}).status_code==200
        assert c.get('/',headers={'Host':'uuuf.online'}).status_code==200
        assert c.get('/api/health',headers={'Host':'localhost:8765'}).status_code==200


