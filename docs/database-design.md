# 数据库表结构

整理日期：2026-11-07。状态：总体表结构仍为第一版草案；已实现 `users`、`credit_accounts`、`api_keys`、`providers`、`models`、`model_prices`、`system_settings`、`tasks`、`credit_entries`、`assets`、`task_assets` 十一张表及五版 Alembic 迁移。兑换码和审计仍未落地；图片账务已覆盖受理冻结、明确失败释放和 OSS 转存成功结算，实际成本核算仍未接入。

业务依据见[需求确认](requirements.md)，任务执行与账务事务见[任务状态流转](task-lifecycle.md)。本文提出字段、约束和索引，不把技术建议或待确认业务变成已确认结论。

## 设计边界

- 首轮已采用 PostgreSQL 17，具体依赖见[技术栈](tech-stack.md)与锁文件。
- 首期采用 13 张业务表；不增加线路、权限角色、在线支付、通用规则引擎、清理归档或独立充值批次表。
- 用户表用管理员标识表达两种权限。管理员的个人任务仍归自己，全站数据通过管理接口访问。
- 数据库保存业务事实；Redis 和队列不作为任务、余额或兑换状态的唯一来源。
- 业务配置可以修改，任务快照和已入账流水不可随配置修改而回写。
- 未落地部分的物理字段、枚举和索引为实施建议；当前实际结构以已有迁移为准。

## 通用约定

| 项目 | 约定 |
| --- | --- |
| 主键 | 普通实体用 `BIGINT` identity；任务用应用生成的 `UUID`。主键不可猜测性不替代归属鉴权 |
| 时间 | `TIMESTAMPTZ`，统一按 UTC 写入，界面按使用者时区展示 |
| 通用字段 | 除只追加的流水和审计外，包含 `created_at`、`updated_at`；下表不重复列出 |
| 必填与可空 | 默认必填或有明确默认值；标注 `可空` 的字段才允许 `NULL` |
| 积分和售价 | `NUMERIC(20,4)`，使用 `Decimal`，金额结果按 `ROUND_HALF_UP` 保留四位小数；禁止二进制浮点记账 |
| 成本原币 | 建议 `NUMERIC(24,8)` 保留原始报价精度，不代表积分改成八位；成本币种、单位和最终精度仍待确认 |
| 数量 | 指定时长建议 `NUMERIC(20,8)`；只接受模型声明支持且可精确表示的值，不静默截断或取整 |
| JSON | `JSONB` 仅用于有限能力配置、参数、快照等结构；关联、金额和查询状态保留独立字段 |
| 状态 | 字符串配合 `CHECK` 与服务层校验，不引入状态配置平台或数据库枚举扩展流程 |
| 删除 | 首期不物理删除业务历史；外键默认限制删除，不级联删除任务、流水或审计 |
| 敏感字段 | 密码用密码哈希；API Key 用摘要认证、原文 Fernet 加密保存；兑换码用摘要；上游和 OSS 凭证按需加密保存 |

金额校验同时覆盖 API 和数据库：拒绝 `NaN`、无穷、负余额及越界值。`NUMERIC` 是精确类型，但不能只靠“非负”校验排除特殊值。售价与冻结金额可以为零；兑换额度必须大于零。所有数量、价格配置先校验精度和范围，再计算入账金额。

## 表关系

```text
users ──1:1── credit_accounts
  ├──1:N── api_keys
  ├──1:N── tasks ──N:1── models ──N:1── providers
  │           │            └──1:N── model_prices
  │           └──1:N── task_assets ──N:1── assets
  ├──1:N── assets
  └──1:N── credit_entries ──N:1── tasks / redemption_codes

redemption_codes ──N:1── users（创建人、兑换人）
system_settings：站点与存储等配置
audit_logs：管理员操作及关键恢复、人工处理记录
```

## 账号与凭证

### 1. users

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 用户标识 |
| `email` | 字符串 | 展示和登录邮箱 |
| `email_normalized` | 字符串，唯一 | 按统一规则规范化后查重；保留原邮箱展示，首期建议去首尾空格并统一大小写 |
| `password_hash` | 字符串 | 密码哈希，不存原密码 |
| `is_admin` | 布尔，默认 `false` | 管理权限；不增加角色、菜单授权表 |
| `is_active` | 布尔，默认 `true` | 账号可用状态；停用不删除历史数据 |

不增加邮箱验证、找回密码、主题偏好字段。注册事务同时创建零余额积分账户。停用账号是否影响已受理任务属于操作策略，不得通过停止查询造成冻结资金无人处理。

### 2. credit_accounts

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `user_id` | 主键、外键 → `users.id` | 一人一个积分账户 |
| `available` | 积分，默认 `0.0000`，非负 | 可用余额 |
| `frozen` | 积分，默认 `0.0000`，非负 | 未结算任务冻结合计 |

不另存“总余额”或“累计消费”等可推导余额。更新账户必须加行锁，并与对应流水、业务状态在同一数据库事务提交。

### 3. api_keys

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | Key 记录标识 |
| `user_id` | 外键 → `users.id` | 所有人 |
| `name` | 字符串 | 用户备注 |
| `key_prefix` | 字符串 | 列表中展示的非敏感前缀 |
| `key_digest` | 字符串，唯一 | 高熵随机 Key 的安全摘要，用于认证 |
| `key_encrypted` | 加密文本，非空 | 用于用户主动查看或复制 |
| `is_active` | 布尔，默认 `true` | 是否可用 |
| `expires_at` | 时间，可空 | 过期时间；空值表示永不过期 |
| `last_used_at` | 时间，可空 | 最近使用记录 |

Key 摘要用于认证，原文以 Fernet 加密保存，仅在当前用户主动查看或复制时通过受保护接口返回。不增加额度、并发或频率字段。任务记录不依赖 Key 记录，删除 Key 后立即失效并移除记录。

本轮已落地：`name` 长度 1-80，`key_prefix` 最大 24，`key_digest` 为 64 位十六进制 SHA-256 摘要并有唯一约束，`user_id` 建索引；原文为本站前缀加 32 字节安全随机值的 URL-safe 编码。管理操作按用户归属校验，调用时同时检查 Key、用户启用状态和过期时间；成功认证更新 `last_used_at`。

## 供应商、模型与价目

### 4. providers

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 一个供应商接入配置 |
| `name` | 字符串 | 后台名称 |
| `adapter_key` | 字符串 | 已实现且允许选择的适配器标识，不加载数据库提供的任意代码 |
| `base_url` | 字符串 | 上游接口地址，管理端校验目标与协议 |
| `credentials_encrypted` | 加密文本 | API Key 等凭证；接口只返回脱敏状态 |
| `request_config` | JSONB 对象 | 该适配器允许的连接、请求超时等有限配置，不包含任意脚本 |
| `is_active` | 布尔，默认 `true` | 是否接收新任务 |

同一供应商记录的身份不应被改成另一个站点或账号；新的接入身份创建新记录。原记录停用不自动取消在途任务。凭证轮换须保持原账号的任务查询能力；若无法保证，先在后台明确核实，不拿新账号查询旧任务。

### 5. models

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 内部标识 |
| `public_id` | 字符串，全局唯一 | 用户提交的本站模型 ID |
| `display_name` | 字符串 | 公开名称 |
| `media_type` | `image` / `video` | 媒体类型 |
| `provider_id` | 外键 → `providers.id` | 唯一绑定供应商，不增加线路表 |
| `upstream_model_id` | 字符串 | 上游要求的模型名称 |
| `capabilities` | JSONB 对象 | 固定支持参数的可选值、默认值、数量等能力 |
| `pricing_dimensions` | JSONB 字符串数组 | 从允许字段中选择计价维度；下面说明匹配方式 |
| `is_active` | 布尔，默认 `false` | 管理员完成配置后上架 |

图片始终校验单张，不允许通过能力配置放开 `n > 1`。后台可修改绑定，新任务使用新配置；已有任务使用原绑定快照。不预置正式上线模型清单。

当前图片管理已落地到现有表，不增加迁移：`capabilities` 使用 `sizes`、`qualities`、`tiers`、`series`、`backgrounds`、`output_formats`、`max_reference_images`、`supports_mask` 和 `defaults`；`defaults` 的键限定为对应的单数请求参数名。选项必须属于所选具体上游型号的已核对能力，默认值必须属于已配置选项。固定像素档自定义尺寸校验像素预算，web 和 `-x` 暂仅配置已核对的比例，不据此开放未验证的自定义尺寸。成本币种当前允许 CNY、USD，单位按张；视频和其他成本口径接入时再扩充。

### 6. model_prices

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 价目标识 |
| `model_id` | 外键 → `models.id` | 归属模型 |
| `variant` | JSONB 对象，默认 `{}` | 默认价或完整计价参数组合 |
| `sale_unit` | `image` / `video` / `second` | 积分售价单位，按媒体类型校验 |
| `sale_unit_price` | 积分，非负 | 管理员配置的售价 |
| `cost_unit` | 字符串 | 原始成本计费单位，最终允许值在成本口径确认后固定 |
| `cost_unit_price` | 原币金额，非负 | 管理员配置的成本单价 |
| `cost_currency` | 字符串 | 明确原始币种，不隐式按人民币处理 |

约束为 `UNIQUE(model_id, variant)`，`variant` 非空且必须为 JSON 对象。使用规范化 JSONB 对象避免键顺序造成重复；不以多个可空参数列直接实现价格唯一性。无默认价可以只配置完整的明确价目；没有匹配价的请求拒绝受理。

#### 最小匹配规则

这是对已确认价格需求的实施建议，不是可编排的计价引擎：

1. 先解析模型配置，补齐参数默认值，校验用户参数属于支持能力。
2. `pricing_dimensions` 只能选适配器允许的少数字段；图片可按实际能力选 `tier`、`quality`、`series`、`size`，视频首期使用 `resolution`。最终字段与接口设计对齐。
3. 用这些字段组成完整对象，查找完全相同的 `variant`；非默认行必须覆盖全部所选维度，不支持局部通配或优先级规则。
4. 没有精确价目时仅回退到该模型显式存在的 `{}` 默认价。默认价只覆盖已支持的参数，不扩展模型能力。
5. 匹配行同时提供独立填写的成本价和售价。公开目录与任务报价调用同一匹配逻辑，但公开序列化不包含成本。
6. 修改计价维度、能力和价目时在一个配置事务中校验一致性；配置不完整的模型不允许上架。

| 示例 | `pricing_dimensions` | `variant` | 售价单位及示例单价 |
| --- | --- | --- | --- |
| 视频 A | `["resolution"]` | `{"resolution":"720p"}` | `second`，`0.1000` |
| 视频 A | `["resolution"]` | `{"resolution":"1080p"}` | `second`，`0.2000` |
| 视频 B | `["resolution"]` | `{}` | `video`，`1.0000`，覆盖其声明支持的 480p、720p、1080p |
| 图片 C | `["tier","quality"]` | `{"tier":"web","quality":"low"}` | `image`，管理员填写 |

以上不是供应商实际报价或需要预置的模型。视频各价目允许选择按条或按秒；按秒数量来自请求指定时长。`amount = ROUND_HALF_UP(sale_unit_price × quantity, 4)`，按张、按条时 `quantity = 1`。

成本与售价不要求同币种或同单位。能依确认口径计算时保存估算成本，不能时留空估算金额但仍保留单价、单位、币种快照；不拿原币成本直接减积分，不以用量字段或配置报价冒充实际扣费。

## 任务与素材

### 7. tasks

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | UUID 主键 | 本站任务编号 |
| `user_id` | 外键 → `users.id` | 任务归属 |
| `api_key_id` | 外键 → `api_keys.id`，可空 | 调用凭证追踪；存在时必须属于同一用户 |
| `model_id` | 外键 → `models.id` | 本站模型关联 |
| `provider_id` | 外键 → `providers.id` | 原供应商关联，不能随模型改绑而修改 |
| `provider_snapshot` | JSONB 对象 | 本站模型 ID、上游模型 ID、适配器、原地址等绑定快照；不复制密钥 |
| `upstream_task_id` | 字符串，可空 | 原上游任务 ID，不强制按数字解析 |
| `request_params` | JSONB 对象 | 规范化且通过能力校验的参数；不放 Base64 媒体、密码或带凭证的源 URL，素材用关联记录表示 |
| `idempotency_key` | 字符串，可空 | 客户端提供时使用的本站受理幂等键，是否作为外部扩展另行确定 |
| `request_hash` | 字符串 | 规范化模型、参数和素材关联的摘要，用于比对幂等重放 |
| `price_snapshot` | JSONB 对象 | 匹配价目 ID、参数组合、售价及成本单价、单位、币种、各自计算依据 |
| `billing_quantity` | 精确数量 | 售价计费数量：单张、单条为 1；按秒为请求指定秒数 |
| `sale_amount` | 积分，非负 | 受理时四舍五入后的冻结及结算金额，不再计算新价 |
| `estimated_cost_amount` | 原币金额，可空 | 按已知配置口径计算的成本估算，非实际支出 |
| `actual_cost_amount` | 原币金额，可空 | 已获取并核验的上游实际扣费；未知为 `NULL` 而非零 |
| `actual_cost_currency` | 字符串，可空 | 实际扣费币种，与金额成对保存 |
| `cost_verified_at` / `cost_evidence` | 时间 / JSONB，可空 | 核验时间与脱敏证据，实际扣费存在时必填 |
| `status` | 字符串 | 本站执行状态，定义见状态文档 |
| `upstream_status` | 字符串，可空 | 适配器归一化状态；原始状态可保存在脱敏错误或审计上下文中 |
| `billing_status` | `held` / `settled` / `released` / `refunded` | 该任务的积分处理状态 |
| `deadline_at` | 时间 | 受理时确定的展示超时阈值，不是资金释放时间 |
| `timed_out_at` | 时间，可空 | 首次超时事实，后续成功也不抹去 |
| `review_required` | 布尔，默认 `false` | 提交受理不明、矛盾结果等需要核实的标记，不阻止可安全执行的原任务查询 |
| `last_error_code` / `last_error_message` | 字符串，可空 | 脱敏后的最近异常；恢复后历史仍留在审计中 |
| `next_run_at` | 时间，可空 | 下一次查询或转存安排，支持丢失队列消息后恢复 |
| `worker_token` / `lease_until` | UUID / 时间，可空 | 短期执行租约，防重复执行和过期 Worker 写回；两者成对 |
| `submitted_at` / `upstream_completed_at` / `completed_at` | 时间，可空 | 上游确认受理、上游生成完成、本站终态时间 |

约束与查询：

- `UNIQUE(provider_id, upstream_task_id)`，仅有上游 ID 的行参与有效去重。
- `UNIQUE(user_id, idempotency_key)`；未提供键时允许多次正常提交，不能按相同提示词自动去重。是否向客户端开放此键不影响内部任务和账务幂等。
- 用户记录索引 `(user_id, created_at)`；恢复索引 `(status, next_run_at)`，按实际查询补充超时核查索引，不预建大量 JSON 索引。
- 价目快照包含已补默认值的分辨率、时长及舍入依据。配置修改、结果实际时长变化都不能改 `sale_amount`。
- 用 `CHECK` 约束同一行的字段配对、执行与账务状态组合；跨表归属、全部结果就绪等必须在业务事务中校验，不用跨表 `CHECK` 假装保证一致性。
- 受理后生成结果的源地址及其必要授权信息应加密保存，禁止进入公开响应或明文日志。

### 8. assets

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 素材或结果文件标识 |
| `user_id` | 外键 → `users.id` | 文件归属，生成结果归任务用户 |
| `source_kind` | `upload` / `external` / `generated` | 本站上传、外部素材、生成结果 |
| `status` | `pending` / `ready` / `error` | 准备或转存状态 |
| `source_url_encrypted` | 加密文本，可空 | 外部 URL 或上游结果源地址；可能含签名，不进入列表日志 |
| `oss_region` / `oss_bucket` / `oss_object_key` | 字符串，可空 | 本站持有文件的实际位置快照，不因以后更换 Bucket 丢失旧定位 |
| `content_type` / `byte_size` | 字符串 / 整数，可空 | 经校验的类型与非负字节数 |
| `checksum` | JSONB 对象，可空 | 校验算法和值，例如 SDK CRC64 及本地内容摘要；不得假设所有 ETag 都是 MD5 |
| `width` / `height` / `duration_seconds` | 整数 / 精确数量，可空 | 实测得到的文件信息，不用请求参数冒充实际结果 |
| `ready_at` | 时间，可空 | 可按其来源规则使用的时间 |

`upload` 和 `generated` 的 `ready` 必须有完整 OSS 定位且上传校验通过；`external` 可以只是已校验的 HTTPS 来源，不强制转存，其 `ready` 不保证外部文件永久存在。实际使用时仍校验外部访问条件。

对象键按任务编号与结果序号稳定生成；任务重试转存复用同一结果槽位，不覆盖其他任务。保存对象定位而非永久保存短期签名下载 URL。下载时鉴权并按最终确定的授权方式取回本站文件。

所有外部获取都校验目标、解析地址和重定向，防止访问内网，限制大小、格式和下载时间；后台配置也不能绕过安全边界。

### 9. task_assets

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `task_id` | 外键 → `tasks.id` | 所属任务 |
| `role` | `reference` / `mask` / `result` | 输入参考、蒙版、输出结果 |
| `position` | 整数，非负 | 同类文件顺序 |
| `asset_id` | 外键 → `assets.id` | 文件记录 |

主键 `(task_id, role, position)`，保证输出槽位唯一，避免重试生成多份交付关联。业务层校验输入与任务归属、角色数量、模型能力；图片输出只允许 `result/0`。不把多参考图压成一个 URL 字段，也不另建通用素材库功能。

结算只检查任务要求的全部 `result` 就绪，不能误把已就绪的参考图当成生成完成；进入转存时同事务固定全部预期输出槽位，空集合不算完成。输出关联及源记录的写入、替换均先锁任务并校验执行租约；就绪后不可替换文件或改回未就绪，避免过期 Worker 覆盖已交付内容。

## 积分与兑换

### 10. credit_entries

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 流水编号 |
| `user_id` | 外键 → `credit_accounts.user_id` | 记账账户 |
| `entry_type` | `freeze` / `settle` / `release` / `refund` / `recharge` / `admin_credit` / `admin_debit` | 业务动作 |
| `idempotency_key` | 字符串，唯一 | 业务幂等键，如 `task:<id>:settle` |
| `task_id` | 外键 → `tasks.id`，可空 | 任务资金动作关联 |
| `redemption_code_id` | 外键 → `redemption_codes.id`，可空 | 兑换关联 |
| `amount` | 积分，非负 | 本次业务金额 |
| `available_delta` / `frozen_delta` | 有符号积分 | 可用、冻结余额变动 |
| `available_after` / `frozen_after` | 积分，非负 | 锁定账户后本次提交的余额 |
| `created_at` | 时间 | 入账时间；只追加，不设 `updated_at` |

按 `entry_type` 校验关联与增减方向：任务结算类关联任务，管理员调账关联管理员填写的备注但不关联任务。账户和任务归属一致；任务相关金额等于原 `sale_amount`。管理员调账金额大于零，按四位小数 `ROUND_HALF_UP` 处理，扣除不得超过可用余额。

除唯一 `event_key` 外，建议以部分唯一索引保证 `(task_id, kind)` 以及已兑换的 `redemption_code_id` 不重复，避免调用方传不同事件键绕过同业务幂等。`settle` 与 `release` 互斥仍要靠任务锁、资金状态检查及事务，不是各自唯一就足够。

流水禁止修改和删除；修正另追加有依据的资金动作，不直接改余额掩盖原记录。首期不提供无审核的任意余额调整功能。

### 11. redemption_codes

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 兑换码标识 |
| `code_digest` | 字符串，唯一 | 高熵兑换码的安全摘要 |
| `code_prefix` | 字符串 | 后台辨认用非敏感前缀 |
| `credit_amount` | 积分，大于零 | 生成时固定的额度 |
| `created_by` | 外键 → `users.id` | 后台生成人，服务层校验管理员 |
| `redeemed_by` | 外键 → `users.id`，可空 | 兑换人 |
| `redeemed_at` | 时间，可空 | 兑换时间，与兑换人成对为空或非空 |

状态由是否已兑换推导，不存 `expires_at`、`disabled` 或多余的兑换状态枚举。明码生成时一次性展示或导出，数据库只保留摘要，不提供明码找回。单次兑换必须与账户、充值流水同事务提交；重复请求不再次到账。

## 设置与审计

### 12. system_settings

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `key` | 字符串主键 | 代码允许且有类型定义的配置名 |
| `value` | JSONB，可空 | 非敏感配置值 |
| `encrypted_value` | 加密文本，可空 | 敏感配置值，与 `value` 恰有一个非空 |
| `updated_by` | 外键 → `users.id`，可空 | 最近修改管理员；引导初始化可空 |

例如站点展示、注册开关、上传限制、任务展示超时、查询间隔、阿里云 OSS 配置。供应商、模型、价目不重复放进本表。关联的 OSS 配置整体校验后原子保存，不出现 Bucket 已改但凭证尚未更新的半套配置。

数据库和 Redis 连接、凭证加密主密钥保留在部署环境。主密钥不能与密文一起放数据库。未知配置键拒绝写入，普通配置不能改变权限、执行任意代码或跳过安全校验。

### 13. audit_logs

| 字段 | 类型 / 约束 | 用途 |
| --- | --- | --- |
| `id` | 主键 | 审计编号 |
| `actor_user_id` | 外键 → `users.id`，可空 | 管理员或操作者；系统动作可空 |
| `action` | 字符串 | 配置修改、提交不明、超时、转存异常、人工核实等 |
| `resource_type` / `resource_id` | 字符串 | 对象类型与标识，不作通用业务关联表使用 |
| `details` | JSONB 对象 | 脱敏后的前后状态、原因和核实依据 |
| `created_at` | 时间 | 只追加，不设 `updated_at` |

重要人工处理与对应状态、账务变更同事务记录。普通每次轮询不写一条业务审计；重复错误合并记录关键变化，技术日志另行脱敏。首期均不设置自动清理。

## 事务与完整性底线

- 创建任务、冻结账户与冻结流水必须一起成功或一起回滚。参数错误或余额不足时不留下已受理任务。
- 结算、释放、已结算退款均先锁任务再锁账户；兑换先锁兑换码再锁账户。统一锁顺序，事务内部不调用供应商或 OSS。
- 状态检查不能仅依赖前端、队列去重或“先查再写”。数据库唯一约束、行锁和业务状态共同保证资金动作幂等。
- 用户不能引用其他用户的 Key、输入素材或任务。管理接口读取权限不等于可以绕过资金不变量。
- 对账时，账户余额应能由不可变流水重放；`frozen` 应等于该用户所有 `held` 任务的 `sale_amount` 合计。对账异常报警，不自动改账。
- 公开、用户、管理响应分别用明确字段白名单，绝不直接返回包含成本快照、源链接或凭证的整行数据。

详细事务、状态矩阵和恢复用例见[任务状态流转](task-lifecycle.md)。

## 尚未定稿

1. 成本原币、单位、精度及必要折算方式。本文保留可追溯结构，不增加汇率或利润计算平台。
2. 长期查不到终态时的退出条件、人工关闭及资金处置，不能先落成自动退款策略。
3. 外部 API 兼容范围、本站幂等键是否开放及具体字段，不把内部表字段直接视为 OpenAI 协议。
4. 视频参数名称与可选时长、OSS 下载授权及上游、存储 SDK 版本，接入时落实；当前数据库已采用 PostgreSQL 17。

## 设计参考

以下用于约束设计，并不代表已执行数据库或 OSS 联调：

- [PostgreSQL 精确数值与特殊值](https://www.postgresql.org/docs/current/datatype-numeric.html)
- [PostgreSQL 约束、唯一性与跨行校验边界](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [PostgreSQL JSONB 与索引能力](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL 行锁与死锁](https://www.postgresql.org/docs/current/explicit-locking.html)
- [阿里云 OSS CRC64 校验](https://www.alibabacloud.com/help/en/oss/developer-reference/crc64)
