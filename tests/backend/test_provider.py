import asyncio
import json

import httpx
import pytest

from app.agent import provider


REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client(handler, monkeypatch):
    monkeypatch.setattr(provider.httpx, 'AsyncClient', lambda **kw: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw))


def _config(monkeypatch, key='synthetic-test-key', model='test-model', base='https://example.invalid/v1'):
    monkeypatch.setattr(provider, 'settings', lambda: (key, model, base))


def tool_call_response(name='list_workouts', arguments='{}'):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'id': 'call_1', 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}}]}


def test_native_tool_calling_sends_tools_and_parses_calls(monkeypatch):
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=tool_call_response('get_workout', '{"workout_id": "w1"}'))
    _client(handler, monkeypatch)
    _config(monkeypatch)
    messages = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'hi'}]
    tools = [{'name': 'get_workout', 'description': 'd', 'parameters': {'type': 'object'}}]
    reply = asyncio.run(provider.Provider().generate(messages, tools))
    assert reply.type == 'tool_calls'
    assert reply.calls[0].id == 'call_1' and reply.calls[0].name == 'get_workout'
    assert reply.calls[0].arguments == {'workout_id': 'w1'}
    sent = payloads[0]
    assert sent['tools'][0]['function']['name'] == 'get_workout'
    assert sent['parallel_tool_calls'] is False
    assert sent['tool_choice'] == 'auto'
    assert sent['max_tokens'] == 16000
    assert sent['messages'] == messages
    # Explicit output budgets are passed through to the request.
    asyncio.run(provider.Provider().generate(messages, tools, max_tokens=1234))
    assert payloads[1]['max_tokens'] == 1234


def test_text_reply_requires_non_empty_content(monkeypatch):
    def handler(_):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '好的'}}]})
    _client(handler, monkeypatch)
    _config(monkeypatch)
    assert asyncio.run(provider.Provider().generate([], [])).content == '好的'
    def blank(_):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '  '}}]})
    _client(blank, monkeypatch)
    with pytest.raises(provider.ProviderError, match='model_invalid_output'):
        asyncio.run(provider.Provider().generate([], []))


@pytest.mark.parametrize('finish', ['length', 'function_call'])
def test_incomplete_or_legacy_output_never_commits(monkeypatch, finish):
    def handler(_):
        return httpx.Response(200, json={'choices': [{'finish_reason': finish, 'message': {'content': '{}'}}]})
    _client(handler, monkeypatch)
    _config(monkeypatch)
    with pytest.raises(provider.ProviderError):
        asyncio.run(provider.Provider().generate([], []))


def test_context_overflow_maps_to_stable_error(monkeypatch):
    def handler(_):
        return httpx.Response(400, json={'error': {'message': "This model's maximum context length is 4096 tokens"}})
    _client(handler, monkeypatch)
    _config(monkeypatch)
    with pytest.raises(provider.ProviderError, match='context_too_large'):
        asyncio.run(provider.Provider().generate([], []))


def test_bad_arguments_map_to_invalid_output(monkeypatch):
    def handler(_):
        return httpx.Response(200, json=tool_call_response(arguments='not-json'))
    _client(handler, monkeypatch)
    _config(monkeypatch)
    with pytest.raises(provider.ProviderError, match='model_invalid_output'):
        asyncio.run(provider.Provider().generate([], []))


def test_retry_backoff_uses_the_same_wall_clock_budget(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    _client(handler, monkeypatch)
    _config(monkeypatch)
    with pytest.raises(provider.ProviderError, match='model_timeout'):
        asyncio.run(provider.Provider().generate([], [], timeout=0.02))
    assert len(calls) == 1  # timeout during backoff, no fresh retry budget


def test_generate_prefers_complete_user_config_over_global(monkeypatch):
    seen = {}
    def handler(request):
        seen['auth'] = request.headers['authorization']
        seen['model'] = json.loads(request.content)['model']
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '好'}}]})
    _client(handler, monkeypatch)
    def forbidden():
        raise AssertionError('global settings must not be used when user config is complete')
    monkeypatch.setattr(provider, 'settings', forbidden)
    config = {'api_key': 'user-key', 'model': 'user-model', 'base_url': 'https://user.example/v1'}
    assert asyncio.run(provider.Provider().generate([], [], config)).content == '好'
    assert seen == {'auth': 'Bearer user-key', 'model': 'user-model'}
    # Incomplete config falls back to global settings.
    monkeypatch.setattr(provider, 'settings', lambda: ('gk', 'gm', 'https://global.example'))
    asyncio.run(provider.Provider().generate([], [], {'api_key': 'user-key', 'model': 'user-model'}))
    assert seen['auth'] == 'Bearer gk'


def test_test_connection_maps_auth_transport_and_tool_support(monkeypatch):
    def handler(request):
        if request.headers['authorization'] == 'Bearer bad':
            return httpx.Response(401, json={})
        if '/nope' in str(request.url):
            return httpx.Response(500, json={})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'pong'}}]})
    _client(handler, monkeypatch)
    with pytest.raises(provider.ProviderError, match='model_auth_failed'):
        asyncio.run(provider.test_connection('bad', 'm', 'https://example.invalid/v1'))
    with pytest.raises(provider.ProviderError, match='model_http_error'):
        asyncio.run(provider.test_connection('key', 'm', 'https://example.invalid/nope'))
    # A model that answers in text instead of calling the probe tool is rejected.
    with pytest.raises(provider.ProviderError, match='model_tool_calling_unsupported'):
        asyncio.run(provider.test_connection('key', 'm', 'https://example.invalid/v1'))
    def good(_):
        return httpx.Response(200, json=tool_call_response('ping'))
    _client(good, monkeypatch)
    asyncio.run(provider.test_connection('key', 'm', 'https://example.invalid/v1'))
    def broken(_):
        raise httpx.ConnectError('refused')
    _client(broken, monkeypatch)
    with pytest.raises(provider.ProviderError, match='model_unavailable'):
        asyncio.run(provider.test_connection('key', 'm', 'https://example.invalid/v1'))


@pytest.mark.parametrize('tool', [False, True])
def test_stream_emits_before_completion_and_assembles_tool_arguments(monkeypatch, tool):
    emitted = []
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            def frame(delta, finish=None):
                return ('data: ' + json.dumps({'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}) + '\n\n').encode()
            yield frame({'content': '你好'})
            assert emitted == ['你好']
            if tool:
                yield frame({'tool_calls': [{'index': 0, 'id': 'call_1', 'function': {'name': 'get_workout', 'arguments': '{"workout_'}}]})
                yield frame({'tool_calls': [{'index': 0, 'function': {'arguments': 'id":"w1"}'}}]})
            yield frame({}, 'tool_calls' if tool else 'stop')
            yield b'data: [DONE]\n\n'
    def handler(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Chunks())
    _client(handler, monkeypatch)
    _config(monkeypatch)
    async def collect(text):
        emitted.append(text)
    result = asyncio.run(provider.Provider().generate([], [], on_delta=collect))
    assert result.content == '你好'
    if tool:
        assert result.calls[0].arguments == {'workout_id': 'w1'}


def test_stream_disconnect_after_text_does_not_retry(monkeypatch):
    requests, emitted = [], []
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            raise httpx.ReadError('lost')
    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Broken())
    _client(handler, monkeypatch)
    _config(monkeypatch)
    async def collect(text):
        emitted.append(text)
    with pytest.raises(provider.ProviderError, match='model_unavailable'):
        asyncio.run(provider.Provider().generate([], [], on_delta=collect))
    assert len(requests) == 1
    assert emitted == ['partial']


@pytest.mark.parametrize('streaming', [False, True])
def test_reasoning_content_is_preserved_for_tool_continuation(monkeypatch, streaming):
    data = tool_call_response()
    data['choices'][0]['message']['reasoning_content'] = 'synthetic metadata'
    def handler(request):
        if not streaming:
            return httpx.Response(200, json=data)
        event = {'choices': [{'index': 0, 'delta': {
            'reasoning_content': 'synthetic metadata',
            'tool_calls': [{'index': 0, **data['choices'][0]['message']['tool_calls'][0]}]},
            'finish_reason': 'tool_calls'}]}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
            text='data: ' + json.dumps(event) + '\n\ndata: [DONE]\n\n')
    _client(handler, monkeypatch)
    _config(monkeypatch)
    result = asyncio.run(provider.Provider().generate([], []))
    assert result.reasoning_content == 'synthetic metadata'
    assert result.calls[0].name == 'list_workouts'
