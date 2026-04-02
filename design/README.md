# MAO 平台系统设计文档

> **MAO (Marketing Agent Orchestration)** — 营销多智能体协同编排平台
>
> **文档版本**：v9.1-PROD | **最后更新**：2026-04

本目录为 MAO 平台完整系统设计归档，面向后端、前端及全栈工程师，旨在达到**初级工程师可直接参照编码实现**的程度。

---

## 目录结构

```
design/
├── README.md                          # 本文件：文档导航索引
│
├── 00_prototypes/                     # 原始需求与交互原型（设计输入）
│   ├── product_requirements.txt       # 产品需求说明
│   ├── b_side_prototype.html          # B 端管理控制台交互原型
│   ├── c_side_prototype.html          # C 端 LUI 工作站交互原型
│   └── api_reference_prototype.html   # API 接口参考原型
│
├── 01_overview/                       # 产品概述与设计原则
│   └── product_overview.md            # 产品定位、核心原则、技术选型
│
├── 02_architecture/                   # 系统架构设计
│   └── system_architecture.md        # 六层架构、模块详细设计、类图、枚举
│
├── 03_data_model/                     # 数据模型设计
│   └── data_model.md                  # 实体关系说明、字段规范
│
├── 04_api/                            # API 接口文档
│   └── api_reference.md               # 全景 OpenAPI v9.0，含 C 端、B 端、回调、审计
│
├── 05_diagrams/                       # 架构图与流程图
│   ├── source/                        # Mermaid 源文件（可编辑）
│   │   ├── 01_overall_architecture.mmd
│   │   ├── 02_intent_routing_sequence.mmd
│   │   ├── 03_async_suspend_resume_sequence.mmd
│   │   ├── 04_dag_multiagent_flow.mmd
│   │   ├── 05_core_class_diagram.mmd
│   │   ├── 06_entity_relationship.mmd
│   │   ├── 07_security_permission_flow.mmd
│   │   ├── 08_skill_registry_module.mmd
│   │   ├── 09_react_agent_execution.mmd
│   │   └── 10_offline_inbox_sequence.mmd
│   └── rendered/                      # 渲染后的 PNG 图片
│       ├── 01_overall_architecture.png
│       ├── 02_intent_routing_sequence.png
│       ├── 03_async_suspend_resume_sequence.png
│       ├── 04_dag_multiagent_flow.png
│       ├── 05_core_class_diagram.png
│       ├── 06_entity_relationship.png
│       ├── 07_security_permission_flow.png
│       ├── 08_skill_registry_module.png
│       ├── 09_react_agent_execution.png
│       └── 10_offline_inbox_sequence.png
│
└── 06_database/                       # 数据库设计
    └── schema.sql                     # 可直接执行的 MySQL DDL 建表语句
```

---

## 快速导航

### 我是前端工程师
1. 阅读 [产品概述](./01_overview/product_overview.md) 了解平台定位
2. 查阅 [API 接口文档](./04_api/api_reference.md) 对接接口
3. 查看 [GUI 卡片双态响应机制](./04_api/api_reference.md#824-提交-gui-卡片动作-双态响应) 实现卡片交互

### 我是后端工程师
1. 阅读 [系统架构设计](./02_architecture/system_architecture.md) 理解六层架构
2. 查阅 [数据模型](./03_data_model/data_model.md) 了解实体关系
3. 执行 [数据库 DDL](./06_database/schema.sql) 初始化数据库
4. 参考 [API 接口文档](./04_api/api_reference.md) 实现接口

### 我是架构师/技术负责人
1. 查看 [整体架构图](./05_diagrams/rendered/01_overall_architecture.png)
2. 查看 [ReAct 执行流程图](./05_diagrams/rendered/09_react_agent_execution.png)
3. 查看 [异步挂起唤醒时序图](./05_diagrams/rendered/03_async_suspend_resume_sequence.png)
4. 查看 [安全权限防线流程图](./05_diagrams/rendered/07_security_permission_flow.png)

---

## 图表索引

| 编号 | 图表名称 | 说明 |
|---|---|---|
| 01 | [整体系统架构图](./05_diagrams/rendered/01_overall_architecture.png) | 六层全局架构，含控制面与执行面分离 |
| 02 | [意图路由时序图](./05_diagrams/rendered/02_intent_routing_sequence.png) | Router 意图识别与 Agent 分发流程 |
| 03 | [异步挂起唤醒时序图](./05_diagrams/rendered/03_async_suspend_resume_sequence.png) | 长程异步四阶段流转（挂起→冻结→回调→唤醒） |
| 04 | [多智能体 DAG 协同流程图](./05_diagrams/rendered/04_dag_multiagent_flow.png) | DAG 编排与共享黑板数据流 |
| 05 | [核心类图](./05_diagrams/rendered/05_core_class_diagram.png) | 执行引擎核心类及接口定义 |
| 06 | [实体关系图 (ER)](./05_diagrams/rendered/06_entity_relationship.png) | 数据库实体关系 |
| 07 | [安全权限防线流程图](./05_diagrams/rendered/07_security_permission_flow.png) | PII 脱敏、幂等防双花、分布式锁 |
| 08 | [技能注册中心模块架构图](./05_diagrams/rendered/08_skill_registry_module.png) | Skill Registry 模块内部结构 |
| 09 | [ReAct Agent 执行流程图](./05_diagrams/rendered/09_react_agent_execution.png) | ReAct 循环含熔断机制 |
| 10 | [离线信箱时序图](./05_diagrams/rendered/10_offline_inbox_sequence.png) | 离线信箱与 WebSocket 主动推送 |
