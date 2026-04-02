"""企业微信渠道适配器。"""
from typing import Any

import httpx

from mao.channel.base import BaseChannelAdapter, OmniMessage


class WeComAdapter(BaseChannelAdapter):
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def channel_type(self) -> str:
        return "WECOM"

    async def send_message(self, external_chat_id: str, omni_message: OmniMessage) -> dict[str, Any]:
        _ = external_chat_id
        webhook = omni_message.metadata.get("webhook_url")
        if not webhook:
            raise ValueError("WeCom webhook_url missing in metadata")
        payload = {"msgtype": "text", "text": {"content": omni_message.content or ""}}
        resp = await self._http.post(str(webhook), json=payload)
        resp.raise_for_status()
        return {"ok": True}

    async def send_card(self, external_chat_id: str, card_schema: dict[str, Any]) -> dict[str, Any]:
        _ = external_chat_id
        webhook = card_schema.get("webhook_url")
        if not webhook:
            raise ValueError("WeCom card webhook_url missing")
        payload = {"msgtype": "markdown", "markdown": {"content": card_schema.get("content", "")}}
        resp = await self._http.post(str(webhook), json=payload)
        resp.raise_for_status()
        return {"ok": True}

    async def update_card(self, external_msg_id: str, card_schema: dict[str, Any]) -> None:
        _ = external_msg_id
        _ = card_schema
        return None


_wecom_adapter: WeComAdapter | None = None


def get_wecom_adapter() -> WeComAdapter:
    global _wecom_adapter
    if _wecom_adapter is None:
        _wecom_adapter = WeComAdapter()
    return _wecom_adapter
