# MAO 平台 — 全景 API 接口文档 (v9.0-PROD)

> **版本**：V9.0-PROD | **更新日期**：2026-04

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
```
// 事件1：文本
event: message
data: {"task_id": "tsk_001", "type": "text", "content": "好的..."}

// 事件2：GUI卡片下发
event: action_card
data: {
  "task_id": "tsk_001", "type": "card_render",
  "card_schema": {
    "component": "TaskConfigForm",
    "payload": {"budget": 20000},
    "actions": [{"id": "submit_oa", "label": "确认提交"}]
  }
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

> `next_state` 枚举值：`SUSPENDED`（异步挂起，等待外部回调）、`SYNC_COMPLETED`（同步完成，`sync_result` 字段包含业务结果）。

#### 8.2.5 拉取离线消息信笱

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
      {"task_id": "tsk_001", "type": "async_result", "quote_ref_id": "msg_OA-8902", "content": "您的审批已通过。"}
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

**Query 参数**：`page=1`, `size=10`, `type=ASYNC_SKILL`

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
{ "code": 200, "data": { "name": "SubmitOAApproval", "type": "ASYNC_SKILL", "input_schema": {...}, "output_schema": {...} } }
```

#### 8.4.3 注册原子技能

```
POST /admin/skills
```

**请求参数**：

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | `string` | 是 | 技能名称 |
| `type` | `string` | 是 | 技能类型：`API_SKILL`、`VIEW_SKILL`、`ASYNC_SKILL`、`MACRO_SKILL` |
| `execution_config` | `object` | 是 | 执行配置，包含 endpoint、auth_type |
| `mao_control_meta` | `object` | 否 | MAO 控制元数据，异步技能必填 |
| `input_schema` | `object` | 是 | 遵循 JSON Schema Draft-07 标准 |
| `output_schema` | `object` | 是 | 遵循 JSON Schema Draft-07 标准 |

**请求示例**：
```json
{
  "name": "SubmitOAApproval", 
  "type": "ASYNC_SKILL",
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

---
