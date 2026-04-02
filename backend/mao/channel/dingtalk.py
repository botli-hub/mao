"""钉钉渠道适配器。"""
import json
from typing import Any

import httpx

from mao.channel.base import BaseChannelAdapter, OmniMessage


class DingTalkAdapter(BaseChannelAdapter):
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)

    @property
    def channel_type(self) -> str:
        return "DINGTALK"

    async def send_message(self, external_chat_id: str, omni_message: OmniMessage) -> dict[str, Any]:
        if omni_message.message_type in ("CARD", "SUSPEND_CARD") and omni_message.card_schema:
            return await self.send_card(external_chat_id, omni_message.card_schema)
        webhook = omni_message.metadata.get("webhook_url")
        if not webhook:
            raise ValueError("DingTalk webhook_url missing in metadata")
        payload = {"msgtype": "text", "text": {"content": omni_message.content or ""}}
        resp = await self._http.post(str(webhook), json=payload)
        resp.raise_for_status()
        return {"ok": True}

    async def send_card(self, external_chat_id: str, card_schema: dict[str, Any]) -> dict[str, Any]:
        webhook = card_schema.get("webhook_url")
        if not webhook:
            raise ValueError("DingTalk card webhook_url missing")
        payload = {
            "msgtype": "actionCard",
            "actionCard": {
                "title": card_schema.get("title", "MAO 助手"),
                "text": json.dumps(card_schema, ensure_ascii=False),
                "singleTitle": "查看",
                "singleURL": card_schema.get("url", "https://example.com"),
            },
        }
        resp = await self._http.post(str(webhook), json=payload)
        resp.raise_for_status()
        return {"ok": True}

    async def update_card(self, external_msg_id: str, card_schema: dict[str, Any]) -> None:
        _ = external_msg_id
        _ = card_schema
        return None


_dingtalk_adapter: DingTalkAdapter | None = None


def get_dingtalk_adapter() -> DingTalkAdapter:
    global _dingtalk_adapter
    if _dingtalk_adapter is None:
        _dingtalk_adapter = DingTalkAdapter()
    return _dingtalk_adapter
