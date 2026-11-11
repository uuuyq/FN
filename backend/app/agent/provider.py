"""Chat Completions transport with native tool calling.

The provider only moves messages and validated tool-call batches; it holds no
domain logic and never returns provider bodies or credentials.
"""
import asyncio
import json
import os
from pathlib import Path

import httpx
import yaml
from pydantic import ValidationError

from .contracts import ModelReply, ToolCallRequest


class ProviderError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def settings():
    path = Path(os.getenv('AI_CONFIG_PATH', str(Path(__file__).resolve().parents[3] / 'config.yaml')))
    # The existing personal config has a single api-key. Environment wins.
    try:
        config = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(config, dict):
            raise ValueError()
        return tuple(str(os.getenv(env) or config.get(key) or default) for env, key, default in (
            ('AI_API_KEY', 'api-key', ''), ('AI_MODEL', 'model', 'deepseek-flash'),
            ('AI_BASE_URL', 'base_url', 'https://api.deepseek.com')))
    except Exception:
        raise ProviderError('model_config_invalid') from None


def context_limit():
    """Conservative model context limit used for request budgeting."""
    try:
        path = Path(os.getenv('AI_CONFIG_PATH', str(Path(__file__).resolve().parents[3] / 'config.yaml')))
        config = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
        return int(os.getenv('AI_CONTEXT_LIMIT') or (config or {}).get('context-limit') or 65536)
    except Exception:
        return 65536


def resolve_config(config):
    if config and all(config.get(field) for field in ('api_key', 'model', 'base_url')):
        return str(config['api_key']), str(config['model']), str(config['base_url'])
    key, model, base = settings()
    if not key or not model or not base:
        raise ProviderError('model_not_configured')
    return key, model, base


def _parse_calls(message):
    calls = []
    for item in message.get('tool_calls') or []:
        function = item.get('function') or {}
        raw = function.get('arguments') or '{}'
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except ValueError:
            raise ProviderError('model_invalid_output') from None
        calls.append(ToolCallRequest(id=str(item.get('id') or ''), name=str(function.get('name') or ''), arguments=arguments))
    if not calls or any(not call.id or not call.name for call in calls):
        raise ProviderError('model_invalid_output')
    return calls


class Provider:
    """Chat Completions-compatible transport, isolated from domain orchestration."""

    async def generate(self, messages, tools, config=None, timeout=65, max_tokens=16000):
        # A single wall-clock budget covers requests, retries and backoff.
        try:
            async with asyncio.timeout(timeout):
                return await self._generate(messages, tools, config, timeout, max_tokens)
        except TimeoutError:
            raise ProviderError('model_timeout') from None

    async def _generate(self, messages, tools, config, timeout, max_tokens):
        key, model, base = resolve_config(config)
        payload = {
            'model': model,
            'messages': messages,
            'tools': [{'type': 'function', 'function': schema} for schema in tools],
            'tool_choice': 'auto',
            'parallel_tool_calls': False,
            'max_tokens': max(16, int(max_tokens)),
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for attempt in range(2):
                try:
                    async with client.stream('POST', base.rstrip('/') + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + key}, json=payload) as response:
                        if response.status_code in (429, 502, 503, 504) and attempt == 0:
                            await asyncio.sleep(1)
                            continue
                        if response.status_code != 200:
                            body = (await response.aread())[:65536].decode(errors='replace').lower()
                            if response.status_code == 400 and ('context' in body or 'token' in body):
                                raise ProviderError('context_too_large')
                            raise ProviderError('model_http_error')
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 1048576:
                                raise ProviderError('model_response_too_large')
                            chunks.append(chunk)
                    data = json.loads(b''.join(chunks))
                    choice = data['choices'][0]
                    message = choice.get('message') or {}
                    if choice.get('finish_reason') == 'tool_calls':
                        return ModelReply(type='tool_calls', calls=_parse_calls(message))
                    if choice.get('finish_reason') != 'stop':
                        raise ProviderError('model_incomplete_output')
                    content = message.get('content')
                    if not isinstance(content, str) or not content.strip():
                        raise ProviderError('model_invalid_output')
                    return ModelReply(type='text', content=content)
                except httpx.TransportError:
                    if attempt:
                        raise ProviderError('model_unavailable') from None
                except (ValueError, KeyError, IndexError, TypeError) as error:
                    failure = ProviderError('model_invalid_output')
                    if isinstance(error, ValidationError):
                        # Internal diagnostics contain schema locations/types only,
                        # never rejected values, raw response bodies or credentials.
                        failure.validation = [{'path': list(e['loc']), 'type': e['type']} for e in error.errors(include_input=False, include_context=False)[:5]]
                    raise failure from None
        raise ProviderError('model_unavailable')


PROBE_TOOLS = [{'type': 'function', 'function': {
    'name': 'ping', 'description': '测试工具调用，返回 pong。',
    'parameters': {'type': 'object', 'properties': {}, 'required': []}}}]


async def test_connection(api_key, model, base_url):
    """Verify reachability and the native tool-calling response structure."""
    payload = {'model': str(model), 'messages': [{'role': 'user', 'content': '请调用 ping 工具'}],
               'tools': PROBE_TOOLS, 'tool_choice': 'auto', 'parallel_tool_calls': False, 'max_tokens': 100}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(str(base_url).rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + str(api_key)}, json=payload)
    except httpx.TransportError:
        raise ProviderError('model_unavailable') from None
    if response.status_code in (401, 403):
        raise ProviderError('model_auth_failed')
    if response.status_code != 200:
        raise ProviderError('model_http_error')
    try:
        choice = response.json()['choices'][0]
        calls = choice['message']['tool_calls']
        if choice.get('finish_reason') != 'tool_calls' or not calls:
            raise ValueError()
        if calls[0]['function']['name'] != 'ping':
            raise ValueError()
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProviderError('model_tool_calling_unsupported') from None
