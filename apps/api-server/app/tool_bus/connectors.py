"""Enterprise connector adapters. Implements: REQ-006."""

from typing import Any, ClassVar

import httpx

from app.core.config import settings
from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolSpec, register_tool_adapter
from app.tool_bus.http_pool import get_http_client


class _HttpConnector(BaseToolAdapter):
    base_url_setting: ClassVar[str]
    routes: ClassVar[dict[str, tuple[str, str]]]
    _specs: ClassVar[list[ToolSpec]] = []

    def list_tools(self) -> list[ToolSpec]:
        return list(self._specs)

    async def health_check(self) -> bool:
        try:
            response = await get_http_client().get(self._base_url())
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        method, path = self.routes[tool_name]
        headers = {}
        if context.access_token:
            headers["Authorization"] = f"Bearer {context.access_token}"
        response = await get_http_client().request(
            method,
            f"{self._base_url()}{path}",
            json=arguments,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            return body
        return {"result": body}

    def _base_url(self) -> str:
        return str(getattr(settings, self.base_url_setting)).rstrip("/")


def _spec(code: str, name: str, description: str, tier: str) -> ToolSpec:
    return ToolSpec(code=code, name=name, description=description, action_tier=tier, input_json_schema={"type": "object"})


@register_tool_adapter
class Office365Adapter(_HttpConnector):
    namespace = "o365"
    provider = "MICROSOFT_365"
    base_url_setting = "O365_BASE_URL"
    _specs = [
        _spec("o365_search_messages", "搜尋郵件", "搜尋 Outlook 信件", "READ"),
        _spec("o365_create_draft", "建立草稿", "建立尚未寄出的郵件草稿", "DRAFT"),
        _spec("o365_send_mail", "寄出郵件", "代表使用者寄出郵件", "COMMIT"),
        _spec("o365_find_meeting_times", "尋找會議空檔", "查詢行事曆空檔", "READ"),
        _spec("o365_create_event", "建立會議", "在行事曆建立會議", "COMMIT"),
        _spec("onedrive_read_file", "讀取 OneDrive 檔案", "讀取 OneDrive 檔案內容", "READ"),
    ]
    routes = {
        "o365_search_messages": ("GET", "/me/messages"),
        "o365_create_draft": ("POST", "/me/messages"),
        "o365_send_mail": ("POST", "/me/sendMail"),
        "o365_find_meeting_times": ("POST", "/me/findMeetingTimes"),
        "o365_create_event": ("POST", "/me/events"),
        "onedrive_read_file": ("GET", "/me/drive/root/children"),
    }


@register_tool_adapter
class TeamsAdapter(_HttpConnector):
    namespace = "teams"
    provider = "MICROSOFT_365"
    base_url_setting = "O365_BASE_URL"
    _specs = [
        _spec("teams_read_channel_thread", "讀取頻道討論", "讀取 Teams 頻道訊息", "READ"),
        _spec("teams_send_message", "傳送 Teams 訊息", "在 Teams 頻道送出訊息", "COMMIT"),
        _spec("teams_send_approval_card", "送出核准卡片", "送出 Adaptive Approval Card", "COMMIT"),
    ]
    routes = {
        "teams_read_channel_thread": ("GET", "/teams/channel/messages"),
        "teams_send_message": ("POST", "/teams/channel/messages"),
        "teams_send_approval_card": ("POST", "/teams/channel/approval-cards"),
    }


@register_tool_adapter
class SlackAdapter(_HttpConnector):
    namespace = "slack"
    provider = "SLACK"
    base_url_setting = "SLACK_BASE_URL"
    _specs = [
        _spec("slack_search_messages", "搜尋 Slack", "搜尋 Slack 訊息", "READ"),
        _spec("slack_post_message", "張貼 Slack 訊息", "在 Slack 頻道張貼訊息", "COMMIT"),
    ]
    routes = {
        "slack_search_messages": ("POST", "/search.messages"),
        "slack_post_message": ("POST", "/chat.postMessage"),
    }


@register_tool_adapter
class MailGatewayAdapter(_HttpConnector):
    namespace = "mail"
    provider = "GENERIC_IMAP"
    base_url_setting = "MAIL_GATEWAY_BASE_URL"
    _specs = [
        _spec("imap_search_unread", "搜尋未讀信", "透過 IMAP 搜尋未讀郵件", "READ"),
        _spec("smtp_send_email", "寄出 SMTP 郵件", "透過 SMTP 寄出郵件", "COMMIT"),
    ]
    routes = {
        "imap_search_unread": ("POST", "/imap/search"),
        "smtp_send_email": ("POST", "/smtp/send"),
    }
