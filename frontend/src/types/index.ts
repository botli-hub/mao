// ─── 枚举 ──────────────────────────────────────────────────────────────────

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUSPENDED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
export type SkillType = 'API' | 'VIEW' | 'ASYNC' | 'MACRO'
export type ChannelType = 'WEB' | 'FEISHU' | 'DINGTALK' | 'WECOM'
export type MessageRole = 'user' | 'assistant' | 'system'
export type MessageType = 'TEXT' | 'CARD' | 'TASK_SUMMARY' | 'SYSTEM_NOTICE' | 'STREAM_CHUNK'
export type NodeType = 'START' | 'END' | 'AGENT' | 'CONDITION' | 'PARALLEL'

// ─── 用户 ──────────────────────────────────────────────────────────────────

export interface User {
  user_id: string
  username: string
  email: string
  role: 'admin' | 'user'
}

// ─── 会话 & 消息 ────────────────────────────────────────────────────────────

export interface Session {
  session_id: string
  title: string
  channel_type: ChannelType
  last_message?: string
  last_message_at?: string
  created_at: string
}

export interface CardField {
  key: string
  label: string
  type: 'text' | 'select' | 'date' | 'number'
  required?: boolean
  options?: string[]
  placeholder?: string
}

export interface CardAction {
  action_id: string
  label: string
  style: 'primary' | 'danger' | 'default'
  action_type: 'CONFIRM' | 'CANCEL' | 'SUBMIT_FORM' | 'SELECT_INTENT'
}

export interface CardSchema {
  title: string
  description?: string
  fields?: CardField[]
  actions: CardAction[]
  client_side_lock: boolean
}

export interface Message {
  message_id: string
  session_id: string
  role: MessageRole
  message_type: MessageType
  content: string
  card_schema?: CardSchema
  task_id?: string
  quote_ref_id?: string
  created_at: string
}

// ─── 任务 ──────────────────────────────────────────────────────────────────

export interface Task {
  task_id: string
  session_id: string
  agent_id: string
  workflow_id?: string
  status: TaskStatus
  suspend_reason?: string
  error_message?: string
  created_at: string
  updated_at: string
}

export interface ManagedTask {
  task_id: string
  title: string
  status: TaskStatus
  agent_id: string
  created_at: string
}

// ─── 技能 ──────────────────────────────────────────────────────────────────

export interface Skill {
  skill_id: string
  name: string
  skill_type: SkillType
  description?: string
  endpoint_url?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SkillCreatePayload {
  name: string
  skill_type: SkillType
  description?: string
  endpoint_url?: string
  http_method?: string
  request_schema?: Record<string, unknown>
  response_schema?: Record<string, unknown>
  mao_control_meta?: Record<string, unknown>
  timeout_seconds?: number
}

// ─── Agent ─────────────────────────────────────────────────────────────────

export interface ModelConfig {
  provider: string
  model: string
  temperature: number
  max_steps: number
}

export interface Agent {
  agent_id: string
  name: string
  description?: string
  is_draft: boolean
  current_version?: string
  skill_count: number
  created_at: string
  updated_at: string
}

export interface AgentDetail extends Agent {
  system_prompt?: string
  model_config: ModelConfig
  rag_retrieval_config?: Record<string, unknown>
  skill_ids: string[]
}

export interface AgentSnapshot {
  snapshot_id: string
  version: string
  published_at: string
  published_by: string
}

// ─── 工作流 ────────────────────────────────────────────────────────────────

export interface WorkflowNode {
  node_id: string
  node_type: NodeType
  label: string
  agent_id?: string
  position: { x: number; y: number }
  config?: Record<string, unknown>
}

export interface WorkflowEdge {
  edge_id: string
  source_node_id: string
  target_node_id: string
  condition?: string
  mappings?: Record<string, string>
}

export interface Workflow {
  workflow_id: string
  name: string
  description?: string
  is_active: boolean
  dag_definition: {
    nodes: WorkflowNode[]
    edges: WorkflowEdge[]
  }
  created_at: string
  updated_at: string
}

// ─── Cron 调度 ─────────────────────────────────────────────────────────────

export interface CronJob {
  cron_id: string
  name: string
  cron_expr: string
  timezone: string
  agent_id?: string
  workflow_id?: string
  overlap_policy: 'SKIP' | 'QUEUE' | 'CONCURRENT'
  is_active: boolean
  last_run_at?: string
  next_run_at?: string
  created_at: string
}

// ─── 审计 ──────────────────────────────────────────────────────────────────

export interface TraceStep {
  step_index: number
  step_type: 'THOUGHT' | 'ACTION' | 'OBSERVATION'
  content: string
  skill_id?: string
  token_usage?: { prompt: number; completion: number }
  execution_version?: string
  created_at: string
}

export interface TraceDetail {
  trace_id: string
  session_id: string
  agent_id: string
  status: TaskStatus
  total_tokens: { prompt: number; completion: number; total: number }
  step_count: number
  steps: TraceStep[]
  created_at: string
  updated_at: string
}

// ─── SSE 事件 ──────────────────────────────────────────────────────────────

export interface SSEEvent {
  event: 'stream_chunk' | 'action_card' | 'task_summary' | 'task_status' | 'error' | 'done'
  data: {
    message_id?: string
    delta?: string
    card_schema?: CardSchema
    task_id?: string
    status?: TaskStatus
    content?: string
    error?: string
    quote_ref_id?: string
  }
}

// ─── API 响应 ──────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total?: number
  page?: number
  page_size?: number
}

export interface ApiError {
  detail: string | Record<string, unknown>
}
