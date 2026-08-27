from dataclasses import dataclass
from enum import Enum, auto
from threading import Lock
from typing import Protocol
from uuid import UUID

from aeroeyes_monitoring_api.domain.attention_event import IngestedAttentionEvent


class EventAcceptanceStatus(Enum):
    CREATED = auto()
    ALREADY_PROCESSED = auto()
    CONFLICT = auto()


@dataclass(frozen=True, slots=True)
class EventAcceptance:
    status: EventAcceptanceStatus
    event: IngestedAttentionEvent


class EventRepository(Protocol):
    def resolve_existing(
        self,
        candidate: IngestedAttentionEvent,
    ) -> EventAcceptance | None: ...

    def accept(self, candidate: IngestedAttentionEvent) -> EventAcceptance: ...


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[UUID, IngestedAttentionEvent] = {}
        self._lock = Lock()

    def _resolve_existing_unlocked(
        self,
        candidate: IngestedAttentionEvent,
    ) -> EventAcceptance | None:
        existing = self._events.get(candidate.event_id)

        if existing is None:
            return None

        if (
            existing.session_id == candidate.session_id
            and existing.semantic_payload == candidate.semantic_payload
        ):
            return EventAcceptance(
                EventAcceptanceStatus.ALREADY_PROCESSED,
                existing,
            )

        return EventAcceptance(EventAcceptanceStatus.CONFLICT, existing)

    def resolve_existing(
        self,
        candidate: IngestedAttentionEvent,
    ) -> EventAcceptance | None:
        with self._lock:
            return self._resolve_existing_unlocked(candidate)

    def accept(self, candidate: IngestedAttentionEvent) -> EventAcceptance:
        with self._lock:
            existing = self._resolve_existing_unlocked(candidate)

            if existing is not None:
                return existing

            self._events[candidate.event_id] = candidate
            return EventAcceptance(EventAcceptanceStatus.CREATED, candidate)
