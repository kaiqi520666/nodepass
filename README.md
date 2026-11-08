# NodePass

图片与视频 API 中转服务。当前已完成第一轮可运行基础工程，业务规则见 [docs](docs/README.md)。

## 当前可用

- Vue 3、Element Plus、Vue Router、Pinia、Axios，官网顶部导航与控制台侧栏采用独立布局，共用登录与主题。
- 官网提供首页、模型广场、API 文档及带图标的注册登录，右侧提供客服和主题；已登录可点击账号名进入控制台。控制台右侧提供客服、公告铃铛和主题，公告仅在登录后的控制台显示。客服使用二维码 Popover 占位，公告使用时间线弹窗，当前暂无公告。
- 控制台主菜单为仪表盘、模型定价、API 令牌、任务日志、账户设置；任务日志暂为占位，仪表盘显示四项统计卡片，其中仅可用积分已接入真实数据。
- 明亮、暗黑、跟随系统，浏览器本地保存主题。
- FastAPI 注册、登录、退出、当前用户和四位小数余额查询。
- PostgreSQL、SQLAlchemy 2、Alembic，已落地用户、积分账户、API Key、供应商、模型、价目、任务、账务流水和系统设置基础表。
- 公开模型目录读取真实数据库；管理员可查看用户、通过操作菜单调整用户积分或修改密码、新增和编辑供应商、管理图片模型与价目、启停供应商及上架/下架模型。没有自动上线模型或默认管理员。
- API 令牌页支持创建、查看、复制、编辑和删除自己的 API Key；Key 摘要用于认证，密钥原文以 Fernet 加密保存，列表不直接返回原文。
- `GET /v1/models` 使用本站 API Key 进行 Bearer 鉴权，返回 OpenAI 兼容模型列表和错误结构。

图片生成闭环已实现：`POST /v1/images/generations` 受理后由独立 Worker 调用沧元、轮询任务、转存结果到阿里云 OSS，并在转存成功后结算积分；明确失败会释放冻结积分。视频、兑换充值和素材上传仍未实现。

`GET /api/public/models` 仅供网站模型与价格页面使用，不属于 OpenAI 标准接口，不在开发者接入文档或公开 OpenAPI 定义中展示。开发者文档以 `/v1/models`、`/v1/images/generations` 和对应查询接口为接入入口。

## 本地启动

需要 Node.js 22.12+、pnpm 10.30.3、uv、Python 3.12。使用项目自带 PostgreSQL 时，请先打开 Docker。

日常只需两个终端。以下都从项目根目录开始，启动后端：

```bash
cd backend
uv run python -m app.dev
```

该命令检查数据库；项目默认本地数据库不可用时，自动执行 Docker Compose 启动 PostgreSQL，随后执行迁移，并一起启动 API 和图片任务 Worker。按 `Ctrl+C` 一起停止 API 和 Worker；数据库继续在后台运行，数据保留。任一后端进程退出时，另一个也会停止。8000 端口被占用时会退出，不会关闭已有程序。

启动前端：

```bash
cd frontend
pnpm dev
```

API 开启代码热更新；修改 Worker 使用的代码后，重新启动后端命令。此合并入口仅用于本地开发；单独启动 API、Worker 的命令仍可用于部署，避免与合并入口重复运行。

全新环境首次安装依赖并生成配置：

```bash
# 在 backend 目录
uv sync --locked
uv run python -m app.cli init-env

# 在 frontend 目录
pnpm install --frozen-lockfile
```

`init-env` 仅首次执行，会从 `.env.example` 生成本地 `.env` 和随机会话密钥；已有文件时拒绝覆盖。重启时不必再次执行。禁止提交 `.env`。

前端：`http://127.0.0.1:5173`。后端存活 / 就绪探针：`http://127.0.0.1:8000/health/live`、`/health/ready`。

前端通过 Vite 代理访问后端，无需跨域配置。更改前端端口时同步修改后端 `.env` 中的 `NODEPASS_WEB_ORIGINS`，否则写请求会被来源检查拒绝。

## 开发者 API

登录后在控制台“API 令牌”（`/console/tokens`）创建 API Key。开发者 Base URL 为 `http://127.0.0.1:5173/v1`（Vite 代理），或直接使用后端 `http://127.0.0.1:8000/v1`。接口示例：

```bash
curl 'http://127.0.0.1:5173/v1/models' \
  -H 'Authorization: Bearer YOUR_API_KEY'
```

无上架模型时返回 `{"object":"list","data":[]}`。缺少、错误或停用的 Key、停用账户均返回 HTTP 401 和 `error` 对象，不接受网页 Cookie 或网页登录令牌代替 Key。模型记录仅含 `id`、`object`、`created`、`owned_by`，不包含价格、成本或供应商信息。`owned_by` 固定为本站标识 `nodepass`。

本地开发的 `uv run python -m app.dev` 已包含 Worker，无需再单独启动。独立运行时，在 `backend` 执行 `uv run python -m app.worker`；API 使用 `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000`。Key 管理属于本站账户功能，不是 OpenAI 标准接口；停用只修改状态、不删除记录。不要把 Key 放在 URL、浏览器存储或日志中，生产调用必须使用 HTTPS。

## 管理员

不把首个注册用户自动设为管理员。在 `backend` 中显式创建：

```bash
uv run python -m app.cli create-admin admin@example.com
```

邮箱换成实际邮箱，密码通过隐藏输入填写，不进入命令历史。管理员登录后继承个人页面，并在侧栏“管理”区访问用户管理、供应商配置、模型与价格；普通注册接口不允许设置管理员权限。

供应商配置为 `/admin/providers`，图片模型与价格为 `/admin/models`。当前配置范围为沧元图片及已核对的 GPT Image 2、2.5、2.6 具体型号。模型默认下架；上架需要有效供应商、合法能力与默认参数、匹配的价目。售价使用积分/张，成本独立填写原币/张，目前成本币种可选 CNY、USD。保存后官网模型广场和控制台模型定价读取同一份售价，不公开成本和上游映射。

供应商密钥使用 Fernet 加密保存，管理接口只返回“已配置”状态；编辑时留空保留原密钥。主密钥 `NODEPASS_CREDENTIALS_KEY` 留在部署环境，须随数据库私下备份，不能丢失或随意重新生成。首次 `init-env` 会一并生成主密钥；已有 `.env` 的项目仅补缺失配置：

```bash
uv run python -m app.cli init-credentials-key
```

命令在 `backend` 运行，拒绝覆盖已有主密钥；补充后重启后端。本轮已为当前本地 `.env` 补充主密钥，未添加上游 API Key。生产环境通过独立环境变量提供该密钥。

## 检查

后端，在 `backend` 中：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run alembic check
```

测试需要本地 PostgreSQL，自动创建独立的 `nodepass_test_<随机值>` 数据库，执行迁移，结束后仅删除自己创建的测试库，不清空开发库。默认使用上述本地容器；可用 `NODEPASS_TEST_DATABASE_URL` 指定另一本地测试服务器，其账号须能创建临时数据库。

前端，在 `frontend` 中：

```bash
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

后端测试同时使用锁定版本的 OpenAI Python SDK 检查模型列表读取和认证错误，不调用 OpenAI 或上游服务。浏览器测试需要已启动后端，可自动启动或复用前端；覆盖公开目录、兼容接口文档与代理、Key 创建及停用交互、错误恢复、登录表单、权限跳转、三态主题和手机导航。不会在开发库注册演示账号或添加模型，Key 界面测试使用明确的 fixture。截图与跟踪位于已忽略的 `frontend/test-results/`。

## 部署边界

当前 Compose 只用于本地开发数据库，并非生产部署方案；示例数据库密码只用于绑定回环地址的本地容器。生产环境须使用独立凭证、HTTPS、`NODEPASS_ENVIRONMENT=production`、`NODEPASS_COOKIE_SECURE=true` 和真实的受信任页面来源。

网页会话使用 HttpOnly、SameSite Cookie，不把令牌存进浏览器 localStorage。会话签名密钥来自环境配置；业务配置后续按既定设计落数据库。管理员接口不出现在公开接口定义中，`/docs` 和 OpenAPI schema 仅开发环境启用。

尚未创建 Git 仓库、生产部署配置、队列或任何上游密钥；不会自动初始化、重建 Codegraph 索引。
