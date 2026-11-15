from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .no_isosceles import Candidate, mutate, verify
from .ports import CandidateExecutor, MemoryEntry, ResearchSearch, SharedMemory

STRATEGIES = ("greedy_add", "ruin_one", "ruin_three", "symmetric_ruin")


@dataclass
class OperatorPolicy:
    weights: dict[str, float] = field(
        default_factory=lambda: {strategy: 1.0 for strategy in STRATEGIES}
    )

    def choose(self, hints: str, rng: random.Random) -> str:
        effective = self.weights.copy()
        lowered = hints.lower()
        if "symmetr" in lowered or "mirror" in lowered:
            effective["symmetric_ruin"] *= 2.0
        if "local search" in lowered or "ruin" in lowered:
            effective["ruin_three"] *= 1.5
        return rng.choices(list(effective), weights=list(effective.values()), k=1)[0]

    def learn(self, strategy: str, accepted: bool, valid: bool) -> None:
        if accepted:
            self.weights[strategy] = min(8.0, self.weights[strategy] * 1.8)
        elif valid:
            self.weights[strategy] = max(0.25, self.weights[strategy] * 0.95)
        else:
            self.weights[strategy] = max(0.25, self.weights[strategy] * 0.6)


@dataclass(frozen=True)
class SwarmConfig:
    grid_size: int
    generations: int
    agents: int
    seed: int
    target_score: int
    backend: str
    search_mode: str
    memory_mode: str


class EvoHive:
    def __init__(
        self,
        *,
        search: ResearchSearch,
        memory: SharedMemory,
        executor: CandidateExecutor,
    ) -> None:
        self._search = search
        self._memory = memory
        self._executor = executor

    def run(self, initial: Candidate, config: SwarmConfig) -> dict[str, Any]:
        started = time.monotonic()
        started_at = datetime.now(UTC).isoformat()
        run_id = str(uuid4())
        rng = random.Random(config.seed)
        incumbent = initial
        policy = OperatorPolicy()
        events: list[dict[str, Any]] = []
        provider_failures: list[dict[str, str]] = []
        stagnant_generations = 0

        for generation in range(config.generations):
            query = (
                f"AlphaEvolve problem 59 no isosceles triangles {config.grid_size}x"
                f"{config.grid_size} newest lower bound construction local search symmetry"
            )
            try:
                hits = self._search.search(query)
            except Exception as error:  # provider failure must not erase the run
                hits = []
                provider_failures.append(
                    {
                        "provider": config.search_mode,
                        "error": str(error),
                        "generation": str(generation),
                    }
                )
            hints = "\n".join(f"{hit.title}\n{hit.text}" for hit in hits)
            source_urls = tuple(hit.url for hit in hits)
            improved = False

            for agent_number in range(config.agents):
                agent_id = f"agent-{agent_number + 1}"
                inherited_from: str | None = None
                parent = incumbent
                try:
                    memories = self._memory.recall(
                        agent_id,
                        "Best verifier-valid construction and failed strategies from other agents",
                    )
                except Exception as error:
                    memories = []
                    provider_failures.append(
                        {"provider": config.memory_mode, "error": str(error), "agent": agent_id}
                    )
                for memory in memories:
                    if memory.valid and memory.candidate.score >= parent.score:
                        parent = memory.candidate
                        inherited_from = memory.agent_id
                        break

                strategy = policy.choose(hints, rng)
                child_points = mutate(parent.points, strategy, config.grid_size, rng)
                candidate = Candidate(
                    points=child_points,
                    agent_id=agent_id,
                    strategy=strategy,
                    parent_id=parent.candidate_id,
                    inherited_from_agent=inherited_from,
                    source_urls=source_urls,
                )

                try:
                    sandbox_result = self._executor.evaluate(candidate, config.grid_size)
                    executor_error: str | None = None
                except Exception as error:
                    sandbox_result = None
                    executor_error = str(error)
                    provider_failures.append(
                        {"provider": config.backend, "error": str(error), "agent": agent_id}
                    )

                trusted = verify(candidate.points, config.grid_size)
                sandbox_agrees = (
                    sandbox_result is not None
                    and sandbox_result.valid == trusted.valid
                    and sandbox_result.score == trusted.score
                )
                accepted = sandbox_agrees and trusted.valid and trusted.score > incumbent.score
                if accepted:
                    incumbent = candidate
                    improved = True
                policy.learn(strategy, accepted, trusted.valid and sandbox_agrees)

                memory_entry = MemoryEntry(
                    run_id=run_id,
                    agent_id=agent_id,
                    candidate=candidate,
                    valid=trusted.valid and sandbox_agrees,
                    accepted=accepted,
                    reason=trusted.reason if sandbox_agrees else "sandbox/verifier disagreement",
                )
                try:
                    self._memory.write(memory_entry)
                except Exception as error:
                    provider_failures.append(
                        {"provider": config.memory_mode, "error": str(error), "agent": agent_id}
                    )

                events.append(
                    {
                        "generation": generation,
                        "agent_id": agent_id,
                        "candidate": candidate.to_dict(),
                        "inherited_from_agent": inherited_from,
                        "research_sources": [asdict(hit) for hit in hits],
                        "sandbox": asdict(sandbox_result) if sandbox_result else None,
                        "executor_error": executor_error,
                        "trusted_verifier": trusted.to_dict(),
                        "sandbox_agrees": sandbox_agrees,
                        "accepted": accepted,
                        "policy_after_feedback": policy.weights.copy(),
                    }
                )

                if incumbent.score > config.target_score:
                    break

            stagnant_generations = 0 if improved else stagnant_generations + 1
            if incumbent.score > config.target_score or stagnant_generations >= 3:
                break

        return {
            "schema_version": 1,
            "run_id": run_id,
            "linear_issue": "TRI-18",
            "started_at": started_at,
            "completed_at": datetime.now(UTC).isoformat(),
            "latency_seconds": time.monotonic() - started,
            "config": asdict(config),
            "initial": initial.to_dict(),
            "best": incumbent.to_dict(),
            "beat_target": incumbent.score > config.target_score,
            "trials": len(events),
            "final_policy": policy.weights,
            "provider_failures": provider_failures,
            "events": events,
        }
