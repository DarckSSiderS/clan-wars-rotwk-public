from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
import json
import logging
import time
from typing import Any

from fastapi import WebSocket
import redis as redis_sync
import redis.asyncio as redis_async
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.config import settings


logger = logging.getLogger(__name__)
_PENDING_EVENTS_KEY = "realtime_events"


class RealtimeHub:
    """WebSocket fan-out backed by Redis Pub/Sub when it is configured."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        channel: str | None = None,
    ) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._presence_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis_url = settings.REDIS_URL if redis_url is None else redis_url
        self._channel = channel or settings.REALTIME_REDIS_CHANNEL
        self._redis: redis_async.Redis | None = None
        self._sync_redis: redis_sync.Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._redis_ready: asyncio.Event | None = None
        self._redis_healthy = False

    @property
    def redis_enabled(self) -> bool:
        return bool(self._redis_url)

    @property
    def redis_status(self) -> str:
        return "up" if self._redis_healthy else "down"

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()
        if not self.redis_enabled:
            logger.info("Realtime transport: local process")
            return

        self._redis_ready = asyncio.Event()
        self._redis = redis_async.Redis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=None,
            health_check_interval=30,
        )
        self._listener_task = asyncio.create_task(
            self._listen_to_redis(),
            name="realtime-redis-listener",
        )
        try:
            await asyncio.wait_for(
                self._redis_ready.wait(),
                timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS + 1,
            )
        except asyncio.TimeoutError:
            logger.warning("Redis realtime subscriber is not ready yet")

    async def shutdown(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._sync_redis is not None:
            self._sync_redis.close()
            self._sync_redis = None
        if self._redis_ready is not None:
            self._redis_ready.clear()
            self._redis_ready = None
        self._redis_healthy = False
        self._loop = None

    async def connect(
        self,
        user_id: int,
        websocket: WebSocket,
        *,
        mark_presence: bool = True,
    ) -> None:
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        self._connections[int(user_id)].add(websocket)
        if mark_presence:
            self._presence_connections[int(user_id)].add(websocket)
            await self.mark_online(user_id)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(int(user_id))
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(int(user_id), None)
        presence_connections = self._presence_connections.get(int(user_id))
        if presence_connections:
            presence_connections.discard(websocket)
            if not presence_connections:
                self._presence_connections.pop(int(user_id), None)

    async def mark_online(self, user_id: int) -> None:
        """Refreshes the cross-worker presence heartbeat for one player."""
        if not self.redis_enabled or self._redis is None:
            return
        try:
            now = time.time()
            await self._redis.zadd(
                settings.PRESENCE_REDIS_KEY,
                {str(int(user_id)): now},
            )
            await self._redis.zremrangebyscore(
                settings.PRESENCE_REDIS_KEY,
                "-inf",
                now - (settings.PRESENCE_TTL_SECONDS * 4),
            )
        except Exception:
            logger.exception("Unable to refresh Redis presence heartbeat")

    def online_user_ids(self, user_ids: set[int]) -> set[int]:
        """Returns players with a fresh heartbeat, including local fallback."""
        normalized_ids = {int(user_id) for user_id in user_ids}
        online = normalized_ids.intersection(self._presence_connections)
        if not normalized_ids or not self.redis_enabled:
            return online

        try:
            redis_client = self._get_sync_redis()
            pipeline = redis_client.pipeline(transaction=False)
            for user_id in sorted(normalized_ids):
                pipeline.zscore(settings.PRESENCE_REDIS_KEY, str(user_id))
            scores = pipeline.execute()
            cutoff = time.time() - settings.PRESENCE_TTL_SECONDS
            for user_id, score in zip(sorted(normalized_ids), scores):
                if score is not None and float(score) >= cutoff:
                    online.add(user_id)
        except Exception:
            logger.exception("Unable to read Redis presence; using local connections")
        return online

    def acquire_cooldown(self, key: str, seconds: int) -> bool | None:
        """Acquires a short Redis-backed cooldown shared by all API workers."""
        if not self.redis_enabled:
            return None
        try:
            return bool(
                self._get_sync_redis().set(
                    key,
                    "1",
                    ex=int(seconds),
                    nx=True,
                )
            )
        except Exception:
            logger.exception("Unable to acquire Redis cooldown")
            return None

    def _get_sync_redis(self) -> redis_sync.Redis:
        if self._sync_redis is None:
            self._sync_redis = redis_sync.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                socket_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                health_check_interval=30,
            )
        return self._sync_redis

    def publish(self, user_ids: set[int], payload: dict[str, Any]) -> None:
        normalized_ids = {int(user_id) for user_id in user_ids}
        if not normalized_ids:
            return

        loop = self._loop
        if loop is not None and not loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(
                self._publish(normalized_ids, payload),
                loop,
            )
            future.add_done_callback(self._consume_delivery_error)
            return

        # The campaign worker has no asyncio application lifecycle. It still
        # publishes committed notification events into the shared Redis bus.
        if self.redis_enabled:
            try:
                self._get_sync_redis().publish(
                    self._channel,
                    self._serialize(normalized_ids, payload),
                )
            except Exception:
                logger.exception("Unable to publish realtime event from worker")

    async def _publish(
        self,
        user_ids: set[int],
        payload: dict[str, Any],
    ) -> None:
        if self.redis_enabled and self._redis is not None:
            try:
                await self._redis.publish(
                    self._channel,
                    self._serialize(user_ids, payload),
                )
                return
            except Exception:
                logger.exception("Redis realtime publish failed; using local fan-out")
        await self._broadcast(user_ids, payload)

    async def _listen_to_redis(self) -> None:
        retry_delay = 1.0
        while True:
            try:
                if self._redis is None:
                    return
                async with self._redis.pubsub() as pubsub:
                    await pubsub.subscribe(self._channel)
                    self._redis_healthy = True
                    if self._redis_ready is not None:
                        self._redis_ready.set()
                    retry_delay = 1.0
                    logger.info("Realtime transport: Redis channel %s", self._channel)
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        await self._deliver_serialized(message.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis realtime subscriber disconnected")
            finally:
                self._redis_healthy = False
                if self._redis_ready is not None:
                    self._redis_ready.clear()

            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 10.0)

    async def _deliver_serialized(self, serialized: Any) -> None:
        try:
            envelope = json.loads(serialized)
            user_ids = {int(user_id) for user_id in envelope["user_ids"]}
            payload = envelope["payload"]
            if not isinstance(payload, dict):
                raise TypeError("Realtime payload must be an object")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Discarded malformed Redis realtime event")
            return
        await self._broadcast(user_ids, payload)

    @staticmethod
    def _serialize(user_ids: set[int], payload: dict[str, Any]) -> str:
        return json.dumps(
            {
                "user_ids": sorted(user_ids),
                "payload": payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    async def _broadcast(
        self,
        user_ids: set[int],
        payload: dict[str, Any],
    ) -> None:
        for user_id in user_ids:
            for websocket in tuple(self._connections.get(user_id, ())):
                try:
                    await websocket.send_json(payload)
                except Exception:
                    self.disconnect(user_id, websocket)

    @staticmethod
    def _consume_delivery_error(future) -> None:
        try:
            future.result()
        except Exception:
            # Realtime delivery supplements committed database state. The UI
            # reconciles its counters again after focus/reconnect.
            logger.exception("Realtime delivery task failed")


realtime_hub = RealtimeHub()


def queue_realtime_event(
    db: Session,
    *,
    user_ids: set[int],
    payload: dict[str, Any],
) -> None:
    if not user_ids:
        return
    db.info.setdefault(_PENDING_EVENTS_KEY, []).append((set(user_ids), payload))


@event.listens_for(Session, "after_commit")
def _publish_committed_events(db: Session) -> None:
    for user_ids, payload in db.info.pop(_PENDING_EVENTS_KEY, []):
        realtime_hub.publish(user_ids, payload)


@event.listens_for(Session, "after_rollback")
def _discard_rolled_back_events(db: Session) -> None:
    db.info.pop(_PENDING_EVENTS_KEY, None)
