"""Message and tool-result contracts shared by provider, runner and tools."""
from typing import Literal

from pydantic import Field, model_validator

from ..schemas import Schema


class ToolCallRequest(Schema):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)


class ToolError(Schema):
    code: str
    message: str
    field: str | None = None


class ModelReply(Schema):
    """One complete model response: either text or a batch of tool calls."""
    type: Literal['text', 'tool_calls']
    content: str | None = None
    calls: list[ToolCallRequest] = Field(default_factory=list)

    @model_validator(mode='after')
    def shape(self):
        if self.type == 'tool_calls':
            if not self.calls or self.content is not None:
                raise ValueError('Tool-call replies need calls and no text content')
        elif self.content is None:
            raise ValueError('Text replies need content')
        return self


def tool_result(ok, data=None, error=None):
    result = {'ok': bool(ok)}
    if data is not None:
        result['data'] = data
    if error is not None:
        result['error'] = ToolError.model_validate(error).model_dump()
    return result
