import { apiClient } from './client'
import type {
  Session, Message, Task, Skill, Agent, AgentDetail, AgentSnapshot,
  Workflow, CronJob, TraceDetail, ManagedTask, PaginatedResponse,
  SkillCreatePayload, CardSchema
} from '../types'

// ─── 聊天 API ──────────────────────────────────────────────────────────────

export const chatAPI = {
  getSessions: () => apiClient.get<PaginatedResponse<Session>>('/chat/sessions'),
  createSession: (title: string) => apiClient.post<Session>('/chat/sessions', { title }),
  getMessages: (sessionId: string) => apiClient.get<Message[]>(`/chat/sessions/${sessionId}/messages`),
  sendMessage: (sessionId: string, content: string) =>
    apiClient.post<Message>(`/chat/sessions/${sessionId}/messages`, { content }),
  executeCardAction: (sessionId: string, messageId: string, actionId: string, formData?: Record<string, unknown>) =>
    apiClient.post(`/chat/action/execute`, { session_id: sessionId, message_id: messageId, action_id: actionId, form_data: formData }),
  getOfflineInbox: (sessionId: string) => apiClient.get<Message[]>(`/chat/offline-inbox?session_id=${sessionId}`),
  getManagedTasks: () => apiClient.get<PaginatedResponse<ManagedTask>>('/chat/managed-tasks'),
}

// ─── 技能管理 ──────────────────────────────────────────────────────────────

export const skillAPI = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<Skill>>(`/admin/skills?page=${page}&page_size=${pageSize}`),
  get: (skillId: string) => apiClient.get<Skill>(`/admin/skills/${skillId}`),
  create: (payload: SkillCreatePayload) => apiClient.post<Skill>('/admin/skills', payload),
  update: (skillId: string, payload: Partial<SkillCreatePayload>) =>
    apiClient.put<Skill>(`/admin/skills/${skillId}`, payload),
  delete: (skillId: string) => apiClient.delete(`/admin/skills/${skillId}`),
}

// ─── Agent 工厂 ────────────────────────────────────────────────────────────

export const agentAPI = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<Agent>>(`/admin/agents?page=${page}&page_size=${pageSize}`),
  get: (agentId: string) => apiClient.get<AgentDetail>(`/admin/agents/${agentId}`),
  create: (name: string, description?: string) =>
    apiClient.post<Agent>('/admin/agents', { name, description }),
  update: (agentId: string, payload: Partial<AgentDetail>) =>
    apiClient.put<Agent>(`/admin/agents/${agentId}`, payload),
  publish: (agentId: string) => apiClient.post(`/admin/agents/${agentId}/publish`),
  getSnapshots: (agentId: string) =>
    apiClient.get<AgentSnapshot[]>(`/admin/agents/${agentId}/snapshots`),
  getSnapshot: (agentId: string, version: string) =>
    apiClient.get<AgentDetail>(`/admin/agents/${agentId}/snapshots/${version}`),
  rollback: (agentId: string, version: string) =>
    apiClient.post(`/admin/agents/${agentId}/snapshots/${version}/restore`),
  bindSkill: (agentId: string, skillId: string) =>
    apiClient.post(`/admin/agents/${agentId}/skills`, { skill_id: skillId }),
  unbindSkill: (agentId: string, skillId: string) =>
    apiClient.delete(`/admin/agents/${agentId}/skills/${skillId}`),
  delete: (agentId: string) => apiClient.delete(`/admin/agents/${agentId}`),
}

// ─── 工作流 ────────────────────────────────────────────────────────────────

export const workflowAPI = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<Workflow>>(`/admin/workflows?page=${page}&page_size=${pageSize}`),
  get: (workflowId: string) => apiClient.get<Workflow>(`/admin/workflows/${workflowId}`),
  create: (name: string, description?: string) =>
    apiClient.post<Workflow>('/admin/workflows', { name, description }),
  update: (workflowId: string, payload: Partial<Workflow>) =>
    apiClient.put<Workflow>(`/admin/workflows/${workflowId}`, payload),
  publish: (workflowId: string) => apiClient.post(`/admin/workflows/${workflowId}/publish`),
  getSnapshots: (workflowId: string) =>
    apiClient.get<Array<{ snapshot_id: string; version: string; published_at: string; published_by: string }>>(`/admin/workflows/${workflowId}/snapshots`),
  rollback: (workflowId: string, version: string) =>
    apiClient.post(`/admin/workflows/${workflowId}/snapshots/${version}/restore`),
  delete: (workflowId: string) => apiClient.delete(`/admin/workflows/${workflowId}`),
}

// ─── Cron 调度 ─────────────────────────────────────────────────────────────

export const cronAPI = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<CronJob>>(`/admin/cron-jobs?page=${page}&page_size=${pageSize}`),
  get: (cronId: string) => apiClient.get<CronJob>(`/admin/cron-jobs/${cronId}`),
  create: (payload: Partial<CronJob>) => apiClient.post<CronJob>('/admin/cron-jobs', payload),
  update: (cronId: string, payload: Partial<CronJob>) =>
    apiClient.put<CronJob>(`/admin/cron-jobs/${cronId}`, payload),
  toggle: (cronId: string, isActive: boolean) =>
    apiClient.patch(`/admin/cron-jobs/${cronId}/toggle`, { is_active: isActive }),
  delete: (cronId: string) => apiClient.delete(`/admin/cron-jobs/${cronId}`),
}

// ─── 监控审计 ──────────────────────────────────────────────────────────────

export const auditAPI = {
  getActiveTasks: (page = 1, pageSize = 20) =>
    apiClient.get<PaginatedResponse<Task>>(`/admin/tasks/active?page=${page}&page_size=${pageSize}`),
  killTask: (taskId: string) => apiClient.post(`/admin/tasks/${taskId}/kill`),
  getTraces: (page = 1, pageSize = 20, status?: string) =>
    apiClient.get<PaginatedResponse<TraceDetail>>(`/admin/audit/traces?page=${page}&page_size=${pageSize}${status ? `&status=${status}` : ''}`),
  getTrace: (traceId: string) => apiClient.get<TraceDetail>(`/admin/audit/traces/${traceId}`),
  reconstructTrace: (traceId: string) =>
    apiClient.get<{ is_complete: boolean; steps: unknown[]; missing_steps?: number[] }>(`/admin/audit/traces/${traceId}/reconstruct`),
  retryTrace: (traceId: string) => apiClient.post(`/admin/audit/traces/${traceId}/retry`),
}
