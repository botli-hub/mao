"""
MAO 平台枚举定义
严格对应设计文档 diagrams_classes_enums.md 第 7 章枚举规范。
"""
from enum import Enum


class TaskStatus(str, Enum):
    """任务生命周期状态机。"""
    PENDING = "PENDING"          # 已创建，等待 Router 分发
    ROUTING = "ROUTING"          # Router 正在进行意图匹配
    RUNNING = "RUNNING"          # 执行引擎推演中
    SUSPENDED = "SUSPENDED"      # 挂起等待外部事件（如 OA 审批）
    RESUMING = "RESUMING"        # 收到回调，正在恢复执行
    COMPLETED = "COMPLETED"      # 成功完成
    FAILED = "FAILED"            # 执行失败（已超过重试次数）
    CANCELLED = "CANCELLED"      # 被用户或管理员主动取消
    EXPIRED = "EXPIRED"          # 超过 TTL 强杀


class StepType(str, Enum):
    """ReAct 推演步骤类型（仅写入 mao_task_log，绝不写入 mao_message）。"""
    ROUTER = "ROUTER"            # 意图路由决策
    THOUGHT = "THOUGHT"          # 大模型思考过程
    ACTION = "ACTION"            # 工具调用请求
    OBSERVATION = "OBSERVATION"  # 工具调用结果
    FINAL_ANSWER = "FINAL_ANSWER"  # 最终回答


class SkillType(str, Enum):
    """技能类型（对应 mao_skill.skill_type 字段）。"""
    API = "API"          # 同步 API 调用，立即返回结果
    VIEW = "VIEW"        # 向 C 端渲染 GUI 卡片，等待用户交互
    ASYNC = "ASYNC"      # 触发后挂起，等待外部回调唤醒（x_mao_suspend: true）
    MACRO = "MACRO"      # 宏工具，移交 DAG 引擎执行 SOP 画布


class MessageType(str, Enum):
    """
    消息类型（仅适用于 mao_message Session Memory 表）。

    内外部记忆隔离规则：
      - L4 执行面的 Thought/Action/Observation 严禁写入 mao_message。
      - 上述执行过程应存入 mao_task_log（Task Scratchpad）。
      - 当且仅当任务彻底结束或需要人类介入时，
        才由 Worker 生成 TASK_SUMMARY 或 CARD 写入 mao_message。
    """
    TEXT = "TEXT"                    # 用户或助手的纯文本消息
    CARD = "CARD"                    # 交互卡片（参数确认、高危写入等）
    TASK_SUMMARY = "TASK_SUMMARY"    # 任务结束摘要（仅由 Worker 生成）
    SYSTEM_NOTICE = "SYSTEM_NOTICE"  # 系统通知（记忆压缩提示等）
    SUSPEND_CARD = "SUSPEND_CARD"    # 挂起状态卡片（等待外部审批）
    STREAM_CHUNK = "STREAM_CHUNK"    # 流式增量块（不写入 mao_message）


class ChannelType(str, Enum):
    """渠道类型。"""
    WEB = "WEB"            # Web 端工作站
    FEISHU = "FEISHU"      # 飞书机器人
    DINGTALK = "DINGTALK"  # 钉钉机器人
    WECOM = "WECOM"        # 企业微信机器人


class NodeType(str, Enum):
    """SOP 画布节点类型。"""
    START = "START"
    END = "END"
    SKILL = "SKILL"
    AGENT = "AGENT"
    CONDITION = "CONDITION"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class CardActionType(str, Enum):
    """卡片动作类型。"""
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    SUBMIT_FORM = "SUBMIT_FORM"
    SELECT_INTENT = "SELECT_INTENT"


class SnapshotTriggerType(str, Enum):
    """快照归档触发方式。"""
    SUSPEND_EVENT = "SUSPEND_EVENT"  # 任务挂起事件触发
    TTL_WARNING = "TTL_WARNING"      # Redis TTL 预警触发
    CRON_SCAN = "CRON_SCAN"          # 兜底定时扫描触发


class OverlapPolicy(str, Enum):
    """Cron 任务重叠策略。"""
    SKIP = "SKIP"            # 跳过本次执行
    QUEUE = "QUEUE"          # 排队等待上次完成
    CONCURRENT = "CONCURRENT"  # 允许并发执行
