"""Conversation, turn and confirmation HTTP endpoints with SSE."""
import asyncio
import json
import time
from typing import Annotated, Literal

from fastapi import Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import write_transaction
from ..models import Conversation, Message, Turn, ConversationAction, User, now
from ..schemas import Schema, Version
from ..services import owned, serialize, fail
from . import actions as actions_module
from . import conversations as conversations_module
from . import runner, turns
from .provider import Provider, ProviderError, settings

RequestId = Annotated[str, Header(alias='X-Request-ID', min_length=8, max_length=100)]


class ConversationCreate(Schema):
    title: str = Field(default='训练对话', min_length=1, max_length=100)


class SendMessage(Schema):
    text: str = Field(min_length=1, max_length=8000)
    mode: Literal['edit', 'read'] = 'edit'


def register(app, engine, identity, mutate, *_):
    app.state.ai_provider = Provider()
    tasks = {}

    def user_ai_config(user_id):
        with Session(engine) as db:
            config = db.get(User, user_id).ai_config or {}
        return config if all(config.get(field) for field in ('api_key', 'model', 'base_url')) else None

    async def execute(turn_id, user_id, token):
        # The runner owns the single deadline, including provider cancellation.
        try:
            await runner.run(app, turn_id, user_id, token)
        finally:
            if tasks.get(turn_id, (None, None))[1] is asyncio.current_task():
                tasks.pop(turn_id, None)

    def launch(turn_id, user_id):
        with Session(engine) as db:
            row = owned(db, Turn, turn_id, user_id)
            existing = tasks.get(turn_id)
            if row.status == 'running' and (not existing or existing[0] != row.token):
                if existing:
                    existing[1].cancel()
                tasks[turn_id] = (row.token, asyncio.create_task(execute(row.id, user_id, row.token)))

    def read_turn(turn_id, user_id):
        with write_transaction(engine) as db:
            row = owned(db, Turn, turn_id, user_id)
            conversations_module.conversation(db, row.conversation_id, user_id)
            turns.expire(db, row.conversation_id)
            return turns.turn_view(row)

    def stream(turn_id, user_id):
        async def events():
            yield 'event: accepted\ndata: ' + json.dumps({'turn_id': turn_id}) + '\n\n'
            last_heartbeat = time.monotonic()
            while True:
                row = read_turn(turn_id, user_id)
                if row['status'] != 'running':
                    yield 'id: ' + turn_id + ':done\nevent: ' + ('completed' if row['status'] == 'succeeded' else 'failed') + '\ndata: ' + json.dumps(row, ensure_ascii=False) + '\n\n'
                    break
                if time.monotonic() - last_heartbeat > 10:
                    yield ': heartbeat\n\n'
                    last_heartbeat = time.monotonic()
                await asyncio.sleep(.25)
        return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/ai/status')
    def ai_status(user_id=Depends(identity)):
        config = user_ai_config(user_id)
        if config:
            return {'configured': True, 'model': config['model'], 'source': 'user'}
        try:
            key, model, _ = settings()
            return {'configured': bool(key), 'model': model, 'source': 'global'}
        except ProviderError:
            return {'configured': False, 'model': None, 'source': 'global'}

    @app.get('/api/conversations')
    def list_conversations(offset: int = 0, limit: int = 50, user_id=Depends(identity)):
        if offset < 0 or not 1 <= limit <= 200:
            fail(422, 'invalid_query')
        with Session(engine) as db:
            rows = db.scalars(select(Conversation).where(Conversation.user_id == user_id, Conversation.deleted_at.is_(None)).order_by(Conversation.created_at.desc(), Conversation.id.desc()).offset(offset).limit(limit))
            return {'items': [serialize(row) for row in rows]}

    @app.post('/api/conversations')
    def create(body: ConversationCreate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = Conversation(user_id=user_id, title=body.title)
            db.add(row)
            db.flush()
            return serialize(row)
        return mutate(request, user_id, x_request_id, body, action)

    @app.patch('/api/conversations/{object_id}')
    def rename_conversation(object_id: str, body: ConversationCreate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = conversations_module.conversation(db, object_id, user_id)
            row.title = body.title
            return serialize(row)
        return mutate(request, user_id, x_request_id, body, action)

    @app.delete('/api/conversations/{object_id}')
    def delete_conversation(object_id: str, body: Schema, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = owned(db, Conversation, object_id, user_id)
            if row.deleted_at:
                return {'deleted': True, 'id': row.id}
            turns.expire(db, object_id)
            if db.scalar(select(Turn.id).where(Turn.conversation_id == object_id, Turn.status == 'running')):
                fail(409, 'conversation_busy')
            row.deleted_at = now()
            for proposal in db.scalars(select(ConversationAction).where(ConversationAction.conversation_id == object_id, ConversationAction.status == 'pending')):
                proposal.status, proposal.version, proposal.completed_at = 'cancelled', proposal.version + 1, now()
            return {'deleted': True, 'id': row.id}
        return mutate(request, user_id, x_request_id, body, action)

    @app.get('/api/conversations/{object_id}')
    def get_conversation(object_id: str, user_id=Depends(identity)):
        with write_transaction(engine) as db:
            row = conversations_module.conversation(db, object_id, user_id)
            turns.expire(db, object_id)
            messages = db.scalars(select(Message).where(Message.conversation_id == object_id).order_by(Message.sequence))
            turns_rows = db.scalars(select(Turn).where(Turn.conversation_id == object_id).order_by(Turn.created_at, Turn.id))
            action_rows = db.scalars(select(ConversationAction).where(ConversationAction.conversation_id == object_id).order_by(ConversationAction.created_at, ConversationAction.id))
            return {**serialize(row),
                    'messages': [conversations_module.message_view(m) for m in messages],
                    'turns': [turns.turn_view(t) for t in turns_rows],
                    'actions': [actions_module.action_view(a) for a in action_rows]}

    @app.post('/api/conversations/{object_id}/messages')
    async def send(object_id: str, body: SendMessage, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        result = mutate(request, user_id, x_request_id, body, lambda db: turns.start(db, user_id, object_id, body))
        launch(result['id'], user_id)
        return stream(result['id'], user_id)

    @app.get('/api/turns/{object_id}')
    def get_turn(object_id: str, user_id=Depends(identity)):
        return read_turn(object_id, user_id)

    @app.get('/api/turns/{object_id}/events')
    async def recover(object_id: str, user_id=Depends(identity)):
        read_turn(object_id, user_id)
        # Reconnecting observes the existing execution; it never calls the model.
        return stream(object_id, user_id)

    @app.post('/api/turns/{object_id}/retry')
    async def retry(object_id: str, body: Schema, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        result = mutate(request, user_id, x_request_id, body, lambda db: turns.retry(db, user_id, object_id))
        launch(result['id'], user_id)
        return stream(result['id'], user_id)

    @app.post('/api/conversation-actions/{object_id}/{operation}')
    async def action(object_id: str, operation: Literal['confirm', 'cancel'], body: Version, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def decide(db):
            row = owned(db, ConversationAction, object_id, user_id)
            if operation == 'confirm' and row.status in ('conflict', 'failed'):
                result = actions_module.action_view(row)
            else:
                result = actions_module.apply(db, user_id, object_id, operation, body.version)
            if row.status in ('confirmed', 'cancelled', 'conflict', 'failed'):
                turns.continue_action(db, user_id, row)
                result = actions_module.action_view(row)
            return result
        result = mutate(request, user_id, x_request_id, body, decide)
        continuation_id = (result.get('result') or {}).get('continuation_turn_id')
        if continuation_id:
            launch(continuation_id, user_id)
        return result
