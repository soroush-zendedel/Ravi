"""Beautiful multi-step progress UI for Ravi CLI (Rich)."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

console = Console()


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    id: str
    label: str
    state: StepState = StepState.PENDING
    detail: str = ""


def _icon(state: StepState) -> Text:
    return {
        StepState.PENDING: Text("○", style="dim"),
        StepState.RUNNING: Text("●", style="cyan bold"),
        StepState.DONE: Text("✓", style="green bold"),
        StepState.FAILED: Text("✗", style="red bold"),
        StepState.SKIPPED: Text("–", style="dim"),
    }[state]


class StageRunner:
    """Checklist of steps + live log tail + optional progress bar."""

    def __init__(self, title: str = "Ravi") -> None:
        self.title = title
        self.steps: list[Step] = []
        self.log_lines: deque[str] = deque(maxlen=8)
        self._progress: Progress | None = None
        self._task_id = None
        self._live: Live | None = None
        self._error: str | None = None

    def add(self, step_id: str, label: str) -> None:
        self.steps.append(Step(id=step_id, label=label))

    def _render(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2)
        table.add_column(ratio=1)
        table.add_column(ratio=2)

        for s in self.steps:
            style = {
                StepState.PENDING: "dim",
                StepState.RUNNING: "cyan",
                StepState.DONE: "green",
                StepState.FAILED: "red",
                StepState.SKIPPED: "dim",
            }[s.state]
            detail = Text(s.detail, style="dim") if s.detail else Text("")
            table.add_row(_icon(s.state), Text(s.label, style=style), detail)

        parts: list = [table]

        if self._progress is not None:
            parts.append(Text(""))
            parts.append(self._progress)

        if self.log_lines:
            log = Text()
            for line in self.log_lines:
                log.append(line[:120] + ("…" if len(line) > 120 else "") + "\n", style="dim")
            parts.append(Text(""))
            parts.append(log)

        if self._error:
            parts.append(Text(""))
            parts.append(Text(self._error, style="bold red"))

        border = "red" if self._error else "cyan"
        return Panel(
            Group(*parts),
            title=f"[bold cyan]{self.title}[/]",
            border_style=border,
            subtitle="[dim]Powered by Openness[/]",
        )

    def __enter__(self) -> "StageRunner":
        self._live = Live(self._render(), console=console, refresh_per_second=12)
        self._live.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        if self._live:
            self._live.update(self._render())
            self._live.__exit__(*exc)
            self._live = None

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _find(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def start_step(self, step_id: str, detail: str = "") -> None:
        s = self._find(step_id)
        s.state = StepState.RUNNING
        s.detail = detail
        self._refresh()

    def detail(self, step_id: str, detail: str) -> None:
        self._find(step_id).detail = detail
        self._refresh()

    def log(self, line: str) -> None:
        line = line.rstrip()
        if not line:
            return
        self.log_lines.append(line)
        self._refresh()

    def done(self, step_id: str, detail: str = "done") -> None:
        s = self._find(step_id)
        s.state = StepState.DONE
        s.detail = detail
        self._stop_progress()
        self._refresh()

    def skip(self, step_id: str, detail: str = "skipped") -> None:
        s = self._find(step_id)
        s.state = StepState.SKIPPED
        s.detail = detail
        self._refresh()

    def fail(self, step_id: str, error: str) -> None:
        s = self._find(step_id)
        s.state = StepState.FAILED
        s.detail = "failed"
        self._error = _friendly_error(error)
        self._stop_progress()
        self._refresh()

    def _stop_progress(self) -> None:
        if self._progress is not None:
            try:
                self._progress.stop()
            except Exception:
                pass
            self._progress = None
            self._task_id = None

    def progress_bar(self, description: str = "Working") -> Progress:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=28),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        self._task_id = self._progress.add_task(description, total=None)
        self._progress.start()
        self._refresh()
        return self._progress

    def set_progress(self, completed: float | None = None, total: float | None = None, description: str | None = None) -> None:
        if self._progress is None or self._task_id is None:
            return
        kwargs = {}
        if total is not None:
            kwargs["total"] = total
        if completed is not None:
            kwargs["completed"] = completed
        if description is not None:
            kwargs["description"] = description
        self._progress.update(self._task_id, **kwargs)
        self._refresh()


_ERROR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"port is already allocated|address already in use", re.I),
     "A port is already in use. Stop the other process or change the published port."),
    (re.compile(r"permission denied", re.I),
     "Permission denied. Try running Docker as a user in the docker group."),
    (re.compile(r"No such image|pull access denied|not found", re.I),
     "Docker image missing or not pullable. Check your network and image name."),
    (re.compile(r"Cannot connect to the Docker daemon", re.I),
     "Docker daemon is not running. Start Docker Desktop / the Docker service."),
    (re.compile(r"POSTGRES_PASSWORD|password authentication failed", re.I),
     "Database password issue. Check POSTGRES_PASSWORD in .env."),
    (re.compile(r"no space left", re.I),
     "Disk is full. Free some space and retry."),
    (re.compile(r"manifest unknown|404", re.I),
     "Model or image not found upstream. Check the name and try again."),
]


def _friendly_error(raw: str) -> str:
    for pat, msg in _ERROR_PATTERNS:
        if pat.search(raw):
            return f"{msg}\n\n[dim]Detail:[/] {raw.strip()[:400]}"
    # last non-empty lines
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    tail = "\n".join(lines[-6:]) if lines else raw
    return f"Something went wrong.\n\n{tail[:600]}"


def run_command_with_logs(
    runner: StageRunner,
    step_id: str,
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict | None = None,
    progress_label: str = "Running",
) -> subprocess.CompletedProcess:
    """Run a process, stream stdout/stderr into the live log panel."""
    runner.start_step(step_id, progress_label)
    runner.progress_bar(progress_label)

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    collected: list[str] = []

    for line in proc.stdout:
        collected.append(line)
        runner.log(line.rstrip())
        # crude percent from docker/ollama style lines
        m = re.search(r"(\d{1,3})\s*%", line)
        if m:
            runner.set_progress(completed=float(m.group(1)), total=100.0)

    code = proc.wait()
    output = "".join(collected)
    if code != 0:
        runner.fail(step_id, output or f"exit code {code}")
        raise subprocess.CalledProcessError(code, cmd, output=output)
    runner.done(step_id, "ok")
    return subprocess.CompletedProcess(cmd, code, output, "")


def banner() -> None:
    console.print(
        Panel(
            "[bold cyan]Ravi[/]  ·  Open Source AI Infrastructure\n"
            "[dim]Powered by Openness. Built for Everyone.[/]",
            border_style="cyan",
        )
    )
