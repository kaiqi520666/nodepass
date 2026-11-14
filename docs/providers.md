# 供应商接入

更新：2026-11-11。记录已确认的映射、协议差异和验证边界。初始化数值不是当前数据库价格，不自动覆盖后台配置。

## 接入原则

- 一个本站模型绑定一个供应商和上游 ID；适配器只做通信及参数/状态/用量转换，账务由本站服务处理。
- 后台仅支持已实现的适配器和固定地址，新增协议需要代码；不能只填任意 URL 即接入，不做多线路或自动切换。
- 新接入重新核验协议、鉴权、素材、价格；模拟验证成功后，真实付费调用另行授权，注明型号、参数、日期和范围，不存密钥或用户媒体。
- 统一任务、资金和快照规则见[任务与账务](task-lifecycle.md)，对外边界见[需求](requirements.md#协议边界)；以下只列供应商差异。

## 沧元图片

- 适配键 `cangyuan_image`，接入地址 `https://direct-api.cangyuansuanli.cn`，Bearer 鉴权。
- 资料：[Image 2](https://ai.cangyuansuanli.cn/docs/chapters/openai-image-2)、[Image 2.5](https://ai.cangyuansuanli.cn/docs/chapters/openai-image-2-5)、[报价](https://ai.cangyuansuanli.cn/pricing)，组合价格核对公开 `GET /api/pricing` 的 `billing_expr`，不能只读顶部 `model_price`。

| 本站 ID | 上游 ID | 计价维度 |
| --- | --- | --- |
| `gpt-image-2` | `gpt-image-2-x` | `tier` |
| `gpt-image-2.5` | `gpt-image-2.5-x` | `series + tier + quality` |

- 不按档位/分支重复建模，无 2.6 或旧型号回退。`tier` 为 web/1k/2k/4k，`size` 为比例，`series` 为 flare/sunburst 分支，不是画风。
- 默认 web、medium、1:1、background=auto；2.5 显式传默认 flare。quality 为 low/medium/high/xhigh/max，原值透传，不把 max 改写为 xhigh。
- 两个 `-x` 公开参数数据未启用 output_format；参考图初始 9 张，支持 mask。上游自定义像素约束未完整核验，当前仅按配置比例校验，不套旧型号像素预算。
- 上游生成 `/v1/images/generations`、编辑 `/v1/images/edits` 均显式传 `async: true`，按各自路径 `/{id}` 轮询；不把上游异步响应直接视为本站协议。
- 本站图片编辑用 JSON `images: [{image_url: HTTPS_URL}]`、可选 `mask: {image_url: HTTPS_URL}`，适配器分别转上游有序 `images: string[]` 和 `mask: string`。编辑与生成共用模型参数、价格及账务，本站统一查询仍为 `/v1/images/generations/{task_id}`；原始请求保存编辑类型，重启不改用生成接口。
- 2026-11-11 只读核验章节及其 `docs-static/catalog.json`：两个 `-x` 的核心参数均为 `images` / `mask`，不使用旧示例的 `image`。目录列出编辑创建/查询路径；接口实现及模拟验证不等于所有真实参考图、mask 组合均通过验收。

2026-11-09 只读核对的初始化报价如下，成本/售价初始同值；2-x 顶部曾显示 0.015，表达式 web 实为 0.017：

| 2-x tier | web | 1k | 2k | 4k |
| --- | --- | --- | --- | --- |
| 每张 | 0.0170 | 0.0550 | 0.0700 | 0.0800 |

| 2.5-x series / tier | low / medium / high | xhigh / max |
| --- | --- | --- |
| flare / web | 0.0250 | 0.0250 |
| flare / 1k | 0.1600 | 0.3200 |
| flare / 2k | 0.1800 | 0.3600 |
| flare / 4k | 0.2000 | 0.4000 |
| sunburst / web | 0.0250 | 0.0250 |
| sunburst / 1k | 0.1800 | 0.3600 |
| sunburst / 2k | 0.2000 | 0.4000 |
| sunburst / 4k | 0.2200 | 0.4400 |

2-x 四条、2.5-x 四十条精确价目，总计 44 条，不是 44 个模型。缺价拒绝，不回退默认价。

历史验证：2026-11-07 经授权测试 2-x web/low/9:16/n=1，完成受理、轮询、URL 和 PNG 下载；当前本站生成闭环及计价组合有离线测试，不代表所有组合、实际扣费、参考图或 mask 均已实测。

2026-11-11 经授权通过本站 `/v1/images/edits` 实测一次 `gpt-image-2`、web/low/16:9/n=1、两张 HTTPS 参考图、无 mask：完成 202 受理、编辑路径轮询、转存和 URL 交付，约 54 秒。用户扣款 `0.01700000`，对应一条冻结和一条结算，冻结余额归零；该金额为本站实际流水，不等同于已核对上游钱包。2.5 编辑及 mask 本轮仅用模拟上游验证。

## MEAICC 视频

- 适配键 `meaicc_video`；[接口资料](https://api.meaicc.com/create/sd-2.html)、[报价](https://api.meaicc.com/pricing)与 `/api/pricing` 于 2026-11-09 核对，接入地址 `https://api.meaicc.com`。
- 创作页与报价描述有差异，初始能力以报价型号描述为基线，保存数据库由管理员调整；`sd-2-c1` 不入库。

| 本站/上游 ID | 标注 | 分辨率 | 秒数范围 | 单位 | 初始成本=售价 |
| --- | --- | --- | --- | --- | --- |
| `sd-2-c4` | fast | 720p | 4–15 | 条 | 1.8000 |
| `sd-2-c5` | fast | 720p | 4–15 | 条 | 2.5000 |
| `sd-2-c7` | fast | 720p | 4–15 | 条 | 2.8000 |
| `sd-2-c8` | full | 720p | 4–15 | 条 | 3.8000 |
| `sd-2.5-c2` | — | 720p | 5–30 | 条 | 6.2000 |
| `sd-2.5-c3` | — | 720p | 4–30 | 条 | 7.7000 |
| `sd-2.5-d1-480` | — | 480p | 4–30 | 秒 | 0.4700 |
| `sd-2.5-d1-720` | — | 720p | 4–30 | 秒 | 0.5400 |
| `sd-2.5-d2` | — | 480p | 5–30 | 秒 | 0.2900 |
| `sd-2.5-d3` | — | 720p | 5–30 | 秒 | 0.3900 |

- 数值直接使用不换汇；十个型号均 `pricing_dimensions=[]`、一条默认价，分辨率/比例仅为能力参数，不作为计价必填项。
- 初始时长 10 秒、比例 16:9、分辨率取型号；按秒仍要求显式 seconds，不取整。2.0 参考上限为 9 图/3 视频/3 音频，2.5 为 30/10/10，首尾帧计入图数，只收 HTTPS。
- 本站统一 `model/prompt/seconds/resolution/aspect_ratio/references`，转上游 `input`、`parameters.duration/ratio/resolution`；`reference_audio` 转 `reference_voice`。
- 上游创建/查询为 `/v1/videos`；成功结果 URL 在 `object`，本站转存后才用 `data[].url` 交付。
- 初始请求超时/轮询间隔/任务时限为 60 秒/60 秒/6 小时，后台可改且无 60 秒轮询上限，创建时快照。
- `seed-videos` 仅导入缺失 ID，不覆盖已有配置；首次供应商/模型停用且无凭证，管理员填密钥启用后再上架，不自动付费探测。
- 验证：有模拟上游全流程测试，经授权用 `sd-2-c4` 完成过 15 秒参考图视频及转存；不能声称十个型号均已真实验收。

## ModelGate GPT

- 适配键 `modelgate_openai`，地址 `https://intl.modelgate.top`；独立凭证，本站与上游型号均为 `gpt-6.1-sol`。这是中转站型号，不根据名称推定官方模型能力。
- 内部统一调用 `POST /v1/responses`；对外保留 Chat Completions / Responses JSON/SSE，支持文本与图片。音频和视频理解已移除，独立视频生成不受影响。
- 支持严格 JSON Schema 输出、自定义函数调用及结果回传。使用原生调用 ID，函数由客户端执行；Responses 回传完整输出历史，包括 reasoning 的 encrypted_content。不存储提示词、回答或服务端会话。
- Responses 的 `tools: [{"type":"web_search"}]`、Chat 的 `web_search_options: {}` 均映射为 Responses 搜索工具；支持 JSON/SSE 引用，不与自定义函数混用。直接调用上游 Chat 时搜索选项未返回搜索事件，因此不走这条路径。
- 2026-11-13 核对价格表与 Sub2API `billing_service.go`：每百万 token 基准价输入 2、输出 10、缓存命中 0.1；成本和售价倍率均为 0.2，不换汇。常规实际单价为 0.4 / 2 / 0.02。
- 输入总量（含缓存）严格大于 272000 时，整次输入与缓存价格乘 2、输出乘 1.5。阈值、倍率、单价均由后台维护并随调用快照，判断不按历史对话累计。
- 价格依据为 `Wei-Shaw/model-price-repo` 与 `Wei-Shaw/sub2api`；2026-11-13 当前 Key 的 `/v1/sub2api/billing` 返回有效倍率 0.2。上游搜索实测 input=12936、cached=8576、output=96，Key 的费用增量 0.00210752，与上述公式一致。未用超长付费请求验证长上下文附加费。
- 上游已验证严格结构化人物场景提取、图片识别、JSON、SSE、函数调用及搜索引用。本站验证范围见测试与后续实测记录。缓存写入、优先服务、批量和独立检索计价不在范围。
- 2026-11-13 经本站第一账号实测：严格 JSON 提取 5.71 秒；Chat 搜索 SSE 7.08 秒并返回引用；Responses 与 Chat 函数调用往返均成功。合计 6 次调用扣款 0.00573952，本站成本、用户余额变化与上游 Key 的 actual_cost 增量一致（分两批核对，4 次及 2 次）。包含缓存命中实扣；未宣称上游钱包层隔离对账完成。
- `seed-gpt` 隐藏输入凭证，仅添加缺失配置；后续通过后台修改倍率和凭证。历史调用保持原计价快照，不重新扣费。
