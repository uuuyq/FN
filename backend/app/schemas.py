from datetime import date, time
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, AnyHttpUrl, field_validator, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Version(Schema):
    version: int = Field(ge=1)


class Login(Schema):
    username: str = Field(min_length=1, max_length=100)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=1024)


class Register(Login):
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=12, max_length=1024)
    password_confirmation: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=12, max_length=1024)

    @model_validator(mode='after')
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError('Passwords must match')
        return self


class Profile(Version):
    days_per_week: int | None = Field(default=None, ge=1, le=7)
    minutes_per_session: int | None = Field(default=None, ge=1, le=1440)
    preferences: str = Field(default='', max_length=10000)
    training_principles: str = Field(default='', max_length=16000)
    history_workout_count: int = Field(default=7, ge=1, le=50)
    timezone: str = 'Asia/Shanghai'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('Unknown IANA timezone')
        return value


class AiConfigTest(Schema):
    reasoning_effort: Literal['none', 'low', 'high', 'max'] = 'high'
    base_url: AnyHttpUrl
    model: str = Field(min_length=1, max_length=100)
    api_key: Annotated[str, StringConstraints(strip_whitespace=False)] | None = Field(default=None, min_length=1, max_length=1024)


class AiConfigSave(AiConfigTest, Version):
    pass


Name = Annotated[str, Field(min_length=1, max_length=100)]

Category = Literal['胸部', '背部', '肩部', '手臂', '腿臀', '核心', '有氧与全身', '其他']


TrainingPart = Literal['胸', '背', '腿', '二头', '三头', '肩', '腹']


class ExerciseInput(Schema):
    training_parts: list[TrainingPart] = Field(default_factory=list, max_length=7)
    name: Name
    aliases: str = Field(default='', max_length=2000)
    primary_muscles: str = Field(default='', max_length=2000)
    secondary_muscles: str = Field(default='', max_length=2000)
    equipment: str = Field(default='', max_length=2000)
    description: str = Field(default='', max_length=4000)
    category: Category = '其他'


class ExerciseUpdate(ExerciseInput, Version):
    pass


class Preference(Version):
    exercise_id: str
    active: bool


class PreferenceBatch(Schema):
    items: list[Preference] = Field(min_length=1, max_length=200)


class EquipmentInput(Schema):
    category: Literal['自由重量', '固定器械', '训练架与凳', '有氧器械', '功能训练', '辅助与恢复', '其他'] | None = None
    name: Name
    equipment_id: str | None = None


class EquipmentUpdate(EquipmentInput, Version):
    pass


class SetInput(Schema):
    id: str | None = None
    kind: Literal['working', 'warmup'] = 'working'
    weight_kg: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=3)
    reps: int | None = Field(default=None, strict=True, ge=0, le=10000)
    notes: str = Field(default='', max_length=2000)


class WorkoutExerciseInput(Schema):
    exercise_id: str | None = None
    custom_name: Name | None = None
    confirm_create: bool = False
    training_parts: list[TrainingPart] = Field(default_factory=list, max_length=7)
    sets: list[SetInput] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def identity(self):
        if bool(self.exercise_id) == bool(self.custom_name):
            raise ValueError('Provide exercise_id or custom_name')
        return self


class WorkoutContent(Schema):
    actual_date: date
    actual_time: time | None = None
    notes: str = Field(default='', max_length=4000)
    exercises: list[WorkoutExerciseInput] = Field(min_length=1, max_length=100)
    missing_information: dict[str, Literal['pending', 'asked', 'skipped']] = Field(default_factory=dict)


class WorkoutCreate(Schema):
    content: WorkoutContent


class ContentUpdate(Version):
    content: WorkoutContent
