"""
DAG 工作流引擎（SOP 画布执行器）
基于拓扑排序实现 DAG 节点的串行/并行执行。
支持节点类型：START / END / AGENT / SKILL / CONDITION / HUMAN_APPROVAL
"""
import asyncio
import logging
from collections import defaultdict, deque
from typing import Any

from mao.core.enums import TaskStatus
from mao.core.redis_client import sse_push
from mao.engine.react.blackboard import Blackboard

logger = logging.getLogger(__name__)


class DAGExecutionError(Exception):
    """DAG 执行异常。"""
    pass


class DAGRunner:
    """
    DAG 工作流执行器。
    DAG 定义格式：
    {
        "nodes": [
            {"id": "n1", "type": "START"},
            {"id": "n2", "type": "AGENT", "agent_id": "agent_xxx", "label": "分析节点"},
            {"id": "n3", "type": "CONDITION", "condition_expr": "blackboard.get('score') > 80"},
            {"id": "n4", "type": "SKILL", "skill_id": "skill_xxx"},
            {"id": "n5", "type": "END"},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3", "mappings": {"analysis_result": "output.result"}},
            {"from": "n3", "to": "n4", "condition": "true"},
            {"from": "n3", "to": "n5", "condition": "false"},
            {"from": "n4", "to": "n5"},
        ]
    }
    """

    def __init__(
        self,
        task_id: str,
        session_id: str,
        dag_definition: dict[str, Any],
        node_executors: dict[str, Any],  # {node_type: executor_callable}
    ) -> None:
        self.task_id = task_id
        self.session_id = session_id
        self.dag = dag_definition
        self.node_executors = node_executors

        # 构建邻接表和入度表
        self._nodes: dict[str, dict[str, Any]] = {
            n["id"]: n for n in dag_definition.get("nodes", [])
        }
        self._edges: list[dict[str, Any]] = dag_definition.get("edges", [])
        self._adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._in_degree: dict[str, int] = defaultdict(int)

        for edge in self._edges:
            self._adj[edge["from"]].append(edge)
            self._in_degree[edge["to"]] += 1

    async def execute(self, blackboard: Blackboard) -> dict[str, Any]:
        """
        执行 DAG 工作流（基于 Kahn 算法拓扑排序）。
        :returns: 执行结果 {"status": "COMPLETED|SUSPENDED", ...}
        """
        # 找到起始节点（入度为 0 的非 END 节点）
        queue: deque[str] = deque()
        in_degree = dict(self._in_degree)

        for node_id, node in self._nodes.items():
            if in_degree.get(node_id, 0) == 0:
                queue.append(node_id)

        executed_nodes: set[str] = set()

        while queue:
            # 收集当前可并行执行的节点
            parallel_nodes = []
            while queue:
                node_id = queue.popleft()
                if node_id not in executed_nodes:
                    parallel_nodes.append(node_id)

            if not parallel_nodes:
                break

            # 并行执行当前层的所有节点
            results = await asyncio.gather(
                *[self._execute_node(node_id, blackboard) for node_id in parallel_nodes],
                return_exceptions=True,
            )

            for node_id, result in zip(parallel_nodes, results):
                executed_nodes.add(node_id)

                if isinstance(result, Exception):
                    logger.error(f"[{self.task_id}] Node {node_id} failed: {result}")
                    raise DAGExecutionError(f"Node {node_id} failed: {result}")

                # 检查是否触发挂起
                if isinstance(result, dict) and result.get("status") == TaskStatus.SUSPENDED.value:
                    await blackboard.save()
                    return result

                # 处理边的 mappings（将节点输出写入黑板）
                for edge in self._adj.get(node_id, []):
                    mappings = edge.get("mappings") or {}
                    if mappings and isinstance(result, dict):
                        for bb_key, output_path in mappings.items():
                            # 支持简单路径如 "output.result"
                            value = self._extract_path(result, output_path)
                            if value is not None:
                                blackboard.set(bb_key, value)

                    # 处理条件边
                    condition = edge.get("condition")
                    if condition is not None:
                        # 评估条件表达式
                        condition_met = self._eval_condition(condition, blackboard)
                        if not condition_met:
                            continue

                    # 减少下游节点入度
                    target_id = edge["to"]
                    in_degree[target_id] = in_degree.get(target_id, 1) - 1
                    if in_degree[target_id] <= 0:
                        queue.append(target_id)

            # 保存黑板状态
            await blackboard.save()

        return {"status": TaskStatus.COMPLETED.value}

    async def _execute_node(
        self, node_id: str, blackboard: Blackboard
    ) -> dict[str, Any]:
        """执行单个 DAG 节点。"""
        node = self._nodes.get(node_id)
        if not node:
            raise DAGExecutionError(f"Node {node_id} not found in DAG")

        node_type = node.get("type", "UNKNOWN")
        logger.info(f"[{self.task_id}] Executing node {node_id} (type={node_type})")

        # 推送 SSE 进度事件
        await sse_push(self.session_id, {
            "event": "node_progress",
            "task_id": self.task_id,
            "node_id": node_id,
            "node_type": node_type,
            "status": "running",
        })

        executor = self.node_executors.get(node_type)
        if node_type in ("START", "END"):
            return {"status": "COMPLETED", "node_id": node_id}

        if not executor:
            raise DAGExecutionError(f"No executor for node type: {node_type}")

        result = await executor(node, blackboard)
        return result

    def _eval_condition(self, condition: str, blackboard: Blackboard) -> bool:
        """
        安全评估条件表达式。
        支持简单的 Python 表达式，上下文为黑板数据。
        """
        if condition in ("true", "True", "1"):
            return True
        if condition in ("false", "False", "0"):
            return False
        try:
            bb = blackboard.to_dict()
            return bool(eval(condition, {"__builtins__": {}}, {"blackboard": blackboard, **bb}))  # noqa: S307
        except Exception as e:
            logger.warning(f"Condition eval failed: {condition!r} → {e}")
            return False

    @staticmethod
    def _extract_path(data: dict[str, Any], path: str) -> Any:
        """从字典中按点分路径提取值，如 'output.result'。"""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
