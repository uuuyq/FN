# 数据导出与导入

入口：`backend/scripts/data_transfer.py`。无需前端，也不新增 HTTP 接口；使用项目的 Python 环境运行。

## 当前库表

默认数据库是项目内的 `backend/data/fitplan.db`，路径不随启动目录变化。
实际数据库版本以 `alembic_version` 为准，当前迁移链最新版本为 `0010`。导入导出前按脚本要求检查数据库版本、完整性和外键。

| 范围 | 表 |
| --- | --- |
| 账户与会话 | users、user_sessions |
| 动作与器材 | exercises、equipment、user_equipment、exercise_preferences |
| 训练记录与草稿 | workouts、workout_exercises、workout_sets、workout_drafts |
| 对话与操作 | conversations、turns、messages、conversation_actions |
| 请求幂等记录 | request_receipts |
| 数据库迁移版本 | alembic_version |

导出包含以上全部表、全部字段及原始 ID，包括已软删除数据、登录会话、密码哈希和用户 AI 配置。JSON 文件可能包含 API 密钥和个人数据，应按数据库备份保管。它用于整库数据迁移，不支持按用户筛选或增量合并。JSON 字段在数据库中的原始文本会保留。

## 使用

在项目根目录进入后端目录，以下命令使用已安装依赖的 `fitplan` Conda 环境：

```powershell
cd backend
# 导出：允许应用运行时执行，读取一致性快照（包含 WAL 中已提交的数据）
conda run -n fitplan python -m scripts.data_transfer export --output ../runtime/exports/fitplan.json

# 导入到已经迁移至同版本、没有业务数据的数据库
conda run -n fitplan python -m scripts.data_transfer --database ../runtime/new.db import --input ../runtime/exports/fitplan.json

# 整库替换现有数据：先停止应用及其他数据库写入进程
conda run -n fitplan python -m scripts.data_transfer import --input ../runtime/exports/fitplan.json --replace
```

可先从项目根目录运行 `./deploy/stop-local.ps1` 停止本地后台服务。导入入口复用部署脚本的实例锁；应用仍在运行时会拒绝导入。自行启动的服务、清理任务等其他写入进程也应停止。

`--database` 必须放在 `export` / `import` 之前，指定路径必须已存在；脚本不会悄悄创建空数据库，也不读取 `DATABASE_URL`。新库应先通过项目 Alembic 迁移初始化到相同版本。执行过 seed 的数据库已有业务数据，需要 `--replace`。

导出目标存在时拒绝覆盖，请使用新文件名。导入仅接受本脚本生成的版本 1 JSON；校验完整表集合、字段顺序、表结构、迁移版本、唯一约束及外键，不执行文件中的 SQL。结构或版本不同应先使用相同版本的项目进行迁移。

默认导入拒绝覆盖有数据的目标。`--replace` 表示删除全部原有行后恢复快照，替换前自动在 `runtime/backups` 保存完整 `.db` 备份，成功后打印备份路径。所有数据删除与插入处于同一事务，任何失败都会回滚。失败退出码为 1，成功为 0。

现有 `python -m scripts.local backup` / `restore --source ...` 仍可用于 SQLite 数据库文件级备份恢复。

## 验证

在项目根目录运行：

```powershell
conda run -n fitplan python -m pytest tests/backend/test_data_transfer.py -q
```
