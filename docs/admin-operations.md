# 管理员异常处理与账务审计

更新：2026-11-15。本文定稿 v1.1 的异常处理动作矩阵、状态映射、接口字段和审计字段。未实现前只是设计规范，不代表页面或接口已经可用。

与 [需求与约定](requirements.md) 冲突时以需求为准；涉及账务和任务状态的既有规则见[任务与账务](task-lifecycle.md)。本文新增的规则在实现时同步回需求文档。

## v1.1 修订

- 明确文本迟到用量的自动结算和异常记录规则，新增 `late_usage` 字段；
- 明确转存行锁、管理员动作 `NOWAIT` 和 409 行为；
- 审计改为数据库触发器与权限限制，不再只依赖应用层；
- 幂等指纹纳入规范化原因；
- 人工扣费超过八位小数直接 422，不自动舍入；
- 定义 `resolution` 为“最近一次人工动作结果”，不用于判断可否操作；
- 将 CI 的 PostgreSQL 测试列为实施前置条件。

## 范围与原则

### v1.1 范围

- 查询待核实、卡住、超时的生成任务和文本调用；
- 对生成任务执行重新查询、重试转存、人工释放；
- 对文本调用执行标记待核实、人工扣费、关闭不扣费；
- 为管理员调账补充审计；
- 提供只读的账务操作审计查询；
- 用户侧展示人工处理后的最终状态。

### 不在 v1.1 范围

- 无结果的人工任务结算；
- 已结算任务的退款；
- 结果补录或外部结果 URL 绑定；
- 自动重试、自动退款、自动关闭；
- 多管理员审批、角色分级、批量处理；
- 供应商、模型价格、OSS 设置等非账务管理操作的完整审计。

### 原则

- 超时不等于失败；人工释放必须填写原因。
- 不修改历史流水，只追加；人工动作与账务、业务状态同事务提交。
- 所有人工动作必须写入数据库级不可修改的审计记录。
- 用户只看到处理后的状态和统一公开文案，不看到内部处理原因。
- 能通过重查或重试转存解决的，不直接释放。
- 结算必须有可交付结果；没有结果时只能重查或释放。
- 迟到用量不伪造、不静默丢弃：能结算则结算，已人工终态则记录异常。
- 管理员动作遇到正在处理的目标返回 409，不阻塞等待。
- 金额使用八位 `Decimal` 字符串，不使用二进制浮点数。

## 角色与权限

- 仅 `users.is_admin = true` 可访问异常列表、执行动作和查询审计。
- 沿用现有网页会话鉴权、来源校验和 `AdminUser` 依赖；非管理员返回 403。
- 普通用户只能看到自己的任务/调用状态，不能看到审计原因和操作人。
- v1.1 不区分超级管理员；所有管理员权限相同，通过审计记录区分操作人。

## 状态与动作矩阵

### 生成任务

任务状态与账务状态分开判断。只有 `billing_status = held` 的任务允许人工动作。

| 当前状态 | 账务 | 是否进入异常列表 | 允许动作 | 动作后状态 | 账务变化 |
| --- | --- | --- | --- | --- | --- |
| `queued` | `held` | 空闲超过 15 分钟时只读展示 | 无 | 等待 Worker | 无 |
| `submitting` | `held` | 空闲超过 15 分钟时只读展示 | 无 | Worker 中断后转 `submission_unknown` | 无 |
| `submission_unknown` | `held` | 是，立即 | 有上游 ID：`requery`；无上游 ID：`release` | `pending` 或 `failed` | 重查无账务变化；释放退冻结 |
| `pending` | `held` | 空闲超过 15 分钟 | `requery`、`release` | 保持 `pending` 或 `failed` | 重查无账务变化；释放退冻结 |
| `processing` | `held` | 空闲超过 15 分钟 | `requery`、`release` | 保持 `processing` 或 `failed` | 同上 |
| `transferring` | `held` | 空闲超过 10 分钟 | 有结果快照/就绪素材：`retry_transfer`；无就绪结果时可 `release` | 保持 `transferring` 或 `failed` | 重试无账务变化；释放退冻结 |
| `succeeded` | `settled` | 否 | 无 | 终态 | 无 |
| `failed` | `released` | 否 | 无 | 终态 | 无 |
| 任意 | `refunded` | 否 | 无 | 终态；v1.1 不提供退款入口 | 无 |

补充规则：

- `queued` 和 `submitting` 只用于发现 Worker 未运行或提交卡住，不提供人工动作；`submitting` 避免与在途提交竞争，等待 Worker 标记或转存。
- `submission_unknown` 只有在存在 `upstream_task_id` 时允许 `requery`；否则只能 `release`。
- `transferring` 存在已就绪结果素材时禁止 `release`，必须使用 `retry_transfer`，避免用户已可获得结果却被退款。
- 转存由 Worker 在持有任务行锁的事务中执行；查询成功后不再递归转存，任务提交为 `transferring` 后由下一次 Worker 循环加锁处理。
- 管理员动作对目标行使用 `FOR UPDATE NOWAIT`；Worker 正在转存时返回 409，不允许在转存进行中释放。
- `release` 只释放当前 `frozen_amount`，不支持部分释放。
- 人工释放后清除 `result_snapshot`；保留已存在的 `Asset` 记录，不做物理删除。
- 任何成功动作都清除 `review_required`，并写入 `resolution`、`resolved_at`、`resolved_by_user_id`。
- 任务再次被 Worker 标记异常时，可以重新进入异常列表；审计保留历史。

### 文本调用

文本调用没有冻结，只有可用余额扣减。状态和动作如下：

| 当前状态 | 是否进入异常列表 | 允许动作 | 动作后状态 | 账务变化 |
| --- | --- | --- | --- | --- |
| `processing` | 至少 30 分钟且超过快照超时 + 15 分钟 | `mark_unknown` | `usage_unknown` | 无 |
| `usage_unknown` | 是，立即 | `manual_charge`、`close_no_charge` | `settled_manually` 或 `closed_no_charge` | 人工扣费或零扣费 |
| `succeeded` | 否 | 无 | 终态 | 已有 `text_charge` |
| `failed` | 否 | 无 | 终态 | 可能已有 `text_charge` |
| `settled_manually` | 否 | 无 | 终态 | 已有 `text_charge` |
| `closed_no_charge` | 否 | 无 | 终态 | 无流水，金额为零 |

补充规则：

- `processing` 只有在同时满足“创建或最后更新已超过 30 分钟”和“超过 `price_snapshot["timeout_seconds"] + 15 分钟` 安全窗口”时允许 `mark_unknown`，避免与仍在执行的调用竞争。管理员动作使用 `FOR UPDATE NOWAIT`，并发处理时返回 409。
- 30 分钟是下限，不是唯一依据；如果确认调用仍在进行（例如上游仍返回流），不要执行 `mark_unknown`，等待调用自行结束。
- `usage_unknown` 尚未进入人工终态时，迟到的可靠用量由 `finish_text_call()` 自动结算，转 `succeeded/failed`；这是自动路径，不是管理员动作。若人工动作先完成，迟到的结算请求看到状态已变，返回 409。
- 已进入 `settled_manually` 或 `closed_no_charge` 后迟到的用量写入 `late_usage`、`late_usage_at`，不改变状态和账务，并记录告警日志；不允许静默丢弃。
- `manual_charge` 只从 `usage_unknown` 进入，金额必须大于零、最多八位小数；允许余额扣成负数。
- `close_no_charge` 只从 `usage_unknown` 进入；`charge_amount` 写 `0.00000000`，不写账务流水。
- `manual_charge` 的 `cost_amount` 保持为空，因为人工核定不代表掌握上游成本。
- `usage` 保持为空，不伪造 token 用量。
- 人工动作写入固定公开文案，内部原因只进审计；不保留可能包含供应商信息的内部错误文案。
- `settled_manually` 和 `closed_no_charge` 是终态，不再接受人工动作。

### 自动迟到结算

`finish_text_call()` 收到最终用量时按以下规则处理：

| 当前状态 | 收到可靠用量 | 处理 |
| --- | --- | --- |
| `processing` | 是 | 按现有规则结算，转 `succeeded` 或 `failed` |
| `usage_unknown` | 是 | 自动结算并扣费，转 `succeeded` 或 `failed`；清除过渡 `resolution` |
| `usage_unknown` | 否 | 保持待核实 |
| `settled_manually` | 是 | 写入 `late_usage`、`late_usage_at`，不二次扣费，不改状态 |
| `closed_no_charge` | 是 | 写入 `late_usage`、`late_usage_at`，不补扣费，不改状态 |
| `succeeded` / `failed` | 是 | 与已有 `usage` 相同视为幂等重放；不同才写 `late_usage`，不重复扣费 |
| 任意终态 | 否 | 不改变状态 |

迟到结算与管理员动作使用同一行锁；管理员动作先完成时，迟到结算看到非 `usage_unknown` 状态，记录异常；迟到结算先完成时，管理员动作看到状态已变，返回 409。

## 动作定义

### `task.requery`

- 适用：`submission_unknown`（必须有上游 ID）、`pending`、`processing`。
- 前置条件：`billing_status = held`，任务存在。
- 效果：
  - `submission_unknown` 改为 `pending`；
  - `pending/processing` 保持原状态；
  - `next_run_at = 当前时间`；
  - `review_required = false`；
  - `resolution = manual_requeued`。
- 账务：无。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；Worker 正在处理时返回 409。
- 审计：记录动作前后状态、上游状态、原因。
- 用户侧：继续显示排队/处理中；不显示“人工”字样。

### `task.retry_transfer`

- 适用：`transferring`。
- 前置条件：`billing_status = held`，且 `result_snapshot` 非空或存在已就绪结果素材。
- 效果：`next_run_at = 当前时间`，`review_required = false`，`resolution = manual_retry_transfer`。
- 账务：无。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；Worker 正在转存时返回 409。
- 审计：记录动作前后状态和结果快照数量（不记录素材 URL）。

### `task.release`

- 适用：`submission_unknown`、`pending`、`processing`、`transferring`。
- 前置条件：`billing_status = held`；不存在状态为 `ready` 的结果素材。
- 效果：
  - `status = failed`；
  - `billing_status = released`；
  - `completed_at = 当前时间`；
  - `next_run_at = null`；
  - `error_code = manual_release`；
  - `error_message = "任务已关闭，冻结积分已释放"`；
  - `review_required = false`；
  - `result_snapshot = []`；
  - `resolution = manual_released`；
  - 如果已到 `deadline_at` 且 `timed_out_at` 为空，写入当前时间。
- 账务：可用余额 `+frozen_amount`，冻结 `-frozen_amount`，写 `release` 流水。
- 流水幂等键：`task:<task_uuid>:manual-release:<request_id>`。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；Worker 正在查询或转存时返回 409，不允许在转存进行中释放。
- 审计：记录原因、释放金额、账务流水 ID。
- 用户侧：任务显示“已失败”，错误文案使用统一公开文案，不返回内部原因。

### `text.mark_unknown`

- 适用：`processing`，且同时满足“至少 30 分钟”和“超过快照超时 + 15 分钟”。
- 效果：
  - `status = usage_unknown`；
  - `completed_at = 当前时间`；
  - `error_message = "调用已中断，用量待核实"`；
  - `resolution = manual_marked_unknown`。
- 账务：无。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；调用仍在结算时返回 409。
- 审计：记录动作前状态、空闲时长、原因。
- 迟到用量：此后到达的可靠用量仍可自动结算；如果先完成人工扣费/关闭，则写入 `late_usage` 异常。

### `text.manual_charge`

- 适用：`usage_unknown`，且没有进入其他人工终态。
- 请求金额：字符串，`> 0`；超过八位小数直接返回 422，不自动舍入；少于八位补零。
- 效果：
  - `status = settled_manually`；
  - `charge_amount = amount`；
  - `cost_amount = null`；
  - `completed_at` 为空时写当前时间；
  - `error_message = "调用已人工核定"`；
  - `resolution = manual_charged`。
- 账务：可用余额 `-amount`，允许负数；写 `text_charge` 流水，`description = "文本调用人工核定扣费"`。
- 流水幂等键：`text:<call_uuid>:manual-charge:<request_id>`。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；迟到结算先完成时返回 409。
- 审计：记录金额、账务流水 ID、原因。
- 用户侧：显示“人工已结算”和实际扣费金额。
- 迟到用量：完成后到达的用量写入 `late_usage`，不二次扣费，不改变状态。
- 大额提示：前端对 `amount >= 100.00000000` 要求二次确认；后端只校验 `0 < amount < 10^16` 和最多八位小数。

### `text.close_no_charge`

- 适用：`usage_unknown`，且没有进入其他人工终态。
- 效果：
  - `status = closed_no_charge`；
  - `charge_amount = 0.00000000`；
  - `cost_amount = null`；
  - `completed_at` 为空时写当前时间；
  - `error_message = "调用已关闭，未扣费"`；
  - `resolution = manual_closed_no_charge`。
- 账务：无流水。
- 并发：目标行使用 `FOR UPDATE NOWAIT`；迟到结算先完成时返回 409。
- 审计：记录原因。
- 迟到用量：完成后到达的用量写入 `late_usage`，不补扣费，不改变状态。
- 用户侧：显示“已关闭，未扣费”和零金额。

### 管理员调账审计

现有 `/api/admin/users/{user_id}/credits` 保持账务行为不变，新增：

- 写 `admin_actions`；
- 动作 `user.credit_increase` / `user.credit_decrease`；
- `target_type = user`，`target_id = 用户 ID`；
- 记录调整金额、原因、请求指纹、账务流水 ID、调整前后可用/冻结余额；
- 请求体增加可选 `request_id`，前端始终传入；提供时参与幂等，未提供时服务端生成且无法幂等重放；
- 请求指纹包含方向、金额和规范化原因；
- 现有原因长度保持 1–240，不改为异常动作的 4–240。

## 数据模型

### 新表 `admin_actions`

只追加、不修改、不删除。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | bigint identity | PK | 审计 ID |
| `actor_user_id` | bigint | FK users.id，非空 | 操作管理员 |
| `action` | varchar(40) | 非空 | 见动作枚举 |
| `target_type` | varchar(20) | 非空 | `task` / `text_call` / `user` |
| `target_id` | varchar(64) | 非空 | 任务或调用 UUID，或用户 ID |
| `request_id` | uuid | 非空、唯一 | 防重复提交 |
| `request_fingerprint` | char(64) | 非空 | 动作、目标、金额、规范化原因的 SHA-256 |
| `reason` | varchar(240) | 非空 | 内部处理原因 |
| `amount` | numeric(24,8) | 可空 | 涉及账务时的金额 |
| `credit_entry_id` | bigint | 可空，FK credit_entries.id | 对应账务流水 |
| `before_snapshot` | jsonb | 非空，默认 `{}` | 关键字段处理前快照 |
| `after_snapshot` | jsonb | 非空，默认 `{}` | 关键字段处理后快照 |
| `created_at` | timestamptz | 非空，默认 now() | 操作时间 |

索引：

- `(target_type, target_id, created_at desc)`
- `(actor_user_id, created_at desc)`
- `(action, created_at desc)`

动作枚举：

```text
task.requery
task.retry_transfer
task.release
text.mark_unknown
text.manual_charge
text.close_no_charge
user.credit_increase
user.credit_decrease
```

快照只保存关键字段：

- 任务：`status`、`billing_status`、`review_required`、`frozen_amount`、`error_code`、`resolution`。
- 文本：`status`、`charge_amount`、`cost_amount`、`error_message`、`resolution`。
- 用户：`available`、`frozen`。

不保存提示词、参考素材 URL、上游任务 ID、供应商凭证、OSS 配置或完整请求快照。

数据库级不可变：

- 迁移创建 `BEFORE UPDATE OR DELETE` 触发器，任何修改或删除都抛出异常；
- 生产环境给应用角色只授予 `admin_actions` 的 `INSERT`、`SELECT`，迁移和运维使用独立角色；
- 测试必须验证直接 `UPDATE`、`DELETE` 审计记录会失败，而不是只验证没有对应 API。

### `tasks` 新增字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `resolution` | varchar(32) 可空 | `manual_requeued` / `manual_retry_transfer` / `manual_released` |
| `resolved_at` | timestamptz 可空 | 最近一次人工处理时间 |
| `resolved_by_user_id` | bigint 可空，FK users.id | 最近一次操作管理员 |

新增索引：`(review_required, status, created_at)`。

### `text_calls` 新增字段与状态

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `resolution` | varchar(32) 可空 | `manual_marked_unknown` / `manual_charged` / `manual_closed_no_charge` |
| `resolved_at` | timestamptz 可空 | 最近一次人工处理时间 |
| `resolved_by_user_id` | bigint 可空，FK users.id | 最近一次操作管理员 |
| `late_usage` | jsonb 可空 | 人工终态后到达的最近一次用量快照 |
| `late_usage_at` | timestamptz 可空 | 最近一次迟到用量时间 |

状态约束扩展为：

```text
processing
succeeded
failed
usage_unknown
settled_manually
closed_no_charge
```

新增索引：`(status, updated_at)`。

`late_usage` 只保存最近一次迟到用量，重复到达时覆盖并记录告警日志；不使用它重算历史账务。

### `resolution` 语义

`resolution` 表示“最近一次人工动作结果”，不是历史记录，也不用于判断当前能否操作；能否操作只看 `status`、`billing_status` 和前置条件。

生命周期：

- `manual_requeued`、`manual_retry_transfer`、`manual_marked_unknown` 是过渡标记：
  - 任务随后自动进入 `succeeded` 或 `failed` 时，清除 `resolution`、`resolved_at`、`resolved_by_user_id`；
  - 文本调用随后由迟到用量自动结算时，同样清除；
  - 再次执行人工动作时覆盖为新结果。
- `manual_released`、`manual_charged`、`manual_closed_no_charge` 是人工终态：
  - 保留 `resolution` 和操作人/时间，用于用户侧展示；
  - 后续迟到数据只写 `late_usage`，不改写 `resolution`。
- 历史动作始终以 `admin_actions` 为准，`resolution` 被清除不影响审计。

### 账务流水

`credit_entries` 结构不变，继续使用 `idempotency_key` 防重。人工动作的流水通过 `admin_actions.credit_entry_id` 关联。

人工释放金额固定为 `frozen_amount`，人工扣费金额来自请求；两者都只追加流水，不回改旧记录。

### 迁移顺序

1. 新建 `admin_actions`，包含 `request_fingerprint`；
2. 创建 `admin_actions` 不可变触发器；
3. 给 `tasks`、`text_calls` 增加 `resolution`、`resolved_at`、`resolved_by_user_id`；
4. 给 `text_calls` 增加 `late_usage`、`late_usage_at`；
5. 替换 `text_calls.status` 检查约束；
6. 增加索引；
7. 不 backfill 历史数据，既有记录 `resolution`、`late_usage` 为空；
8. 同步更新 `text_calls.status` 的 Pydantic Literal、账户返回 schema、前端状态映射、公开文档状态表和测试；
9. 执行 `alembic check` 确认模型与迁移一致。

## 后端接口

所有接口前缀为 `/api/admin`，仅管理员可访问，不进入公开 OpenAPI。

### 汇总

```text
GET /api/admin/exceptions/summary
```

响应：

```json
{
  "tasks": {
    "submission_unknown": 2,
    "stuck_queued": 0,
    "stuck_submitting": 0,
    "stuck_processing": 1,
    "stuck_transferring": 0,
    "review_required": 3
  },
  "text_calls": {
    "usage_unknown": 1,
    "stuck_processing": 0,
    "late_usage": 0
  },
  "oldest_waiting_seconds": 5400
}
```

### 任务异常列表

```text
GET /api/admin/exceptions/tasks
```

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string 可选 | 任务状态 |
| `review_required` | bool 可选 | 是否只看待核实 |
| `min_idle_minutes` | int 可选 | 距最后更新时间的最小分钟数 |
| `min_age_minutes` | int 可选 | 距创建时间的最小分钟数 |
| `user_id` | int 可选 | 用户 |
| `task_id` | uuid 可选 | 任务 UUID |
| `offset` | int | 默认 0 |
| `limit` | int | 默认 20，最大 100 |

响应：

```json
{
  "data": [
    {
      "id": "uuid",
      "user": { "id": 1, "email": "user@example.com" },
      "model": "gpt-image-2",
      "media_type": "image",
      "status": "submission_unknown",
      "billing_status": "held",
      "frozen_amount": "1.23000000",
      "created": 1763150000,
      "updated": 1763150300,
      "waiting_seconds": 3600,
      "idle_seconds": 3300,
      "upstream_status": null,
      "has_upstream_id": false,
      "has_ready_result": false,
      "review_required": true,
      "resolution": null,
      "allowed_actions": ["release"],
      "last_action": null
    }
  ],
  "total": 1
}
```

`last_action` 包含 `action`、`actor_email`、`created_at`，不返回原因和快照。

`allowed_actions` 由后端按当前状态和前置条件计算，前端只渲染允许的动作；动作接口仍会再次校验，不能只依赖前端按钮。

### 文本异常列表

```text
GET /api/admin/exceptions/text-calls
```

查询参数与任务列表一致，`task_id` 改为 `call_id`；额外支持 `has_late_usage` 布尔筛选。

响应：

```json
{
  "data": [
    {
      "id": "uuid",
      "user": { "id": 1, "email": "user@example.com" },
      "model": "gpt-6.1-sol",
      "endpoint": "/v1/responses",
      "status": "usage_unknown",
      "created": 1763150000,
      "updated": 1763150300,
      "waiting_seconds": 3600,
      "idle_seconds": 3300,
      "charge_amount": null,
      "error_message": "调用已中断，用量待核实",
      "has_late_usage": false,
      "late_usage_at": null,
      "resolution": null,
      "allowed_actions": ["manual_charge", "close_no_charge"],
      "last_action": null
    }
  ],
  "total": 1
}
```

### 任务动作

```text
POST /api/admin/tasks/{task_id}/resolve
```

请求体：

```json
{
  "action": "release",
  "reason": "上游未受理，人工核实关闭",
  "request_id": "a3f1c2d4-0000-4000-8000-000000000001"
}
```

`action` 枚举：`requery`、`retry_transfer`、`release`。

响应：

```json
{
  "id": "uuid",
  "status": "failed",
  "billing_status": "released",
  "resolution": "manual_released",
  "resolved_at": "2026-11-15T12:00:00Z",
  "audit_id": 12,
  "credit_entry_id": 34
}
```

### 文本动作

```text
POST /api/admin/text-calls/{call_id}/resolve
```

请求体：

```json
{
  "action": "manual_charge",
  "amount": "0.86333000",
  "reason": "按上游账单人工核定",
  "request_id": "a3f1c2d4-0000-4000-8000-000000000002"
}
```

`action` 枚举：`mark_unknown`、`manual_charge`、`close_no_charge`。

- `mark_unknown` 要求 `processing` 同时满足 30 分钟下限和快照超时 + 15 分钟安全窗口；
- `mark_unknown`、`close_no_charge` 不接受 `amount`；
- `manual_charge` 必须提供 `amount`，超过八位小数返回 422，少于八位补零；
- 未知字段返回 422。

响应：

```json
{
  "id": "uuid",
  "status": "settled_manually",
  "charge_amount": "0.86333000",
  "resolution": "manual_charged",
  "resolved_at": "2026-11-15T12:00:00Z",
  "audit_id": 13,
  "credit_entry_id": 35
}
```

### 审计列表与详情

```text
GET /api/admin/audit-actions
GET /api/admin/audit-actions/{action_id}
```

筛选：`actor_user_id`、`action`、`target_type`、`target_id`、`created_from`、`created_to`、`offset`、`limit`。

列表返回操作人邮箱、动作、目标、金额、原因摘要、时间；详情额外返回前后快照和账务流水 ID。

审计接口只读，不提供修改和删除。

### 校验、幂等与并发

所有写接口统一规则：

1. 校验管理员身份和请求来源；
2. 使用 Pydantic 禁止未知字段；
3. 异常处理动作的 `reason` 去空格后为 4–240 字符；现有调账接口保持 1–240；
4. `request_id` 必须是 UUID；
5. 人工扣费金额为 `0 < amount < 10^16`；超过八位小数返回 422，少于八位补零；现有管理员调账保持原有四舍五入；
6. 使用 `FOR UPDATE NOWAIT` 锁定目标行；锁冲突返回 409；
7. 锁定积分账户；
8. 检查当前状态是否允许该动作；
9. 写业务状态、账务流水、审计记录；
10. 单次提交事务。

错误码：

| HTTP | 场景 |
| --- | --- |
| 403 | 非管理员 |
| 404 | 任务、调用或用户不存在 |
| 409 | 当前状态不允许该动作、重复请求参数不一致、存在就绪结果却尝试释放、目标正在被 Worker 处理而无法加锁 |
| 422 | 字段未知、原因长度不合规、金额格式错误、超过八位小数、动作与状态不匹配 |
| 200 | 首次成功，或相同 `request_id` 的幂等重放 |

幂等规则：

- `admin_actions.request_id` 唯一；
- `request_fingerprint` 由动作、目标、金额和规范化原因生成；
- 相同 `request_id` 且指纹一致时，返回第一次的结果；
- 相同 `request_id` 但指纹不同返回 409；
- 账务流水使用 `request_id` 派生唯一键；即使并发请求同时到达，也只产生一条流水。

并发规则：

- 先锁 Task/TextCall，再锁 CreditAccount，与现有结算/释放顺序一致；
- 管理员动作用 `FOR UPDATE NOWAIT`，目标被 Worker 持有锁时立即返回 409，不阻塞请求；
- 第二个并发请求看到终态后返回 409；
- 不允许批量动作，避免一次锁定大量账户。

## 前端页面

### 异常处理

新增 `/admin/exceptions`，管理菜单增加“异常处理”。

- 顶部统计卡：待核实任务、卡住任务、待核实文本调用、最久等待时长；
- 两个 Tab：生成任务、文本调用；
- 筛选：状态、空闲时长、用户、ID；
- 桌面表格、移动端卡片；
- 详情抽屉：任务/调用快照、上游状态、冻结/扣费金额、最近动作、审计时间线；
- 操作区：
  - 任务：重新查询、重试转存、释放；
  - 文本：标记待核实、人工扣费、关闭不扣费；
  - 原因必填；
  - 人工扣费金额输入使用字符串，显示八位小数；
  - 释放和扣费需要二次确认；
  - 提交时禁用按钮，成功后刷新列表。

打开动作弹窗时生成 `request_id`，同一弹窗内重试复用同一个 ID；关闭后重新打开生成新 ID。

### 操作审计

新增 `/admin/audit`，或作为异常处理的独立 Tab：

- 筛选操作人、动作、目标类型、日期；
- 只读表格；
- 详情展示前后快照、金额、原因、账务流水 ID；
- 不提供编辑和删除。

### 用户侧展示

- 账户返回的 `TaskSummary`、`TextCallSummary` 增加只读 `resolution` 字段，不返回原因、操作人和审计 ID；
- 任务：`failed` 且 `resolution = manual_released` 时显示“已关闭”，错误文案使用统一文案；
- 任务：`resolution = manual_requeued` / `manual_retry_transfer` 是过渡标记，自动进入终态后清除；过渡期间可显示“已重新处理”；
- 文本：`settled_manually` 显示“人工已结算”；`closed_no_charge` 显示“已关闭未扣费”和零金额；
- 公开日志不显示管理员、内部原因、审计 ID 或账务流水 ID。

公开文案映射：

| 场景 | 用户可见状态 | 用户可见 `error_message` |
| --- | --- | --- |
| 任务人工释放 | `failed` | 任务已关闭，冻结积分已释放 |
| 文本标记待核实 | `usage_unknown` | 调用已中断，用量待核实 |
| 文本人工扣费 | `settled_manually` | 调用已人工核定 |
| 文本关闭不扣费 | `closed_no_charge` | 调用已关闭，未扣费 |
| 迟到用量异常 | 保持原状态 | 不改变用户文案，只记录内部异常 |

内部原因、供应商错误、审计 ID 和账务流水 ID 只返回管理员，不进入账户接口或公开日志。

## 审计与安全

- 审计记录只追加；迁移创建 `BEFORE UPDATE OR DELETE` 触发器，数据库层拒绝修改和删除；
- 生产环境给应用角色只授予 `admin_actions` 的 `INSERT`、`SELECT`；迁移和运维使用独立角色；
- 原因字段可能包含用户信息，只返回管理员；
- 快照不包含密钥、提示词、素材 URL、上游任务 ID；
- 管理员调账和人工扣费都必须记录金额与账务流水；
- 人工扣费允许负余额，页面必须提示当前可用余额；
- 迟到用量只写 `late_usage` 和告警日志，不自动补扣或退款；
- 不做自动重试或自动退款；
- 审计保留期暂定永久，后续按数据量决定归档策略。

## 测试与验收

### 测试环境

- CI 必须提供 PostgreSQL service，并执行 `pytest`、`alembic check`；
- 并发、迟到用量、审计不可变和转存竞态测试必须在 CI 的 PostgreSQL 中运行，不能用 SQLite 或 mock 替代；
- 本地通过 `NODEPASS_TEST_DATABASE_URL` 复现同一套测试。

### 后端

- 非管理员访问所有接口返回 403；
- 动作矩阵逐项覆盖：合法状态成功、非法状态 409；
- `requery` 无上游 ID 被拒绝；
- `retry_transfer` 无结果快照/就绪素材被拒绝；
- 存在就绪结果时 `release` 被拒绝；
- `release` 冻结转可用、写 `release` 流水、任务终态；
- `manual_charge` 扣可用余额、允许负数、写 `text_charge` 流水；
- `close_no_charge` 不写流水、金额为零；
- `mark_unknown` 未满足 30 分钟或快照超时 + 15 分钟被拒绝；
- `usage_unknown` 收到迟到可靠用量后自动结算；
- 已 `settled_manually` / `closed_no_charge` 后收到用量只写 `late_usage`，不二次扣费；
- `succeeded/failed` 收到相同用量不写异常，收到不同用量才写 `late_usage`；
- 转存中 `release` 返回 409，释放成功后 Worker 不再上传，不产生孤儿素材；
- 查询成功后不再递归转存；测试需覆盖任务停留在 `transferring` 后由下一次 Worker 循环完成转存和结算；
- 相同 `request_id` 且指纹一致返回原结果，不重复记账；
- 相同 `request_id` 但原因或其他参数不同返回 409；
- 人工扣费超过八位小数返回 422；
- 同一目标并发处理只有一个成功；
- `resolution` 在自动终态后清除，人工终态保留；
- 审计记录包含操作人、原因、金额、前后快照和账务流水；
- 直接 UPDATE/DELETE `admin_actions` 被数据库拒绝；
- 审计接口无写入、修改、删除路由；
- 迁移后 `alembic check` 通过。

### 前端

- 管理员可见异常处理和操作审计入口；普通用户不可见，直接访问被拒；
- 筛选、分页、详情、移动卡片；
- 动作与状态联动，非法动作不可选；
- 原因、金额校验；
- 提交中按钮禁用；
- 释放/扣费二次确认；
- 审计页只读；
- 三态主题、375px 无横向滚动。

### 验收标准

- 常见异常无需直接修改数据库即可处理；
- 每次人工动作都有审计、操作人和原因；
- 每次账务变化都有唯一流水，重复提交不重复记账；
- 用户侧状态与实际账务一致；
- 完整后端测试在 CI 的 PostgreSQL 环境通过。

## 实施顺序与运维

### 实施顺序

1. **CI + PostgreSQL**：先让后端测试和迁移检查可重复执行；
2. 迁移与数据模型：`admin_actions`、触发器、请求指纹、`resolution` 字段、`late_usage`、新文本状态、索引；
3. 状态机修复：文本迟到用量、取消递归转存、转存入口守卫，并补并发测试；
4. 审计写入、动作矩阵和幂等；
5. 后端动作服务与接口，先内部使用验证；
6. 只读异常列表、汇总和审计页；
7. 低风险动作：`requery`、`retry_transfer`；
8. 释放动作和文本三个动作；
9. 用户侧状态和公开文案；
10. 完整管理页面、移动端适配和交互。

### 运维约定

- 每日查看异常汇总，优先处理 `submission_unknown` 和 `usage_unknown`；
- 释放前先核实上游任务是否已受理或已产生结果；
- 人工扣费必须能对应上游账单或调用记录；
- 监控 `late_usage`；出现时复核人工扣费或关闭决定，不自动补扣或退款；
- 每次处理在客服工单记录审计 ID；
- 不直接修改数据库；紧急操作也必须留下审计；
- 大额扣费或批量异常先升级处理，不在 v1.1 提供批量入口。

### 待后续决定

- 已结算任务的全额/部分退款；
- 无结果人工结算和结果补录；
- 多管理员审批和角色分级；
- 审计归档、保留期和导出；
- 供应商、模型价格、OSS 设置变更的审计。
