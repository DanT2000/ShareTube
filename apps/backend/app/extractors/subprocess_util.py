"""Safe async subprocess execution.

Rules enforced here (per spec):
- never shell=True; args are always an explicit list
- hard timeout with process-group kill (children die too)
- cancellation support via asyncio task cancellation
- no user-supplied arbitrary flags reach the binary (callers build args)
"""
from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass

from ..logging_config import get_logger

log = get_logger("subprocess")

IS_WINDOWS = os.name == "nt"


@dataclass
class ProcResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


async def run(argv: list[str], *, timeout: int, env: dict | None = None,
              cwd: str | None = None,
              line_callback: Callable[[str], None] | None = None,
              capture_stdout: bool = True) -> ProcResult:
    """Run argv with a timeout. If line_callback given, streams stderr lines to it
    (yt-dlp/ffmpeg progress goes to stderr/stdout). Kills the whole process group on timeout.
    """
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv), "argv must be list[str]"

    full_env = {**os.environ, **(env or {})}
    creationflags = 0
    preexec = None
    if IS_WINDOWS:
        creationflags = getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        preexec = os.setsid  # new process group -> killpg

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
        cwd=cwd,
        preexec_fn=preexec,
        creationflags=creationflags,
        # yt-dlp -J emits a single huge JSON line; the default 64KB StreamReader limit
        # makes readline() raise "chunk exceed the limit". Raise it well above any
        # metadata blob so long/4K videos with many formats parse fine.
        limit=64 * 1024 * 1024,
    )

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    async def _pump_stdout(stream, chunks):
        # Read stdout in raw chunks (not lines) — it may be one giant JSON with no newline.
        while True:
            data = await stream.read(65536)
            if not data:
                break
            chunks.append(data)

    async def _pump_progress(stream, chunks):
        # Progress goes to stderr as newline-delimited lines.
        while True:
            try:
                line = await stream.readline()
            except (ValueError, asyncio.LimitOverrunError):
                # over-long stderr line: drain the rest in chunks, keep going
                data = await stream.read(65536)
                if not data:
                    break
                chunks.append(data)
                continue
            if not line:
                break
            chunks.append(line)
            if line_callback:
                try:
                    line_callback(line.decode("utf-8", "replace").rstrip())
                except Exception:  # progress must never crash the download
                    pass

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _pump_stdout(proc.stdout, stdout_chunks),
                _pump_progress(proc.stderr, stderr_chunks),
                proc.wait(),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        _kill(proc)
        await _drain(proc)
        return ProcResult(returncode=-1, stdout=b"".join(stdout_chunks),
                          stderr=b"".join(stderr_chunks), timed_out=True)
    except asyncio.CancelledError:
        _kill(proc)
        await _drain(proc)
        raise

    return ProcResult(
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
    )


def _kill(proc: asyncio.subprocess.Process) -> None:
    try:
        if IS_WINDOWS:
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def _drain(proc: asyncio.subprocess.Process) -> None:
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass
