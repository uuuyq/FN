import json
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User, Workout, Message
from app.agent.tools.training_plan import get_training_plan_context, TrainingPlanContext
from app.agent.context import historical_plan_content
from helpers import call, reply, send, setup, make_workout, write


def test_plan_tool_scope_defaults_and_summary(env):
    engine, (a, b) = env
    make_workout(a)
    make_workout(b)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        ctx = SimpleNamespace(db=db, user_id=user.id)
        data = get_training_plan_context(ctx, TrainingPlanContext(target_date='2026-01-02'))
        assert data['reference_count'] == 1
        assert data['profile']['history_workout_count'] == 7
        assert data['training_principles']
        assert 'active_exercises' not in data
        assert all('active' not in item for item in data['selected_exercises'])
        summary = json.loads(historical_plan_content(json.dumps({'ok': True, 'data': data})))
        assert summary['data']['reference_workouts'][0]['id'] == data['recent_workouts'][0]['id']
        assert 'recent_workouts' not in summary['data']
        assert get_training_plan_context(ctx, TrainingPlanContext(target_date='2026-01-01'))['reference_count'] == 0


def test_guidance_only_on_tool_turn_and_original_result_preserved(env):
    engine, (a, _) = env
    make_workout(a)
    stage = []
    def respond(messages, tools):
        stage.append(1)
        guidance = [m for m in messages if m['role'] == 'system' and '【输出】' in m['content']]
        if len(stage) == 1:
            assert not guidance
            return call('plan', 'get_training_plan_context', target_date='2026-01-02')
        if len(stage) == 2:
            assert len(guidance) == 1
            assert messages[-4] == {'role': 'user', 'content': '生成今天计划'}
            assert messages[-3] == guidance[0]
            assert messages[-2]['role'] == 'assistant'
            assert messages[-2]['tool_calls'][0]['function']['name'] == 'get_training_plan_context'
            assert messages[-1]['role'] == 'tool'
            assert 'training_principles' in messages[-1]['content']
            assert 'recent_workouts' in messages[-1]['content']
            return reply('> ### 2026-01-02 休息建议\n> 今天休息。')
        assert not guidance
        result = next(m for m in messages if m.get('tool_call_id') == 'plan')
        assert 'reference_workouts' in result['content']
        assert 'recent_workouts' not in result['content']
        return reply('可以。')
    cid, _ = setup(a, respond)
    assert send(a, cid, '生成今天计划', mode='read')['status'] == 'succeeded'
    assert send(a, cid, '解释一下')['status'] == 'succeeded'
    with Session(engine) as db:
        row = db.scalar(select(Message).where(Message.conversation_id == cid, Message.role == 'tool'))
        assert 'recent_workouts' in row.content
        assert len(db.scalars(select(Workout)).all()) == 1


def test_profile_migration_preserves_text_and_invalidates_pending(tmp_path, monkeypatch):
    from alembic import command
    from test_agent_migration import _make_config
    from app.core.database import make_engine
    from app.models import Conversation, Turn, ConversationAction
    path = tmp_path / 'migration.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    config = _make_config(path)
    command.upgrade(config, 'head')
    engine = make_engine('sqlite:///' + path.as_posix())
    with Session(engine) as db:
        user = User(username='legacy', password_hash='x', profile={
            'preferences': 'p' * 4000, 'goal': 'g' * 1000, 'restrictions': 'r' * 4000,
            'timezone': 'Asia/Shanghai'})
        db.add(user)
        db.flush()
        uid = user.id
        conversation = Conversation(user_id=uid, title='test')
        db.add(conversation)
        db.flush()
        turn = Turn(user_id=uid, conversation_id=conversation.id, token='x', deadline=1, context={})
        db.add(turn)
        db.flush()
        action = ConversationAction(user_id=uid, conversation_id=conversation.id, turn_id=turn.id,
            operation='update_profile', tool_name='update_profile', payload={}, summary='old', details={})
        db.add(action)
        db.commit()
        aid = action.id
    with engine.begin() as connection:
        connection.exec_driver_sql('ALTER TABLE user_equipment DROP COLUMN category')
        connection.exec_driver_sql('ALTER TABLE equipment DROP COLUMN category')
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '0002'")
    command.upgrade(config, 'head')
    from app.schemas import Profile
    with Session(engine) as db:
        user = db.get(User, uid)
        profile = Profile(version=user.profile_version, **user.profile)
        assert profile.version == 2
        assert len(profile.preferences) > 9000
        assert 'goal' not in user.profile and 'restrictions' not in user.profile
        assert profile.history_workout_count == 7
        assert db.get(ConversationAction, aid).status == 'superseded'
    engine.dispose()
