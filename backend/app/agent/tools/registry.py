"""Tool definitions. A tool without a declared read/write kind cannot register."""
from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, Field
from ...schemas import Schema


class WriteSummary(Schema):
    summary: str | None = Field(default=None, max_length=500, description="本次操作的简短说明，概括新增内容、修改差异、删除目标或撤销效果，仅供展示")


@dataclass
class Tool:
    name: str
    description: str
    model: type[BaseModel]
    kind: Literal['read', 'write']
    execution: Literal['direct', 'user_confirmation']
    execute: Callable  # (ctx, params) -> data, scheduled according to execution
    validate: Callable | None = None  # (ctx, params) read-only checks, shared by proposal and confirm
    operation: Callable | None = None  # payload -> card operation label
    summary: Callable | None = None  # (ctx, payload) -> confirmation card summary
    details: Callable | None = None  # (ctx, payload) -> confirmation card details

    def __post_init__(self):
        if self.kind not in ('read', 'write'):
            raise ValueError(f'Tool {self.name} must declare kind=read|write')
        if self.execution not in ('direct', 'user_confirmation'):
            raise ValueError(f'Tool {self.name} needs an execution strategy')
        if self.execution == 'user_confirmation' and not (self.validate and self.operation and self.summary and self.details):
            raise ValueError(f'Confirmation tool {self.name} needs validate, operation, summary and details')


class ToolRegistry:
    def __init__(self, tools):
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name):
        return self._tools.get(name)

    def tools(self, read_only=False):
        return [tool for tool in self._tools.values() if not (read_only and tool.kind != 'read')]

    def schemas(self, read_only=False):
        def clean(schema):
            return {key: value for key, value in schema.items() if key != 'title'}
        return [{'name': tool.name, 'description': tool.description,
                 'parameters': clean(tool.model.model_json_schema())}
                for tool in self.tools(read_only)]
