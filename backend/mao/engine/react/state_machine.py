"""
任务状态机
管理 mao_task 的状态流转，确保合法转换，防止非法状态跳转。
"""
from mao.core.enums import TaskStatus

# 合法的状态转换表
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.SUSPENDED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.SUSPENDED: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),   # 终态
    TaskStatus.FAILED: {TaskStatus.RUNNING},  # 允许断点续传重试
    TaskStatus.CANCELLED: set(),   # 终态
}


class InvalidTransitionError(Exception):
    """非法状态转换异常。"""
    pass


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    """
    验证状态转换是否合法。
    :raises InvalidTransitionError: 转换不合法时抛出
    """
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Invalid task status transition: {current.value} → {target.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )


def is_terminal(status: TaskStatus) -> bool:
    """判断是否为终态（COMPLETED 或 CANCELLED）。"""
    return status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
