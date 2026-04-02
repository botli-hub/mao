"""
意图路由器（Intent Router）
将用户自然语言输入路由到最合适的 Agent 或 Workflow。
支持 LLM 语义匹配 + 关键词快速路由两种模式。
"""
import json
import logging
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.config import get_settings
from mao.db.models.agent import MaoAgent
from mao.db.models.workflow import MaoWorkflow

logger = logging.getLogger(__name__)
settings = get_settings()


class RouterResult:
    """路由结果。"""
    def __init__(
        self,
        route_type: str,           # "AGENT" | "WORKFLOW" | "DIRECT_REPLY"
        target_id: str | None,     # agent_id 或 workflow_id
        target_name: str | None,
        confidence: float,
        reason: str,
    ) -> None:
        self.route_type = route_type
        self.target_id = target_id
        self.target_name = target_name
        self.confidence = confidence
        self.reason = reason


class IntentRouter:
    """
    意图路由器。
    路由策略：
    1. 快速路由：用户消息包含明确的 Agent/Workflow 名称时直接路由
    2. LLM 语义路由：调用 LLM 从候选列表中选择最合适的目标
    3. 兜底：无匹配时返回 DIRECT_REPLY（直接对话模式）
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def route(self, user_message: str) -> RouterResult:
        """
        对用户消息进行意图路由。
        :returns: RouterResult 路由结果
        """
        # 获取所有已发布的 Agent 和 Workflow
        agents = await self._get_published_agents()
        workflows = await self._get_published_workflows()

        if not agents and not workflows:
            return RouterResult(
                route_type="DIRECT_REPLY",
                target_id=None,
                target_name=None,
                confidence=1.0,
                reason="No published agents or workflows available",
            )

        # 构建候选列表
        candidates = []
        for agent in agents:
            candidates.append({
                "type": "AGENT",
                "id": agent.agent_id,
                "name": agent.name,
                "description": agent.description or "",
            })
        for wf in workflows:
            candidates.append({
                "type": "WORKFLOW",
                "id": wf.workflow_id,
                "name": wf.name,
                "description": wf.description or "",
            })

        # LLM 语义路由
        return await self._llm_route(user_message, candidates)

    async def _llm_route(
        self, user_message: str, candidates: list[dict[str, Any]]
    ) -> RouterResult:
        """使用 LLM 进行语义路由。"""
        candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
        prompt = f"""你是一个意图路由器。根据用户输入，从候选列表中选择最合适的处理器。

用户输入：{user_message}

候选处理器列表：
{candidates_json}

请以 JSON 格式返回路由结果：
{{
  "route_type": "AGENT" | "WORKFLOW" | "DIRECT_REPLY",
  "target_id": "处理器 ID（DIRECT_REPLY 时为 null）",
  "target_name": "处理器名称",
  "confidence": 0.0-1.0,
  "reason": "选择理由（一句话）"
}}

如果没有合适的处理器，返回 route_type="DIRECT_REPLY"。"""

        try:
            response = await self._llm.chat.completions.create(
                model=settings.openai_router_model,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content or "{}")
            return RouterResult(
                route_type=result.get("route_type", "DIRECT_REPLY"),
                target_id=result.get("target_id"),
                target_name=result.get("target_name"),
                confidence=float(result.get("confidence", 0.5)),
                reason=result.get("reason", ""),
            )
        except Exception as e:
            logger.error(f"Router LLM call failed: {e}")
            return RouterResult(
                route_type="DIRECT_REPLY",
                target_id=None,
                target_name=None,
                confidence=0.0,
                reason=f"Router failed: {e}",
            )

    async def _get_published_agents(self) -> list[MaoAgent]:
        """获取所有已发布（非草稿）且启用的 Agent。"""
        result = await self.db.execute(
            select(MaoAgent).where(
                MaoAgent.is_draft == False,  # noqa: E712
                MaoAgent.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def _get_published_workflows(self) -> list[MaoWorkflow]:
        """获取所有已发布且启用的 Workflow。"""
        result = await self.db.execute(
            select(MaoWorkflow).where(
                MaoWorkflow.is_draft == False,  # noqa: E712
                MaoWorkflow.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())
