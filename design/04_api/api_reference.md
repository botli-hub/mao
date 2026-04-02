# MAO 平台 — 全景 API 接口文档 (v9.0-PROD)

> **版本**：V9.5-PROD | **更新日期**：2026-04 | **新增**：8.9 渠道适配层接口、8.10 统一消息下发规范、8.11 渠道类型枚举、8.12 热冷数据一致性接口

---

## 8. RESTful API 接口文档

### 8.1 基础规范

| 规范项 | 说明 |
|---|---|
| **Base URL** | `/api/v1` |
| **Content-Type** | `application/json` |
| **C 端鉴权** | Bearer Token (User_JWT)，在 Header 中传入：`Authorization: Bearer {token}` |
| **B 端鉴权** | Bearer Token (Admin_JWT)，在 Header 中传入：`Authorization: Bearer {token}` |
| **幂等键** | 写操作请在 Header 中传入：`Idempotency-Key: uuid-v4-xxxxx` |
| **Webhook 防重放** | 回调接口需携带 `X-Timestamp`、`X-Nonce`、`X-Signature` 三个安全头 |
| **响应格式** | 统一返回 `{"code": 200, "message": "Success", "data": {}}` |
| **分页格式** | 分页响应统一包含 `page_info: {total, current_page, has_more}` |

#### 8.1.1 接口契约唯一源头 (Single Source of Truth)

- 本文档 (`design/04_api/api_reference.md`) 是 MAO 平台 **API 契约唯一源头**。路径、请求/响应结构、枚举、鉴权头、错误码均以本文档为准。
- 其他设计文档（如 `03_data_model/data_model.md`、`06_database/schema.sql`）中的接口相关描述仅用于实现说明，不得定义与本文档冲突的独立契约。
- 若发生差异，必须先更新本文档，再同步更新其他文档。

### 8.2 C 端交互核心层 (User Workspace)

#### 8.2.1 获取最近会话列表

```
GET /chat/sessions
```

**描述**：获取左侧边栏最近会话列表。

**Query 参数**：`page=1`, `size=20`

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "items": [{"session_id": "sess_001", "title": "五一母婴线策划", "updated_at": "2026-05-01T10:24:00Z"}],
    "page_info": { "total": 45, "current_page": 1, "has_more": true }
  }
}
```

#### 8.2.2 获取我的后台托管任务

```
GET /chat/managed-tasks
```

**描述**：获取左侧边栏我的后台托管任务 (Cron/盯盘)。

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "running_count": 2,
    "tasks": [{"task_id": "tsk_cron_1", "name": "预算盯盘", "trigger": "条件触发", "status": "RUNNING"}]
  }
}
```

#### 8.2.3 发起自然语言会话 (SSE)

```
POST /chat/completions
```

**描述**：发起自然语言会话，支持 Server-Sent Events 流式返回。

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `session_id` | `string` | 是 | 会话 ID |
| `message` | `string` | 是 | 用户输入的自然语言 |
| `target_task_id` | `string` | 否 | 允许指定目标任务ID，便于显式干预旧任务 |
| `context_mode` | `string` | 否 | 上下文模式，默认 `auto` |
| `source_channel` | `string` | 否 | 来源渠道，如 `LUI_WORKSPACE` |

**请求示例**：
```json
{
  "session_id": "sess_001",
  "message": "帮我建一个促活任务，总预算两万。",
  "target_task_id": null,
  "context_mode": "auto",
  "source_channel": "LUI_WORKSPACE"
}
```

**响应（text/event-stream）**：

> **内外部记忆隔离规则**：下列 SSE 事件中，`event: message` 和 `event: action_card` 与 `event: task_summary` 才会写入 `mao_message`（Session Memory）。Worker 内部的 Thought/Action/Observation 严禁通过 SSE 将原文写入会话历史，应将其存入 `mao_task_log`。

```
// 事件1：流式文本增量（STREAM_CHUNK，不写入 mao_message）
event: message
data: {"task_id": "tsk_001", "type": "stream_chunk", "content": "好的..."}

// 事件2：GUI卡片下发（CARD，写入 mao_message）
event: action_card
data: {
  "task_id": "tsk_001", "type": "card_render",
  "card_schema": {
    "component": "TaskConfigForm",
    "payload": {"budget": 20000},
    "actions": [{"id": "submit_oa", "label": "确认提交"}],
    "client_side_lock": true
  }
}

// 事件3：任务结束摘要（TASK_SUMMARY，写入 mao_message，仅在任务彻底结束或需要人类介入时发出）
event: task_summary
data: {
  "task_id": "tsk_001",
  "type": "task_summary",
  "content": "您的排查 SOP 已执行完毕，发现 3 个异常，请查看卡片",
  "task_status": "COMPLETED",
  "summary_card": null
}
```

#### 8.2.4 提交 GUI 卡片动作 (双态响应)

```
POST /chat/action/execute
```

**描述**：提交 GUI 卡片动作，支持同步完成与异步挂起双态响应。

**请求头**：`Idempotency-Key: uuid-v4-xxxxx`

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `session_id` | `string` | 是 | 会话 ID |
| `task_id` | `string` | 是 | 任务 ID |
| `action_id` | `string` | 是 | 卡片动作 ID |
| `payload` | `object` | 是 | 用户填写的表单数据 |

**请求示例**：
```json
{
  "session_id": "sess_001", 
  "task_id": "tsk_001",
  "action_id": "submit_oa",
  "payload": {"budget": 20000, "is_confirmed": true}
}
```

**响应示例**：
```json
{
  "code": 200, 
  "message": "Action executed",
  "data": {
    "next_state": "SUSPENDED",
    "trace_id": "OA-2024-8902",
    "sync_result": null
  }
}
```

> `next_state` 枚举値：`SUSPENDED`（异步挂起，等待外部回调）、`SYNC_COMPLETED`（同步完成，`sync_result` 字段包含业务结果）。

> **`client_side_lock` 说明**：`card_schema` 中的 `client_side_lock: true` 属性指示渠道适配层在下发卡片时启用渠道原生物理锁定能力：飞书渠道自动设置卡片的 `Exclusive` 属性（点击后卡片即时灰化且仅首个点击生效）；Web 端前端在按鈕点击后立即设置按鈕为禁用状态直到收到服务端响应。此机制与后端幂等防护共同构成双层防抖。

#### 8.2.5 拉取离线消息信箱

```
GET /chat/offline-inbox
```

**描述**：拉取离线期间后台执行完毕的任务通知。

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "unread_count": 1,
    "messages": [
      {
        "id": 42,
        "task_id": "tsk_001",
        "type": "async_result",
        "quote_ref_id": "msg_OA-8902",
        "content": "您的审批已通过。",
        "channel_type": "WEB",
        "retry_count": 0,
        "last_retry_at": null
      }
    ]
  }
}
```

### 8.3 统一回调网关层 (Event Gateway)

#### 8.3.1 外部系统统一异步唤醒接口

```
POST /callbacks/webhook/unified
```

**描述**：外部系统统一异步唤醒接口，增加防重放安全头。

**安全请求头**：

| Header 名 | 说明 |
|---|---|
| `X-Timestamp` | Unix 时间戳，请求必须在 5 分钟内 |
| `X-Nonce` | 随机字符串，防重放攻击 |
| `X-Signature` | HMAC-SHA256 签名，格式为 `sha256=xxx` |

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `source_system` | `string` | 是 | 来源系统标识，如 `OA_SYSTEM`、`RISK_SYSTEM` |
| `trace_id` | `string` | 是 | MAO 平台内部跟踪 ID |
| `status` | `string` | 是 | 回调结果，如 `APPROVED`、`REJECTED` |
| `observation_data` | `object` | 否 | 附加观测数据 |

**请求示例**：
```json
{
  "source_system": "OA_SYSTEM",
  "trace_id": "OA-2024-8902",
  "status": "APPROVED",
  "observation_data": { "approver": "王总监", "comment": "同意" }
}
```

**响应示例**：
```json
{ "code": 200, "message": "Callback received. Resuming." }
```

### 8.4 B 端：技能注册中心 (Skill Registry)

#### 8.4.1 分页查询技能列表

```
GET /admin/skills
```

**Query 参数**：`page=1`, `size=10`, `type=ASYNC`

**响应示例**：
```json
{ "code": 200, "data": { "items": [{"id": "sk_9901", "name": "SubmitOAApproval"}], "page_info": {"total": 124, "current_page": 1, "has_more": true} } }
```

#### 8.4.2 获取技能详情

```
GET /admin/skills/{skill_id}
```

**响应示例**：
```json
{ "code": 200, "data": { "name": "SubmitOAApproval", "type": "ASYNC", "input_schema": {...}, "output_schema": {...} } }
```

#### 8.4.3 注册原子技能

```
POST /admin/skills
```

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `string` | 是 | 技能名称 |
| `type` | `string` | 是 | 技能类型：`API`、`VIEW`、`ASYNC`、`MACRO` |
| `execution_config` | `object` | 是 | 执行配置，包含 endpoint、auth_type |
| `mao_control_meta` | `object` | 否 | MAO 控制元数据，异步技能必填 |
| `input_schema` | `object` | 是 | 遵循 JSON Schema Draft-07 标准 |
| `output_schema` | `object` | 是 | 遵循 JSON Schema Draft-07 标准 |

**请求示例**：
```json
{
  "name": "SubmitOAApproval", 
  "type": "ASYNC",
  "execution_config": { "endpoint": "https://oa.corp.com/api", "auth_type": "SYSTEM_AK_SK" },
  "mao_control_meta": { "x_mao_suspend": true, "ttl_seconds": 259200, "callback_expect": "WEBHOOK" },
  "input_schema": { "type": "object", "properties": { "amount": {"type": "number"} } },
  "output_schema": { "type": "object", "properties": { "ticket_id": {"type": "string"} } }
}
```

#### 8.4.4 更新技能配置

```
PUT /admin/skills/{skill_id}
```

#### 8.4.5 删除原子技能

```
DELETE /admin/skills/{skill_id}
```

### 8.5 B 端：智能体工厂 (Agent Factory)

#### 8.5.1 分页查询智能体列表

```
GET /admin/agents
```

**Query 参数**：`page=1`, `size=20`, `status=PUBLISHED`

#### 8.5.2 新建智能体草稿

```
POST /admin/agents
```

**请求示例**：
```json
{ "agent_name": "未命名智能体草稿" }
```

#### 8.5.3 获取 Agent 当前草稿详情

```
GET /admin/agents/{agent_id}
```

#### 8.5.4 保存智能体草稿

```
PUT /admin/agents/{agent_id}
```

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `agent_name` | `string` | 是 | Agent 名称 |
| `system_prompt` | `string` | 是 | System Prompt 内容 |
| `mounted_skills_ids` | `array` | 否 | 挂载的技能 ID 列表 |
| `rag_kb_ids` | `array` | 否 | RAG 知识库 ID 列表 |
| `rag_retrieval_config` | `object` | 否 | RAG 召回配置，防止 Context 爆仓 |
| `model_config` | `object` | 否 | LLM 推理配置，包含燔断限制 |

**请求示例**：
```json
{
  "agent_name": "发奖专员",
  "system_prompt": "你的职责是...",
  "mounted_skills_ids": ["sk_01", "sk_02"],
  "rag_kb_ids": ["rag_1001"],
  "rag_retrieval_config": {
    "top_k": 3,
    "similarity_threshold": 0.75
  },
  "model_config": {
    "provider": "gemini-1.5-pro",
    "temperature": 0.2,
    "max_output_tokens": 2048,
    "agent_max_steps": 7
  }
}
```

#### 8.5.5 发布草稿生成不可变快照

```
POST /admin/agents/{agent_id}/publish
```

**请求示例**：
```json
{ "version_desc": "上线新风控能力" }
```

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "version_id": "v1.3",
    "validation_results": [{"level": "WARN", "msg": "提示词未引用知识库"}]
  }
}
```

> **宏工具环路检测**：发布时系统会对该 Agent 所有已挂载技能进行 DFS 环路检测。若发现某个 `MACRO` 类型技能的实际工作流内包含当前 Agent（即 Agent A 调用 Macro B，Macro B 内部的 SOP 画布又调用 Agent A），发布将被阻断，返回错误码 `422` 和具体环路路径描述：
```json
{
  "code": 422,
  "error": "MACRO_CYCLE_DETECTED",
  "detail": "Cycle path: agent_A -> macro_B (wf_xxx) -> agent_A"
}
```

#### 8.5.6 获取历史快照列表

```
GET /admin/agents/{agent_id}/snapshots
```

#### 8.5.7 查看特定历史快照详情

```
GET /admin/agents/{agent_id}/snapshots/{version}
```

#### 8.5.8 一键回滚 (覆盖当前草稿)

```
POST /admin/agents/{agent_id}/snapshots/{version}/restore
```

#### 8.5.9 删除智能体

```
DELETE /admin/agents/{agent_id}
```

### 8.6 B 端：全局编排画布 (SOP Workflows)

#### 8.6.1 分页查询画布列表

```
GET /admin/workflows
```

**Query 参数**：`page=1`, `size=10`

#### 8.6.2 新建画布空草稿

```
POST /admin/workflows
```

#### 8.6.3 获取 DAG 草稿详情

```
GET /admin/workflows/{workflow_id}
```

#### 8.6.4 保存画布草稿

```
PUT /admin/workflows/{workflow_id}
```

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `string` | 是 | 画布名称 |
| `blackboard_schema` | `object` | 是 | 共享黑板 Schema 定义 |
| `nodes` | `array` | 是 | 节点列表，支持 AGENT、CONDITION、TRIGGER、END 类型 |
| `edges` | `array` | 是 | 边列表，支持 mappings 变量映射 |

**请求示例**：
```json
{
  "name": "资损排查 SOP",
  "blackboard_schema": { "type": "object", "properties": { "risk_level": {"type": "string"} } },
  "nodes": [
    { "node_id": "n_agent_1", "type": "AGENT", "ref_id": "ag_1001", "config": { "timeout_sec": 30 } },
    { "node_id": "n_cond_1", "type": "CONDITION", "config": { "expression": "$.risk_level == 'HIGH'" } }
  ],
  "edges": [
    {
      "source_node": "n_agent_1",
      "target_node": "n_cond_1",
      "mappings": [ { "source_path": "$.output.level", "target_path": "bb.risk_level" } ]
    },
    { "source_node": "n_cond_1", "source_handle": "TRUE", "target_node": "n_suspend_oa" },
    { "source_node": "n_cond_1", "source_handle": "FALSE", "target_node": "n_finish" }
  ]
}
```

#### 8.6.5 发布画布生成不可变快照

```
POST /admin/workflows/{workflow_id}/publish
```

#### 8.6.6 获取历史快照列表

```
GET /admin/workflows/{workflow_id}/snapshots
```

#### 8.6.7 查看特定历史快照详情

```
GET /admin/workflows/{workflow_id}/snapshots/{version}
```

#### 8.6.8 一键回滚 (覆盖当前草稿)

```
POST /admin/workflows/{workflow_id}/snapshots/{version}/restore
```

#### 8.6.9 将工作流发布为宏工具

```
POST /admin/workflows/{workflow_id}/publish-as-macro
```

#### 8.6.10 彻底删除画布

```
DELETE /admin/workflows/{workflow_id}
```

### 8.7 B 端：监控调度大盘 (Monitor & Cron)

#### 8.7.1 查询全局活跃的 Task 列表

```
GET /admin/tasks/active
```

**Query 参数**：`page=1`, `size=50`, `status=RUNNING,SUSPENDED`

**响应示例**：
```json
{ "code": 200, "data": { "items": [{"task_id": "tsk_01", "status": "RUNNING"}], "page_info": {"total": 1208, "has_more": true} } }
```

#### 8.7.2 强制燔断挂起任务

```
POST /admin/tasks/{task_id}/kill
```

**描述**：强制燔断挂起任务，释放实体锁。

**请求示例**：
```json
{ "reason": "死循环消耗超标" }
```

#### 8.7.3 分页查询定时调度任务

```
GET /admin/cron-jobs
```

**Query 参数**：`page=1`, `size=20`

#### 8.7.4 创建后台定时任务

```
POST /admin/cron-jobs
```

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_intent` | `string` | 是 | 任务意图描述 |
| `cron_expression` | `string` | 是 | Cron 表达式 |
| `timezone` | `string` | 是 | 时区，防云原生漂移，如 `Asia/Shanghai` |
| `overlap_policy` | `string` | 是 | 防重叠策略：`SKIP`、`QUEUE`、`CONCURRENT` |
| `jitter_sec` | `int` | 否 | 随机抖动秒数，防隷群效应 |
| `target_type` | `string` | 是 | 目标类型：`AGENT`、`WORKFLOW` |
| `target_ref_id` | `string` | 是 | 目标 Agent/Workflow ID |
| `auth_impersonation` | `object` | 否 | 权限代理配置 |
| `retry_policy` | `object` | 否 | 重试策略 |
| `fallback_action` | `object` | 否 | 降级通知配置 |

**请求示例**：
```json
{
  "task_intent": "每天早上发早报",
  "cron_expression": "0 10 * * *",
  "timezone": "Asia/Shanghai",
  "overlap_policy": "SKIP",
  "jitter_sec": 300,
  "target_type": "AGENT",
  "target_ref_id": "ag_1001",
  "auth_impersonation": { "mode": "SERVICE_ACCOUNT_DELEGATION", "impersonate_user_id": "U_9527" },
  "retry_policy": { "max_attempts": 3, "backoff_sec": 300 },
  "fallback_action": { "type": "NOTIFY_CREATOR", "notify_channel": "WECHAT_WORK" }
}
```

#### 8.7.5 更新定时任务配置

```
PUT /admin/cron-jobs/{job_id}
```

#### 8.7.6 暂停/恢复调度任务

```
PATCH /admin/cron-jobs/{job_id}/toggle
```

**请求示例**：
```json
{ "target_status": "PAUSED" }
```

#### 8.7.7 删除调度任务

```
DELETE /admin/cron-jobs/{job_id}
```

### 8.8 B 端：会话审计与容灾 (Audit)

#### 8.8.1 分页查询执行链路日志 (Trace Logs)

```
GET /admin/audit/traces
```

**Query 参数**：`page=1`, `size=20`, `status=FAILED`

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "trace_id": "tr_8899", "trigger_source": "LUI_WORKSPACE",
        "agent_id": "ag_1001", "snapshot_version": "v1.2",
        "status": "COMPLETED", "tokens": 4250
      }
    ],
    "page_info": { "total": 2450, "current_page": 1, "has_more": true }
  }
}
```

#### 8.8.2 获取单次 Task 完整的执行脑电图详情

```
GET /admin/audit/traces/{trace_id}
```

**响应示例**：
```json
{
  "trace_id": "tr_8899",
  "status": "PAUSED_FOR_APPROVAL",
  "execution_snapshot_version": "v1.0.3",
  "metrics": { "total_tokens_consumed": 4250, "execution_time_ms": 2400 },
  "steps": [
    {"step": 1, "type": "THOUGHT", "content": "准备提取参数..."},
    {"step": 2, "type": "ACTION", "tool": "RunCompensateSOP"}
  ]
}
```

#### 8.8.3 断点续传：基于历史快照从失败节点拉起重试

```
POST /admin/audit/traces/{task_id}/retry
```

**请求示例**：
```json
{ "resume_mode": "RETRY_FAILED_NODE" }
```

#### 8.8.4 回港重构：审计视角的断点还原

```
GET /admin/audit/traces/{trace_id}/reconstruct
```

**描述**：提供审计视角的“断点还原”能力。接口采用两段式重组逻辑：优先读取 Redis 全量快照；若 Redis 缺失，则自动通过 MySQL 中的 `mao_task_log.state_digest` 序列按时间戳重组执行链路。

**响应示例（完整还原）**：
```json
{
  "code": 200,
  "data": {
    "trace_id": "tr_8899",
    "is_complete": true,
    "source": "REDIS",
    "execution_version": "v1.2",
    "steps": [
      {
        "step_index": 0,
        "type": "THOUGHT",
        "content": "准备提取参数...",
        "state_digest": {
          "blackboard_snapshot": {"user_id": "u123"},
          "execution_version": "v1.2",
          "token_usage": {"prompt": 800, "completion": 120}
        }
      },
      {"step_index": 1, "type": "ACTION", "tool": "RunCompensateSOP", "state_digest": {}}
    ]
  }
}
```

**响应示例（部分还原， Redis 缺失）**：
```json
{
  "code": 200,
  "data": {
    "trace_id": "tr_8899",
    "is_complete": false,
    "source": "MYSQL_RECONSTRUCT",
    "missing_steps": [3, 4],
    "execution_version": "v1.2",
    "steps": [
      {"step_index": 0, "type": "THOUGHT", "content": "准备提取参数..."},
      {"step_index": 1, "type": "ACTION", "tool": "RunCompensateSOP"},
      {"step_index": 2, "type": "OBSERVATION", "content": "SOP 已启动"}
    ]
  }
}
```

> 当 `is_complete: false` 时，`missing_steps` 字段返回缺失的步骤索引列表，审计人员可明确知晓审计盲区范围。此接口不会返回 404，始终返回已可还原的最大局部链路。

---


### 8.9 渠道适配层 (Channel Adapter)

本节定义多渠道接入相关的接口，包括飞书机器人 Webhook 接收、渠道账号绑定管理，以及统一的消息下发机制。

---

#### 8.9.1 飞书机器人 Webhook 接收入口

```
POST /callbacks/channel/feishu
```

**描述**：接收飞书开放平台推送的事件（用户发送消息、卡片回调等）。飞书要求此接口在 3 秒内返回 HTTP 200，否则会重试。渠道适配层收到事件后立即入队，异步处理。

**安全验证**：飞书通过 `X-Lark-Signature` 和 `X-Lark-Request-Timestamp` 进行签名验证，适配层必须在处理前校验签名。

**请求 Header**：

| Header | 说明 |
|---|---|
| `X-Lark-Signature` | 飞书事件签名 |
| `X-Lark-Request-Timestamp` | 请求时间戳 |
| `X-Lark-Request-Nonce` | 随机字符串（防重放） |

**请求体（飞书消息事件示例）**：
```json
{
  "schema": "2.0",
  "header": {
    "event_id": "5e3702a84e847582be8db7fb73283c02",
    "event_type": "im.message.receive_v1",
    "app_id": "cli_9f3fc9489b001234"
  },
  "event": {
    "sender": {
      "sender_id": { "open_id": "ou_7d8a6e6df7621556ce0d21922b676706" }
    },
    "message": {
      "message_id": "om_dc13264520392913993dd051dba21dcf",
      "chat_id": "oc_5ad11d72b830411d72b836c20",
      "message_type": "text",
      "content": "{\"text\":\"帮我查一下五一活动的预算消耗\"}"
    }
  }
}
```

**适配层处理逻辑**：

1. 校验 `X-Lark-Signature` 签名，不合法则返回 HTTP 401。
2. 通过 `open_id` 查询 `mao_channel_account` 表，获取对应的内部 `user_id`。
3. 通过 `chat_id` 查询 `mao_channel_session` 表，获取或创建对应的 MAO `session_id`。
4. 将事件转换为内部标准 `OmniMessage` 对象，调用 `/chat/completions` 核心逻辑。
5. 立即返回 HTTP 200 空响应，异步处理并通过飞书 OpenAPI 回复结果。

**响应**：
```json
{ "code": 0 }
```

---

#### 8.9.2 飞书卡片回调接收入口

```
POST /callbacks/channel/feishu/card-action
```

**描述**：接收飞书交互式卡片的用户操作回调（如用户点击卡片上的"确认"按钮）。适配层将其转换为内部的 `/chat/action/execute` 调用，唤醒挂起的任务。

**请求体（飞书卡片操作事件）**：
```json
{
  "open_id": "ou_7d8a6e6df7621556ce0d21922b676706",
  "action": {
    "tag": "button",
    "value": {
      "card_action_id": "card_act_abc123",
      "task_id": "task_xyz789",
      "payload": { "budget": 20000, "confirmed": true }
    }
  }
}
```

**适配层处理逻辑**：

1. 校验飞书签名。
2. 提取 `card_action_id` 和 `task_id`，转换为内部 `POST /chat/action/execute` 请求。
3. 返回飞书要求的卡片更新响应（将卡片更新为只读确认状态）。

**响应（飞书卡片更新格式）**：
```json
{
  "toast": {
    "type": "success",
    "content": "已确认，任务正在执行中..."
  },
  "card": {
    "config": { "update_multi": false }
  }
}
```

---

#### 8.9.3 渠道账号绑定管理

```
POST /admin/channel-accounts/bind
```

**描述**：将外部渠道用户身份（如飞书 OpenID）与 MAO 系统用户绑定。

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `user_id` | `number` | 是 | MAO 系统内部用户 ID |
| `channel_type` | `string` | 是 | 渠道类型：`FEISHU` / `DINGTALK` / `WECOM` |
| `external_user_id` | `string` | 是 | 外部渠道用户唯一标识（如飞书 OpenID） |
| `external_app_id` | `string` | 是 | 外部应用 ID（如飞书 App ID） |

**请求示例**：
```json
{
  "user_id": 1001,
  "channel_type": "FEISHU",
  "external_user_id": "ou_7d8a6e6df7621556ce0d21922b676706",
  "external_app_id": "cli_9f3fc9489b001234"
}
```

**响应示例**：
```json
{
  "code": 200,
  "message": "绑定成功",
  "data": { "binding_id": 55 }
}
```

---

```
GET /admin/channel-accounts
```

**描述**：查询渠道账号绑定列表。

**Query 参数**：`channel_type=FEISHU`, `page=1`, `size=20`

---

```
DELETE /admin/channel-accounts/{id}
```

**描述**：解绑渠道账号。

---

#### 8.9.4 渠道会话映射管理

```
POST /admin/channel-sessions/bind
```

**描述**：将外部渠道会话（如飞书群 ChatID）与 MAO 内部 Session 绑定，用于运营群组场景。

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `session_id` | `string` | 是 | MAO 内部 Session ID |
| `channel_type` | `string` | 是 | 渠道类型 |
| `external_chat_id` | `string` | 是 | 外部渠道会话/群组 ID |
| `external_app_id` | `string` | 是 | 外部应用 ID |

---

### 8.10 统一消息下发规范 (Outbound Message Protocol)

本节定义引擎向各渠道下发消息的内部标准协议，由渠道适配层负责翻译。

#### 8.10.1 标准 OmniMessage 对象

执行引擎输出的所有消息均遵循以下标准格式，由渠道适配层翻译为目标渠道格式：

```json
{
  "session_id": "sess_001",
  "task_id": "task_xyz789",
  "channel_type": "FEISHU",
  "message_type": "TEXT | CARD | TASK_SUMMARY | STREAM_CHUNK | SYSTEM_NOTICE",
  "content": {
    "text": "任务执行完成，预算消耗率 87.3%",
    "card_schema": null
  },
  "metadata": {
    "is_final": true,
    "card_action_id": null
  }
}
```

#### 8.10.2 渠道格式翻译规则

| 内部 `message_type` | Web 端输出 | 飞书机器人输出 |
|---|---|---|
| `TEXT` | SSE `event: message` 流式推送 | 调用飞书 `im.message.create` 发送文本消息 |
| `CARD` | SSE `event: action_card` + WebSocket 推送 | 调用飞书 `im.message.create` 发送 Interactive Card |
| `TASK_SUMMARY` | SSE `event: task_summary`，写入 mao_message | 调用飞书 `im.message.create` 发送文本摘要，可附带卡片链接 |
| `STREAM_CHUNK` | SSE `event: message` 流式增量，**不写入 mao_message** | 飞书不支持流式，缓冲后一次性发送 |
| `SYSTEM_NOTICE` | 聊天框顶部系统通知条 | 调用飞书 `im.message.create` 发送系统通知文本 |

#### 8.10.3 飞书 Interactive Card 模板规范

当 `message_type = CARD` 时，适配层将内部 `card_schema` 翻译为飞书标准卡片格式：

```json
{
  "msg_type": "interactive",
  "card": {
    "config": { "wide_screen_mode": true },
    "header": {
      "title": { "tag": "plain_text", "content": "任务参数确认" },
      "template": "blue"
    },
    "elements": [
      {
        "tag": "div",
        "text": { "tag": "lark_md", "content": "**活动名称**：五一母婴线\n**总预算**：20,000 元" }
      },
      {
        "tag": "action",
        "actions": [
          {
            "tag": "button",
            "text": { "tag": "plain_text", "content": "确认执行" },
            "type": "primary",
            "value": {
              "card_action_id": "card_act_abc123",
              "task_id": "task_xyz789",
              "action": "CONFIRM"
            }
          },
          {
            "tag": "button",
            "text": { "tag": "plain_text", "content": "取消" },
            "type": "default",
            "value": {
              "card_action_id": "card_act_abc123",
              "task_id": "task_xyz789",
              "action": "CANCEL"
            }
          }
        ]
      }
    ]
  }
}
```

---

### 8.11 渠道类型枚举 (ChannelType)

| 枚举值 | 说明 | 入站协议 | 出站协议 |
|---|---|---|---|
| `WEB` | Web 端工作站 | HTTP POST + SSE | SSE / WebSocket |
| `FEISHU` | 飞书机器人 | Webhook HTTP POST | 飞书 OpenAPI (HTTP) |
| `DINGTALK` | 钉钉机器人 | Webhook HTTP POST | 钉钉 OpenAPI (HTTP) |
| `WECOM` | 企业微信机器人 | Webhook HTTP POST | 企业微信 API (HTTP) |
