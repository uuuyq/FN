"""Message and tool-result contracts shared by provider, runner and tools."""
from typing import Any, Literal

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
            if not self.calls:
                raise ValueError('Tool-call replies need calls')
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


class ExecutionResult(Schema):
    """Scheduler outcome independent of tool permissions and business domain."""
    data: Any = None
    action: object | None = None
    error: ToolError | None = None
    continuation: Literal['continue', 'await_confirmation'] = 'continue'

    def message_result(self):
        return tool_result(self.error is None, data=self.data,
                           error=self.error.model_dump() if self.error else None)
