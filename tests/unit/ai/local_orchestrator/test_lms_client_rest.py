from __future__ import annotations

from app.ai.local_orchestrator.lms_client_rest import _chat_message_text


def test_chat_message_text_uses_content_first():
    assert _chat_message_text({"content": "ok", "reasoning_content": "hidden"}) == "ok"


def test_chat_message_text_falls_back_to_reasoning_content():
    assert _chat_message_text({"content": "", "reasoning_content": '{"ok": true}'}) == '{"ok": true}'
