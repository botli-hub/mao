"""
ReAct Runner — L4 智能执行引擎
实现 Thought → Action → Observation 推演循环。
核心特性：
  - 无状态：每步推演前从 Redis 恢复黑板，每步结束后写回 Redis
  - Token 熔断：连续失败 N 次或超过 Max_Steps 后强制中断
  - 内外部记忆隔离：Thought/Action/Observation 只写 mao_task_log，绝不写 mao_message
  - Observer Log：每步异步投入 Kafka 审计
"""
import asyncio
import logging
import random
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from mao.core.config import get_settings
from mao.core.enums import StepType, TaskStatus
from mao.core.kafka_client import emit_thought
from mao.core.redis_client import state_append_step
from mao.engine.react.blackboard import Blackboard
from mao.engine.react.skill_executor import (
    SkillExecutionError,
    SkillExecutor,
    SuspendSignal,
    ViewSignal,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class CircuitBreakerTripped(Exception):
    """熔断器触发异常：连续失败次数超过阈值。"""
    pass


class MaxStepsExceeded(Exception):
    """超过最大推演步数。"""
    pass


class ReActRunner:
    """
    ReAct 推演引擎。
    每个 Task 实例化一个 Runner，Runner 本身无状态（所有状态存于 Redis）。
    """

    def __init__(
        self,
        task_id: str,
        agent_config: dict[str, Any],
        skill_registry: dict[str, dict[str, Any]],
    ) -> None:
        self.task_id = task_id
        self.agent_config = agent_config
        self.skill_registry = skill_registry  # {skill_name: skill_def}

        model_cfg = agent_config.get("model_config_data") or {}
        self.model_candidates = self._build_model_candidates(model_cfg)
        self._active_model_idx = 0
        self.model = self.model_candidates[self._active_model_idx]
        self.temperature = model_cfg.get("temperature", 0.2)
        self.max_steps = model_cfg.get("max_steps", settings.engine_max_steps)

        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._executor = SkillExecutor()
        self._consecutive_failures = 0

    async def run(
        self,
        user_message: str,
        blackboard: Blackboard,
        step_offset: int = 0,
    ) -> dict[str, Any]:
        """
        执行 ReAct 推演循环。
        :param user_message: 用户输入的自然语言指令
        :param blackboard: 任务黑板（已从 Redis 加载）
        :param step_offset: 断点续传时的步骤偏移量
        :returns: 最终执行结果 {"status": "COMPLETED|SUSPENDED|CARD_EMITTED", ...}
        """
        system_prompt = self._build_system_prompt(blackboard)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        for step in range(step_offset + 1, step_offset + self.max_steps + 1):
            # ── Thought：调用 LLM 推演 ──────────────────────────────────────
            thought_start = time.monotonic()
            try:
                response = await self._call_llm_with_backoff(messages)
            except Exception as e:
                self._consecutive_failures += 1
                logger.error(f"[{self.task_id}] LLM call failed (step {step}): {e}")
                if self._should_switch_model(e):
                    switched = self._switch_to_next_model()
                    if switched:
                        logger.warning(
                            f"[{self.task_id}] Switched model from {switched['from']} to {switched['to']}"
                        )
                        continue
                if self._consecutive_failures >= settings.engine_circuit_breaker_threshold:
                    raise CircuitBreakerTripped(
                        f"Circuit breaker tripped after {self._consecutive_failures} consecutive failures"
                    )
                continue

            latency_ms = int((time.monotonic() - thought_start) * 1000)
            choice = response.choices[0]
            token_usage = {
                "prompt": response.usage.prompt_tokens if response.usage else 0,
                "completion": response.usage.completion_tokens if response.usage else 0,
                "total": response.usage.total_tokens if response.usage else 0,
            }

            # ── 记录 Thought 到 Redis StateDB ──────────────────────────────
            thought_content = choice.message.content or ""
            await self._record_step(
                step_seq=step,
                step_type=StepType.THOUGHT,
                content=thought_content,
                token_usage=token_usage,
                latency_ms=latency_ms,
                blackboard=blackboard,
            )

            # Observer Log：异步投入 Kafka
            asyncio.create_task(emit_thought(self.task_id, step, thought_content, token_usage))

            # ── 检查是否有工具调用 ──────────────────────────────────────────
            tool_calls = choice.message.tool_calls
            if not tool_calls:
                # 无工具调用 = Final Answer
                final_answer = thought_content
                await self._record_step(
                    step_seq=step,
                    step_type=StepType.FINAL_ANSWER,
                    content=final_answer,
                    token_usage={},
                    latency_ms=0,
                    blackboard=blackboard,
                )
                await blackboard.save()
                return {"status": TaskStatus.COMPLETED, "final_answer": final_answer}

            # ── Action：并行执行工具调用 ────────────────────────────────────
            messages.append(choice.message.model_dump(exclude_none=True))

            # 支持并行工具调用（LLM 输出多个 tool_call）
            action_tasks = []
            for tc in tool_calls:
                import json
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                skill_def = self.skill_registry.get(tool_name)
                if not skill_def:
                    logger.warning(f"[{self.task_id}] Unknown tool: {tool_name}")
                    continue

                action_tasks.append(
                    self._execute_single_action(step, tc.id, tool_name, tool_input, skill_def, blackboard)
                )

            # 并行执行所有工具调用
            results = await asyncio.gather(*action_tasks, return_exceptions=True)

            # 处理执行结果
            for tc, result in zip(tool_calls, results):
                if isinstance(result, SuspendSignal):
                    await blackboard.save()
                    return {
                        "status": TaskStatus.SUSPENDED,
                        "callback_expect": result.callback_expect,
                        "ttl_seconds": result.ttl_seconds,
                    }
                elif isinstance(result, ViewSignal):
                    await blackboard.save()
                    return {
                        "status": "CARD_EMITTED",
                        "card_schema": result.card_schema,
                    }
                elif isinstance(result, Exception):
                    self._consecutive_failures += 1
                    observation = f"ERROR: {result}"
                    if self._consecutive_failures >= settings.engine_circuit_breaker_threshold:
                        raise CircuitBreakerTripped(str(result))
                else:
                    self._consecutive_failures = 0
                    observation = str(result)

                # 将 Observation 加入消息历史（供下一步 LLM 推演）
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation if isinstance(observation, str) else str(result),
                })

        raise MaxStepsExceeded(f"Exceeded max steps: {self.max_steps}")

    async def _execute_single_action(
        self,
        step: int,
        tool_call_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
        skill_def: dict[str, Any],
        blackboard: Blackboard,
    ) -> Any:
        """执行单个工具调用，记录 Action 和 Observation 到 StateDB。"""
        await self._record_step(
            step_seq=step,
            step_type=StepType.ACTION,
            content=f"Calling {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
            token_usage={},
            latency_ms=0,
            blackboard=blackboard,
        )

        try:
            result = await self._executor.execute(
                task_id=self.task_id,
                step_seq=step,
                skill_def=skill_def,
                tool_input=tool_input,
            )

            # 处理宏工具移交
            if isinstance(result, dict) and result.get("__macro_handoff__"):
                return result

            # 将工具输出写入黑板（如有 output_mapping 配置）
            output_mapping = skill_def.get("output_mapping") or {}
            if output_mapping:
                blackboard.update({k: result.get(v) for k, v in output_mapping.items()})

            await self._record_step(
                step_seq=step,
                step_type=StepType.OBSERVATION,
                content=str(result),
                tool_name=tool_name,
                tool_output=result,
                token_usage={},
                latency_ms=0,
                blackboard=blackboard,
            )
            return result

        except (SuspendSignal, ViewSignal):
            raise
        except SkillExecutionError as e:
            await self._record_step(
                step_seq=step,
                step_type=StepType.OBSERVATION,
                content=f"ERROR: {e}",
                tool_name=tool_name,
                token_usage={},
                latency_ms=0,
                blackboard=blackboard,
            )
            raise

    async def _record_step(
        self,
        step_seq: int,
        step_type: StepType,
        content: str,
        token_usage: dict[str, Any],
        latency_ms: int,
        blackboard: Blackboard,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_output: dict[str, Any] | None = None,
    ) -> None:
        """将推演步骤追加到 Redis StateDB（Append-only）。"""
        step_data: dict[str, Any] = {
            "step_seq": step_seq,
            "step_type": step_type.value,
            "content": content,
            "token_usage": token_usage,
            "latency_ms": latency_ms,
            "state_digest": {
                "blackboard_snapshot": blackboard.snapshot(),
                "execution_version": self.agent_config.get("published_version"),
                "token_usage": token_usage,
            },
        }
        if tool_name:
            step_data["tool_name"] = tool_name
        if tool_input:
            step_data["tool_input"] = tool_input
        if tool_output:
            step_data["tool_output"] = tool_output

        await state_append_step(self.task_id, step_data)

    def _build_system_prompt(self, blackboard: Blackboard) -> str:
        """构建系统提示词，注入黑板上下文。"""
        base_prompt = self.agent_config.get("system_prompt") or "You are a helpful assistant."
        bb_context = blackboard.snapshot()
        if bb_context:
            import json
            context_str = json.dumps(bb_context, ensure_ascii=False, indent=2)
            return f"{base_prompt}\n\n## 当前执行上下文（黑板）\n```json\n{context_str}\n```"
        return base_prompt

    def _build_tool_specs(self) -> list[dict[str, Any]]:
        """将技能注册表转换为 OpenAI Function Calling 格式的工具规范。"""
        tools = []
        for skill_name, skill_def in self.skill_registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": skill_name,
                    "description": skill_def.get("description", ""),
                    "parameters": skill_def.get("input_schema") or {"type": "object", "properties": {}},
                },
            })
        return tools

    def _build_model_candidates(self, model_cfg: dict[str, Any]) -> list[str]:
        """
        构建可切换模型列表。
        支持 model_config_data:
          - model: 主模型
          - model_fallbacks: 备选模型列表
          - model_candidates: 全量模型列表（优先级最高）
        """
        primary = model_cfg.get("model", settings.openai_default_model)
        from_candidates = model_cfg.get("model_candidates") or []
        from_fallbacks = model_cfg.get("model_fallbacks") or []

        merged = [*from_candidates] if from_candidates else [primary, *from_fallbacks]
        candidates: list[str] = []
        for model in merged:
            if isinstance(model, str) and model and model not in candidates:
                candidates.append(model)
        if not candidates:
            candidates = [settings.openai_default_model]
        return candidates

    def _switch_to_next_model(self) -> dict[str, str] | None:
        """切换到下一个可用模型。若已经是最后一个模型，返回 None。"""
        if self._active_model_idx >= len(self.model_candidates) - 1:
            return None
        from_model = self.model
        self._active_model_idx += 1
        self.model = self.model_candidates[self._active_model_idx]
        self._consecutive_failures = 0
        return {"from": from_model, "to": self.model}

    def _should_switch_model(self, err: Exception) -> bool:
        """仅在可恢复的上游错误时切换模型，避免业务逻辑错误触发抖动。"""
        if len(self.model_candidates) <= 1:
            return False
        if isinstance(err, RateLimitError):
            return True
        transient_error_markers = (
            "timeout",
            "temporarily unavailable",
            "overloaded",
            "server error",
            "service unavailable",
        )
        err_text = str(err).lower()
        return any(marker in err_text for marker in transient_error_markers)

    async def _call_llm_with_backoff(self, messages: list[dict[str, Any]]) -> Any:
        """
        使用指数退避重试调用 LLM。
        仅对可恢复错误重试（RateLimit/Timeout/Connection）。
        """
        last_error: Exception | None = None
        max_attempts = max(1, settings.engine_llm_retry_attempts)

        for attempt in range(1, max_attempts + 1):
            try:
                return await self._llm.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=messages,
                    tools=self._build_tool_specs(),
                    tool_choice="auto",
                )
            except Exception as err:
                last_error = err
                if attempt >= max_attempts or not self._is_retryable_llm_error(err):
                    raise
                delay = self._calculate_backoff_delay(attempt)
                logger.warning(
                    f"[{self.task_id}] LLM transient error on model {self.model}, "
                    f"retry {attempt}/{max_attempts} in {delay:.2f}s: {err}"
                )
                await asyncio.sleep(delay)

        raise last_error or RuntimeError("LLM call failed without specific error")

    def _is_retryable_llm_error(self, err: Exception) -> bool:
        """判断错误是否适合指数退避重试。"""
        if isinstance(err, (RateLimitError, APITimeoutError, APIConnectionError)):
            return True
        transient_error_markers = ("timeout", "temporarily unavailable", "overloaded")
        text = str(err).lower()
        return any(marker in text for marker in transient_error_markers)

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """指数退避 + 抖动。"""
        base = max(0.1, settings.engine_llm_retry_base_delay_seconds)
        expo = base * (2 ** (attempt - 1))
        jitter = random.uniform(0, base)
        return min(10.0, expo + jitter)
