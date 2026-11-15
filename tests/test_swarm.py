from tripathy_experiment.adapters import (
    FixtureResearchSearch,
    InMemorySharedMemory,
    LocalCandidateExecutor,
)
from tripathy_experiment.no_isosceles import Candidate
from tripathy_experiment.swarm import EvoHive, SwarmConfig


def test_swarm_uses_cross_agent_memory_and_records_sources() -> None:
    memory = InMemorySharedMemory()
    swarm = EvoHive(
        search=FixtureResearchSearch(),
        memory=memory,
        executor=LocalCandidateExecutor(),
    )
    initial = Candidate(points=(), agent_id="baseline", strategy="empty")
    config = SwarmConfig(
        grid_size=5,
        generations=1,
        agents=2,
        seed=7,
        target_score=999,
        backend="local",
        search_mode="fixture",
        memory_mode="local",
    )

    evidence = swarm.run(initial, config)

    assert evidence["trials"] == 2
    assert evidence["events"][1]["inherited_from_agent"] == "agent-1"
    assert evidence["events"][0]["research_sources"][0]["url"].startswith("https://github.com/")
    assert {entry.agent_id for entry in memory.entries} == {"agent-1", "agent-2"}
    assert evidence["best"]["score"] > 0
