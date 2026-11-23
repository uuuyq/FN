from helpers import write, content


def test_parts_roundtrip_union_and_unclassified(env):
    _, (client, other) = env
    action = write(client, '/exercises', {'name': '复合动作', 'training_parts': ['胸', '肩', '胸']})
    assert action['training_parts'] == ['胸', '肩']
    write(client, '/exercises', {'name': '非法分类', 'training_parts': ['无效']}, status=422)
    data = content()
    data['exercises'].append({'custom_name': '自定义弯举', 'confirm_create': True,
                              'training_parts': ['二头'], 'sets': [{'reps': 8}]})
    data['exercises'].append({'exercise_id': action['id'], 'sets': [{'reps': 8}]})
    first = write(client, '/workouts', {'content': data})
    second = write(client, '/workouts', {'content': data})
    def parts():
        return client.get('/api/workouts/calendar?month=2026-01').json()['days'][0]['parts']
    assert parts() == ['胸', '二头', '肩']
    assert other.get('/api/workouts/calendar?month=2026-01').json()['days'] == []
    write(client, '/workouts/' + first['id'], {'version': first['version']}, 'DELETE')
    assert parts() == ['胸', '二头', '肩']
    write(client, '/workouts/' + second['id'], {'version': second['version']}, 'DELETE')
    write(client, '/workouts', {'content': {'actual_date': '2026-01-02', 'exercises': [
        {'custom_name': '未分类动作', 'confirm_create': True, 'sets': [{'reps': 5}]}]}})
    assert parts() == []


def test_onboarding_persisted_and_isolated(env):
    _, (client, other) = env
    assert client.get('/api/auth/me').json()['onboarding_dismissed'] is False
    write(client, '/auth/onboarding/dismiss', {})
    write(client, '/auth/onboarding/dismiss', {})
    assert client.get('/api/auth/me').json()['onboarding_dismissed'] is True
    assert other.get('/api/auth/me').json()['onboarding_dismissed'] is False


def test_old_edit_preserves_parts(env):
    _, (client, _) = env
    action = write(client, '/exercises', {'name': '测试分类', 'training_parts': ['背']})
    result = write(client, '/exercises/' + action['id'], {'name': '测试分类修改', 'version': action['version']}, 'PUT')
    assert result['training_parts'] == ['背']
    result = write(client, '/exercises/' + action['id'], {'name': result['name'], 'version': result['version'], 'training_parts': []}, 'PUT')
    assert result['training_parts'] == []
