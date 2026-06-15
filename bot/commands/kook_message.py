"""Small KOOK message helpers shared by button workflows."""
import json
import logging

from khl import api

log = logging.getLogger(__name__)


async def update_public_message(client, message_id: str | None, payload) -> bool:
    """Best-effort update for a previously sent public message/card."""
    if not message_id:
        return False
    content = json.dumps(payload, ensure_ascii=False) if isinstance(payload, list) else str(payload)
    try:
        await client.gate.exec_req(api.Message.update(msg_id=message_id, content=content))
        return True
    except Exception as exc:
        log.warning("更新 KOOK 消息失败 message=%s: %s", message_id, exc)
        return False
