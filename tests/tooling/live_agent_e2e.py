"""Run real-provider agent acceptance against an isolated seeded database."""
import json
import os
import secrets
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from app.core.database import make_engine
from app.main import create_app
from scripts.seed import seed


def main():
    output = Path(tempfile.mkdtemp(prefix='agent-live-', dir=ROOT / 'runtime'))
    os.environ['DATABASE_URL'] = 'sqlite:///' + (output / 'test.db').as_posix()
    os.environ['COOKIE_SECURE'] = 'false'
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    command.upgrade(config, 'head')
    engine = make_engine()
    seed(engine)
    app = create_app(engine)
    report = {'database': str(output / 'test.db'), 'checks': [], 'conversations': []}

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)


    try:
        with TestClient(app) as client:
            password = secrets.token_urlsafe(18)
            def register(name):
                r = client.post('/api/auth/register', json={'username': name, 'password': password, 'password_confirmation': password})
                assert r.status_code == 200, r.text
                client.headers['X-CSRF-Token'] = r.json()['csrf_token']
            def request(path, method='GET', body=None):
                r = client.request(method, '/api' + path, json=body, headers={'X-Request-ID': str(uuid4())})
                assert r.status_code == 200, r.text
                return r.json()
            def workout(day, exercise='bench-press', weight='60', reps=8, note=''):
                return request('/workouts', 'POST', {'content': {'actual_date': day, 'notes': note,
                    'exercises': [{'exercise_id': exercise, 'sets': [{'weight_kg': weight, 'reps': reps} for _ in range(3)]}]}})
            today = date(2026, 11, 15)
            register('live-other')
            foreign = workout(today.isoformat(), note='OTHER_USER_SECRET')
            register('live-athlete')
            profile = request('/profile')
            request('/profile', 'PUT', {**profile, 'preferences': '目标增肌，喜欢力量训练，避免跳跃',
                'days_per_week': 3, 'minutes_per_session': 45, 'history_workout_count': 7})
            catalog = request('/exercises?limit=200')
            entries = catalog if isinstance(catalog, list) else catalog['items']
            chosen = [request('/exercises/' + eid) for eid in ('bench-press', 'squat', 'deadlift', 'lat-pulldown', 'barbell-row', 'overhead-press')]
            request('/exercise-preferences', 'PUT', {'items': [{'exercise_id': e['id'], 'version': e['preference_version'], 'active': True} for e in chosen]})
            history = [workout((today - timedelta(days=i)).isoformat(), chosen[i % len(chosen)]['id'], str(30+i), 8+i%3) for i in range(1, 10)]
            deleted = workout(today.isoformat(), note='DELETED_SECRET')
            request('/workouts/' + deleted['id'], 'DELETE', {'version': deleted['version']})
            future = workout((today + timedelta(days=1)).isoformat(), note='FUTURE_SECRET')
            check('seed two users, nine history records, deleted and future boundaries', len(history) == 9)
            def new_chat(title):
                cid = request('/conversations', 'POST', {'title': title})['id']
                report['conversations'].append(cid)
                return cid
            def send(cid, text, mode='edit'):
                print('SEND ' + text, flush=True)
                r = client.post('/api/conversations/' + cid + '/messages', json={'text': text, 'mode': mode}, headers={'X-Request-ID': str(uuid4())})
                assert r.status_code == 200, r.text
                events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith('data: ')]
                turn = events[-1]
                data = request('/conversations/' + cid)
                (output / (cid + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                check('turn succeeded: ' + text, turn['status'] == 'succeeded')
                return data, turn
            def calls(data, name):
                return [c for m in data['messages'] for c in (m.get('tool_calls') or []) if c['name'] == name]
            def confirm(data):
                action = next(a for a in reversed(data['actions']) if a['status'] == 'pending')
                result = request('/conversation-actions/' + action['action_id'] + '/confirm', 'POST', {'version': action['version']})
                check('confirm ' + action['operation'], result['status'] == 'confirmed')
                deadline = time.monotonic() + 185
                while any(t['status'] == 'running' for t in request('/conversations/' + data['id'])['turns']):
                    assert time.monotonic() < deadline, 'confirmation continuation timed out'
                    time.sleep(0.25)
                return result
            cid = new_chat('真实模型训练计划')
            data, _ = send(cid, '请生成2026-11-15的训练计划。今天状态良好，没有疼痛，45分钟，直接给完整安排。', 'read')
            check('planning context tool called', bool(calls(data, 'get_training_plan_context')))
            tool_id = calls(data, 'get_training_plan_context')[-1]['id']
            context = json.loads(next(m['content'] for m in data['messages'] if m.get('tool_call_id') == tool_id))['data']
            ids = {w['id'] for w in context['recent_workouts']}
            check('latest seven history records and correct isolation', ids == {w['id'] for w in history[:7]} and foreign['id'] not in ids and future['id'] not in ids and deleted['id'] not in ids)
            check('selected exercise context exact', {e['id'] for e in context['selected_exercises']} == {e['id'] for e in chosen})
            check('Markdown plan and no write action', any(m['role'] == 'assistant' and '> ' in m['content'] for m in data['messages']) and not data['actions'])
            data, _ = send(cid, '改成20分钟，今天有些疲劳，请调整并给出完整更新方案。', 'read')
            check('multi-turn adjustment refreshes context', len(calls(data, 'get_training_plan_context')) >= 2)
            check('planning creates no training record', request('/workouts?on=' + today.isoformat())['total'] == 0)
            cid = new_chat('真实模型训练记录 CRUD')
            data, _ = send(cid, '记录2026-11-15实际完成的杠铃卧推，总重量60公斤，3组，每组8次。')
            check('create asks for confirmation', bool(data['actions']))
            confirm(data)
            records = request('/workouts?on=' + today.isoformat())['items']
            check('created three sets', len(records) == 1 and len(records[0]['content']['exercises'][0]['sets']) == 3)
            wid = records[0]['id']
            send(cid, '查询2026-11-15的训练记录，告诉我实际完成的组次。', 'read')
            data, _ = send(cid, '将刚才2026-11-15那条卧推记录的第一组改成10次，其他保持原样。')
            confirm(data)
            record = request('/workouts/' + wid)
            check('update preserves remaining sets', [s['reps'] for s in record['content']['exercises'][0]['sets']] == [10, 8, 8])
            data, _ = send(cid, '删除刚才2026-11-15的那条训练记录。')
            confirm(data)
            check('delete removes record from query', request('/workouts?on=' + today.isoformat())['total'] == 0)
            cid = new_chat('真实模型个人条件')
            data, _ = send(cid, '将我的单次训练时间改成30分钟，其他个人设置保持原样。')
            check('profile update reads current profile', bool(calls(data, 'get_profile')))
            confirm(data)
            check('profile update preserves preferences', request('/profile')['minutes_per_session'] == 30 and request('/profile')['history_workout_count'] == 7)
    finally:
        engine.dispose()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('ARTIFACTS ' + str(output), flush=True)
    if any(not item['passed'] for item in report['checks']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
