from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from .no_isosceles import Candidate, verify
from .ports import MemoryEntry, ResearchHit, SandboxResult


class FixtureResearchSearch:
    """Offline research feed with the same boundary as Exa."""

    def search(self, query: str) -> list[ResearchHit]:
        del query
        return [
            ResearchHit(
                title="Public 58-point certificate uses mirror symmetry and exact checks",
                url="https://github.com/google-deepmind/alphaevolve_repository_of_problems/issues/10",
                text="mirror symmetry local search exact-integer verifier",
            )
        ]


class ExaResearchSearch:
    def __init__(self, api_key: str | None = None, timeout_seconds: float = 15) -> None:
        self._api_key = api_key or os.environ.get("EXA_API_KEY", "")
        if not self._api_key:
            raise ValueError("EXA_API_KEY is required for --search exa")
        self._timeout_seconds = timeout_seconds

    def search(self, query: str) -> list[ResearchHit]:
        request = urllib.request.Request(
            "https://api.exa.ai/search",
            data=json.dumps(
                {
                    "query": query,
                    "type": "auto",
                    "numResults": 5,
                    "contents": {"highlights": True},
                }
            ).encode("utf-8"),
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        payload = _read_json(request, self._timeout_seconds)
        return [
            ResearchHit(
                title=str(item.get("title", "untitled")),
                url=str(item.get("url", "")),
                text="\n".join(str(value) for value in item.get("highlights", [])),
            )
            for item in payload.get("results", [])
            if item.get("url")
        ]


class InMemorySharedMemory:
    def __init__(self) -> None:
        self.entries: list[MemoryEntry] = []

    def recall(self, reader: str, query: str) -> list[MemoryEntry]:
        del query
        return sorted(
            (entry for entry in self.entries if entry.agent_id != reader),
            key=lambda entry: (entry.valid, entry.candidate.score),
            reverse=True,
        )

    def write(self, entry: MemoryEntry) -> None:
        self.entries.append(entry)


class PastSharedMemory:
    """Small past.dev adapter; local artifacts remain the source of truth."""

    _base_url = "https://api.past.dev/api/v1"

    def __init__(self, api_key: str | None = None, timeout_seconds: float = 15) -> None:
        self._api_key = api_key or os.environ.get("PAST_API_KEY", "")
        if not self._api_key:
            raise ValueError("PAST_API_KEY is required for --memory past")
        self._timeout_seconds = timeout_seconds

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def recall(self, reader: str, query: str) -> list[MemoryEntry]:
        payload = self._post("/recall", {"query": query, "identity": reader, "level": "medium"})
        entries: list[MemoryEntry] = []
        for result in payload.get("results", []):
            content = result.get("content", "")
            try:
                item = json.loads(content)
                candidate_payload = item["candidate"]
                points = tuple((int(x), int(y)) for x, y in candidate_payload["points"])
                candidate = Candidate(
                    points=points,
                    agent_id=str(candidate_payload["agent_id"]),
                    strategy=str(candidate_payload["strategy"]),
                    parent_id=candidate_payload.get("parent_id"),
                    inherited_from_agent=candidate_payload.get("inherited_from_agent"),
                    source_urls=tuple(candidate_payload.get("source_urls", [])),
                )
                entries.append(
                    MemoryEntry(
                        run_id=str(item["run_id"]),
                        agent_id=str(item["agent_id"]),
                        candidate=candidate,
                        valid=bool(item["valid"]),
                        accepted=bool(item["accepted"]),
                        reason=str(item["reason"]),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return entries

    def write(self, entry: MemoryEntry) -> None:
        source_id = f"evohive-{entry.run_id}-{entry.agent_id}-{entry.candidate.candidate_id}"
        payload = self._post(
            "/ingest",
            {
                "id": source_id,
                "label": f"EvoHive trial by {entry.agent_id}",
                "timestamp": datetime.now(UTC).isoformat(),
                "content": json.dumps(
                    {
                        **asdict(entry),
                        "candidate": entry.candidate.to_dict(),
                    },
                    sort_keys=True,
                ),
            },
        )
        ingestion_id = payload.get("ingestionId")
        if not ingestion_id:
            return
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = self._get(f"/ingest/{ingestion_id}")
            if status.get("status") in {"completed", "failed"}:
                return
            time.sleep(1)

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        request = urllib.request.Request(
            self._base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers,
            method="POST",
        )
        return _read_json(request, self._timeout_seconds)

    def _get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(self._base_url + path, headers=self._headers)
        return _read_json(request, self._timeout_seconds)


class LocalCandidateExecutor:
    def evaluate(self, candidate: Candidate, grid_size: int) -> SandboxResult:
        started = time.monotonic()
        result = verify(candidate.points, grid_size)
        return SandboxResult(
            valid=result.valid,
            score=result.score,
            reason=result.reason,
            backend="local",
            latency_seconds=time.monotonic() - started,
        )


class ModalCandidateExecutor:
    """Evaluate one candidate in a disposable, network-blocked Modal Sandbox."""

    def __init__(self, app_name: str | None = None) -> None:
        self._app_name = app_name or os.environ.get("EVOHIVE_MODAL_APP", "evohive-track1")

    def evaluate(self, candidate: Candidate, grid_size: int) -> SandboxResult:
        try:
            import modal
        except ImportError as error:  # pragma: no cover - exercised only in live mode
            raise RuntimeError("Install the modal optional dependency") from error

        started = time.monotonic()
        app = modal.App.lookup(self._app_name, create_if_missing=True)
        image = modal.Image.debian_slim(python_version="3.12")
        sandbox = modal.Sandbox.create(
            "sleep",
            "30",
            app=app,
            image=image,
            block_network=True,
            cpu=1.0,
            memory=512,
            timeout=30,
        )
        try:
            sandbox.filesystem.write_text(
                json.dumps({"points": candidate.points, "grid_size": grid_size}),
                "/tmp/candidate.json",
            )
            sandbox.filesystem.write_text(_SANDBOX_VERIFIER, "/tmp/verify.py")
            process = sandbox.exec("python", "/tmp/verify.py", timeout=10)
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"sandbox verifier failed: {stderr[-500:]}")
            payload = json.loads(stdout)
            return SandboxResult(
                valid=bool(payload["valid"]),
                score=int(payload["score"]),
                reason=str(payload["reason"]),
                backend="modal-sandbox",
                latency_seconds=time.monotonic() - started,
            )
        finally:
            sandbox.terminate()


def _read_json(request: urllib.request.Request, timeout_seconds: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return payload
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"provider returned HTTP {error.code}: {detail}") from error


_SANDBOX_VERIFIER = r'''
import json

payload = json.load(open("/tmp/candidate.json", encoding="utf-8"))
points = [tuple(point) for point in payload["points"]]
grid_size = int(payload["grid_size"])
valid = len(set(points)) == len(points)
reason = "exact verifier passed"
if valid and any(x < 0 or y < 0 or x >= grid_size or y >= grid_size for x, y in points):
    valid, reason = False, "point outside grid"
if valid:
    for px, py in points:
        distances = set()
        for ox, oy in points:
            if (px, py) == (ox, oy):
                continue
            distance = (px - ox) ** 2 + (py - oy) ** 2
            if distance in distances:
                valid, reason = False, "equal distances from one pivot"
                break
            distances.add(distance)
        if not valid:
            break
print(json.dumps({"valid": valid, "score": len(points), "reason": reason}))
'''.strip()
