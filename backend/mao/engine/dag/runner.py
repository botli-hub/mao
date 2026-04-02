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


class DAGRunner:
    def __init__(
        self,
        task_id: str,
        session_id: str,
        dag_definition: dict[str, Any],
        node_executors: dict[str, Any],
    ) -> None:
        self.task_id = task_id
        self.session_id = session_id
        self.dag = dag_definition
        self.node_executors = node_executors

        self._nodes: dict[str, dict[str, Any]] = {n["id"]: n for n in dag_definition.get("nodes", [])}
        self._edges: list[dict[str, Any]] = dag_definition.get("edges", [])
        self._adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._in_degree: dict[str, int] = defaultdict(int)

        for edge in self._edges:
            self._adj[edge["from"]].append(edge)
            self._in_degree[edge["to"]] += 1

    async def execute(
        self,
        blackboard: Blackboard,
        resume_from_node_id: str | None = None,
        skip_nodes: set[str] | None = None,
    ) -> dict[str, Any]:
        skip_nodes = skip_nodes or set()
        queue: deque[str] = deque()
        in_degree = dict(self._in_degree)

        for node_id in self._nodes:
            if in_degree.get(node_id, 0) == 0:
                queue.append(node_id)

        if resume_from_node_id:
            if resume_from_node_id not in self._nodes:
                raise DAGExecutionError(f"Resume node not found: {resume_from_node_id}")
            queue = deque([resume_from_node_id])

        executed_nodes: set[str] = set()

        while queue:
            parallel_nodes = []
            while queue:
                node_id = queue.popleft()
                if node_id not in executed_nodes:
                    parallel_nodes.append(node_id)

            if not parallel_nodes:
                break

            results = await asyncio.gather(
                *[self._execute_node(node_id, blackboard, skip_nodes) for node_id in parallel_nodes],
                return_exceptions=True,
            )

            for node_id, result in zip(parallel_nodes, results):
                executed_nodes.add(node_id)

                if isinstance(result, Exception):
                    logger.error(f"[{self.task_id}] Node {node_id} failed: {result}")
                    return {
                        "status": TaskStatus.FAILED.value,
                        "failed_node_id": node_id,
                        "error": str(result),
                    }

                if isinstance(result, dict) and result.get("status") == TaskStatus.SUSPENDED.value:
                    await blackboard.save()
                    return result

                for edge in self._adj.get(node_id, []):
                    mappings = edge.get("mappings") or {}
                    if mappings and isinstance(result, dict):
                        for bb_key, output_path in mappings.items():
                            value = self._extract_path(result, output_path)
                            if value is not None:
                                blackboard.set(bb_key, value)

                    condition = edge.get("condition")
                    if condition is not None and not self._eval_condition(condition, blackboard):
                        continue

                    target_id = edge["to"]
                    in_degree[target_id] = in_degree.get(target_id, 1) - 1
                    if in_degree[target_id] <= 0:
                        queue.append(target_id)

            await blackboard.save()

        return {"status": TaskStatus.COMPLETED.value}

    async def _execute_node(self, node_id: str, blackboard: Blackboard, skip_nodes: set[str]) -> dict[str, Any]:
        node = self._nodes.get(node_id)
        if not node:
            raise DAGExecutionError(f"Node {node_id} not found in DAG")

        node_type = node.get("type", "UNKNOWN")
        if node_id in skip_nodes:
            await sse_push(
                self.session_id,
                {"event": "node_progress", "task_id": self.task_id, "node_id": node_id, "node_type": node_type, "status": "skipped"},
            )
            return {"status": "SKIPPED", "node_id": node_id}

        await sse_push(
            self.session_id,
            {"event": "node_progress", "task_id": self.task_id, "node_id": node_id, "node_type": node_type, "status": "running"},
        )

        executor = self.node_executors.get(node_type)
        if node_type in ("START", "END"):
            return {"status": "COMPLETED", "node_id": node_id}
        if not executor:
            raise DAGExecutionError(f"No executor for node type: {node_type}")
        return await executor(node, blackboard)

    def _eval_condition(self, condition: str, blackboard: Blackboard) -> bool:
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
        parts = path.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
