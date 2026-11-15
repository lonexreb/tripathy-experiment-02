"""Narrow Modal gateway: the only module of the P2 comparison that touches Modal.

It creates one Sandbox per call with exactly the isolation the controller asks
for, and passes no Secrets, Volumes, mounts or environment. Authentication stays
in the local Modal profile; nothing here reads or forwards a credential.
"""

from __future__ import annotations

import importlib
import os
import time
from typing import Any

from .parallel_comparison import ExecResult

WORKDIR = "/tmp"
MAX_STDERR_CHARS = 2000


def _read_bounded(stream: Any, limit: int) -> bytes:
    """Read at most ``limit + 1`` bytes so an oversized stream is detectable."""
    chunks: list[bytes] = []
    size = 0
    for chunk in stream:
        data = chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
        chunks.append(data)
        size += len(data)
        if size > limit:
            break
    return b"".join(chunks)[: limit + 1]


class _ModalSandbox:
    def __init__(self, sandbox: Any, timeouts: tuple[type[BaseException], ...]) -> None:
        self._sandbox = sandbox
        self._timeouts = timeouts
        self.sandbox_id = str(sandbox.object_id)

    def write_file(self, name: str, data: bytes) -> None:
        self._sandbox.filesystem.write_bytes(data, f"{WORKDIR}/{name}")

    def exec(self, command: list[str], timeout_seconds: int, max_stdout_bytes: int) -> ExecResult:
        started = time.monotonic()
        try:
            process = self._sandbox.exec(
                *command, timeout=timeout_seconds, workdir=WORKDIR, text=False
            )
            stdout = _read_bounded(process.stdout, max_stdout_bytes)
            if len(stdout) > max_stdout_bytes:
                return ExecResult(None, stdout, "")  # do not wait for a runaway process
            stderr = _read_bounded(process.stderr, MAX_STDERR_CHARS).decode("utf-8", "replace")
            exit_code = process.wait()
        except self._timeouts as error:
            raise TimeoutError(f"sandbox exec timed out: {type(error).__name__}") from error
        if exit_code == -1 and time.monotonic() - started >= timeout_seconds - 1:
            raise TimeoutError("sandbox exec reached its timeout")  # Modal reports -1 on expiry
        return ExecResult(exit_code, stdout, stderr[:MAX_STDERR_CHARS])

    def terminate(self) -> int | None:
        code = self._sandbox.terminate(wait=True)
        return code if isinstance(code, int) else None


class ModalSandboxGateway:
    def __init__(self, app_name: str | None = None) -> None:
        try:
            # importlib keeps mypy results identical with and without Modal installed
            self._modal: Any = importlib.import_module("modal")
        except ImportError as error:
            raise RuntimeError("Install the modal optional dependency") from error
        self._app_name = app_name or os.environ.get("EVOHIVE_MODAL_APP", "evohive-track1")
        self._app: Any = None
        # The compiler is baked into the image; sandboxes themselves have no network.
        self._image = self._modal.Image.debian_slim(python_version="3.11").apt_install(
            "gcc", "libc6-dev"
        )

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "modal",
            "client_version": str(self._modal.__version__),
            "app_name": self._app_name,
            "image": "debian_slim(python 3.11) + apt gcc libc6-dev",
            "workdir": WORKDIR,
        }

    def prepare(self) -> None:
        self._app = self._modal.App.lookup(self._app_name, create_if_missing=True)
        self._image.build(self._app)

    def create(self, isolation: dict[str, Any]) -> _ModalSandbox:
        if isolation["secrets"] or isolation["mounts"]:
            raise ValueError("this gateway never attaches secrets or mounts")
        if self._app is None:
            raise RuntimeError("gateway.prepare() did not complete")
        timeout = int(isolation["timeout_seconds"])
        sandbox = self._modal.Sandbox.create(
            "sleep",
            str(timeout),
            app=self._app,
            image=self._image,
            runtime=isolation["runtime"],
            block_network=isolation["block_network"],
            cpu=isolation["cpu"],
            memory=isolation["memory_mib"],
            timeout=timeout,
        )
        exceptions = self._modal.exception
        return _ModalSandbox(
            sandbox, (exceptions.SandboxTimeoutError, exceptions.ExecTimeoutError, TimeoutError)
        )
