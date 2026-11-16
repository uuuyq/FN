"""Read current planning inputs without creating a workout."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ...models import now
from ...schemas import Schema
from ...modules.catalog.service import list_exercises
from ...modules.workouts.service import query_workouts, workout_view
from .profile import get_profile
from .registry import Tool
from ..planning import planning_settings


class TrainingPlanContext(Schema):
    target_date: date | None = None


def get_training_plan_context(ctx, params):
    profile = get_profile(ctx, None)
    target = params.target_date or datetime.now(ZoneInfo(profile['timezone'])).date()
    rows, _ = query_workouts(ctx.db, ctx.user_id, end_date=target,
                                limit=profile['history_workout_count'])
    settings = planning_settings()
    return {'target_date': target.isoformat(), 'loaded_at': now(), 'profile': profile,
            'training_principles': profile['training_principles'] or settings['default_principles'],
            'selected_exercises': [
                {key: value for key, value in item.items() if key != 'active'}
                for item in list_exercises(ctx.db, ctx.user_id, active=True)],
            'recent_workouts': [workout_view(ctx.db, row) for row in rows],
            'reference_count': len(rows)}


GET_TRAINING_PLAN_CONTEXT = Tool(name='get_training_plan_context',
    description='生成训练计划或需要刷新计划资料时调用，读取最新个人设置、训练指导原则、用户选择动作和最近若干次完整训练记录。日期默认用户当地今天。',
    model=TrainingPlanContext, kind='read', execution='direct', execute=get_training_plan_context)
