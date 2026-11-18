# 当前 Agent 工具清单

整理日期为 2026-11-15，依据当前工作区的注册表、参数模型、执行器和业务服务。

## 1. 工具总览

当前 `build_registry()` 注册 9 个工具。

| 工具名称 | 用途 | 权限类型 `kind` | 执行策略 `execution` |
| --- | --- | --- | --- |
| `list_workouts` | 按日期分页查询训练摘要 | `read` | `direct` |
| `get_workout` | 获取一条训练的完整内容 | `read` | `direct` |
| `save_workout` | 新增或完整更新训练记录 | `write` | `user_confirmation` |
| `delete_workout` | 删除训练记录 | `write` | `user_confirmation` |
| `update_profile` | 更新用户个人条件 | `write` | `user_confirmation` |
| `update_preferences` | 批量更新动作可用偏好 | `write` | `user_confirmation` |
| `add_equipment` | 新增用户可用器械 | `write` | `user_confirmation` |
| `list_operations` | 查询最近七天的 Agent 训练操作 | `read` | `direct` |
| `undo_operation` | 撤销一次训练操作 | `write` | `user_confirmation` |

`kind` 用于权限过滤与执行校验，`execution` 用于调度。两者分别声明。只读模式提供三个查询工具。

## 2. 通用参数与执行约定

- 所有写工具支持可选 `summary`（最多 500 字），由当前 Agent 概括新增内容、修改差异、删除目标或撤销效果。仅用于展示，空值使用后端摘要，不进入业务模型。卡片默认展示摘要，详情折叠，自定义动作创建和重量/次数缺失由后端独立提示。
- 工具参数使用 Pydantic 模型，拒绝未定义字段，字符串会去除首尾空白。
- 用户身份、数据库会话、会话 ID、轮次 ID 和运行模式由服务端 `ToolContext` 提供。
- `direct` 在调用时执行业务函数，结果返回模型，模型可以继续调用工具或回复。
- `user_confirmation` 在调用时校验参数、保存提案并展示确认卡片。本轮结束，用户确认后再次校验并执行。
- 成功、取消、冲突和失败的真实结果返回模型上下文，触发一次持久化续跑。模型自主决定后续回复与工具调用。
- 确认接口读取服务端保存的提案参数。重复决定复用已有执行结果与续跑轮次。
- 包含用户确认策略的工具批次只允许一个调用。直接执行工具按顺序执行。

## 3. `list_workouts`

按单日、日期范围或动作查询当前用户的未删除记录，返回分页摘要。无日期条件时查询最近记录，按训练日期、时间、创建时间、ID 倒序。

### 参数

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `on` | date 或 null | 否 | `null` | 单日查询，与日期范围互斥 |
| `start_date` / `end_date` | date 或 null | 否 | `null` | 包含边界的日期范围，支持单边界，起始不能晚于结束 |
| `exercise_id` | string 或 null | 否 | `null` | 只返回包含此动作的训练，每条训练仅返回一次 |
| `offset` | integer | 否 | `0` | 分页偏移量，大于等于 0 |
| `limit` | integer | 否 | `20` | 每页数量，范围 1～50 |

### 返回数据

| 字段 | 含义 |
| --- | --- |
| `items` | 摘要列表，每项包含 `id`、`version`、`summary` |
| `total` | 该日期下的记录总数 |
| `has_more` | 是否还有下一页 |
| `next_offset` | 下一页偏移量，末页为 `null` |

## 4. `get_workout`

读取一条归属当前用户的训练记录。

### 参数

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `workout_id` | string | 是 | 训练记录 ID |

### 返回数据

返回记录 `id`、`version`、`deleted_at` 和完整 `content`。训练内容按动作组织组数据，包含稳定组 ID、动作名称、重量、次数和备注。已删除记录的详情由业务服务拒绝读取。

## 5. `save_workout`

通过同一个工具新增或完整更新训练记录。新增对应 `create_workout`，修改对应 `update_workout`。

### 顶层参数

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `content` | ToolContent | 是 | — | 完整训练内容 |
| `workout_id` | string 或 null | 否 | `null` | 修改目标记录 ID |
| `expected_version` | integer 或 null | 否 | `null` | 修改目标记录版本，大于等于 1 |
| `allow_missing` | array of string | 否 | `[]` | 允许缺失的字段名称，可选 `reps`、`weight_kg`，最多 2 项 |
| `assumptions` | array of string | 否 | `[]` | 卡片展示的待核实假设，最多 10 项 |

`workout_id` 与 `expected_version` 必须同时提供或同时为空。修改使用完整内容替换，稳定组 ID 用于保留已有组的身份。

### `content` 字段

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `actual_date` | date | 是 | — | 训练实际发生日期，格式 `YYYY-MM-DD` |
| `actual_time` | time 或 null | 否 | `null` | 训练实际发生时间 |
| `notes` | string | 否 | `""` | 整场训练备注，最多 4000 字符 |
| `exercises` | array of ToolExerciseInput | 是 | — | 动作列表，1～100 项 |

### 每个动作的字段

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `exercise_id` | string 或 null | 条件必填 | `null` | 已有公共或个人动作 ID |
| `custom_name` | string 或 null | 条件必填 | `null` | 新个人动作名称，1～100 字符 |
| `sets` | array of ToolSetInput | 是 | — | 按顺序排列的组列表，1～100 项 |

`exercise_id` 和 `custom_name` 必须且只能选择一个。自定义动作的实际创建发生在确认事务内，卡片会披露待创建名称。

### 每组的字段

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `id` | string 或 null | 否 | `null` | 稳定组 ID，新增组由保存服务生成 |
| `kind` | enum | 否 | `working` | `working` 为正式组，`warmup` 为热身组 |
| `weight_kg` | decimal 或 null | 否 | `null` | 公斤重量，范围 0～10000，最多 3 位小数，十进制字符串可用于传输 |
| `reps` | integer 或 null | 否 | `null` | 次数，严格整数，范围 0～10000 |
| `notes` | string | 否 | `""` | 单组备注，最多 2000 字符 |

重量和次数的 `0` 与 `null` 分别表示零值与未知值。业务层将公斤重量转换为整数克保存。

### 当前业务校验

- 修改时检查归属、删除状态和记录版本。
- 新增时，正式组缺失次数且 `allow_missing` 未包含 `reps`，会返回 `missing_key_information`。
- 当前准备度代码仅强制检查新增训练的正式组次数。热身组以及重量缺失不在这项检查中。
- 动作引用、稳定 ID 和训练结构继续由共享业务服务校验。

### 确认后的业务回执

返回 `workout_id`、更新后的 `version`、训练 `summary` 和撤销日志 `operation_id`。

## 6. `delete_workout`

按 ID 和版本删除当前用户的一条训练记录。

| 字段 | 类型 | 必填 | 含义与约束 |
| --- | --- | --- | --- |
| `workout_id` | string | 是 | 目标训练记录 ID |
| `expected_version` | integer | 是 | 目标记录当前版本，大于等于 1 |

提案与确认阶段检查归属、删除状态和版本。执行软删除，业务回执为 `deleted`、记录 `id` 和撤销日志 `operation_id`。

## 7. `update_profile`

更新完整个人条件。参数继承业务 `Profile` 模型，执行后递增个人条件版本。

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `version` | integer | 是 | — | 当前个人条件版本，大于等于 1 |
| `goal` | string | 否 | `""` | 训练目标，最多 1000 字符 |
| `days_per_week` | integer 或 null | 否 | `null` | 每周训练天数，范围 1～7 |
| `minutes_per_session` | integer 或 null | 否 | `null` | 每次训练分钟数，范围 1～1440 |
| `preferences` | string | 否 | `""` | 训练偏好，最多 4000 字符 |
| `restrictions` | string | 否 | `""` | 训练限制，最多 4000 字符 |
| `timezone` | string | 否 | `Asia/Shanghai` | 有效 IANA 时区 |

执行时保存完整参数模型，省略可选字段会采用表中默认值。卡片包含 `before` 和 `after`。业务回执包含保存后的个人条件及新 `version`。

## 8. `update_preferences`

批量更新指定动作的可用偏好。

| 字段 | 类型 | 必填 | 含义与约束 |
| --- | --- | --- | --- |
| `items` | array of Preference | 是 | 偏好变更列表，1～200 项 |
| `items[].exercise_id` | string | 是 | 公共或个人动作 ID |
| `items[].active` | boolean | 是 | 目标可用状态 |
| `items[].version` | integer | 是 | 当前偏好版本，大于等于 1，对应目录的 `preference_version` |

同一批次的动作 ID 必须唯一。不存在偏好行时，初始版本按 1 检查。存在偏好行时校验当前版本。业务回执的 `items` 包含更新后的动作目录数据。

`active` 表达用户可用偏好，当前业务服务允许读取及引用未启用的动作。

## 9. `add_equipment`

向当前用户的器械列表新增一项。

| 字段 | 类型 | 必填 | 默认值 | 含义与约束 |
| --- | --- | --- | --- | --- |
| `name` | string | 是 | — | 用户器械名称，1～100 字符 |
| `equipment_id` | string 或 null | 否 | `null` | 关联的公共器械 ID |

提供 `equipment_id` 时检查公共器械是否存在。业务回执为新增的用户器械对象，包含个人器械 `id`、`user_id`、公共引用 `equipment_id`、`name` 和 `version`。

## 10. 统一结果结构

直接执行成功的模型工具结果如下。

```json
{
  "ok": true,
  "data": {}
}
```

需要用户确认时，初始工具结果的 `data` 包含 `confirmation_required`、`action_id`、`operation`、操作 `version` 和 `summary`。前端卡片另有结构化详情。

决定完成后，组装模型上下文时将实际结果投影到原工具调用的结果位置，保留原 `tool_call_id`。成功结果如下。

```json
{
  "ok": true,
  "data": {
    "status": "confirmed",
    "action_id": "...",
    "result": {}
  }
}
```

取消时 `status` 为 `cancelled`、`ok` 为 `false`，业务结果为 `null`。冲突或执行失败时 `status` 为 `conflict` 或 `failed`，并附带实际错误。错误字段包含 `code`、`message` 和可选 `field`。

## 11. 当前定义中的职责分布

当前工具定义同时包含字段契约与部分 Agent 行为指导。

- `actual_date` 在参数模型中必填，没有日期默认值。未提供日期时使用上下文 today 的规则保留在 system prompt。
- 工具描述说明完整替换、版本检查、分页查询和确认执行等契约。
- `allow_missing` 与 `assumptions` 承载信息收集与假设披露数据。
- 执行器对 `missing_key_information` 生成的错误消息包含后续追问指导。

本节记录当前实现，便于后续讨论责任划分。

## 12. 源码位置

- 工具注册入口为 `backend/app/agent/tools/__init__.py`。
- 工具声明契约为 `backend/app/agent/tools/registry.py`。
- 训练工具与嵌套参数模型为 `backend/app/agent/tools/workouts.py`。
- 个人条件工具为 `backend/app/agent/tools/profile.py`。
- 偏好和器械工具为 `backend/app/agent/tools/catalog.py`。
- 共享参数模型为 `backend/app/schemas.py`。
- 调度与统一结果为 `backend/app/agent/tools/executor.py` 和 `backend/app/agent/contracts.py`。
- 确认结果的模型上下文投影为 `backend/app/agent/context.py`。

## 13. 操作历史与撤销

`list_operations(workout_id?, offset=0, limit=20)` 按执行时间倒序分页返回当前用户最近七天的成功 Agent 训练操作，每页最多 50 条。返回 `operation_id`、`operation`、`workout_id`、`summary`、`created_at`、`undone`、`can_undo`、`reason`，以及标准分页字段。可撤销状态仅代表查询时状态。

`undo_operation(operation_id, summary?)` 提出撤销，确认时重新检查权限、七天期限、撤销状态、目标版本和动作引用。新增训练撤销为软删除，保留自定义动作目录项。修改和删除恢复操作前完整训练，保留组 ID，版本继续递增。后续发生页面或 Agent 修改会导致版本冲突。重复确认复用结果。

仅成功的 Agent 训练新增、修改、删除生成日志。恢复快照与业务变更原子提交，撤销变更与日志状态也原子提交。撤销不生成可再次撤销的操作。页面写入和旧操作无日志。已提交操作不会因后续模型回复失败而自动撤销。

日志包含来源确认 ID、用户、目标、类型、摘要、原内容、执行后版本和撤销结果。清理任务在七天后清除恢复快照，保留审计信息。初始数据库迁移包含日志表，不回填旧操作。

动作新增参数 `training_parts` 为训练部位数组，取值胸、背、腿、二头、三头、肩、腹。新增个人动作及训练中创建动作均支持，分类随确认卡片展示，空数组表示未分类。
