import asyncio
import json
from typing import List
from .redis_client import redis_client
from utils.utils import logger, config
from .redis_queues import CLICK_QUEUE_KEY
from database.database import execute_query


class SyncWorker:
    def __init__(self):
        self.redis = redis_client
        self.running = False
        self._task = None
        self.batch_size = config.get('cache', {}).get('click_queue_batch_size', 25)
        self.block_ms = int(config.get('cache', {}).get('sync_worker_block_ms', 500))

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._process_click_queue())
        logger.info("SyncWorker started")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SyncWorker stopped")

    async def _process_click_queue(self):
        while self.running:
            client = await self.redis.get_client()
            if not client:
                logger.debug("Redis not available - SyncWorker sleeping")
                await asyncio.sleep(1)
                continue

            try:
                # Read up to batch_size messages from the stream using XREAD
                # Using block in ms
                entries = await client.xread({CLICK_QUEUE_KEY: '0-0'}, count=self.batch_size, block=self.block_ms)
                if not entries:
                    await asyncio.sleep(0.05)
                    continue

                # entries structure: [(key, [(id, {field: value}), ...])]
                for stream_key, messages in entries:
                    # Collect click rows
                    for msg_id, fields in messages:
                        try:
                            game_id = int(fields.get('game_id'))
                            user_id = int(fields.get('user_id'))
                            click_time = fields.get('click_time')
                            timer_value = float(fields.get('timer_value'))
                            # Insert into DB (simple insert per message to keep logic safe)
                            query = "INSERT INTO button_clicks (game_id, user_id, click_time, timer_value) VALUES (%s, %s, %s, %s)"
                            execute_query(query, (game_id, user_id, click_time, timer_value), commit=True)

                            # After inserting, delete stream message
                            try:
                                await client.xdel(CLICK_QUEUE_KEY, msg_id)
                            except Exception as e:
                                logger.debug(f"Failed to xdel message {msg_id}: {e}")

                        except Exception as e:
                            logger.error(f"Error processing click message {msg_id}: {e}")
                            # Move on to next message
                            continue

            except Exception as e:
                logger.error(f"SyncWorker loop error: {e}")
                await asyncio.sleep(1)


# Single global worker instance
sync_worker = SyncWorker()
