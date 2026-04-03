# 前端代码二次 Review（基于 design 目录）

- Review 日期：2026-04-02
- 范围：`frontend/src/**` 与 `design/**`（原型、API、产品需求）
- 结论：当前前端实现为 **MVP 骨架**，已具备「会话 + SSE + 管理台基础导航」能力，但与设计稿相比仍有多处关键能力缺口，尤其是 **C 端 HITL 交互闭环** 与 **B 端编排/调度核心能力**。

---

## 1) 对齐结果总览

### 已对齐（部分）

1. 已有 C 端会话侧边栏 + 聊天主窗口基础结构。  
2. 已有 SSE 事件消费基础，支持 `stream_chunk`、`action_card`、`task_summary`、`done`。  
3. 已有 B 端主导航（技能、Agent、工作流、审计）和技能列表/审计列表基础页面。

### 未对齐（关键）

1. C 端「我的后台托管任务（My Scheduler）」模块缺失。  
2. C 端「离线信箱 + 铃铛红点 + 离线分割线 + 引用锚点」缺失。  
3. C 端卡片交互未打通服务端（`sendMessage` / `executeCardAction` 仅注释或日志）。  
4. B 端 Agent 工厂、全局编排画布仍为占位页，尚未实现核心 CRUD、版本发布、快照回滚、画布编辑。  
5. B 端「监控与调度大盘（含 Cron 管理）」未落地，仅有审计记录简表。

---

## 2) 差异清单（按优先级）

## P0（必须先补）

### P0-1 C 端消息发送与卡片动作未真正调用后端
- 现状：`ChatWindow` 的 `handleSendMessage` 没有调用 `chatAPI.sendMessage`；卡片按钮点击也仅 `console.log`。  
- 风险：无法形成设计中 LUI + GUI 的 HITL 闭环，前端只是在“假交互”。  
- 建议：
  - 在 `handleSendMessage` 中调用 `chatAPI.sendMessage(sessionId, content)`；
  - 在 `GUICard` 的 `onActionClick` 中调用 `chatAPI.executeCardAction(...)`；
  - 成功后立即本地锁按钮，失败时回滚并提示。

### P0-2 卡片“提交后只读锁定”机制缺失
- 现状：虽然类型里有 `client_side_lock` 字段，但 UI 层没有落地禁用态与状态回填。  
- 风险：与设计中的“防重放 + 防双击 + 幂等”不一致，可能重复提交。
- 建议：
  - `GUICard` 增加 `isLocked` 与 `pendingActionId`；
  - 点击后即灰化（前端锁），并等待服务端态确认；
  - 刷新后以消息状态恢复锁定（以后端为准）。

### P0-3 B 端核心页面仍为占位，无法支持上线使用
- 现状：`AgentsTab` / `WorkflowsTab` 仅展示“开发中...”。
- 风险：与设计中“智能体工厂 / DAG 画布”核心价值严重不匹配。
- 建议：按“列表页 -> 详情页 -> 发布/回滚 -> 审计跳转”分期建设。

## P1（高优先级）

### P1-1 C 端缺少“我的后台托管任务”侧栏区块
- 现状：`SessionSidebar` 只有会话列表，没有托管任务区域。  
- 设计要求：展示任务状态、暂停/恢复/终止等操作。  
- 建议：接入 `chatAPI.getManagedTasks()` 并增加任务区块和状态 Tag。

### P1-2 离线信箱体验链路缺失
- 现状：无铃铛入口、无离线消息拉取触发、无“离线期间完成任务”分割线。
- 建议：
  - 顶栏增加 Inbox Bell；
  - 首次进会话主动拉取 `getOfflineInbox(sessionId)`；
  - 插入系统分割消息（`SYSTEM_NOTICE`）和 `quote_ref` 展示。

### P1-3 意图澄清卡片（Intent Disambiguation）未实现
- 现状：类型有 `SELECT_INTENT`，但 UI 无专门渲染与提交流程。
- 建议：在 `GUICard` 中为 `SELECT_INTENT` 行为提供单选 + 提交，纳入统一 action pipeline。

### P1-4 管理台缺少 Cron 管理与运行态看板
- 现状：已有 `cronAPI`，但无实际页面。
- 建议：新增 Dashboard/CronTab，落地 list/create/toggle/delete 与活跃任务联动。

## P2（体验与工程质量）

### P2-1 会话切换未自动拉取历史消息
- 现状：`ChatPage` 当前只加载会话列表，不见切换后加载 `getMessages` 的逻辑。
- 建议：监听 `currentSessionId` 后请求消息并处理分页。

### P2-2 事件类型与消息落库语义需进一步收敛
- 现状：前端消费 `stream_chunk`，但 API 设计强调仅部分事件写会话历史。
- 建议：将“流式中间态”和“最终持久化态”在 store 层分轨，避免重复渲染和重复落库心智。

---

## 3) 建议实施路线（两周版本）

### Sprint A（先打通闭环）
1. 打通 `sendMessage` / `executeCardAction` 真调用；
2. 落地卡片客户端锁定与错误回滚；
3. 增加会话切换拉历史消息。

### Sprint B（补齐设计关键体验）
1. C 端托管任务侧栏；
2. 离线信箱入口 + 分割线 + 引用锚点；
3. B 端 Cron 管理页面。

### Sprint C（补 B 端核心能力）
1. Agent 工厂列表/详情/发布回滚；
2. Workflow 列表 + 编辑器最小可用版（先不做复杂 Data Mapper）。

---

## 4) 验收标准（建议）

1. 用户可完成：输入诉求 → 收到卡片 → 提交卡片 → 卡片锁定 → 收到最终结果。  
2. 用户离线后再上线可见：离线红点、补发消息、离线分割线。  
3. 管理员可完成：创建/启停 Cron、查看活跃任务、审计追踪。  
4. Agent/Workflow 不再是占位页，至少具备可读写与发布能力。
