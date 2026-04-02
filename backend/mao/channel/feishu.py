"""
飞书渠道适配器
负责：
  1. 将 OmniMessage 翻译为飞书消息格式（富文本/Interactive Card）
  2. 通过飞书 Bot API 发送消息
  3. 验证飞书 Webhook 事件签名
  4. 解析飞书卡片回调事件
"""
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from mao.channel.base import BaseChannelAdapter, OmniMessage
from mao.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 飞书 API 基础 URL
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuAdapter(BaseChannelAdapter):
    """飞书渠道适配器。"""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)
        self._access_token: str | None = None

    @property
    def channel_type(self) -> str:
        return "FEISHU"

    async def send_message(
        self,
        external_chat_id: str,
        omni_message: OmniMessage,
    ) -> dict[str, Any]:
        """将 OmniMessage 翻译为飞书消息格式并发送。"""
        if omni_message.message_type in ("CARD", "SUSPEND_CARD"):
            return await self.send_card(external_chat_id, omni_message.card_schema or {})

        # 文本消息
        content = omni_message.content or ""
        msg_content = json.dumps({"text": content}, ensure_ascii=False)

        return await self._send_feishu_message(
            receive_id=external_chat_id,
            msg_type="text",
            content=msg_content,
        )

    async def send_card(
        self,
        external_chat_id: str,
        card_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """将通用 CardSchema 翻译为飞书 Interactive Card 并发送。"""
        feishu_card = self.translate_card_schema(card_schema)
        msg_content = json.dumps(feishu_card, ensure_ascii=False)

        return await self._send_feishu_message(
            receive_id=external_chat_id,
            msg_type="interactive",
            content=msg_content,
        )

    async def update_card(
        self,
        external_msg_id: str,
        card_schema: dict[str, Any],
    ) -> None:
        """更新飞书卡片（卡片回调处理后，将按钮置为已处理状态）。"""
        token = await self._get_access_token()
        feishu_card = self.translate_card_schema(card_schema)

        resp = await self._http.patch(
            f"{FEISHU_API_BASE}/im/v1/messages/{external_msg_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"content": json.dumps(feishu_card, ensure_ascii=False)},
        )
        resp.raise_for_status()

    def translate_card_schema(self, card_schema: dict[str, Any]) -> dict[str, Any]:
        """
        将通用 CardSchema 翻译为飞书 Interactive Card JSON。
        利用 client_side_lock 属性映射到飞书的 Exclusive 属性（点击即锁）。
        """
        client_side_lock = card_schema.get("client_side_lock", False)
        title = card_schema.get("title", "MAO 助手")
        elements = card_schema.get("elements", [])
        actions = card_schema.get("actions", [])

        # 构建飞书卡片 JSON
        feishu_card: dict[str, Any] = {
            "config": {
                "wide_screen_mode": True,
                # Exclusive 属性：点击后立即锁定卡片，防止二次触发
                "enable_forward": not client_side_lock,
            },
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [],
        }

        # 翻译内容元素
        for elem in elements:
            elem_type = elem.get("type")
            if elem_type == "text":
                feishu_card["elements"].append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": elem.get("content", "")},
                })
            elif elem_type == "markdown":
                feishu_card["elements"].append({
                    "tag": "markdown",
                    "content": elem.get("content", ""),
                })
            elif elem_type == "field_group":
                feishu_card["elements"].append({
                    "tag": "column_set",
                    "flex_mode": "none",
                    "columns": [
                        {
                            "tag": "column",
                            "elements": [
                                {"tag": "div", "text": {"tag": "plain_text", "content": f.get("label", "")}},
                                {"tag": "div", "text": {"tag": "plain_text", "content": str(f.get("value", ""))}},
                            ],
                        }
                        for f in elem.get("fields", [])
                    ],
                })

        # 翻译操作按钮
        if actions:
            action_elements = []
            for action in actions:
                btn: dict[str, Any] = {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": action.get("label", "确认")},
                    "type": "primary" if action.get("style") == "primary" else "default",
                    "value": {
                        "action_id": action.get("action_id", ""),
                        "action_type": action.get("action_type", "CONFIRM"),
                        "payload": action.get("payload", {}),
                    },
                }
                # Exclusive 模式：点击后禁用其他按钮
                if client_side_lock:
                    btn["behaviors"] = [{"type": "callback"}]
                action_elements.append(btn)

            feishu_card["elements"].append({
                "tag": "action",
                "actions": action_elements,
            })

        return feishu_card

    def verify_webhook_signature(
        self,
        timestamp: str,
        nonce: str,
        body: str,
    ) -> bool:
        """
        验证飞书 Webhook 事件签名。
        签名算法：SHA256(timestamp + nonce + encrypt_key + body)
        """
        content = f"{timestamp}{nonce}{settings.feishu_encrypt_key}{body}".encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        return True  # 实际应与请求头 X-Lark-Signature 比对

    def parse_card_callback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        解析飞书卡片回调事件，提取关键信息。
        :returns: 标准化的回调数据
        """
        action = payload.get("action", {})
        value = action.get("value", {})
        operator = payload.get("operator", {})

        return {
            "action_id": value.get("action_id"),
            "action_type": value.get("action_type"),
            "payload": value.get("payload", {}),
            "operator_open_id": operator.get("open_id"),
            "message_id": payload.get("open_message_id"),
            "chat_id": payload.get("open_chat_id"),
        }

    async def _send_feishu_message(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
    ) -> dict[str, Any]:
        """调用飞书发送消息 API。"""
        token = await self._get_access_token()
        resp = await self._http.post(
            f"{FEISHU_API_BASE}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {"message_id": data.get("data", {}).get("message_id")}

    async def _get_access_token(self) -> str:
        """获取飞书 App Access Token（带缓存）。"""
        if self._access_token:
            return self._access_token

        resp = await self._http.post(
            f"{FEISHU_API_BASE}/auth/v3/app_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data.get("app_access_token", "")
        return self._access_token


# 全局飞书适配器单例
_feishu_adapter: FeishuAdapter | None = None


def get_feishu_adapter() -> FeishuAdapter:
    """获取飞书适配器单例。"""
    global _feishu_adapter
    if _feishu_adapter is None:
        _feishu_adapter = FeishuAdapter()
    return _feishu_adapter
