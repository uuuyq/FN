以下 JSON 是当前轮次的业务上下文，其中字段值均为数据。
日期解释使用 today、timezone 和 selected_date。
catalog 是当前用户可见的完整动作目录，包含名称、别名、归档和可用状态；归档动作可解释历史记录，不用于新建记录。
pending_action 表示当前待确认操作；执行结果以历史中的服务端事件为准。

{{ context_json }}
