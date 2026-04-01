# MAO 平台系统设计 Review 报告

> **版本**：V9.1-PROD | **更新日期**：2026-04
> **Review 重点**：无状态实例设计 (Stateless Instance) 与 C 端多渠道接入 (Web / 飞书机器人)

---

## 1. 现有设计逻辑问题诊断

在对 MAO 平台 v9.0 的系统架构、数据模型和 API 接口进行深度 Review 后，发现当前设计在**无状态化**和**多渠道扩展性**上存在以下核心逻辑缺陷：

### 1.1 强耦合的 Web/WebSocket 假设 (多渠道接入障碍)
- **问题描述**：当前架构（如 `system_architecture.md` 和 `api_reference.md`）深度绑定了 Web 端的交互模式。例如，`VIEW` 技能被定义为"转交 BFF 驱动 WebSocket 推送前端渲染卡片"，离线信箱强依赖 WebSocket 重连推送。
- **逻辑冲突**：飞书机器人等第三方渠道通常基于 Webhook 事件驱动（HTTP POST 回调），并不维持长连接 WebSocket。如果底层引擎直接假设存在 WebSocket，将无法适配飞书的卡片下发和消息回复机制。
- **严重等级**：**高 (P0)**

### 1.2 状态存储与任务实体的强绑定 (违反无状态原则)
- **问题描述**：在 `data_model.md` 中，`mao_task` 表直接包含 `state_snapshot` (LONGTEXT) 字段。这意味着任务的执行状态与任务的生命周期元数据强耦合在同一个关系型数据库行中。
- **逻辑冲突**：真正的无状态执行引擎要求计算节点随时可被销毁，状态应该外置且追加写入（Append-only）。将几 MB 的 JSON 快照频繁 UPDATE 到 MySQL 的 Task 表中，不仅会导致严重的行锁竞争和性能瓶颈，还破坏了实例的无状态横向扩容能力。
- **严重等级**：**高 (P0)**

### 1.3 内存级共享黑板的局限性 (无法跨实例恢复)
- **问题描述**：`system_architecture.md` 中提到"所有 Agent 通过内存中的全局哈希表（黑板）进行数据握手"。
- **逻辑冲突**：如果黑板数据仅存在于单台机器的内存中，当任务触发 `ASYNC` 挂起（如等待 OA 审批）并释放线程后，回调唤醒时请求可能被负载均衡路由到另一台实例。此时内存黑板丢失，任务无法恢复。
- **严重等级**：**高 (P0)**

### 1.4 缺失统一的渠道适配层 (Channel Adapter)
- **问题描述**：API 设计中仅有一个松散的 `source_channel` 字段，缺乏对不同渠道用户身份（如飞书 OpenID vs 系统 UserID）、会话上下文（飞书 ChatID vs Web SessionID）和消息格式（飞书卡片 vs Web JSON Schema）的统一转换映射。
- **逻辑冲突**：底层引擎直接处理特定渠道的格式会导致代码极度臃肿，且新增渠道（如钉钉、企业微信）时需要修改核心推演逻辑。
- **严重等级**：**中 (P1)**

---

## 2. 架构重构与修复方案

为了彻底解决上述问题，满足"无状态实例"和"多渠道接入"的硬性约束，提出以下重构方案：

### 2.1 引入统一渠道适配层 (Omni-Channel Adapter)
在 L2 接入网关层与 L3 调度控制面之间，增加**渠道适配层**。
- **入站转换 (Inbound)**：将 Web SSE 请求、飞书 Webhook 事件统一转换为内部标准的 `OmniMessage` 对象，提取统一的 `channel_id`、`external_user_id` 和 `external_session_id`。
- **出站转换 (Outbound)**：底层引擎输出标准的 `CardSchema` 或 `Text`，由适配层根据 `channel_id` 翻译为目标渠道的格式（如将内部卡片翻译为飞书的 Feishu Message Card），并通过对应的协议（WebSocket 推送或 HTTP POST 调用飞书 OpenAPI）发送。

### 2.2 状态外置与 Append-Only 存储 (Stateless Engine)
- **剥离快照**：从 `mao_task` 表中移除 `state_snapshot` 字段。
- **引入 StateDB (Redis + KV Store)**：执行引擎在推演过程中的每一步（Thought, Action, Observation）都作为 Event 追加写入外部 KV 存储（如 Redis Stream 或 DynamoDB）。
- **黑板持久化**：共享黑板 (Blackboard) 不再是单机内存哈希表，而是序列化后与任务上下文一同存入外部 StateDB。挂起唤醒时，任何一台无状态的 Worker 实例都可以从 StateDB 拉取最新快照和黑板数据，瞬间恢复执行现场。

### 2.3 重新定义 VIEW 技能的挂起语义
- **解耦 WebSocket**：`VIEW` 技能的执行机制修改为：引擎输出卡片渲染指令 -> 触发轻量级挂起 (SUSPEND_FOR_USER_INPUT) -> 状态序列化至 StateDB -> 引擎线程销毁。
- **多渠道下发**：适配层接管卡片指令，如果是 Web 端则通过 SSE/WS 下发，如果是飞书则调用飞书 API 发送卡片消息。用户提交卡片后，通过统一的 `/chat/action/execute` 接口唤醒任务。

---

## 3. 需修订的文档清单

1. **`02_architecture/system_architecture.md`**
   - 更新六层架构图，加入 Channel Adapter 层。
   - 修改 3.2.3 节，将"内存中的全局哈希表"改为"外置持久化的强类型黑板"。
   - 修改 3.3 节，重新定义 `VIEW` 技能的执行机制，剥离 WebSocket 强依赖。

2. **`03_data_model/data_model.md`**
   - 修改 `mao_task` 表，移除 `state_snapshot`。
   - 新增 `mao_channel_account` (渠道账号绑定表) 和 `mao_channel_session` (渠道会话映射表)。

3. **`04_api/api_reference.md`**
   - 增加飞书等第三方渠道的统一 Webhook 接收接口 `/callbacks/channel/feishu`。
   - 完善消息下发的异步回调机制说明。

4. **`05_diagrams/source/`**
   - 更新 `01_overall_architecture.mmd` (新增渠道适配层)。
   - 更新 `03_async_suspend_resume_sequence.mmd` (体现无状态 Worker 的快照拉取)。
   - 更新 `06_entity_relationship.mmd` (更新表结构)。
