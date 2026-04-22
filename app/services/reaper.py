from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import SessionLocal
from app.services.booking import reap_expired_reservations

logger = logging.getLogger(__name__)


async def _tick() -> None:
    async with SessionLocal() as session:
        try:
            count = await reap_expired_reservations(session)
            await session.commit()
            if count:
                logger.info("reaper released %d expired reservations", count)
        except Exception:
            await session.rollback()
            logger.exception("reaper tick failed")


def start_reaper(interval_seconds: int = 60) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_tick, trigger="interval", seconds=interval_seconds, id="reap-reservations")
    scheduler.start()
    return scheduler
