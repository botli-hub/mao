"""
共享黑板（Blackboard）
任务执行过程中的共享状态容器，外置持久化至 Redis StateDB。
Worker 无状态：每步推演前从 Redis 加载，每步结束后写回 Redis。
"""
from typing import Any

from mao.core.redis_client import state_get_blackboard, state_set_blackboard


class Blackboard:
    """
    任务执行的共享状态黑板。
    - 所有数据存储于 Redis，Worker 实例无内存状态。
    - 支持任意 Worker 节点从 Redis 恢复完整执行现场。
    """

    def __init__(self, task_id: str, initial_data: dict[str, Any] | None = None) -> None:
        self.task_id = task_id
        self._data: dict[str, Any] = initial_data or {}

    @classmethod
    async def load(cls, task_id: str) -> "Blackboard":
        """从 Redis 加载黑板状态（Worker 恢复执行现场时调用）。"""
        data = await state_get_blackboard(task_id)
        return cls(task_id=task_id, initial_data=data)

    async def save(self) -> None:
        """将黑板状态持久化到 Redis（每步推演结束后调用）。"""
        await state_set_blackboard(self.task_id, self._data)

    def get(self, key: str, default: Any = None) -> Any:
        """读取黑板变量。"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """写入黑板变量。"""
        self._data[key] = value

    def update(self, mapping: dict[str, Any]) -> None:
        """批量写入黑板变量（来自节点输出的 mappings）。"""
        self._data.update(mapping)

    def snapshot(self) -> dict[str, Any]:
        """获取当前黑板的完整副本（用于 state_digest 写入）。"""
        return dict(self._data)

    def to_dict(self) -> dict[str, Any]:
        return self._data
