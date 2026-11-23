"""Shared helpers for agent tests: fake provider, SSE sending, fixtures."""
import asyncio
import json
from uuid import uuid4

from app.agent.contracts import ModelReply, ToolCallRequest


def write(client, path, body, method='POST', request_id=None, status=200):
    response = client.request(method, '/api' + path, json=body, headers={'X-Request-ID': request_id or str(uuid4())})
    assert response.status_code == status, response.text
    return response.json()


def content():
    return {'actual_date': '2026-01-02', 'exercises': [{'exercise_id': 'bench-press', 'sets': [{'weight_kg': '60.125', 'reps': 8}, {'weight_kg': '65', 'reps': 6}, {'kind': 'warmup', 'weight_kg': None, 'reps': None}]}]}


def make_workout(client):
    return None, write(client, '/workouts', {'content': content()})


class FakeProvider:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    async def generate(self, messages, tools, config=None, timeout=None, max_tokens=16000, on_delta=None):
        self.calls.append({'messages': messages, 'tools': tools, 'max_tokens': max_tokens})
        value = self.fn(messages, tools)
        if asyncio.iscoroutine(value):
            value = await value
        if isinstance(value, Exception):
            raise value
        return value


def reply(text):
    return ModelReply(type='text', content=text)


def call(id, name, **arguments):
    return ModelReply(type='tool_calls', calls=[ToolCallRequest(id=id, name=name, arguments=arguments)])


def setup(a, fn):
    provider = FakeProvider(fn)
    a.app.state.ai_provider = provider
    conversation = write(a, '/conversations', {'title': '测试对话'})
    return conversation['id'], provider


def send(a, cid, text='记录', request_id=None, mode='edit'):
    body = {'text': text, 'mode': mode}
    response = a.post(f'/api/conversations/{cid}/messages', json=body, headers={'X-Request-ID': request_id or str(uuid4())})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[0]['turn_id'] == events[-1]['id']
    return events[-1]
