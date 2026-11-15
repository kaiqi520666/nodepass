# 任务与账务

更新：2026-11-16。图片/视频异步冻结，文本同步或流式后付费；两种状态和账务不能混用。

## 图片与视频状态

| `tasks.status` | 行为 | 账务 |
| --- | --- | --- |
| `queued` | 待提交 | `held` |
| `submitting` | 已持久化提交中；中断不重发 | `held` |
| `submission_unknown` | 受理不明，不自动调度，等待核实 | `held` |
| `pending` | 查询原上游任务 | `held` |
| `processing` | 查询原上游任务 | `held` |
| `transferring` | 上游成功，仅重试结果保存 | `held` |
| `succeeded` | 本站转存完成并结算，保证结果 URL | `settled` |
| `failed` | 明确失败，已全额释放冻结 | `released` |

HTTP 200 仅说明查询成功；未知状态不判成功/失败、不重提，保留任务 ID 核实。后端人工处理接口与管理员异常处理页已实现；动作矩阵见[管理员异常处理与账务审计](admin-operations.md)。

## 受理、执行与恢复

1. API Key 鉴权，校验模型/供应商启用、补齐默认值、校验能力。图片只允许一张；按秒视频必须显式 `seconds`，按条可用默认时长。
2. 按 `pricing_dimensions` 精确匹配 `model_prices.variant`，缺价拒绝；空维度的 `{}` 是精确价目，不是兜底。按张/条数量为 1，按秒使用请求合法秒数，不按成片时长重算。
3. 锁积分账户；同事务创建 `queued/held` 任务、快照、可用转冻结和唯一冻结流水，受理失败不留下任务。
4. 单 Worker 用 `FOR UPDATE SKIP LOCKED` 领取 `held`、未标记 `review_required` 的到期任务；先保存 `submitting` 再调用一次上游，远程付费 POST 不自动重试。
5. 上游成功先保存 `result_snapshot` 并进入 `transferring`；不在查询事务内递归转存，由下一次 Worker 持任务行锁处理。管理员动作遇到该行锁返回 409，避免释放与转存竞态。图片下载上传，视频流式下载至临时文件再上传 OSS，每任务当前只接收一个结果。
6. 转存完成后，同事务写 `Asset`、有序结果关联、`succeeded/settled`、完成时间、结算流水及冻结减少，清除临时结果快照和错误。

图片编辑复用上述流程和模型价格，不另建任务表或账务类型。`request_params.images` 保存有序参考图对象，mask 单独保存；适配器据此选择编辑的提交和查询路径，重启后仍查询原编辑任务。外部参考图只转发 HTTPS URL，不自动转存为本站素材。

| 中断或异常 | 恢复规则 |
| --- | --- |
| `queued` 时重启 | 扫描后提交 |
| 提交前本地配置错误（凭证、适配器、快照） | 暂停为 `queued/review_required`，`next_run_at=null`，保留冻结；管理员核实从未提交后可恢复提交或释放 |
| `submitting` 时重启或受理无法确认 | 标记 `submission_unknown/review_required`，保留冻结，不重提 |
| 已有上游 ID | 继续查询原供应商、原 ID |
| 查询暂时异常、长时间生成或超时 | 按快照间隔继续查询，保留冻结 |
| 查询被明确拒绝（含 404）、执行配置错误、缺少上游 ID | 暂停并标记 `review_required`，保留冻结，不根据 HTTP 错误自动释放 |
| OSS 配置不完整、主密钥不可用或明确权限错误 | 暂停并标记 `review_required`，保留冻结；网络中断和上游 5xx 仍按间隔重试 |
| 转存暂时失败或转存中重启 | 用已存结果引用只重试转存，不重新生成、不结算；回滚后若管理员已改变任务状态，Worker 不覆盖人工动作 |
| 无效结果快照或未预期的任务异常 | 回滚后重新锁定任务，按已持久化阶段暂停；`submitting` 转受理不明，其余保留阶段，保留冻结 |
| 提交上游被明确拒绝或生成状态明确失败 | 同事务释放冻结、写 `failed` 与完成时间 |
| 已结算/释放后重复执行 | 返回既有结果，不重复记账 |

对象键按任务和序号稳定生成，重试可能覆盖同一对象；视频临时文件退出时关闭。当前没有断点续传、执行租约、并发池或对象恢复扫描器。等待生成靠 `next_run_at`，不睡眠几小时；一次网络请求/转存仍占用单 Worker。

`review_required=true` 表示暂停，Worker 不再领取，避免异常任务反复刷新 `updated_at`。`next_run_at=null` 本身不表示暂停，未标记的任务仍可立即领取。管理员恢复会清除标记、重设调度时间并写审计；不会刷新旧任务快照。凭证修复读取当前供应商凭证，适配器/地址等仍取原快照；快照本身不可恢复时应核实后释放，不能强行改成新配置。

任务级隔离不吞 `KeyboardInterrupt/SystemExit`；任务写入被数据库拒绝（`DataError/IntegrityError`）回滚后暂停。连接等基础设施错误交由 Worker 外层记录异常类型、关闭当前 Session 并按空闲间隔退避。`--once` 基础设施失败返回非零。日志只记录任务 ID、阶段和异常类型，不记录异常原文、SQL 参数、密钥、素材 URL 或完整快照。本次不增加重试预算、Worker 心跳或完整请求日志体系。

仍仅支持单 Worker。`submitting` 的持久化提交会释放行锁，`SKIP LOCKED` 不等于执行租约；不得直接多开 Worker，未来扩容须另行实现执行归属及旧执行者写入保护。

## 快照与超时

| 数据 | 边界 |
| --- | --- |
| 模型映射、参数、价目、单位与金额 | 创建时保存 `request_params/model_snapshot`，后台改价不回写 |
| 供应商地址、适配器、请求超时/轮询间隔/任务时限 | `provider_snapshot`，只影响新任务；由时限计算 `deadline_at` |
| 供应商凭证 | 执行时读取原 `provider_id` 当前凭证，轮换会影响在途查询 |
| OSS 配置与凭证 | 转存时读当前设置；已交付 URL 不重写 |
| 文本价格、倍率、模型、地址、请求超时与返回方式 | 本次 `text_calls.price_snapshot`，不随后台修改 |
| 数据库连接、会话签名及 Fernet 主密钥 | 部署环境维护，不存业务设置 |

任务时限不是退款时间。`timed_out` 按超时记录，或 `(completed_at 或当前时间) >= deadline_at` 判断；及时完成的历史任务不会后来误标。迟到成功仍交付结算并保留超时事实。

视频 API 和账户日志返回 `timed_out`，图片开发者查询暂不返回。`created/completed` 为 Unix 秒级时间戳；未完成时 `completed=null`，终态写完成时间。`submission_unknown` 不在自动领取清单，查询本站不会使其自行恢复。

停用供应商只阻止新调用，不自动取消或退款在途任务。没有客户端提交幂等键，两次合法 POST 会建两个任务；响应丢失或受理不明先核实，不能自动重新提交。

## 生成账务

金额统一八位 `Decimal/ROUND_HALF_UP`；使用创建时 `frozen_amount`，不按当前售价或成本扣用户。`quantity` 保存请求计费数量，`cost_amount` 为估算快照，不冒充上游实扣。

| 动作 | 可用变化 | 冻结变化 |
| --- | --- | --- |
| 冻结 A | `-A` | `+A` |
| 成功结算 A | `0` | `-A` |
| 明确失败释放 A | `+A` | `-A` |

结算/释放先锁任务再锁账户，检查 `held` 并用 `task:<UUID>:freeze/settle/release` 唯一事件键防重；账户、状态、流水同事务。释放不是已结算退款，不重复执行两种返还。

账务流水只追加，不回改旧流水。数据库允许退款/充值类型不代表业务已开放；长期不明、永久无法交付及人工退款规则见[需求待办](requirements.md#未实现与待确认)。

## 文本后付费

文本使用 `text_calls`，不进入生成任务 Worker，不冻结预估金额；准入检查可用余额大于零，正文不入库。

| 状态 | 含义 |
| --- | --- |
| `processing` | 调用中，金额未知 |
| `succeeded` | 获得可靠用量并结算 |
| `failed` | 拒绝或生成失败，有可靠用量仍可扣款 |
| `usage_unknown` | 无可靠用量，金额未知待核实；进入人工终态前收到迟到可靠用量仍可自动结算 |

```text
普通输入 = input_tokens - cached_tokens
基准费用 = (普通输入 × 输入价 + 缓存命中 × 缓存价 + 输出总量 × 输出价) / 1,000,000
扣款 = ROUND_HALF_UP(基准费用 × sale_multiplier, 8)
成本 = ROUND_HALF_UP(基准费用 × cost_multiplier, 8)
```

输出总量已含思考 token，不重复相加；SSE 只取最终累计用量，不逐块累加。不先舍入基准费用，不把销售倍率乘在已乘成本倍率的费用上。

当本次 `input_tokens`（含缓存）严格超过快照的 `long_context_threshold` 时，输入价和缓存价乘 `long_context_input_multiplier`，输出价乘 `long_context_output_multiplier`，再按上述公式结算；恰好达到阈值不加价。GPT 初始配置为 272000 / 2 / 1.5。

结算先锁调用再锁账户，同事务写用量、状态、成本/扣款、余额和唯一 `text:<UUID>:charge` 流水；已结算不再扣。只减可用余额，允许负数，不动生成冻结；负余额阻止后续调用。

客户端断开后尽可能继续读用量；可靠用量即结算，包括生成失败的调用。缺失用量记待核实，不伪造免费成功或自动重试；进入 `settled_manually` 或 `closed_no_charge` 后到达的用量写入 `late_usage`，不二次扣费。API 进程终止可能遗留 `processing`，没有 Worker 自动补扣。

## 日志、统计与验证入口

- 生成“扣除积分”在冻结时显示 A 与冻结 Tag，成功 A 与已结算，释放为零与已释放；文本未知金额为“—”，不是零。
- 个人日志显式返回销售字段和用量，不公开成本或完整快照。
- 仪表盘请求统计任务与文本调用；消耗取 `settle + text_charge - refund`，不含冻结、释放、充值或调账，今日按北京时间流水记账日。
- 后端关键测试：`test_generations.py`、`test_image_parameters.py`、`test_image_edits.py`、`test_task_execution.py`、`test_videos.py`、`test_video_storage.py`、`test_text.py`、`test_account_activity.py`、`test_openai.py`，位于 `backend/tests/`。
- 公开文档与日志浏览器测试位于 `frontend/tests/{api-docs,text-logs,app}.spec.ts`；检查命令见[根目录 README](../README.md#检查)。
- 修改账务/状态须覆盖成功、明确失败、重复结算/释放、受理不明、超时后成功、转存失败和重启；文本还核对缓存/思考用量、SSE 与中断。离线测试不等于真实上游验收。
