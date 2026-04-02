-- ============================================================
-- MAO 营销多智能体协同编排平台 - 数据库 DDL 建表语句
-- 版本: V9.5-PROD
-- 数据库: MySQL 8.0+
-- 规范: 严格遵循 18 条数据库设计规范
-- ============================================================

-- 用户表
CREATE TABLE `mao_user` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `username`         VARCHAR(64)  NOT NULL                COMMENT '用户名',
  `email`            VARCHAR(128) NOT NULL                COMMENT '邮箱',
  `role`             VARCHAR(32)  NOT NULL                COMMENT '角色: ADMIN/OPERATOR/VIEWER',
  `department`       VARCHAR(64)                          COMMENT '所属部门',
  `permission_level` VARCHAR(8)   NOT NULL DEFAULT 'L1'   COMMENT '权限等级: L1/L2/L3/L4',
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  UNIQUE KEY `uk_email` (`email`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';

-- 会话表
CREATE TABLE `mao_session` (
  `id`             BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id`     VARCHAR(64)   NOT NULL                COMMENT '会话唯一标识 sess_{uuid}',
  `user_id`        BIGINT        NOT NULL                COMMENT '所属用户 ID',
  `title`          VARCHAR(256)                          COMMENT '会话标题（由首条消息自动生成）',
  `context_window` TEXT                                  COMMENT '当前滑动窗口内的压缩上下文',
  `status`         VARCHAR(32)   NOT NULL DEFAULT 'ACTIVE' COMMENT '状态: ACTIVE/ARCHIVED',
  `message_count`  INT           NOT NULL DEFAULT 0      COMMENT '消息总数',
  `updated_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_session_id` (`session_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_session_user` FOREIGN KEY (`user_id`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话信息表';

-- 消息表
CREATE TABLE `mao_message` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id`   VARCHAR(64)  NOT NULL                COMMENT '所属会话 ID',
  `role`         VARCHAR(16)  NOT NULL                COMMENT '角色: user/assistant/system',
  `content`      TEXT                                 COMMENT '文本内容',
  `message_type` VARCHAR(32)  NOT NULL DEFAULT 'TEXT' COMMENT '类型: TEXT/CARD/SYSTEM_NOTICE/SUSPEND_CARD',
  `card_schema`  JSON                                 COMMENT '卡片 JSON Schema（type=CARD 时必填）',
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_message_session` FOREIGN KEY (`session_id`) REFERENCES `mao_session` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话消息表';

-- 任务表
CREATE TABLE `mao_task` (
  `id`                BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `task_id`           VARCHAR(64)   NOT NULL                COMMENT '任务唯一标识 task_{uuid}',
  `session_id`        VARCHAR(64)   NOT NULL                COMMENT '所属会话 ID',
  `agent_id`          VARCHAR(64)                           COMMENT '承接的 Agent ID（与 workflow_id 二选一）',
  `workflow_id`       VARCHAR(64)                           COMMENT '承接的 SOP 画布 ID（与 agent_id 二选一）',
  `status`            VARCHAR(32)   NOT NULL DEFAULT 'PENDING' COMMENT '任务状态（见 TaskStatus 枚举）',
  `fail_reason`       VARCHAR(64)                           COMMENT '失败原因（见 TaskFailReason 枚举）',
  `state_snap_key`    VARCHAR(128)                          COMMENT 'StateDB 外置快照 Key（实际快照存储于 Redis）',
  `execution_version` VARCHAR(32)                           COMMENT '执行时绑定的 SOP 版本号（如 v1.0）',
  `oa_ticket_id`      VARCHAR(64)                           COMMENT '关联的 OA 审批单号',
  `idempotency_key`   VARCHAR(128)                          COMMENT '幂等键: {task_id}_{card_action_id}',
  `expired_at`        DATETIME                              COMMENT '任务过期时间（用于 TTL 强杀）',
  `updated_at`        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_id` (`task_id`),
  UNIQUE KEY `uk_idempotency_key` (`idempotency_key`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_status` (`status`),
  KEY `idx_state_snap_key` (`state_snap_key`),
  KEY `idx_oa_ticket_id` (`oa_ticket_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_task_session` FOREIGN KEY (`session_id`) REFERENCES `mao_session` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务实例表';

-- 任务执行日志表
CREATE TABLE `mao_task_log` (
  `id`          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
  `task_id`     VARCHAR(64) NOT NULL                COMMENT '所属任务 ID',
  `step_type`   VARCHAR(32) NOT NULL                COMMENT '步骤类型: ROUTER/THOUGHT/ACTION/OBSERVATION',
  `step_index`  INT         NOT NULL                COMMENT '步骤序号（从 0 开始）',
  `input_data`  JSON                                COMMENT '步骤输入数据',
  `output_data` JSON                                COMMENT '步骤输出数据',
  `duration_ms`    INT         COMMENT '执行耗时（毫秒）',
  `state_digest`    JSON        COMMENT 'Shadow Sync 状态摘要：{blackboard_snapshot, execution_version, token_usage}',
  `status`          VARCHAR(32) NOT NULL DEFAULT 'SUCCESS' COMMENT '状态: SUCCESS/FAILED/SKIPPED',
  `updated_at`  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_task_id` (`task_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_task_log_task` FOREIGN KEY (`task_id`) REFERENCES `mao_task` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务执行日志表（链路脑电图）';

-- 智能体配置表
CREATE TABLE `mao_agent` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `agent_id`      VARCHAR(64)  NOT NULL                COMMENT 'Agent 唯一标识 agent_{uuid}',
  `name`          VARCHAR(128) NOT NULL                COMMENT 'Agent 名称',
  `description`   TEXT         NOT NULL                COMMENT 'Agent 职责描述（Router 匹配依据）',
  `system_prompt` TEXT         NOT NULL                COMMENT 'System Prompt 完整内容',
  `max_steps`     INT          NOT NULL DEFAULT 7      COMMENT '最大推演步数（熔断阈值）',
  `rag_kb_ids`    JSON                                 COMMENT '关联的 RAG 知识库 ID 列表',
  `created_by`    BIGINT       NOT NULL                COMMENT '创建人 ID',
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_id` (`agent_id`),
  KEY `idx_created_by` (`created_by`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_agent_user` FOREIGN KEY (`created_by`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体配置表';

-- 技能注册表
CREATE TABLE `mao_skill` (
  `id`            BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `skill_id`      VARCHAR(64)   NOT NULL                COMMENT '技能唯一标识（如 QueryTaskConfig）',
  `name`          VARCHAR(128)  NOT NULL                COMMENT '技能名称',
  `description`   TEXT          NOT NULL                COMMENT '技能功能描述（供 Agent 语义检索）',
  `type`          VARCHAR(16)   NOT NULL                COMMENT '技能类型: API/VIEW/ASYNC/MACRO',
  `auth_type`     VARCHAR(32)   NOT NULL                COMMENT '鉴权方式: USER_TOKEN/SYSTEM_AK_SK/OAUTH2_DYNAMIC',
  `endpoint`      VARCHAR(256)                          COMMENT 'HTTP 接口路径（API 类型必填）',
  `http_method`   VARCHAR(8)                            COMMENT 'HTTP 方法: GET/POST/PUT/DELETE',
  `input_schema`  JSON          NOT NULL                COMMENT '输入参数 JSON Schema',
  `output_schema` JSON                                  COMMENT '输出结果 JSON Schema',
  `ttl_ms`        BIGINT                                COMMENT '最大存活时间（ASYNC 类型必填，单位毫秒）',
  `pii_fields`    JSON                                  COMMENT '需要脱敏的 PII 字段列表',
  `is_high_risk`  TINYINT(1)    NOT NULL DEFAULT 0      COMMENT '是否为高危 API（禁止在 Cron 中直接执行）',
  `call_count`    BIGINT        NOT NULL DEFAULT 0      COMMENT '调用次数（调用热度统计）',
  `created_by`    BIGINT        NOT NULL                COMMENT '创建人 ID',
  `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_skill_id` (`skill_id`),
  KEY `idx_type` (`type`),
  KEY `idx_created_by` (`created_by`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_skill_user` FOREIGN KEY (`created_by`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能注册表';

-- 智能体技能关联表
CREATE TABLE `mao_agent_skill_rel` (
  `id`         BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
  `agent_id`   VARCHAR(64) NOT NULL                COMMENT '智能体 ID',
  `skill_id`   VARCHAR(64) NOT NULL                COMMENT '技能 ID',
  `sort_order` INT         NOT NULL DEFAULT 0      COMMENT '排序权重',
  `updated_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at` DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_skill` (`agent_id`, `skill_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_rel_agent` FOREIGN KEY (`agent_id`) REFERENCES `mao_agent` (`agent_id`),
  CONSTRAINT `fk_rel_skill` FOREIGN KEY (`skill_id`) REFERENCES `mao_skill` (`skill_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体技能关联表';

-- SOP 工作流表
CREATE TABLE `mao_workflow` (
  `id`             BIGINT        NOT NULL AUTO_INCREMENT COMMENT '主键',
  `workflow_id`    VARCHAR(64)   NOT NULL                COMMENT '工作流唯一标识 wf_{uuid}',
  `name`           VARCHAR(128)  NOT NULL                COMMENT '工作流名称',
  `description`    TEXT                                  COMMENT '工作流描述',
  `version`        VARCHAR(32)   NOT NULL DEFAULT 'v1.0' COMMENT '版本号',
  `dag_definition` TEXT          NOT NULL                COMMENT 'DAG 图定义 JSON（节点、边、参数映射）',
  `status`         VARCHAR(32)   NOT NULL DEFAULT 'DRAFT' COMMENT '状态: DRAFT/PUBLISHED/DEPRECATED',
  `macro_skill_id` VARCHAR(64)                           COMMENT '注册为宏工具后对应的 skill_id',
  `created_by`     BIGINT        NOT NULL                COMMENT '创建人 ID',
  `updated_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_workflow_id` (`workflow_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created_by` (`created_by`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_workflow_user` FOREIGN KEY (`created_by`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SOP 工作流表';

-- 定时任务表
CREATE TABLE `mao_cron_job` (
  `id`                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`            BIGINT       NOT NULL                COMMENT '所属用户 ID',
  `job_name`           VARCHAR(128) NOT NULL                COMMENT '任务名称',
  `trigger_type`       VARCHAR(16)  NOT NULL                COMMENT '触发类型: CRON/CONDITION',
  `cron_expr`          VARCHAR(64)                          COMMENT 'Cron 表达式（CRON 类型必填）',
  `condition_rule`     JSON                                 COMMENT '条件触发规则（CONDITION 类型必填）',
  `target_type`        VARCHAR(16)  NOT NULL                COMMENT '目标类型: AGENT/WORKFLOW',
  `target_agent_id`    VARCHAR(64)                          COMMENT '目标 Agent ID',
  `target_workflow_id` VARCHAR(64)                          COMMENT '目标工作流 ID',
  `status`             VARCHAR(32)  NOT NULL DEFAULT 'ACTIVE' COMMENT '状态: ACTIVE/PAUSED/EXPIRED',
  `last_run_at`        DATETIME                             COMMENT '上次执行时间',
  `next_run_at`        DATETIME                             COMMENT '下次执行时间',
  `expired_at`         DATETIME                             COMMENT '过期时间',
  `updated_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_next_run_at` (`next_run_at`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_cron_user` FOREIGN KEY (`user_id`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务配置表';

-- 离线信箱表
CREATE TABLE `mao_offline_inbox` (
  `id`              BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`         BIGINT      NOT NULL                COMMENT '目标用户 ID',
  `task_id`         VARCHAR(64) NOT NULL                COMMENT '关联任务 ID',
  `channel_type`    VARCHAR(32) NOT NULL DEFAULT 'WEB'  COMMENT '目标渠道: WEB/FEISHU/DINGTALK/WECOM',
  `message_content` TEXT        NOT NULL                COMMENT '消息文本内容',
  `card_schema`     JSON                                COMMENT '消息卡片 Schema',
  `status`          VARCHAR(16) NOT NULL DEFAULT 'UNREAD' COMMENT '状态: UNREAD/READ',
  `read_at`         DATETIME                            COMMENT '阅读时间',
  `retry_count`     INT         NOT NULL DEFAULT 0      COMMENT '已重试次数（退避重试计数，最大 5 次）',
  `last_retry_at`   DATETIME                            COMMENT '最近一次重试时间',
  `updated_at`      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_id_status` (`user_id`, `status`),
  KEY `idx_retry_count` (`retry_count`),
  KEY `idx_last_retry_at` (`last_retry_at`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_inbox_user` FOREIGN KEY (`user_id`) REFERENCES `mao_user` (`id`),
  CONSTRAINT `fk_inbox_task` FOREIGN KEY (`task_id`) REFERENCES `mao_task` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='离线信箱表（支持退避重试投递）';

-- ============================================================
-- v9.1 新增：渠道适配层相关表
-- ============================================================

-- 渠道账号绑定表
CREATE TABLE `mao_channel_account` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`          BIGINT       NOT NULL               COMMENT '系统内部用户 ID',
  `channel_type`     VARCHAR(32)  NOT NULL               COMMENT '渠道类型: WEB/FEISHU/DINGTALK/WECOM',
  `external_user_id` VARCHAR(128) NOT NULL               COMMENT '外部渠道用户唯一标识（如飞书 OpenID）',
  `external_app_id`  VARCHAR(128)                        COMMENT '外部应用 ID（如飞书 App ID）',
  `access_token`     TEXT                                COMMENT '渠道访问凭证（AES-256 加密存储）',
  `token_expires_at` DATETIME                            COMMENT '凭证过期时间',
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_external_user` (`channel_type`, `external_user_id`, `external_app_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_channel_account_user` FOREIGN KEY (`user_id`) REFERENCES `mao_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道账号绑定表';

-- 渠道会话映射表
CREATE TABLE `mao_channel_session` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `session_id`       VARCHAR(64)  NOT NULL               COMMENT 'MAO 内部 Session ID',
  `channel_type`     VARCHAR(32)  NOT NULL               COMMENT '渠道类型: WEB/FEISHU/DINGTALK/WECOM',
  `external_chat_id` VARCHAR(256) NOT NULL               COMMENT '外部渠道会话/群组 ID（如飞书 ChatID）',
  `external_app_id`  VARCHAR(128) NOT NULL               COMMENT '外部应用 ID',
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_channel_chat` (`channel_type`, `external_chat_id`, `external_app_id`),
  KEY `idx_session_id` (`session_id`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_channel_session_session` FOREIGN KEY (`session_id`) REFERENCES `mao_session` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道会话映射表';

-- ============================================================
-- v9.5 新增：热冷数据一致性保障表
-- ============================================================

-- 任务快照归档表（挂起时深冻结快照持久化）
CREATE TABLE `mao_task_snapshot_archive` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `task_id`          VARCHAR(64)  NOT NULL               COMMENT '关联任务 ID',
  `suspend_seq`      INT          NOT NULL DEFAULT 1     COMMENT '第几次挂起（支持多轮审批）',
  `trigger_type`     VARCHAR(32)  NOT NULL               COMMENT '触发方式: SUSPEND_EVENT/TTL_WARNING/CRON_SCAN',
  `snapshot_data`    JSON         NOT NULL               COMMENT 'Redis 全量快照序列化内容（ReAct 历史+黑板+执行版本）',
  `redis_key`        VARCHAR(128) NOT NULL               COMMENT '对应的 Redis Key（归档后仅保留索引）',
  `execution_version` VARCHAR(32) NOT NULL               COMMENT '快照时的 SOP 执行版本号',
  `archived_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '归档时间',
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_task_suspend_seq` (`task_id`, `suspend_seq`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_trigger_type` (`trigger_type`),
  KEY `ix_updated_at` (`updated_at`),
  KEY `ix_created_at` (`created_at`),
  CONSTRAINT `fk_snapshot_task` FOREIGN KEY (`task_id`) REFERENCES `mao_task` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务快照归档表（热冷数据一致性保障）';

-- ============================================================
-- 说明：
-- 本文件为目标态建表 SQL（greenfield 初始化库直接执行）。
-- 存量库升级请使用独立迁移脚本，不在本设计 SQL 中使用 ALTER TABLE 过程语句。
-- ============================================================
