"""
技能执行器（Tool Executor）
负责根据 LLM 输出的 Action 调用对应技能，处理四种技能类型。
"""
import asyncio
import logging
import time
from typing import Any

import httpx

from mao.core.enums import SkillType
from mao.core.kafka_client import emit_action

logger = logging.getLogger(__name__)


class SkillExecutionError(Exception):
    """技能执行失败异常。"""
    pass


class SuspendSignal(Exception):
    """
    ASYNC 类型技能触发挂起信号。
    由 ReAct Runner 捕获后将任务置为 SUSPENDED 状态。
    """
    def __init__(self, callback_expect: str, ttl_seconds: int = 3600) -> None:
        self.callback_expect = callback_expect
        self.ttl_seconds = ttl_seconds
        super().__init__(f"Task suspended, waiting for: {callback_expect}")


class ViewSignal(Exception):
    """
    VIEW 类型技能触发卡片下发信号。
    由 ReAct Runner 捕获后将卡片 Schema 推送到 C 端。
    """
    def __init__(self, card_schema: dict[str, Any]) -> None:
        self.card_schema = card_schema
        super().__init__("View card emitted")


class SkillExecutor:
    """
    技能执行器：根据技能类型分发执行逻辑。
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def execute(
        self,
        task_id: str,
        step_seq: int,
        skill_def: dict[str, Any],
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行技能调用。
        :param task_id: 所属任务 ID（用于审计日志）
        :param step_seq: 当前步骤序号
        :param skill_def: 技能定义（来自技能注册中心）
        :param tool_input: LLM 生成的工具调用参数
        :returns: 工具调用结果
        :raises SuspendSignal: ASYNC 技能触发挂起
        :raises ViewSignal: VIEW 技能触发卡片下发
        :raises SkillExecutionError: 调用失败
        """
        skill_type = SkillType(skill_def.get("skill_type", "API"))
        tool_name = skill_def.get("name", "unknown")
        start_ts = time.monotonic()

        try:
            if skill_type == SkillType.API:
                result = await self._execute_api(skill_def, tool_input)
            elif skill_type == SkillType.VIEW:
                result = await self._execute_view(skill_def, tool_input)
            elif skill_type == SkillType.ASYNC:
                result = await self._execute_async(skill_def, tool_input)
            elif skill_type == SkillType.MACRO:
                result = await self._execute_macro(skill_def, tool_input)
            else:
                raise SkillExecutionError(f"Unknown skill type: {skill_type}")

            latency_ms = int((time.monotonic() - start_ts) * 1000)

            # Observer Log：异步发送 Action 审计事件
            asyncio.create_task(
                emit_action(task_id, step_seq, tool_name, tool_input, result, latency_ms)
            )

            return result

        except (SuspendSignal, ViewSignal):
            raise
        except Exception as e:
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            asyncio.create_task(
                emit_action(task_id, step_seq, tool_name, tool_input, {"error": str(e)}, latency_ms)
            )
            raise SkillExecutionError(f"Skill '{tool_name}' failed: {e}") from e

    async def _execute_api(
        self, skill_def: dict[str, Any], tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """执行同步 API 技能。"""
        endpoint = skill_def.get("endpoint", "")
        method = skill_def.get("http_method", "POST").upper()
        auth_config = skill_def.get("auth_config") or {}

        headers: dict[str, str] = {}
        if auth_config.get("type") == "API_KEY":
            headers[auth_config.get("header_name", "X-API-Key")] = auth_config.get("api_key", "")
        elif auth_config.get("type") == "BEARER":
            headers["Authorization"] = f"Bearer {auth_config.get('token', '')}"

        if method == "GET":
            resp = await self._http.get(endpoint, params=tool_input, headers=headers)
        else:
            resp = await self._http.request(method, endpoint, json=tool_input, headers=headers)

        resp.raise_for_status()
        return resp.json()

    async def _execute_view(
        self, skill_def: dict[str, Any], tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """
        执行 VIEW 技能：渲染卡片 Schema 并触发 ViewSignal。
        卡片 Schema 由 Jinja2 模板 + tool_input 渲染生成。
        """
        template = skill_def.get("card_schema_template") or {}
        # 简单变量替换（生产环境使用 Jinja2）
        card_schema = {**template, "payload": tool_input, "client_side_lock": True}
        raise ViewSignal(card_schema=card_schema)

    async def _execute_async(
        self, skill_def: dict[str, Any], tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """
        执行 ASYNC 技能：先调用 API 触发外部流程，再挂起等待回调。
        """
        # 先调用 API 触发外部流程
        await self._execute_api(skill_def, tool_input)

        # 获取挂起控制元数据
        mao_meta = skill_def.get("mao_control_meta") or {}
        callback_expect = mao_meta.get("callback_expect", "CALLBACK_RECEIVED")
        ttl_seconds = mao_meta.get("ttl_seconds", 3600)

        # 触发挂起信号
        raise SuspendSignal(callback_expect=callback_expect, ttl_seconds=ttl_seconds)

    async def _execute_macro(
        self, skill_def: dict[str, Any], tool_input: dict[str, Any]
    ) -> dict[str, Any]:
        """
        执行 MACRO 宏工具：移交 DAG 引擎。
        返回一个特殊标记，由 ReAct Runner 识别后移交 DAG Runner。
        """
        workflow_id = skill_def.get("workflow_id") or tool_input.get("workflow_id")
        if not workflow_id:
            raise SkillExecutionError("MACRO skill missing workflow_id")
        return {"__macro_handoff__": True, "workflow_id": workflow_id, "input": tool_input}
