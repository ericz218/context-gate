# Context Gate 实现规格

本文档概述 Context Gate 的核心上下文筛选流水线、记账与证据链规格。

## 流程

用户请求 → 读取现有 AI 记忆中的核心段 → 本地确定性检索 → Jev 主 Context Gate → 高置信且充分时生成 Context Pack；否则 Laya 二次审核。**二审时 Laya 不可用则仍用 Jev 二审**。不足时按缺口补检索，扩大 Pack；持续不确定时 Full Context 回退。正确率优先。

最终模型收到：核心记忆原文 + 当前请求 + Context Pack + 必要冲突/风险说明。不得把审核内部过程、淘汰候选或搜索日志转发给最终模型。

## 核心记忆

直接读取已有 AI 记忆文件中 `[CORE_MEMORY_START]` 至 `[CORE_MEMORY_END]` 的唯一核心段。建议约 500–2000 tokens。内容包含项目目标、阶段、架构决定、长期约束、禁止项和重要状态。每轮原样携带，Jev/Laya 只读；最终 AI 自己负责更新。

项目记忆（2026-10-29）：核心记忆之后附 MemoryOS 项目记忆，只读 `/v1/context`，按 MemoryOS 权重顺序在 `memory_os_tokens` 预算内截取，低权重尾部截掉并在 Pack `memory` 字段列出；MemoryOS 不可用时回退文件记忆并在 [RISKS] 标明原因。超窗口仍阻止发送，不靠裁剪记忆凑窗口。

## 检索与 Pack

文件名、ripgrep、AST、symbol 引用、callers/callees、git diff、tests、config、scene/asset 和依赖关系把几千文件缩到几十候选。每项有路径、symbol、行号、内容、来源类型、相关理由、新鲜度、置信度。不携带无关日志和旧代码。

发出前评估：仅看到所选内容的最终 AI 是否会因为缺某个信息而做错？充分则发送；缺 caller/test/config/asset 则定向补检索。

跨模块重构、公共接口修改、深调用链、scene/config/asset 联动、序列化和架构调整默认保守。

## 路由与实测

Jev 同一候选 state 批量问相关性、保留项、测试、配置、跨模块、缺失依赖和充分性。用户提供的 8648-token 长文本实测：1 问约 222 ms，4 问约 227 ms，8 问约 228 ms。

Laya 只复核低置信、判断冲突、高风险、跨模块和充分性存疑的情况。用户实测：常驻短请求约 121 ms；512-token 单问约 563 ms；长文本 4 问约 1.81 s，8 问约 4.57 s。模型常驻、少量合理 batch，初始甜区约 4 问一批，不做 16/32 路 GPU 并发。

模型能力表（2026-10-29）：路由候选的可用性来自 router.db 被动统计（只读）与显式主动探测；状态取最新决定性事件，7 天窗口外的旧成功不算可用（状态记为未知，原因 stale_success）。路由器不落库的客户端超时（如 180 秒超时）被动统计看不到，只能靠主动探测补。直连备用默认关闭，密钥只经路由 App 管理桥单次取用、不落盘。

## 目标与预期（不是验收实测）

- 普通请求筛选额外开销约 0.5–1.5 s：本地检索 0.1–0.8 s，Jev 约 0.23 s，组装 0.05–0.2 s。
- 需要 Laya 时额外增加约 1.8–5 s，复杂请求合计约 2.5–6 s。
- 长期项目平均远端上下文减少约 85–95%，尽量减少 Claude/Opus TTFT 和输入成本。

| 原始上下文 | 新上下文 | 节省 |
|---|---|---|
| 100k | 20–40k | 60–80% |
| 300k | 30–60k | 80–90% |
| 500k | 30–70k | 86–94% |
| 1M | 40–100k | 90–96% |

500k → 核心记忆 2k + 请求 2k + 代码/测试 35k + metadata 3k ≈ 42k，少约 458k。

净时间收益预期：<50k 可能无需启用，100k 约 0–2 s，300k 约 1–5 s，500k 约 2–8 s，1M+ 约 5–15 s 或更多。启用阈值最终由真实 A/B 测试确定。

## 首版可调初值（工程选择，不是用户实测）

小上下文阈值 50k，Pack 预算 60k，首轮候选预算 16k/40 项，最多 2 轮，置信度门槛 0.8，最终窗口初值 200k，单次接口超时 6 s；首次钥匙串本人认证单独等待最多 50 s。任何一个初值都需按真实项目调整。

## QuotaGuard (2026-10-12)

Subscription limits integrated in console. Direct Codex/Claude usage reads, second-level intervals, numeric thresholds, background alerts and optional local interruption. Scope and verified limits: docs/QUOTA_GUARD.md. Stop control defaults off. No model turns.

## Evidence (2026-10-29)

每次 AI 任务追加一条哈希链证据（状态目录 evidence/，0600，不进仓库）：任务/会话、root、commit 与 dirty、模型/provider/档位、tokens、成本、耗时、测试结果、CI 链接、时间。tokens 与成本只引用账本行 id 并只读汇总，不新增计费行，账本统计不读证据；拿不到的字段为 null 并标来源。CLI `evidence.py record|verify|list|show`，本地接口 `/v1/evidence`。详见 README。
