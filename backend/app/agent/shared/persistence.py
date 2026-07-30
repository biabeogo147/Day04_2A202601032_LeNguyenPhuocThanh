from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func, select, update
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.schemas import RunRead, SessionRead, TraceEventRead


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version_id: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    chat_model: Mapped[str] = mapped_column(String(80))
    embedding_provider: Mapped[str] = mapped_column(String(32))
    embedding_model: Mapped[str] = mapped_column(String(80))
    dataset_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    user_message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    query: Mapped[str] = mapped_column(Text)
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TraceEventRecord(Base):
    __tablename__ = "trace_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Database:
    def __init__(self, url: str) -> None:
        self.engine = create_async_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def interrupt_unfinished_runs(self) -> int:
        async with self.sessions() as session:
            result = await session.execute(
                update(RunRecord)
                .where(RunRecord.status.in_(("queued", "running")))
                .values(status="interrupted", error_code="backend_restarted", updated_at=utcnow())
            )
            await session.commit()
        return int(result.rowcount or 0)

    async def create_session(
        self,
        *,
        context: dict[str, Any] | None = None,
        version_id: str,
        provider: str,
        chat_model: str,
        embedding_provider: str,
        embedding_model: str,
        dataset_fingerprint: str,
    ) -> SessionRead:
        record = SessionRecord(
            id=str(uuid.uuid4()),
            context=dict(context or {}),
            version_id=version_id,
            provider=provider,
            chat_model=chat_model,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            dataset_fingerprint=dataset_fingerprint,
        )
        async with self.sessions() as session:
            session.add(record)
            await session.commit()
        return SessionRead.model_validate(record)

    async def update_session_context(
        self,
        session_id: str,
        patch: dict[str, Any],
    ) -> SessionRead:
        async with self.sessions() as session:
            record = await session.get(SessionRecord, session_id)
            if record is None:
                raise KeyError(session_id)
            record.context = {**(record.context or {}), **patch}
            record.updated_at = utcnow()
            await session.commit()
        return SessionRead.model_validate(record)

    async def get_session(self, session_id: str) -> SessionRead | None:
        async with self.sessions() as session:
            record = await session.get(SessionRecord, session_id)
        return SessionRead.model_validate(record) if record else None

    async def list_sessions(self) -> list[SessionRead]:
        statement = select(SessionRecord).order_by(SessionRecord.created_at)
        async with self.sessions() as session:
            records = (await session.scalars(statement)).all()
        return [SessionRead.model_validate(record) for record in records]

    async def create_run(self, session_id: str, query: str) -> RunRead:
        message = MessageRecord(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="user",
            content=query,
        )
        record = RunRecord(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_message_id=message.id,
            query=query,
            status="queued",
        )
        async with self.sessions() as session:
            session.add_all([message, record])
            await session.commit()
        return RunRead.model_validate(record)

    async def get_run(self, run_id: str) -> RunRead | None:
        async with self.sessions() as session:
            record = await session.get(RunRecord, run_id)
        return RunRead.model_validate(record) if record else None

    async def update_run(
        self,
        run_id: str,
        *,
        status: str,
        answer: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> RunRead:
        async with self.sessions() as session:
            record = await session.get(RunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            record.status = status
            record.answer = answer
            record.error_code = error_code
            record.updated_at = utcnow()
            await session.commit()
        return RunRead.model_validate(record)

    async def append_trace(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> TraceEventRead:
        async with self.sessions() as session:
            maximum = await session.scalar(
                select(func.max(TraceEventRecord.sequence)).where(TraceEventRecord.run_id == run_id)
            )
            record = TraceEventRecord(
                run_id=run_id,
                sequence=int(maximum or 0) + 1,
                type=event_type,
                payload=payload,
            )
            session.add(record)
            await session.commit()
        return TraceEventRead.model_validate(record, from_attributes=True)

    async def list_trace(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[TraceEventRead]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(TraceEventRecord)
                    .where(
                        TraceEventRecord.run_id == run_id,
                        TraceEventRecord.sequence > after_sequence,
                    )
                    .order_by(TraceEventRecord.sequence)
                )
            ).all()
        return [TraceEventRead.model_validate(record, from_attributes=True) for record in records]
