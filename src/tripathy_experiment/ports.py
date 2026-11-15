from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .no_isosceles import Candidate


@dataclass(frozen=True)
class ResearchHit:
    title: str
    url: str
    text: str


@dataclass(frozen=True)
class MemoryEntry:
    run_id: str
    agent_id: str
    candidate: Candidate
    valid: bool
    accepted: bool
    reason: str


@dataclass(frozen=True)
class SandboxResult:
    valid: bool
    score: int
    reason: str
    backend: str
    latency_seconds: float


class ResearchSearch(Protocol):
    def search(self, query: str) -> list[ResearchHit]: ...


class SharedMemory(Protocol):
    def recall(self, reader: str, query: str) -> list[MemoryEntry]: ...

    def write(self, entry: MemoryEntry) -> None: ...


class CandidateExecutor(Protocol):
    def evaluate(self, candidate: Candidate, grid_size: int) -> SandboxResult: ...
