"""Public error messages. Never expose raw exception or provider text."""

MESSAGES = {
    "invalid_credentials": "账号或密码不正确，请重新输入。",
    "unauthenticated": "登录状态已失效，请重新登录；当前修改请先保留。",
    "csrf_failed": "页面验证已失效，请刷新页面后重试。",
    "origin_rejected": "请求来源验证失败，请从本站重新打开页面。",
    "username_taken": "账号已被使用，请换一个名字或返回登录。",
    "conversation_busy": "这个对话正在处理上一轮，请先恢复轮次查看结果。",
    "draft_bound_to_other_conversation": "这份草稿属于另一个对话，请返回原对话继续。",
    "draft_not_editable": "待确认内容已经确认或取消",
    "turn_not_retryable": "本轮无法重试，请恢复轮次查看结果或发送新消息。",
    "workout_confirmation_required": "请先核对完整训练总结，再单独回复“确认写入”；需要修改请直接说明。",
    "workout_trashed": "训练记录已删除，无法修改。",
    "exercise_archived": "该动作已停用，请选择其他动作。",
    "exercise_not_found": "该动作已不存在，请刷新动作列表。",
    "equipment_not_found": "该器械已不存在，请刷新器械列表。",
    "duplicate_exercise": "存在重复动作，请检查后再保存。",
    "shared_exercise_readonly": "共享动作不能修改，请创建自定义动作。",
    "custom_exercise_confirmation_required": "请先确认创建自定义动作。",
    "context_too_large": "对话内容过长，请精简内容或开始新对话。",
    "read_only_turn": "仅查询模式无法修改待确认内容，请切换模式后重新发送",
    "ambiguous_workout_target": "无法确定要修改的训练，请先明确选择目标。",
    "model_invalid_reference": "无法确定引用的动作或记录，请明确说明对象",
    "model_capacity": "模型服务繁忙，请稍后重试。",
    "database_busy": "保存服务繁忙，请稍后重试。",
    "request_too_large": "提交内容过大，请减少内容后重试。",
    "request_id_reused": "本次请求与之前的操作不一致，请刷新数据后重新操作。",
    "execution_expired": "处理已中断",
    "action_not_pending": "该操作已处理，请刷新对话查看结果。",
    "model_unavailable": "暂时无法连接模型服务",
    "model_not_configured": "模型连接尚未配置",
    "model_auth_failed": "模型连接鉴权失败，请检查 API Key。",
    "model_config_invalid": "模型连接配置有误",
    "model_http_error": "模型服务返回错误",
    "model_timeout": "模型处理超时",
    "model_invalid_output": "模型返回的内容未通过校验",
    "model_incomplete_output": "模型返回的内容不完整",
    "model_response_too_large": "模型返回的内容过长",
    "model_tool_calling_unsupported": "模型连接不支持工具调用，请更换模型。",
    "agent_loop_limit": "本轮处理步骤过多，请换一种说法或稍后重试。",
    "version_conflict": "数据已变化，请查看服务端版本后处理本地修改。",
    "not_found": "内容已不存在或无法访问，请刷新后重试。",
    "constraint_conflict": "数据存在冲突，请刷新数据后检查再提交。",
    "stable_id_conflict": "记录标识冲突，请刷新数据后重试。",
    "duplicate_stable_id": "存在重复的记录标识，请检查后重试。",
    "invalid_pagination": "分页参数无效，请刷新后重试。",
    "invalid_query": "查询条件无效，请检查后重试。",
    "invalid_month": "月份无效，请重新选择。",
    "database_error": "服务暂时不可用，请稍后重试。",
    "validation_error": "提交内容不符合要求，请检查填写的信息后重试。",
    "internal_error": "服务发生异常，请稍后重试。",
    "model_failed": "模型处理失败，请恢复轮次查看结果。",
    "model_result_rejected": "模型结果未通过校验，请检查内容后重试。"
}


def error_message(code):
    return MESSAGES.get(code, '未知异常，请稍后重试。')


def error_detail(code, **details):
    return {**details, 'code': code, 'message': error_message(code)}
