import json
import asyncio
from typing import Any, Dict, List
from .redis_client import redis_client
from utils.utils import logger, config

CLICK_QUEUE_KEY = 'click_queue'
USER_UPDATE_QUEUE_KEY = 'user_update_queue'


async def push_click_to_queue(game_id: int, user_id: int, click_time: str, timer_value: float, user_name: str, old_timer: float = None):
    client = await redis_client.get_client()
    if not client:
        logger.debug("Redis unavailable - push_click_to_queue fallback (no-op)")
        return None

    payload = {
        'game_id': str(game_id),
        'user_id': str(user_id),
        'click_time': str(click_time),
        'timer_value': str(timer_value),
        'user_name': str(user_name),
    }
    if old_timer is not None:
        payload['old_timer'] = str(old_timer)

    try:
        msg_id = await client.xadd(CLICK_QUEUE_KEY, payload)
        logger.debug(f"Pushed click to queue {msg_id} for game {game_id}")
        return msg_id
    except Exception as e:
        logger.error(f"Failed to push click to queue: {e}")
        return None


async def push_user_update(user_id: int, action: str, data: Dict[str, Any]):
    client = await redis_client.get_client()
    if not client:
        logger.debug("Redis unavailable - push_user_update fallback (no-op)")
        return None

    payload = {
        'user_id': str(user_id),
        'action': action,
        'data': json.dumps(data)
    }
    try:
        msg_id = await client.xadd(USER_UPDATE_QUEUE_KEY, payload)
        logger.debug(f"Pushed user update to queue {msg_id} for user {user_id}")
        return msg_id
    except Exception as e:
        logger.error(f"Failed to push user update to queue: {e}")
        return None
