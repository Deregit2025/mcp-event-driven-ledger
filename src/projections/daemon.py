"""
src/projections/daemon.py
==========================
ProjectionDaemon — polls the event store and updates projection tables.

Features:
  - Per-projection PostgreSQL advisory locks (prevents duplicate processing)
  - Per-projection checkpoints (independent resume after crash)
  - Fault-tolerant batch processing with retry
  - Projection lag measurement and SLO monitoring (500ms SLO)
  - Zero-downtime rebuild support

Usage:
    daemon = ProjectionDaemon(db_url)
    daemon.register(ApplicationSummaryProjection())
    daemon.register(AgentPerformanceLedgerProjection())
    daemon.register(ComplianceAuditViewProjection())
    await daemon.run_all()
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Protocol

import asyncpg

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 100        # poll every 100ms
BATCH_SIZE = 200              # events per batch
LAG_SLO_MS = 500             # 500ms SLO
MAX_RETRIES = 3               # retries per event on error
ADVISORY_LOCK_RETRY_S = 5.0  # wait between advisory lock attempts


# ── PROJECTION PROTOCOL ───────────────────────────────────────────────────────

class Projection(Protocol):
    """Interface every projection must implement."""

    @property
    def name(self) -> str:
        """Unique name — used as checkpoint key and advisory lock key."""
        ...

    async def handle(self, event: dict, conn: asyncpg.Connection) -> None:
        """Process one event and update the projection table."""
        ...


# ── DAEMON ────────────────────────────────────────────────────────────────────

class ProjectionDaemon:
    """
    Background worker that keeps projection tables up to date.

    Each projection runs in its own asyncio task with its own
    PostgreSQL advisory lock — guaranteeing exactly-once processing
    even when multiple application instances run simultaneously.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._projections: list[Projection] = []
        self._pool: asyncpg.Pool | None = None
        self._lag_ms: dict[str, float] = {}
        self._running = False

    def register(self, projection: Projection) -> None:
        self._projections.append(projection)

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self.db_url, min_size=2, max_size=10
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def run_all(self) -> None:
        """Start all projections concurrently."""
        if not self._pool:
            await self.connect()
        self._running = True
        tasks = [
            asyncio.create_task(self._run_projection(p))
            for p in self._projections
        ]
        await asyncio.gather(*tasks)

    def stop(self) -> None:
        self._running = False

    def get_lag(self, projection_name: str) -> float | None:
        """Current lag in milliseconds for a projection."""
        return self._lag_ms.get(projection_name)

    def get_health(self) -> dict:
        """Health status for all projections."""
        slo_breaches = [
            name for name, lag in self._lag_ms.items()
            if lag > LAG_SLO_MS
        ]
        return {
            "projections": {
                p.name: {
                    "lag_ms": self._lag_ms.get(p.name),
                    "slo_ok": (self._lag_ms.get(p.name) or 0) <= LAG_SLO_MS,
                }
                for p in self._projections
            },
            "slo_breaches": slo_breaches,
            "overall_healthy": len(slo_breaches) == 0,
        }

    # ── PER-PROJECTION RUNNER ─────────────────────────────────────────────────

    async def _run_projection(self, projection: Projection) -> None:
        """
        Run one projection with advisory lock for leader election.
        If another instance holds the lock, sleep and retry.
        """
        lock_key = self._advisory_lock_key(projection.name)

        while self._running:
            async with self._pool.acquire() as conn:
                try:
                    row = await conn.fetchrow(
                        "SELECT pg_try_advisory_lock($1) AS acquired",
                        lock_key,
                    )

                    if not row["acquired"]:
                        # Another instance is processing this projection
                        logger.debug(
                            f"[{projection.name}] advisory lock held by "
                            f"another instance — sleeping {ADVISORY_LOCK_RETRY_S}s"
                        )
                        await asyncio.sleep(ADVISORY_LOCK_RETRY_S)
                        continue

                    logger.info(f"[{projection.name}] acquired advisory lock")

                    try:
                        await self._process_forever(projection, conn)
                    finally:
                        await conn.execute(
                            "SELECT pg_advisory_unlock($1)", lock_key
                        )
                        logger.info(f"[{projection.name}] released advisory lock")

                except Exception as e:
                    logger.error(f"[{projection.name}] error: {e}")
                    await asyncio.sleep(ADVISORY_LOCK_RETRY_S)

    async def _process_forever(
        self,
        projection: Projection,
        conn: asyncpg.Connection,
    ) -> None:
        """Poll for new events and process them continuously."""
        while self._running:
            t_start = time.time()

            checkpoint = await self._load_checkpoint(conn, projection.name)
            rows = await conn.fetch(
                "SELECT event_id, stream_id, stream_position, global_position,"
                "       event_type, event_version, payload, metadata, recorded_at"
                " FROM events"
                " WHERE global_position > $1"
                " ORDER BY global_position ASC"
                " LIMIT $2",
                checkpoint,
                BATCH_SIZE,
            )

            if rows:
                for row in rows:
                    event = {
                        "event_id": str(row["event_id"]),
                        "stream_id": row["stream_id"],
                        "stream_position": row["stream_position"],
                        "global_position": row["global_position"],
                        "event_type": row["event_type"],
                        "event_version": row["event_version"],
                        "payload": dict(row["payload"]) if row["payload"] else {},
                        "metadata": dict(row["metadata"]) if row["metadata"] else {},
                        "recorded_at": row["recorded_at"],
                    }

                    for attempt in range(MAX_RETRIES):
                        try:
                            async with conn.transaction():
                                await projection.handle(event, conn)
                                await self._save_checkpoint(
                                    conn,
                                    projection.name,
                                    event["global_position"],
                                )
                            break
                        except Exception as e:
                            if attempt == MAX_RETRIES - 1:
                                logger.error(
                                    f"[{projection.name}] failed after "
                                    f"{MAX_RETRIES} attempts on event "
                                    f"{event['global_position']}: {e}"
                                )
                            else:
                                await asyncio.sleep(0.05 * (2 ** attempt))

                # Measure lag
                last_recorded_at = rows[-1]["recorded_at"]
                if last_recorded_at:
                    if last_recorded_at.tzinfo is None:
                        last_recorded_at = last_recorded_at.replace(
                            tzinfo=timezone.utc
                        )
                    lag = (
                        datetime.now(timezone.utc) - last_recorded_at
                    ).total_seconds() * 1000
                    self._lag_ms[projection.name] = lag
                    if lag > LAG_SLO_MS:
                        logger.warning(
                            f"[{projection.name}] SLO BREACH: lag={lag:.0f}ms "
                            f"(SLO={LAG_SLO_MS}ms)"
                        )

            t_elapsed = (time.time() - t_start) * 1000
            sleep_ms = max(0, POLL_INTERVAL_MS - t_elapsed)
            await asyncio.sleep(sleep_ms / 1000)

    # ── CHECKPOINT MANAGEMENT ─────────────────────────────────────────────────

    async def _load_checkpoint(
        self,
        conn: asyncpg.Connection,
        projection_name: str,
    ) -> int:
        row = await conn.fetchrow(
            "SELECT last_position FROM projection_checkpoints"
            " WHERE projection_name = $1",
            projection_name,
        )
        return row["last_position"] if row else 0

    async def _save_checkpoint(
        self,
        conn: asyncpg.Connection,
        projection_name: str,
        position: int,
    ) -> None:
        await conn.execute(
            "INSERT INTO projection_checkpoints (projection_name, last_position, updated_at)"
            " VALUES ($1, $2, NOW())"
            " ON CONFLICT (projection_name)"
            " DO UPDATE SET last_position = $2, updated_at = NOW()",
            projection_name,
            position,
        )

    async def rebuild_from_scratch(self, projection_name: str) -> None:
        """
        Reset checkpoint to 0 — daemon will replay all events on next run.
        The projection table must be cleared separately.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO projection_checkpoints (projection_name, last_position, updated_at)"
                " VALUES ($1, 0, NOW())"
                " ON CONFLICT (projection_name)"
                " DO UPDATE SET last_position = 0, updated_at = NOW()",
                projection_name,
            )
        logger.info(f"[{projection_name}] checkpoint reset to 0 — rebuild will start on next poll")

    # ── ADVISORY LOCK KEY ─────────────────────────────────────────────────────

    @staticmethod
    def _advisory_lock_key(projection_name: str) -> int:
        """Stable integer key derived from projection name."""
        return int(
            hashlib.md5(projection_name.encode()).hexdigest()[:8], 16
        ) % (2 ** 31)