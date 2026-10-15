"""Task-local SQL transaction shared by repositories on the same engine.

Joining a transaction never commits it. Only its outer owner commits; failures,
including a failed flush, roll the entire mutation back. Do not spawn concurrent
tasks inside a unit of work: AsyncSession is deliberately task-confined.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_current: ContextVar[AsyncSession | None] = ContextVar("engine_unit_of_work", default=None)


class TransactionSessions:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    def current(self) -> AsyncSession | None:
        session = _current.get()
        if session is not None and session.bind is self.factory.kw.get("bind"):
            if session.info.get("uow_task") is not asyncio.current_task():
                raise RuntimeError("A unit of work cannot be shared across concurrent tasks")
            return session
        return None

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[AsyncSession]:
        session = self.current()
        if session is not None:
            yield session
        else:
            async with self.factory() as session:
                yield session

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        session = self.current()
        if session is not None:
            try:
                yield session
                await session.flush()
            except BaseException:
                session.info["uow_failed"] = True
                raise
            return
        async with self.factory.begin() as session:
            # SQLite has no row locks. Acquire its writer reservation before
            # reading mutable state, rather than upgrading a stale read snapshot.
            if session.get_bind().dialect.name == "sqlite":
                await session.execute(sa.text("BEGIN IMMEDIATE"))
            session.info["uow_task"] = asyncio.current_task()
            token = _current.set(session)
            try:
                yield session
                if session.info.get("uow_failed"):
                    raise RuntimeError("A joined mutation failed; unit of work must roll back")
                await session.flush()
            finally:
                _current.reset(token)
