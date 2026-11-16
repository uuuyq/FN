"""Tool registry, confirmation wrapping and the confirm/cancel contract."""
from helpers import call, content, make_workout, reply, send, setup, write
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent.tools import build_registry
from app.agent.tools.registry import Tool
from app.models import ConversationAction, Workout


def count(engine, model):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def last_event(engine, cid):
    with Session(engine) as db:
        from app.models import Message
        rows = db.scalars(select(Message).where(Message.conversation_id == cid, Message.role == 'event', Message.event_kind != 'action_result').order_by(Message.sequence)).all()
        return rows[-1] if rows else None


def test_registry_requires_kind_and_filters_read_only():
    registry = build_registry()
    assert {tool.name for tool in registry.tools()} == {'get_profile', 'get_training_plan_context', 'list_workouts', 'get_workout', 'save_workout',
        'delete_workout', 'update_profile', 'update_preferences', 'add_equipment', 'add_exercise', 'list_operations', 'undo_operation'}
    assert all(tool.kind == 'read' for tool in registry.tools(read_only=True))
    assert {tool.name for tool in registry.tools(read_only=True)} == {'get_profile', 'get_training_plan_context', 'list_workouts', 'get_workout', 'list_operations'}
    schemas = registry.schemas()
    assert all(schema['name'] and schema['description'] and schema['parameters'].get('type') == 'object' for schema in schemas)
    save = registry.get('save_workout')
    with pytest.raises(ValueError):
        Tool(name='x', description='x', model=save.model, kind='admin', execution='direct', execute=save.execute)


def test_save_workout_schema_hides_internal_fields_and_documents_inputs():
    registry = build_registry()
    save = next(schema for schema in registry.schemas() if schema['name'] == 'save_workout')
    parameters = save['parameters']
    def resolve(schema):
        return parameters['$defs'][schema['$ref'].split('/')[-1]] if '$ref' in schema else schema
    # Nested models arrive as $defs references; follow them to the real fields.
    content_props = resolve(parameters['properties']['content'])['properties']
    # Server-side authorization fields never reach the model schema.
    assert 'confirm_create' not in content_props
    assert 'missing_information' not in content_props
    exercise_props = resolve(content_props['exercises']['items'])['properties']
    assert 'confirm_create' not in exercise_props
    assert '公斤重量' in resolve(exercise_props['sets']['items'])['properties']['weight_kg']['description']
    assert '新建个人动作的名称' in exercise_props['custom_name']['description']
    assert 'YYYY-MM-DD' in content_props['actual_date']['description']
    assert 'weight_mode' not in exercise_props and 'weight_scope' not in exercise_props


def test_write_tool_proposes_card_without_touching_business_data(env):
    engine, (a, _) = env
    cid, provider = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推')
    assert result['status'] == 'succeeded'
    assert result['result']['type'] == 'confirmation_required'
    assert result['result']['operation'] == 'create_workout'
    assert '卧推' in result['result']['summary']
    assert result['result']['allowed_operations'] == ['confirm', 'cancel']
    assert count(engine, Workout) == 0
    snapshot = a.get('/api/conversations/' + cid).json()
    action = snapshot['actions'][0]
    assert action['status'] == 'pending' and action['tool_name'] == 'save_workout'
    assert action['details']['creating_custom'] == []
    # The model never sees request_confirmation tools.
    assert all(schema['name'] != 'request_confirmation' for schema in provider.calls[0]['tools'])


def test_confirm_executes_once_replays_idempotent_and_records_event(env):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推')
    request_id = str(uuid4())
    confirmed = write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1}, request_id=request_id)
    assert confirmed['status'] == 'confirmed'
    assert confirmed['result']['workout_id']
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1
    replay = write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1}, request_id=request_id)
    assert replay['status'] == 'confirmed'
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1
    event = last_event(engine, cid)
    assert event.event_kind == 'action_confirmed'
    assert '已确认执行' in event.content


def test_cancel_keeps_business_data_and_is_final(env):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推')
    cancelled = write(a, '/conversation-actions/' + result['result']['action_id'] + '/cancel', {'version': 1})
    assert cancelled['status'] == 'cancelled' and cancelled['allowed_operations'] == []
    assert count(engine, Workout) == 0
    write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1}, status=409)
    assert last_event(engine, cid).event_kind == 'action_cancelled'


def test_confirm_cross_user_is_404_and_wrong_version_is_409(env):
    _, (a, b) = env
    cid, _ = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推')
    action_id = result['result']['action_id']
    write(b, '/conversation-actions/' + action_id + '/confirm', {'version': 1}, status=404)
    write(b, '/conversation-actions/' + action_id + '/cancel', {'version': 1}, status=404)
    write(a, '/conversation-actions/' + action_id + '/confirm', {'version': 2}, status=409)
    write(a, '/conversation-actions/' + action_id + '/confirm', {'version': 1})


def test_read_only_mode_rejects_write_tool(env):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推', mode='read')
    assert result['status'] == 'failed'
    assert result['error'] == 'read_only_turn'
    assert count(engine, Workout) == 0
    assert count(engine, ConversationAction) == 0


def test_update_flow_conflict_marks_action_conflict_without_overwrite(env):
    _, (a, _) = env
    _, workout = make_workout(a)
    def model(messages, tools):
        return call('t1', 'save_workout', content=content(), workout_id=workout['id'], expected_version=1)
    cid, _ = setup(a, model)
    result = send(a, cid, '把卧推改一下')
    assert result['result']['operation'] == 'update_workout'
    # The record changes underneath while the card is pending.
    changed = dict(content())
    changed['exercises'][0]['sets'] = [{'weight_kg': '90', 'reps': 3}]
    write(a, '/workouts/' + workout['id'], {'version': 1, 'content': changed}, 'PUT')
    outcome = write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1})
    assert outcome['status'] == 'conflict'
    current = a.get('/api/workouts/' + workout['id']).json()
    assert current['version'] == 2
    assert current['content']['exercises'][0]['sets'][0]['weight_kg'] == '90'


def test_confirm_crash_rolls_back_without_partial_data(env, monkeypatch):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: reply('已收到执行结果') if messages[-1]['role'] != 'user' and any(m.get('role') == 'tool' and '"status"' in m.get('content', '') for m in messages) else call('t1', 'save_workout', content=content()))
    result = send(a, cid, '记录卧推')
    from app.agent.tools import workouts as workout_tools
    original = workout_tools.save_workout
    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('fail after insert')
    monkeypatch.setattr(workout_tools, 'save_workout', broken)
    outcome = write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1})
    assert outcome['status'] == 'failed'
    assert count(engine, Workout) == 0
    assert count(engine, ConversationAction) == 1
    monkeypatch.setattr(workout_tools, 'save_workout', original)
    # A new proposal can still be confirmed after the failure.
    result2 = send(a, cid, '再记录一次')
    write(a, '/conversation-actions/' + result2['result']['action_id'] + '/confirm', {'version': 1})
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1


def test_correctable_tool_error_returns_to_model(env):
    engine, (a, _) = env
    calls = {'n': 0}
    def model(messages, tools):
        calls['n'] += 1
        if calls['n'] == 1:
            bad = content()
            bad['exercises'][0]['exercise_id'] = 'missing-exercise'
            return call('t1', 'save_workout', content=bad)
        tool_messages = [m for m in messages if m.get('role') == 'tool']
        assert tool_messages and '"ok": false' in tool_messages[-1]['content']
        return reply('那个动作不存在，请说明具体动作。')
    cid, _ = setup(a, model)
    result = send(a, cid, '记录未知动作')
    assert result['status'] == 'succeeded'
    assert result['result']['type'] == 'reply'
    assert count(engine, Workout) == 0
    assert calls['n'] == 2
    snapshot = a.get('/api/conversations/' + cid).json()
    tool_rows = [m for m in snapshot['messages'] if m['role'] == 'tool']
    assert tool_rows and 'exercise_not_found' in tool_rows[0]['content']


def test_update_card_shows_before_and_after(env):
    _, (a, _) = env
    _, workout = make_workout(a)
    changed = dict(content())
    changed['exercises'] = [{**content()['exercises'][0], 'sets': [{'weight_kg': '70', 'reps': 5}]}]
    cid, _ = setup(a, lambda messages, tools: call('t1', 'save_workout', content=changed,
                                                   workout_id=workout['id'], expected_version=1))
    result = send(a, cid, '把卧推改成 70 公斤 5 次')
    details = result['result']['details']
    assert details['before']['exercises'][0]['sets'][0]['weight_kg'] == '60.125'
    assert details['after']['exercises'][0]['sets'][0]['weight_kg'] == '70'
    # Names are resolved so the user sees real exercise labels, not raw IDs.
    assert details['after']['exercises'][0]['name'] == '杠铃卧推'
    write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1})
    assert a.get('/api/workouts/' + workout['id']).json()['content']['exercises'][0]['sets'][0]['weight_kg'] == '70'


def test_custom_exercise_created_only_after_confirmation(env):
    engine, (a, _) = env
    custom = {'actual_date': '2026-01-02', 'exercises': [{'custom_name': '自创动作', 'sets': [{'reps': 5}]}]}
    cid, _ = setup(a, lambda messages, tools: call('t1', 'save_workout', content=custom))
    result = send(a, cid, '记录自创动作')
    assert result['result']['details']['creating_custom'] == ['自创动作']
    assert '确认后将创建自定义动作' in result['result']['summary'] or '自创动作' in result['result']['summary']
    assert count(engine, Workout) == 0
    write(a, '/conversation-actions/' + result['result']['action_id'] + '/confirm', {'version': 1})
    saved = a.get('/api/workouts?on=2026-01-02').json()['items'][0]
    assert saved['content']['exercises'][0]['name'] == '自创动作'
