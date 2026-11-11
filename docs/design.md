# Fnote Design

更新日期：2026-11-10。

## 1. 产品与业务边界

Fnote 是个人训练记录应用。用户通过日历回顾训练，通过多轮对话录入、补充、修改和查询训练。服务端保存结构化的真实训练数据，模型负责理解表达和提出业务操作，业务服务负责校验与执行。

后端由三类能力组成：

| 能力 | 职责 |
| --- | --- |
| 训练记录 | 记录增删改查、按日期与动作筛选、月度日历聚合；维护动作目录作为记录的基础数据 |
| 对话 Agent | 会话与消息管理、上下文组装、模型调用、业务操作分发、用户确认和执行结果反馈 |
| 用户与配置 | 账号认证、数据隔离、个人条件、动作与器械偏好、时区和 AI 连接配置 |

训练计划生成、任务执行追踪和完成度管理不属于当前业务范围。

## 2. 系统架构

```text
React / TypeScript / Ant Design
              │ 同源 /api，轮次事件通过 SSE 获取
              ▼
           FastAPI
              ├── auth：账号与会话
              ├── profile：个人条件与 AI 配置
              ├── catalog：动作、器械与用户偏好
              ├── workouts：训练查询与变更
              └── agent：会话、工具、循环与确认编排
                       │
                 共享业务服务
                       │
                SQLAlchemy / SQLite

agent ── Provider ── Chat Completions 原生 tool calling
Windows 任务计划程序 ── scripts.cleanup_workouts ── SQLite
```

模型不持有数据库连接，也不直接执行 SQL。HTTP 操作与对话操作复用训练保存、删除、个人条件和目录维护等业务函数。模型调用发生在数据库写事务之外。

开发环境：Vite 5173 将 `/api` 代理到后端 8000。
本机部署：FastAPI 在 `127.0.0.1:8765` 同时提供前端构建产物、API 和 SSE，采用单进程运行。

## 3. 训练记录

### 数据结构

一条训练对应多个有序动作，每个动作对应多个有序训练组。

| 层级 | 主要内容 |
| --- | --- |
| Workout | 所属用户、实际日期、可选时间、备注、创建时间、状态、删除时间、版本 |
| WorkoutExercise | 动作引用、当时名称快照、顺序、计重方式与计重口径 |
| WorkoutSet | 顺序、热身或正式组、重量、次数、备注 |

重量在数据库中存为整数克，接口通过公斤字符串表达，避免浮点误差。未知重量和次数保留空值，未知计重方式与口径使用 `unknown`。自重、附加重量、辅助重量和外部重量分别表达；总重量和单侧重量分别表达。

动作与组使用稳定 ID。编辑记录时保留未变更项的 ID；名称快照使历史记录不受目录改名影响。完整训练的写入在一个事务内完成，校验失败整体回滚。

### 查询与修改

- 列表支持实际日期、起止日期、动作过滤与分页。
- 月度日历返回训练天数和每天的记录数量。
- 详情返回完整动作与逐组数据。
- 修改携带已读取的版本；版本不匹配返回冲突，避免覆盖其他修改。
- 对话保存结果由服务端根据实际持久化记录生成，包含记录 ID 和训练总结。

手动录入使用 WorkoutDraft 暂存、自动保存与确认接口；对话写入使用 ConversationAction 确认卡片，两者复用相同训练业务函数，但不相互接管草稿。训练查询共用 SQL 分页，HTTP 列表返回完整记录和 total；Agent 工具返回摘要，再按需读取详情。

### 删除与定时清理

删除立即将记录标记为 `closed`，写入 UTC 删除时间并递增版本。列表、日历、详情和对话历史查询不再向用户返回该记录。

物理清理由 Windows 任务计划程序统一触发，应用查询不触发清理。任务每天检查已关闭且删除满七天的训练，在一个写事务中清除其逐组数据、动作明细、引用和主记录。未满七天的记录保留。七天是最短保留时间，实际删除时间取决于任务下一次成功运行；当前不提供回收站或恢复接口。

任务入口为 `backend/scripts/cleanup_workouts.py`，固定操作项目的 `backend/data/fitplan.db`。数据库不存在时任务失败，不会因工作目录错误创建空数据库。成功记录删除条数，失败记录异常并返回非零退出码。

注册命令在项目根目录执行：

```powershell
./deploy/register-workout-cleanup.ps1
```

默认任务名 `FitPlan-WorkoutCleanup`，每天本机时间 03:00 运行。可用 `-At '04:00'` 指定时间，或用 `-Python` 指定解释器。默认查找 Conda `fitplan` 环境。

任务采用当前用户交互式登录身份，需用户已登录；错过时间后在可用时补跑，禁止重叠执行，最长运行十分钟。日志为 `runtime/workout-cleanup.log`，单文件上限 1 MiB，保留三个轮转备份。`deploy/start-local.ps1` 启动时会用当前解释器自动注册（覆盖同名同目录任务，幂等），`deploy/stop-local.ps1` 停止时会注销该任务；上面的独立命令用于在不启动服务时单独注册。

## 4. 对话 Agent

### 会话与轮次

Conversation 保存会话标题、归属和删除标记；Message 保存完整消息历史，`role` 为 `user / assistant / tool / event`，包含 `content`、`tool_calls`、`tool_call_id`、会话内单调递增 `sequence`，服务端确认结果以 `event_kind` 与结构化 `event_data` 记录；Turn 保存执行状态、运行配置（读写模式、选中日期）、执行令牌、租约截止时间和结果。

会话支持创建、列表、改名、删除和历史读取。每个会话同时最多执行一个轮次，全局最多四个有效运行轮次。

处理流程：

1. 校验账号、会话归属、并发容量；将旧待确认操作标记 superseded，为中断轮次补齐缺失的工具结果，创建 Turn 并保存用户消息。
2. 组装固定 System Prompt、运行上下文 JSON、按 sequence 排序的完整历史，在事务外调用模型。
3. 文本回复直接落库并结束；查询工具串行执行并将结果回传模型继续；写工具生成待确认操作后立即结束本轮。
4. 每次模型输出和工具结果均实际落库；写事务中检查执行令牌、租约、归属与版本。
5. SSE 返回轮次完成或失败事件；断线后可重新读取同一轮次状态。

Turn 状态为 `running / succeeded / failed / conflict / interrupted`；成功结果区分 `reply` 与 `confirmation_required`。轮次租约 200 秒，单轮总预算 180 秒、最多 8 次模型调用与 12 次工具调用，均为服务端配置。失败或中断轮次支持显式重试，仅限无后续用户消息的轮次；重试保留失败轨迹，不重复保存用户消息。后台执行使用进程内异步任务，进程重启后不自动续跑；过期轮次在后续访问时被标记为中断。

轮次使用统一截止时间，模型请求、重试和退避共用总预算；模型返回后、工具执行前后以及成功提交前检查期限，超时不生成新的确认卡片。工具批次超过剩余额度时整批拒绝，每个调用均保存额度不足结果，随后结束轮次。

训练保存由共享业务函数校验归档动作：新增训练及修改时新增或替换的动作不得引用归档项；保留相同稳定条目 ID 和动作 ID 的历史引用允许继续使用。历史查询与展示不受影响，按钮确认时重新检查。

SSE 提供接受、心跳和最终状态通知，当前没有模型逐字输出。

### 模型契约与业务操作

模型通过 Chat Completions 兼容接口的原生 tool calling 交互；不支持工具调用的连接在配置测试时明确报错。工具定义由注册表统一生成 JSON Schema，并通过同一 Pydantic 参数模型校验调用。不向模型暴露 `request_confirmation` 等确认元工具。

初始工具：`list_workouts / get_workout / save_workout / delete_workout / update_profile / update_preferences / add_equipment`。查询工具分页返回（默认 20、上限 50，`has_more` 与 `next_offset`），写入类工具只校验并挂起为待确认操作。工具错误区分模型可修正（回传工具结果继续）与执行失效（终止轮次）。上下文超限统一映射为 `context_too_large`，不截断任何目录或消息。

包含写工具的模型返回批次只允许一个调用，否则整批返回可修正错误。关闭 parallel_tool_calls，工具串行执行。

### 确认与可信边界

写工具内部统一走确认包装器：校验参数与权限，保存不可变 payload 与契约版本，生成确认卡片后结束轮次。修改时保留输入中的稳定条目 ID，新条目未提供 ID 时由保存服务生成。自定义动作创建在卡片中披露，实际创建延迟到确认事务内。

确认接口从数据库读取工具名称、契约版本与 payload，经注册表解析到原业务函数，在事务内重新检查归属与版本，SAVEPOINT 内执行并保存回执；不重新进入确认循环。取消只改状态；重复确认返回原回执；业务冲突标记 `conflict`，执行失败标记 `failed`。新用户消息使旧待确认操作 superseded，并以服务端事件写入历史。

卡片数据（`action_id / operation / status / version / summary / details / allowed_operations`）随轮次结果与历史接口返回，便于刷新恢复。每个会话最多一个 pending 操作。

Action 状态为 `pending / confirmed / cancelled / superseded / conflict / failed`。确认与取消返回最新 Action；HTTP 200 也可能携带 conflict/failed，前端以 status 和 result.error 判断实际结果。按钮只提交 Action.version，执行数据库保存的参数，不接收新的业务 payload。确认后由服务端生成执行事件，不再调用模型。修改训练和个人条件的 details 提供 before/after 供用户核对。

### 上下文

每次模型调用收到：固定 System Prompt、一条运行上下文 JSON（today、timezone、selected_date、读写模式、个人条件、器械、完整动作目录、待确认状态）、按 sequence 排序的完整会话历史（含工具调用、工具结果与服务端事件），以及本轮新增的工具消息。目录不设条数上限；历史不做裁剪或摘要。

请求前做保守 token 估算（CJK 每字约 1 token）加输出预留与字节上限检查，超限返回 `context_too_large`；模型上下文上限为连接配置（`config.yaml` 的 `context-limit`，默认 65536，环境变量 `AI_CONTEXT_LIMIT` 优先）。只读模式只注册查询工具并在 System 中注明。当前没有长期对话摘要或跨会话记忆。

System Prompt 与运行上下文模板分别位于 agent/prompts/system.md 和 context.md；工具描述及字段说明与工具参数模型集中维护，通过 API 的 tools 字段发送。动作标准名、别名、肌群与器械信息全量注入，由模型理解和匹配；当前不做额外检索、匹配评分或自动同义词归并。未匹配动作可在用户核对后创建为个人动作。

### 前端对话展示

历史按 Message.sequence 组织：user 和非空 assistant.content 显示聊天文本，tool 与纯工具调用消息隐藏，event 显示服务端结果。由 Turn.result.action_id 关联最新 Action，每张确认卡片只渲染一次；卡片状态以历史 actions 为准，不以轮次中生成时的快照为准。

新消息被接受后旧卡片失效；等待按钮不占用运行轮次，用户可以继续补充内容。确认成功刷新训练、日历及配置数据；取消与失败仅更新操作状态。重放确认复用请求 ID，SSE 重连只观察原轮次。上下文超限提示新建会话并隐藏重试入口；模型超时等失败仍可在没有后续用户输入时显式重试。页面刷新默认进入空白会话，可从历史打开并恢复运行轮次和确认卡片。

## 5. 用户、目录与配置

账号支持注册、登录、退出、修改用户名和密码。密码采用 Argon2 哈希；修改密码撤销已有会话。会话通过 HttpOnly Cookie 传递，默认有效期七天。

个人条件包括训练目标、每周频次、单次时长、偏好、限制和 IANA 时区。动作目录包含公共动作与用户自定义动作，以及别名、肌群、器械信息和归档状态。用户可以维护可用动作及自己的器械列表。

内置目录由 `backend/scripts/catalog_data.py` 维护，通过 `python -m scripts.seed` 导入。重复导入只补缺失 ID，不覆盖已有条目。保持稳定 ID，避免把同义名称作为新动作。

目录分类整理参考 [ACE Exercise Library](https://www.acefitness.org/resources/everyone/exercise-library/) 和 [MuscleWiki](https://musclewiki.com/exercises)。中文名称、英文别名和主要肌群为项目人工整理，并非来源数据库完整抓取或逐项验证结果，不包含教程、图片或视频。

用户 AI 配置支持连接测试和保存，包含兼容接口地址、模型和密钥。完整的用户配置优先，否则使用服务器默认配置。服务器从根目录 `config.yaml` 读取 `api-key / model / base_url`，环境变量 `AI_API_KEY / AI_MODEL / AI_BASE_URL` 优先；应用不自动加载 `.env`。配置读取接口不返回完整密钥。用户配置中的密钥当前存于数据库 JSON，数据库及备份均应作为包含凭据的数据管理。

## 6. 一致性与接口约定

- 用户资源按所属用户隔离，模型提供的资源 ID 仍需服务端授权。
- 写操作校验 CSRF Token；认证接口校验 Origin。
- `X-Request-ID` 与请求摘要用于幂等回执，相同 ID 的不同请求内容返回冲突。
- `version` 实现乐观并发控制，冲突由用户重新核对后提交。
- SQLite 启用外键、WAL 和 busy timeout；写事务使用 `BEGIN IMMEDIATE`。
- 业务错误使用稳定错误码与公开信息；不向客户端回传原始异常、模型响应或密钥。
- 请求体最大 1 MiB，模型响应最大 1 MiB。

主要 API 分组：

| 路径 | 用途 |
| --- | --- |
| `/api/auth/*` | 账号与登录会话 |
| `/api/profile` | 个人条件 |
| `/api/ai-config`、`/api/ai-config/test`、`/api/ai/status` | 模型配置与可用状态 |
| `/api/exercises*`、`/api/exercise-preferences` | 动作目录与用户偏好 |
| `/api/equipment`、`/api/user-equipment*` | 公共器械及个人器械 |
| `/api/workouts`、`/api/workouts/calendar`、`/api/workouts/{id}` | 训练列表、日历与单条记录 |
| `/api/workout-drafts*` | 手动训练编辑器的暂存、修改、确认与取消 |
| `/api/conversations*` | 会话与发送消息 |
| `/api/turns/{id}`、`/events`、`/retry` | 轮次读取、事件与重试；后两项接在轮次路径之后 |
| `/api/conversation-actions/{id}/{operation}` | 确认或取消待执行操作 |
| `/api/health` | 数据库连通性与 SQLite 版本 |

完整方法、字段及约束以 FastAPI 运行时 `/openapi.json` 为准，不维护静态接口快照。

## 7. 代码组织

```text
backend/app/main.py                  应用组装、认证依赖、中间件与错误处理
backend/app/models.py                ORM 模型
backend/app/schemas.py               业务输入与字段约束
backend/app/services.py              共享校验与幂等回执
backend/app/core/database.py         数据库连接与事务
backend/app/agent/router.py          会话、轮次、确认接口与 SSE
backend/app/agent/conversations.py   会话管理与完整消息/事件存储
backend/app/agent/turns.py           轮次状态、租约、并发与重试
backend/app/agent/context.py         Prompt 与运行上下文组装
backend/app/agent/runner.py          有界串行 Agent 循环
backend/app/agent/actions.py         待确认操作存储、确认/取消与回执
backend/app/agent/provider.py        Chat Completions 原生工具调用传输
backend/app/agent/contracts.py       模型消息、工具调用与结果契约
backend/app/agent/prompts/           System 与运行上下文模板
backend/app/agent/tools/             工具注册表、参数模型与确认包装
backend/app/modules/auth/            账号与会话
backend/app/modules/profile/         个人条件与 AI 配置
backend/app/modules/catalog/         动作、器械与用户偏好
backend/app/modules/workouts/service.py  HTTP 与 Agent 共用的训练领域服务
backend/app/modules/workouts/drafts.py   手动训练草稿生命周期
backend/migrations/                  Alembic 数据库迁移
backend/scripts/                     初始化、目录导入、部署、清理脚本
frontend/src/                       React 界面和 API 客户端
frontend/src/Conversation.tsx        会话、历史、SSE 与请求恢复
frontend/src/conversation-types.ts   对话契约、卡片关联与重试资格
frontend/src/ConversationActionCard.tsx  确认卡片及操作状态展示
frontend/src/useWorkoutDraft.ts      手动训练草稿自动保存
deploy/                             Windows 部署与任务注册脚本
tests/                              后端单元与接口测试、前端单元、浏览器测试
docs/design.md                      当前实现设计（已完成重构的计划与交接文档合并到此）
docs/data-transfer.md               整库导入导出说明
docs/agent-e2e-tests.md             端到端场景与验证记录
```

## 8. 部署与验证

本机部署依赖 Conda `fitplan` 环境、Node.js 22+ 和 pnpm 11；后端使用 Python 3.14，SQLite 要求至少 3.51.3。Python 依赖见 `backend/requirements.lock`，前端依赖见 `frontend/package.json`。

项目根目录启动：

```powershell
./deploy/stop-local.ps1
./deploy/start-local.ps1 -Prepare -Build -Background
```

`-Prepare` 执行升级前备份、迁移、目录导入和数据库检查，`-Build` 构建前端。数据库版本落后于代码时 `serve` 拒绝启动并提示先执行 `-Prepare`。启动脚本自动注册清理任务，停止脚本自动注销。访问 `http://127.0.0.1:8765`，首次使用通过网页注册，没有默认账号。

数据库位于 `backend/data/fitplan.db`；运行日志、进程信息和备份位于 `runtime/`。数据库迁移保留完整升级链，升级前停止服务并备份；含删除数据的迁移不能依靠降级恢复。恢复操作由 `backend/scripts/local.py` 提供，要求停止写入并持有独占锁。

0010 是开发阶段已确认的数据重构迁移：清空旧会话、轮次、消息与确认记录，清除关联的旧幂等回执，保留账号、训练、动作目录及配置。该迁移只随升级执行，不在服务启动时重复清空。迁移链不可因对应业务代码已删除而清理。

整库导入导出入口为 backend/scripts/data_transfer.py，按数据库表及原始 ID 保存数据；具体命令和限制见 [数据导入导出](data-transfer.md)。导出可能包含账号哈希、会话及 AI 密钥，应按数据库备份保管。

验证按改动范围执行：

```powershell
# 项目根目录，完整后端测试；临时产物放入 runtime
./backend/.venv/Scripts/python.exe -m pytest tests/backend -q --basetemp=runtime/pytest

# frontend 目录
pnpm check
pnpm test
pnpm build
pnpm test:e2e
```

跨后端模块变更运行完整后端 pytest；核心界面流程变更或发布前运行 `pnpm build` 与 `pnpm test:e2e`。真实模型评测按需运行，不进入常规离线测试。

端到端测试使用生产前端构建、真实后端和独立 SQLite，只替换模型 Provider，不访问用户数据库或外部模型。分为核心流程 9 组与异常/历史 12 组，可分别运行 `pnpm test:e2e:core` 与 `pnpm test:e2e:resilience`。覆盖确认、取消、冲突、重放、断线恢复、账号隔离和超过 40 条输入的完整历史；详细边界见 [测试说明](agent-e2e-tests.md)。失败截图、trace 和服务器日志保存在 runtime，测试源码继续保留。
