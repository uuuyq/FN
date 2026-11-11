"""Real E2E app with deterministic native tool calls; no external AI access."""
import json
import asyncio
from copy import deepcopy
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo


def _content(reps, weight="60"):
    return {"actual_date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "exercises": [{"exercise_id": "bench-press", "weight_mode": "external",
                           "weight_scope": "total", "sets": [{"weight_kg": weight, "reps": reps}]}]}


def create_app():
    from app.agent.contracts import ModelReply, ToolCallRequest
    from app.agent.provider import ProviderError
    from app.main import create_app as real_create_app
    application = real_create_app()

    def call(tool, **arguments):
        return ModelReply(type="tool_calls", calls=[ToolCallRequest(
            id="e2e-" + uuid4().hex, name=tool, arguments=arguments)])

    class ScriptedProvider:
        failed_once = False

        async def generate(self, messages, tools, config=None, timeout=None, max_tokens=None):
            # Only results after this input can determine the current tool stage.
            index = max(i for i, m in enumerate(messages) if m["role"] == "user")
            text = messages[index]["content"]
            results = [json.loads(m["content"]) for m in messages[index + 1:] if m["role"] == "tool"]
            if text == "检查长历史":
                count = sum(m["role"] == "user" for m in messages) - 1
                return ModelReply(type="text", content=f"历史中保留 {count} 条用户输入。")
            if text == "模拟上下文超限":
                raise ProviderError("context_too_large")
            if text == "模拟模型超时":
                raise ProviderError("model_timeout")
            if text == "循环查询":
                return call("list_workouts", latest=True)
            if text == "慢速记录":
                await asyncio.sleep(3)
                return call("save_workout", content=_content(8))
            if text == "故障后重试":
                if not self.failed_once:
                    self.failed_once = True
                    raise ProviderError("model_unavailable")
                return ModelReply(type="text", content="重试成功，原输入未重复保存。")
            if text == "信息不全":
                return ModelReply(type="text", content="卧推的重量和次数是多少？也可以明确留空。")
            if text == "直接写入，重量次数留空":
                return call("save_workout", content=_content(None, None))
            if text == "查询训练":
                if not results:
                    return call("list_workouts", limit=20)
                data = results[-1]["data"]
                return ModelReply(type="text", content=f"查询完成：共 {data['total']} 条训练。")
            if text in ("删除这条记录", "修改为10次", "再记录一次"):
                if not results:
                    return call("list_workouts", latest=True)
                data = results[-1]["data"]
                if "items" in data:
                    if not data["items"]:
                        return ModelReply(type="text", content="没有找到训练记录。")
                    target = data["items"][0]
                    if text == "删除这条记录":
                        return call("delete_workout", workout_id=target["id"], expected_version=target["version"])
                    return call("get_workout", workout_id=target["id"])
                updated = deepcopy(data["content"])
                updated.pop("missing_information", None)
                for exercise in updated["exercises"]:
                    exercise.pop("name_snapshot", None)
                updated["exercises"][0]["sets"][0]["reps"] = 10
                return call("save_workout", content=updated, workout_id=data["id"], expected_version=data["version"])
            if text == "第一组改9次":
                return call("save_workout", content=_content(9))
            if text == "自定义动作记录":
                data = _content(5)
                data["exercises"][0].pop("exercise_id")
                data["exercises"][0]["custom_name"] = "端到端自定义划船"
                return call("save_workout", content=data)
            if text in ("更新个人条件", "更新动作偏好"):
                raw = messages[1]["content"]
                runtime = json.JSONDecoder().raw_decode(raw[raw.index("{"):])[0]
                if text == "更新个人条件":
                    return call("update_profile", **{**runtime["profile"], "goal": "端到端增肌目标"})
                entry = next(e for e in runtime["catalog"] if e["id"] == "bench-press")
                return call("update_preferences", items=[{"exercise_id": entry["id"],
                    "version": entry["preference_version"], "available": True}])
            if text == "新增器械":
                return call("add_equipment", name="端到端弹力带")
            if text in ("端到端记录", "取消新增测试"):
                return call("save_workout", content=_content(8))
            raise AssertionError(f"Unscripted E2E input: {text!r}")

    application.state.ai_provider = ScriptedProvider()
    return application
