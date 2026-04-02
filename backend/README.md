# MAO Backend — Python FastAPI 后端

> MAO 营销多智能体协同编排平台后端服务，基于 **Python 3.11 + FastAPI + Kafka + MySQL + Redis** 构建。

---

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 异步 HTTP + SSE 流式推送 |
| ORM | SQLAlchemy 2.0 (async) | 异步数据库操作 |
| 数据库 | MySQL 8.0+ | 持久化存储（元数据 + 审计） |
| 缓存/状态 | Redis 7+ (AOF) | 热态快照（Append-only）+ SSE 队列 |
| 消息队列 | Apache Kafka | 异步事件解耦 + Observer Log |
| LLM 调用 | OpenAI SDK (async) | ReAct 推演 + 意图路由 |
| 任务调度 | APScheduler | Cron 定时任务 |
| 数据校验 | Pydantic v2 | 请求/响应 Schema + 黑板校验 |

---

## 项目结构

```
backend/
├── mao/
│   ├── main.py                    # FastAPI 应用入口
│   ├── core/
│   │   ├── config.py              # 配置管理（Pydantic Settings）
│   │   ├── enums.py               # 全局枚举定义
│   │   ├── redis_client.py        # Redis 客户端（SSE 队列 + StateDB）
│   │   ├── kafka_client.py        # Kafka 生产者/消费者
│   │   └── security.py            # JWT 认证 + 权限校验
│   ├── db/
│   │   ├── database.py            # 数据库连接（AsyncSession）
│   │   └── models/                # SQLAlchemy ORM 模型
│   │       ├── user.py
│   │       ├── session.py
│   │       ├── message.py
│   │       ├── task.py            # mao_task + mao_task_log + snapshot_archive
│   │       ├── skill.py
│   │       ├── agent.py           # mao_agent + snapshot + skill_rel
│   │       ├── workflow.py
│   │       ├── cron.py
│   │       └── channel.py         # mao_channel_account + mao_channel_session
│   ├── engine/
│   │   ├── router.py              # 意图路由器（LLM 语义路由）
│   │   ├── task_service.py        # 任务生命周期管理
│   │   ├── cron_scheduler.py      # Cron 调度器（APScheduler）
│   │   ├── react/
│   │   │   ├── runner.py          # ReAct 推演引擎（核心）
│   │   │   ├── blackboard.py      # 共享黑板（Redis Append-only）
│   │   │   ├── skill_executor.py  # 技能执行器（HTTP/VIEW/ASYNC/MACRO）
│   │   │   └── state_machine.py   # 任务状态机（合法转换校验）
│   │   └── dag/
│   │       └── runner.py          # DAG 工作流引擎（拓扑排序）
│   ├── channel/
│   │   ├── base.py                # 渠道适配器基类 + OmniMessage 协议
│   │   ├── feishu.py              # 飞书渠道适配器
│   │   └── dispatcher.py          # 渠道消息分发器
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py            # C 端聊天 API（SSE + 卡片交互）
│   │       ├── callbacks.py       # 统一回调网关 + 飞书卡片回调
│   │       └── admin/
│   │           ├── skills.py      # B 端技能管理 API
│   │           ├── agents.py      # B 端 Agent 工厂 API（含快照/回滚）
│   │           └── audit.py       # B 端监控审计 API（脑电图 + 熔断）
│   └── services/
│       ├── archiver.py            # 归档服务（Kafka 消费 + 深冻结）
│       └── inbox_retrier.py       # 离线信箱退避重投服务
├── pyproject.toml                 # 依赖配置
├── .env.example                   # 环境变量模板
└── README.md
```

---

## 快速启动

### 1. 安装依赖

```bash
cd backend
pip install -e ".[dev]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 MySQL、Redis、Kafka、OpenAI 等配置
```

### 3. 初始化数据库

```bash
# 执行 DDL 建表
mysql -u root -p mao_db < ../design/06_database/schema.sql
```

### 4. 启动服务

```bash
# 开发模式（热重载）
uvicorn mao.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式（多进程）
gunicorn mao.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 5. 访问 API 文档

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

---

## 核心设计原则

### 无状态 Worker

每个 ReAct 推演步骤完成后，Worker 将状态以 Append-only 方式写入 Redis（`RPUSH mao:state:{task_id}:steps`）。任务挂起时触发深冻结归档到 MySQL。Worker 崩溃或重启后，新 Worker 从 Redis 完整恢复执行现场，实现横向弹性扩缩容。

### 内外部记忆物理隔离

- **Session Memory**（`mao_message`）：仅存储用户可见的对话历史（TEXT / CARD / TASK_SUMMARY）
- **Task Scratchpad**（`mao_task_log`）：仅存储 Worker 内部执行链路（THOUGHT / ACTION / OBSERVATION）
- Worker 内部的中间过程**绝对禁止**写入 `mao_message`，防止污染滑动窗口

### 防双引擎死循环

Agent 发布时强制执行 DFS 宏工具环路检测。若 MACRO 技能的调用链最终回到当前 Agent 自身，发布操作将被拒绝（`422 MACRO_CYCLE_DETECTED`）。

### 卡片物理防抖

所有 GUI 卡片携带 `client_side_lock: true`，飞书渠道映射为 Exclusive 属性（点击即锁），Web 渠道映射为按钮 `disabled`。配合后端幂等键（`idempotency_key`）形成双层防护。
