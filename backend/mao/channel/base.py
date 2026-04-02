"""
渠道适配器基类与 OmniMessage 统一消息协议
所有渠道适配器必须继承 BaseChannelAdapter 并实现抽象方法。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OmniMessage:
    """
    统一消息协议。
    执行引擎输出标准 OmniMessage，由适配层根据 channel_type 翻译格式。
    """
    session_id: str
    message_type: str          # TEXT / CARD / TASK_SUMMARY / SYSTEM_NOTICE / STREAM_CHUNK
    content: str | None = None
    card_schema: dict[str, Any] | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChannelAdapter(ABC):
    """
    渠道适配器抽象基类。
    每个渠道（Web、飞书、钉钉等）实现一个具体适配器。
    """

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """渠道类型标识，如 'WEB' / 'FEISHU'。"""
        ...

    @abstractmethod
    async def send_message(
        self,
        external_chat_id: str,
        omni_message: OmniMessage,
    ) -> dict[str, Any]:
        """
        将 OmniMessage 翻译为渠道格式并发送。
        :returns: 渠道侧的消息 ID 等元数据
        """
        ...

    @abstractmethod
    async def send_card(
        self,
        external_chat_id: str,
        card_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """
        发送交互卡片。
        :returns: 渠道侧的消息 ID 等元数据
        """
        ...

    @abstractmethod
    async def update_card(
        self,
        external_msg_id: str,
        card_schema: dict[str, Any],
    ) -> None:
        """更新已发送的卡片（如将按钮置为已处理状态）。"""
        ...

    def translate_card_schema(self, card_schema: dict[str, Any]) -> dict[str, Any]:
        """
        将通用 CardSchema 翻译为渠道原生格式。
        子类可重写此方法实现渠道特定的卡片格式。
        """
        return card_schema
