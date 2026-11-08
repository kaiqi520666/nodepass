# 项目目录

整理日期：2026-11-07。本文件维护项目目录规划，首轮前后端基础工程已创建。

## 当前与规划

当前已包含根目录指引、文档、本地技能、用户初始化的 `.codegraph/`、前后端工程及本地 PostgreSQL Compose，已增加 API 令牌管理、图片生成受理、沧元 Worker、OSS 转存和 `/v1` 图片查询，官网与控制台布局已拆分。启动步骤见[根目录说明](../README.md)。视频、兑换和素材输入仍按需实现。

```text
NodePass/
├── AGENTS.md                   # 项目执行规则与文档入口
├── .agents/
│   └── skills/                 # 项目本地设计技能、资料和辅助脚本
├── .codegraph/                 # 用户初始化的代码图谱，不手工编辑索引
├── docs/
│   ├── README.md               # 文档索引
│   ├── requirements.md         # 已确认需求和待定事项
│   ├── tech-stack.md           # 技术栈和依赖边界
│   ├── project-structure.md    # 本文件，目录规划
│   ├── ui-ux-pro-max.md        # 设计技能用法和项目界面规范
│   ├── architecture.md         # 系统职责、流程和数据组织
│   ├── database-design.md      # 数据表、约束、价目和账务数据设计
│   ├── task-lifecycle.md       # 任务与积分状态、事务和恢复流程
│   └── providers.md            # 上游文档、协议差异和接入验证
├── README.md                   # 后续项目说明与启动入口
├── .gitignore
├── compose.yaml
├── deploy/
│   └── nginx.conf
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── .env.example
│   ├── Dockerfile
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── api/                # Axios 实例、用户和管理接口
│       ├── assets/             # 统一主题样式、Logo、静态素材
│       ├── components/         # PageHeader、AppTable、AppPagination、主题、客服等共用组件
│       ├── layouts/            # PublicLayout 官网、ConsoleLayout 控制台
│       ├── router/             # 路由与权限标记
│       ├── stores/             # 用户状态、主题模式
│       ├── types/
│       └── views/
│           ├── home/           # 官网首页；素材暂用占位
│           ├── auth/           # 注册、登录
│           ├── account/        # 仪表盘、API 令牌、账户设置、任务日志
│           ├── models/         # 官网模型广场与控制台模型定价复用目录
│           ├── docs/           # 无需登录的 API 接入文档
│           └── admin/          # 额外的管理功能页面
└── backend/
    ├── pyproject.toml
    ├── uv.lock
    ├── .env.example
    ├── Dockerfile
    ├── alembic.ini
    ├── migrations/
    ├── tests/
    └── app/
        ├── main.py
        ├── dev.py              # 本地数据库检查、迁移、API 与 Worker 统一启停
        ├── core/               # 配置、连接、鉴权、日志和异常
        ├── api/
        │   ├── public.py       # 公开模型与价格只读接口
        │   ├── openai.py       # 当前 /v1/models，扩大后再拆目录
        │   ├── api_keys.py     # 当前个人 API Key 管理
        │   ├── account/        # 登录、用户、API Key、积分
        │   ├── admin/          # 后台管理接口
        │   └── assets/         # 本站素材上传接口
        ├── models/             # SQLAlchemy 数据模型
        ├── schemas.py          # 账户与公开接口请求、响应
        ├── schemas_catalog.py  # 供应商、图片能力与价格管理校验
        ├── services/           # 模型、任务、素材、积分和兑换业务
        ├── providers/          # 沧元等上游协议适配
        └── worker.py           # 图片提交、查询、转存与结算 Worker
```

## 组织原则

- 按实际功能逐步创建文件，不提前生成空模块。
- 官网、用户与管理页面共用工程、登录和主题，官网与控制台分别使用顶部导航和侧栏布局；`views/admin/` 归类管理专用页面，管理员入口不占用户的五项菜单。
- 官网路由为 `/`、`/pricing`、`/api-docs`、`/login`、`/register`，保留 `/models` 为定价页别名；官网与控制台共用客服二维码 Popover 组件，公告铃铛和时间线弹窗只放在控制台布局中，不单独建页面。
- 控制台路由为 `/console`、`/console/models`、`/console/tokens`、`/console/tasks`、`/console/settings`；旧 `/account` 重定向至账户设置；管理路由为 `/admin/users`、`/admin/providers`、`/admin/models`。供应商与图片模型价目业务放在 `services/catalog_admin.py`，管理员表单位于 `views/admin/`。
- 公开模型、价格和 API 文档在同一前端，访客可直接进入；已登录也可浏览官网，点击账号名进入控制台。
- 同一业务的接口使用相同业务服务，不分别实现多份扣费、任务或模型逻辑。
- 供应商按协议边界组织；确定存在共享逻辑后再提取，不建立万能配置引擎。
- 不增加多线路、创作台或自动清理目录。
- 供应商回调等可选能力确定使用后再增加入口。
- `.agents/skills/` 保留技能原始说明和资源；项目实际使用约定写在文档中。

模块职责与调用规则见[系统架构](architecture.md)，设计技能使用方式见[UI/UX Pro Max 使用与界面规范](ui-ux-pro-max.md)。
