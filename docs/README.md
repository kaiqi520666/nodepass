# NodePass Agent 入口

更新：2026-11-11。本目录供 AI Agent 接手开发，只维护代码无法直接表达的决定、关键约束和接入差异，不复制完整字段表、目录树或公开 API 文档。

## 按任务阅读

先遵守根目录 [AGENTS.md](../AGENTS.md)，再按任务读取：

| 任务 | 文档 |
| --- | --- |
| 业务范围、权限、界面和未完成事项 | [需求与约定](requirements.md) |
| 生成任务、计费、超时、重启与恢复 | [任务与账务](task-lifecycle.md) |
| 界面设计 token、页面结构、组件与改造清单 | [界面设计规范](ui-design.md) |
| 上游映射、初始化计价与验证边界 | [供应商接入](providers.md) |
| 安装、启动、环境、初始化与检查命令 | [根目录 README](../README.md) |

## 当前实现

- 官网和控制台采用独立布局，共用 Vue 工程、登录与三态主题。
- 后台维护用户、供应商、三类模型与价格、OSS；支持调账、修改用户密码。
- 图片为沧元两个参数化模型，支持生成及 HTTPS 参考图编辑、可选 mask；MEAICC 十个视频型号已接入异步生成；ModelGate `gpt-6.1-sol` 支持文本、图片理解、严格结构化输出、函数调用、搜索与 JSON/SSE。
- 图片/视频由数据库任务驱动单 Worker，完成本站结果转存后结算；文本在 API 进程内调用、按最终用量后付费。
- 任务日志分生成任务和文本调用；仪表盘读取真实统计、近 7 日消耗与最近任务。尚未实现项只在[需求待办](requirements.md#未实现与待确认)维护。
- 已实现不等于所有上游型号和参数均经真实付费验收；范围见[供应商接入](providers.md)。

## 技术与运行

- 前端：Vue 3、TypeScript、Vite、Element Plus 及其图标库、Vue Router、Pinia、Axios、pnpm。
- 后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy 2、psycopg 3、PostgreSQL、Alembic；Cookie 会话、Argon2 密码哈希、Fernet 凭证加密。
- 生成通信使用标准库，文本 JSON/SSE 使用 HTTPX；结果存储使用阿里云 `oss2`；检查使用 Ruff、pytest、vue-tsc、Playwright。
- 模块化单体，数据库是配置、调度和账务事实源；没有 Redis、Celery、外部队列或生产编排。
- 本地两个入口为前端 `pnpm dev`、后端 `uv run python -m app.dev`；后者统一管理数据库检查、迁移、API 和 Worker。
- 精确依赖见 `frontend/package.json`、`backend/pyproject.toml` 及对应锁文件；不新增文档框架、高亮库、主题库或通用协议引擎。

## 关键代码入口

下列路径相对项目根目录；查具体行为时读取相关代码和测试，不在文档复刻实现。

| 关注点 | 入口 |
| --- | --- |
| 应用、错误与网页来源校验 | `backend/app/main.py`、`backend/app/core/errors.py` |
| 开发者接口与鉴权 | `backend/app/api/openai.py`、`backend/app/api/dependencies.py` |
| 生成参数、价格匹配与冻结 | `backend/app/schemas.py`、`backend/app/services/generations.py` |
| 调度、转存、结算与释放 | `backend/app/worker.py`、`backend/app/services/task_execution.py` |
| 文本请求、JSON/SSE 与扣费 | `backend/app/schemas_text.py`、`backend/app/services/text_generation.py`、`backend/app/services/text_billing.py` |
| 供应商与初始化配置 | `backend/app/providers/`、`backend/app/services/{catalog,text_catalog,video_catalog}.py` |
| 模型后台与能力校验 | `backend/app/services/catalog_admin.py`、`backend/app/schemas_catalog.py` |
| 结果下载、OSS 与设置 | `backend/app/services/{media,storage,settings}.py` |
| 表结构、约束与迁移 | `backend/app/models/`、`backend/migrations/versions/` |
| 个人日志、统计、Key 与管理 | `backend/app/api/{account,api_keys,admin}.py` |
| 页面、菜单、主题与共用样式 | `frontend/src/{views,layouts,router,stores,components}/`、`frontend/src/assets/main.css` |
| 公开接入文档 | `frontend/src/views/docs/ApiDocsView.vue`、`ApiCodeBlock.vue`、`image-generation.example.json`、`image-edit.example.json` |
| 离线与浏览器验证 | `backend/tests/`、`frontend/tests/`；具体入口见[任务与账务](task-lifecycle.md#日志统计与验证入口) |

## 维护方式

- 用户最新决定优先；只在对应一处维护规则，其余引用。区分已确认、已实现和待核验。
- 改业务决定更新需求；改结算/恢复更新任务文档；改接入差异更新供应商文档；改入口更新本页。
- 接口字段以路由、schema、转换代码和实际响应为准；表结构以 ORM 和迁移为准。变更对外协议同时维护公开 `/api-docs` 和相关测试。
- 不创建重复的内部 API/数据库手册、历史归档或未实现模块空目录；保留有助于后续决策的限制与验证结论。
- 不保存真实密钥、用户素材地址或媒体全文，不把临时探测文件当长期可重放证据。
