"""
意图路由器（Intent Router）
将用户自然语言输入路由到最合适的 Agent 或 Workflow。
支持 LLM 语义匹配 + 关键词快速路由两种模式。
"""
import json
import logging
import math
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mao.core.config import get_settings
from mao.core.redis_client import semantic_cache_get, semantic_cache_put
from mao.db.models.agent import MaoAgent
from mao.db.models.workflow import MaoWorkflow

logger = logging.getLogger(__name__)
settings = get_settings()


class RouterResult:
    """路由结果。"""

    def __init__(
        self,
        route_type: str,  # "AGENT" | "WORKFLOW" | "DIRECT_REPLY" | "CLARIFICATION_REQUIRED"
        target_id: str | None,
        target_name: str | None,
        confidence: float,
        reason: str,
        clarification_candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.route_type = route_type
        self.target_id = target_id
        self.target_name = target_name
        self.confidence = confidence
        self.reason = reason
        self.clarification_candidates = clarification_candidates or []


class IntentRouter:
    """意图路由器。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def route(self, user_message: str) -> RouterResult:
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

        candidates = []
        for agent in agents:
            candidates.append(
                {
                    "type": "AGENT",
                    "id": agent.agent_id,
                    "name": agent.name,
                    "description": agent.description or "",
                }
            )
        for wf in workflows:
            candidates.append(
                {
                    "type": "WORKFLOW",
                    "id": wf.workflow_id,
                    "name": wf.name,
                    "description": wf.description or "",
                }
            )

        routed = await self._llm_route(user_message, candidates)
        if routed.route_type == "DIRECT_REPLY" and candidates:
            ranked = self._rank_candidates_by_keyword(user_message, candidates)
            if ranked and ranked[0]["score"] > 0:
                top = ranked[:3]
                near_tie = len(top) > 1 and abs(top[0]["score"] - top[1]["score"]) <= 1
                low_confidence = routed.confidence < 0.65
                if near_tie or low_confidence:
                    return RouterResult(
                        route_type="CLARIFICATION_REQUIRED",
                        target_id=None,
                        target_name=None,
                        confidence=0.5,
                        reason="Multiple candidates overlap; clarification required",
                        clarification_candidates=[item["candidate"] for item in top],
                    )
        return routed

    async def _llm_route(self, user_message: str, candidates: list[dict[str, Any]]) -> RouterResult:
        llm_result: dict[str, Any] | None = None
        if settings.engine_semantic_cache_enabled:
            cached = await self._semantic_cache_lookup(user_message)
            if cached:
                return cached

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
            llm_result = json.loads(response.choices[0].message.content or "{}")
            return RouterResult(
                route_type=llm_result.get("route_type", "DIRECT_REPLY"),
                target_id=llm_result.get("target_id"),
                target_name=llm_result.get("target_name"),
                confidence=float(llm_result.get("confidence", 0.5)),
                reason=llm_result.get("reason", ""),
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
        finally:
            if settings.engine_semantic_cache_enabled:
                await self._semantic_cache_store(user_message, llm_result)

    async def _get_published_agents(self) -> list[MaoAgent]:
        result = await self.db.execute(
            select(MaoAgent).where(
                MaoAgent.is_draft == False,  # noqa: E712
                MaoAgent.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def _get_published_workflows(self) -> list[MaoWorkflow]:
        result = await self.db.execute(
            select(MaoWorkflow).where(
                MaoWorkflow.is_draft == False,  # noqa: E712
                MaoWorkflow.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def _embed(self, text: str) -> list[float]:
        rsp = await self._llm.embeddings.create(model=settings.openai_embedding_model, input=text)
        return rsp.data[0].embedding

    async def _semantic_cache_lookup(self, user_message: str) -> RouterResult | None:
        try:
            target_embedding = await self._embed(user_message)
            cache_items = await semantic_cache_get(namespace="intent-router", limit=settings.engine_semantic_cache_top_k)
            best_item: dict[str, Any] | None = None
            best_score = -1.0
            for item in cache_items:
                emb = item.get("embedding") or []
                if not isinstance(emb, list):
                    continue
                score = self._cosine_similarity(target_embedding, emb)
                if score > best_score:
                    best_score = score
                    best_item = item
            if best_item and best_score >= settings.engine_semantic_cache_threshold:
                return RouterResult(
                    route_type=best_item.get("route_type", "DIRECT_REPLY"),
                    target_id=best_item.get("target_id"),
                    target_name=best_item.get("target_name"),
                    confidence=float(best_item.get("confidence", 0.8)),
                    reason=f"Semantic cache hit (score={best_score:.3f})",
                )
        except Exception as e:
            logger.warning(f"Semantic cache lookup skipped: {e}")
        return None

    async def _semantic_cache_store(self, user_message: str, route_result: dict[str, Any] | None) -> None:
        if not route_result:
            return
        try:
            embedding = await self._embed(user_message)
            await semantic_cache_put(
                namespace="intent-router",
                item={
                    "embedding": embedding,
                    "route_type": route_result.get("route_type", "DIRECT_REPLY"),
                    "target_id": route_result.get("target_id"),
                    "target_name": route_result.get("target_name"),
                    "confidence": float(route_result.get("confidence", 0.5)),
                },
                ttl_seconds=settings.engine_semantic_cache_ttl_seconds,
                max_items=settings.engine_semantic_cache_max_items,
            )
        except Exception as e:
            logger.warning(f"Semantic cache store skipped: {e}")

    def _rank_candidates_by_keyword(self, user_message: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keywords = {w.lower() for w in user_message.split() if w.strip()}
        ranked: list[dict[str, Any]] = []
        for c in candidates:
            text = f"{c.get('name', '')} {c.get('description', '')}".lower()
            score = sum(1 for k in keywords if k and k in text)
            ranked.append({"candidate": c, "score": score})
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return -1.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return -1.0
        return dot / (norm1 * norm2)
