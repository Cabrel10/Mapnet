"""MapNet APPLICATION — Bus d'événements (Event-Driven).

Un bus in-memory simple, synchrone et thread-safe : les handlers s'abonnent à
un type d'événement et sont invoqués à sa publication. Découple les émetteurs
(domaine) des réactions (projections, sync, notifications).
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable, Dict, List

from ..domain.events import DomainEvent

Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Handler]] = defaultdict(list)
        self._log: List[DomainEvent] = []
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            self._subs[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            self._log.append(event)
            handlers = list(self._subs.get(event.event_type, []))
        for h in handlers:
            try:
                h(event)
            except Exception:
                # Un handler défaillant ne casse jamais le bus.
                pass

    def publish_many(self, events: List[DomainEvent]) -> None:
        for e in events:
            self.publish(e)

    @property
    def event_count(self) -> int:
        return len(self._log)

    def recent(self, n: int = 20) -> List[Dict]:
        with self._lock:
            return [e.to_dict() for e in self._log[-n:]]
