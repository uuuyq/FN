# FNote

每一次训练，都有迹可循。

FNote 是一个个人训练记录应用，支持训练日历、动作与器械管理，以及通过 AI 对话查询和整理训练记录。提供 Web 界面和 Android WebView 客户端，可在 Windows 本地运行，也可部署到 Ubuntu 服务器。

## 功能

- **训练记录**：记录训练动作、组数、重量和次数，通过日历查看训练历史与摘要。
- **动作与器械**：管理动作目录、可用器械及个人动作偏好。
- **个人设置**：维护个人条件和训练指导原则，为训练建议提供背景。
- **AI 助手**：流式对话、查询训练历史、提出训练记录与个人设置修改；写入操作需在界面确认后执行，支持查询和撤销近期训练操作。
- **独立账号**：支持注册、登录及按用户配置模型服务和 API Key。
- **数据维护**：数据库迁移、在线备份、恢复与过期删除记录清理。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| Web 前端 | React、TypeScript、Vite、Ant Design |
| 后端 | Python、FastAPI、SQLAlchemy、Alembic |
| 数据库 | SQLite，使用 WAL；要求 SQLite ≥ 3.51.3 |
| Android | Kotlin、系统 WebView，Android 8.0+ |
| 服务器部署 | Ubuntu 24.04、systemd、Caddy |

## Windows 本地运行

准备 Python 3.12、Node.js 22 和 pnpm 10。先在 PowerShell 中激活要使用的 Python 环境，脚本沿用当前 PATH 中的 Python。Python 实际链接的 SQLite 版本须达到 3.51.3，可执行以下命令检查。

```powershell
python -c "import sqlite3; print(sqlite3.sqlite_version); assert sqlite3.sqlite_version_info >= (3,51,3)"
```

在项目根目录启动或停止应用。

```powershell
powershell -ExecutionPolicy Bypass -File deploy/local.ps1
powershell -ExecutionPolicy Bypass -File deploy/local.ps1 --stop
```

启动脚本会安装 Python 和前端依赖、构建前端、备份并迁移已有数据库，然后在后台启动应用。首次本地运行会初始化数据库。在浏览器打开 [本地应用](http://127.0.0.1:8765)，注册账号后使用。

脚本注册当前用户的每日清理和备份任务，需要保持登录。重启机器后需重新执行启动命令。应用日志位于 `runtime/server.log` 和 `runtime/server-error.log`。

## AI 配置与数据

在应用设置中选择模型服务商并填写 API Key，连接测试通过后保存。支持替换和删除已保存的 Key。未配置模型时可以手动记录训练。

API Key 使用 Fernet 加密保存，默认主密钥文件为项目下的 `runtime/secrets/ai-config.key`。数据库默认位于 `backend/data/fnote.db`，本地备份位于 `runtime/backups/`，备份保留 30 天。

请单独备份主密钥。迁移加密数据库到另一台机器时，需安全传递同一份主密钥。丢失主密钥后需要重新配置 API Key。旧数据库或迁移前备份可能保留明文凭据，应作为敏感文件保管。

数据库、备份、主密钥、日志和 Android 签名文件均已通过忽略规则排除。分享项目时也应检查打包文件是否包含这些数据。

## Ubuntu 部署与 Android

Ubuntu 24.04 使用两个脚本，需要 sudo 权限。`deploy/setup.sh` 安装或更新独立环境、同步代码到 `/opt/fnote`、安装依赖并构建前端。Miniforge、Conda、Python 和前端依赖默认使用官方源，支持预先上传 Miniforge 安装器及 SHA256 文件。安装更新会停止已有应用，完成后执行启动脚本。

`deploy/server.sh` 使用已安装的代码和环境，准备数据库并通过 systemd 启动应用和维护任务，配置 Caddy HTTPS。再次启动不会安装依赖或重新构建前端。代码和依赖有更新时，先重新执行 `setup.sh`。

应用和维护服务通过 `PrivateTmp=true` 获得可写的独立临时目录，供 SQLite 等组件使用；配合 `ProtectSystem=strict` 保留文件系统保护。更新此配置后需重新执行 `server.sh`，仅重启旧服务不会更新配置。

当前服务器脚本面向已有数据库的迁移，首次部署前需停止原应用，并准备数据库及存在的 WAL/SHM 文件。已有加密配置时，还需将主密钥放到上传项目的 `runtime/secrets/ai-config.key`。运行前检查脚本中的域名，并配置 DNS 和公网 TCP 80/443。

```bash
# 首次安装或更新代码、依赖
sudo bash deploy/setup.sh
# 启动或重新部署已有版本
sudo bash deploy/server.sh
# 停止应用
sudo bash deploy/server.sh --stop
```

Ubuntu 日志统一保存在 `/opt/fnote/runtime/`：`server.log` 为应用标准输出，`server-error.log` 为应用错误输出，`deploy.log` 为安装和部署日志。清理、备份任务的标准输出和错误分别合并到 `cleanup.log`、`backup.log`；清理程序不再额外写入 `workout-cleanup.log`。更新已有部署后，需重新执行 `server.sh` 才会更新服务日志路径和轮转配置；历史 journal 和旧日志文件不自动迁移或删除。

部署脚本安装并启用系统 `logrotate.timer`，每天清空上述应用、部署和任务输出日志，不保留归档、不压缩，空日志跳过。原文件保留供进程继续写入，无需重启应用。Windows 本地的 `workout-cleanup.log` 沿用程序自身的 1 MB、3 份备份轮转策略。

```bash
sudo tail -n 100 -f /opt/fnote/runtime/server-error.log
```

Android 构建、签名和设备验证见 [Android 说明](android/README.md)。

## 开发检查

在已激活的 Python 环境中安装依赖，并从项目根目录运行后端测试。

```powershell
python -m pip install -r requirements.txt
python -m pytest tests/backend -q
```

前端检查、单元测试和构建在 `frontend` 目录执行。

```powershell
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

