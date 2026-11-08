# 技术栈

整理日期：2026-11-07。用于记录技术选择及依赖边界，现已初始化首轮基础工程。

## 已指定技术

| 层面 | 技术 | 用途 |
| --- | --- | --- |
| 前端框架 | Vue 3 | 用户与管理页面，共用一个工程 |
| UI 组件 | Element Plus | 表格、表单、弹窗、导航及反馈 |
| 图标 | `@element-plus/icons-vue` | 统一菜单和操作图标 |
| 路由 | Vue Router | 页面路由、权限标记与访问控制 |
| 状态 | Pinia | 登录信息、主题模式等共享状态 |
| HTTP | Axios | 前端统一请求入口 |
| 后端语言 | Python | API、供应商适配及后台任务 |
| 对象存储 | 阿里云 OSS | 本站素材上传及全部生成结果的统一转存与交付 |

## 补充实施建议

首轮已采用 TypeScript、Vite、pnpm、FastAPI、Uvicorn、Pydantic Settings、PostgreSQL 17、SQLAlchemy 2、psycopg 3、Alembic、PyJWT、pwdlib、uv、Ruff、pytest 和 Playwright。实际版本固定在 `frontend/pnpm-lock.yaml` 与 `backend/uv.lock`，不另手抄一份版本表。

下表其余组件仍是按需落地建议：Redis、ESLint、Nginx 等尚未安装或实现；阿里云 OSS SDK 已用于结果转存，后台 Worker 首期使用独立 Python 进程和数据库轮询，HTTPX 当前仅用于后端测试。Compose 当前只编排本地 PostgreSQL。

OpenAI Python SDK 作为开发测试依赖，用于本地验证 `/v1/models` 与认证错误；不用于转发调用，不需要 OpenAI 账号或真实凭证，版本以 `backend/uv.lock` 为准。

供应商配置管理已加入 `cryptography`，使用 Fernet 保存需要恢复原文的上游凭证；主密钥由环境变量提供，与网页会话密钥分开，不自行实现加密算法。实际版本固定在 `backend/uv.lock`。

| 层面 | 建议技术 | 用途 |
| --- | --- | --- |
| 前端开发 | TypeScript、Vite、pnpm | 类型检查、开发构建和包管理 |
| API 服务 | FastAPI、Uvicorn | 兼容 API、用户和管理接口 |
| 参数与配置 | Pydantic、pydantic-settings | 请求响应校验、部署配置读取 |
| 数据库 | PostgreSQL | 用户、模型、任务、素材和账务记录 |
| 数据访问 | SQLAlchemy 2、psycopg 3 | 数据操作和事务 |
| 数据迁移 | Alembic | 表结构版本管理 |
| 后台执行 | 独立 Python Worker | 生成提交、查询和结果转存；数据库任务是事实源 |
| 周期调度 | Worker 数据库轮询 | 调度待查询任务，包含超时后继续查询 |
| 上游 HTTP | Python 标准库 urllib | 首期调用沧元接口和获取结果文件 |
| 对象存储接入 | 阿里云 OSS 官方 Python SDK | 具体 SDK 和版本在工程初始化时核验并固定；不增加多云存储抽象 |
| 登录 | PyJWT、pwdlib | 登录令牌和密码哈希 |
| 前端检查 | 类型检查、ESLint | 类型与代码质量检查 |
| 后端工具 | uv、Ruff、pytest | 依赖、格式与静态检查、业务验证 |
| 部署 | Docker Compose、Nginx | 服务编排、静态资源及反向代理 |

## 依赖边界

- 图标统一使用 Element Plus 图标库，品牌 Logo 使用相应 SVG 或图片资源。
- 主题使用 Element Plus 暗黑样式及浏览器能力实现，不额外引入主题库。
- 不因设计技能中的示例安装 React、shadcn/ui、Tailwind 或其他图标库。
- 保持模块化单体；API 与 Worker 共用业务代码、分进程运行。本地开发用 `uv run python -m app.dev` 统一启动和停止，部署时可分别启动。
- 公开模型价格和 API 文档使用现有 Vue 工程，不单独引入文档站框架或内容管理系统。
- 业务配置尽量保存数据库；数据库、Redis 连接和凭证加密主密钥由部署环境提供。
- 网页登录令牌与开发者 API Key 分开；管理员身份和数据权限由后端校验。
- 不为邮箱验证、找回密码、在线支付或业务限流安装依赖，这些均不在首期范围。

## 相关文档

- [需求确认](requirements.md)：已确认业务范围和待确认事项。
- [系统架构](architecture.md)：模块职责、调用关系和数据组织。
- [项目目录](project-structure.md)：代码和配置的存放位置。
- [UI/UX Pro Max 使用与界面规范](ui-ux-pro-max.md)：权限菜单、主题和设计技能使用边界。
