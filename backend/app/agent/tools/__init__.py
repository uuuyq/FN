"""Agent tools: registry, parameter models, execution and confirmation wrapping."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import registry as registry_module
from .registry import Tool, ToolRegistry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    """Server-provided execution identity; the model never supplies these."""
    db: 'Session'
    user_id: str
    conversation_id: str
    turn_id: str
    mode: str  # 'edit' | 'read'


def build_registry() -> ToolRegistry:
    from .workouts import LIST_WORKOUTS, GET_WORKOUT, SAVE_WORKOUT, DELETE_WORKOUT
    from .profile import UPDATE_PROFILE, GET_PROFILE
    from .training_plan import GET_TRAINING_PLAN_CONTEXT
    from .catalog import UPDATE_PREFERENCES, ADD_EQUIPMENT, ADD_EXERCISE
    from .operations import LIST_OPERATIONS, UNDO_OPERATION
    return ToolRegistry([GET_PROFILE, GET_TRAINING_PLAN_CONTEXT, LIST_OPERATIONS, UNDO_OPERATION, LIST_WORKOUTS, GET_WORKOUT, SAVE_WORKOUT, DELETE_WORKOUT, UPDATE_PROFILE, UPDATE_PREFERENCES, ADD_EQUIPMENT, ADD_EXERCISE])
