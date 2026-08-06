"""Run the Claude Code CLI as a training worker.

Two ways to call a model, both going through the same `claude` binary so the
project has exactly one external dependency:

- `run_agent()`  -- a tool-using agent. It can Read the memory pool, Write
  screenplays and commit with git. We capture the full stream-json log, render
  a readable trajectory, and record which files the agent read (used later for
  credit assignment).
- `run_text()`   -- one call in, one answer out, for the steps that are plain
  transformations (noising, loss report). The CLI still has its tools; these
  prompts simply give it no reason to reach for them, and the material they
  need is inlined.

Authentication is whatever your `claude` CLI already uses: a Claude
subscription login, `ANTHROPIC_API_KEY`, or an Anthropic-compatible gateway via
`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`. This project never reads keys.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .trajectory import collect_read_trace, render_trajectory

# Load no settings layers at all. Your own CLAUDE.md is written for you, not for
# a training agent, and it will be obeyed: a personal "always answer in Chinese"
# rule silently produced Chinese chapters here until this was set to empty.
# Authentication is unaffected, so the agent still runs as you. Set
# MEMSGD_SETTING_SOURCES=user,project,local to get the CLI's normal behaviour back.
SETTING_SOURCES = os.environ.get("MEMSGD_SETTING_SOURCES", "")
# A single API request that goes silent is the one failure the outer timeout
# cannot heal quickly. Ten minutes is generous for one turn and lets the CLI
# retry on a fresh connection instead of hanging for the whole step budget.
API_TIMEOUT_MS = os.environ.get("MEMSGD_API_TIMEOUT_MS", "600000")


class AgentError(RuntimeError):
    """Raised when a model call fails in a way the caller cannot recover from."""


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    # Claude Code can write its own long-term memory. In a training loop that is
    # a side channel: one run's notes would leak into the next run's context and
    # quietly contaminate the comparison. Keep every run's state on disk, in the
    # run directory, where it can be inspected.
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env["API_TIMEOUT_MS"] = API_TIMEOUT_MS
    return env


def _base_cmd(model: str | None) -> list[str]:
    # The prompt goes in on stdin, not as an argument. Inlining several episodes
    # of two screenplays gets into the hundreds of kilobytes, which is close
    # enough to the operating system's argument limit to matter, and it would
    # also put the whole prompt in everyone's `ps` output.
    cmd = ["claude", "-p", "--dangerously-skip-permissions",
           "--setting-sources", SETTING_SOURCES]
    if model:
        cmd += ["--model", model]
    return cmd


def run_text(prompt: str, *, model: str | None = None, timeout: int = 1800,
             retries: int = 2, min_chars: int = 200) -> str:
    """One call in, one answer out. Returns the model's answer as text.

    Retries on transport errors and on suspiciously short answers, which is how
    a refusal or a truncated stream usually shows up.
    """
    cmd = _base_cmd(model) + ["--output-format", "text"]
    last = ""
    for attempt in range(1, retries + 2):
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  timeout=timeout, env=_child_env(), check=False)
        except subprocess.TimeoutExpired:
            last = f"timed out after {timeout}s"
            continue
        answer = proc.stdout.strip()
        if proc.returncode == 0 and len(answer) >= min_chars:
            return answer
        last = (f"exit={proc.returncode} chars={len(answer)} "
                f"stderr={proc.stderr.strip()[:300]}")
        print(f"  [llm] attempt {attempt} failed: {last}", flush=True)
    raise AgentError(f"text call failed after {retries + 1} attempts: {last}")


def run_agent(
    *,
    role: str,
    prompt: str,
    workdir: Path,
    out_dir: Path,
    model: str | None = None,
    timeout: int = 2400,
    expect: Path | Sequence[Path] | None = None,
    retries: int = 2,
    retry_on_error: bool = False,
    before_retry: Callable[[], None] | None = None,
) -> int:
    """Spawn a tool-using agent and archive everything it did.

    `out_dir` receives four files named after `role`:
      <role>_prompt.md      exactly what the agent was told
      <role>.jsonl          raw stream-json from the CLI
      <role>_trajectory.md  readable transcript
      <role>_reads.txt      files the agent opened, in order

    `expect` is a path, or several, that the agent is supposed to produce. A
    model can finish its turn cleanly without writing anything, so exit code
    alone is not proof of work; the artifacts are, and all of them have to be
    there. `before_retry` lets the caller roll back external state (the memory
    pool's git repo, for instance) between attempts.

    Returns the exit code of the last attempt; -1 means the wall-clock timeout hit.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / f"{role}_prompt.md"
    log_path = out_dir / f"{role}.jsonl"
    traj_path = out_dir / f"{role}_trajectory.md"
    reads_path = out_dir / f"{role}_reads.txt"
    err_path = out_dir / f"{role}.stderr"
    prompt_path.write_text(prompt, encoding="utf-8")

    cmd = _base_cmd(model) + ["--output-format", "stream-json", "--verbose"]
    wanted = [expect] if isinstance(expect, Path) else list(expect or ())
    total = max(0, retries) + 1
    rc = -2

    for attempt in range(1, total + 1):
        if attempt > 1:
            print(f"[{role}] retry {attempt}/{total}", flush=True)
            if before_retry:
                before_retry()
            for p in (log_path, traj_path, reads_path, err_path):
                if p.exists():
                    # `replace`, not `rename`: a re-run of the same step would
                    # otherwise raise on Windows and silently clobber elsewhere.
                    p.replace(p.with_name(f"{p.stem}_attempt{attempt - 1}{p.suffix}"))

        print(f"[{role}] claude subprocess, timeout {timeout}s, "
              f"prompt {len(prompt):,} chars", flush=True)
        started = time.time()
        # The prompt is piped in from the archived file, so what is on disk is
        # provably what was sent. stderr goes to its own file, because folding
        # it into the log would put non-JSON lines in a .jsonl.
        with log_path.open("w", encoding="utf-8") as log, \
                err_path.open("w", encoding="utf-8") as err, \
                prompt_path.open("rb") as stdin:
            try:
                rc = subprocess.run(cmd, cwd=str(workdir), stdin=stdin, stdout=log,
                                    stderr=err, timeout=timeout, env=_child_env(),
                                    check=False).returncode
            except subprocess.TimeoutExpired:
                err.write(f"\n=== TIMEOUT after {timeout}s ===\n")
                rc = -1
        if err_path.stat().st_size == 0:
            err_path.unlink()
        print(f"[{role}] exit={rc} in {time.time() - started:.0f}s", flush=True)

        traj_path.write_text(render_trajectory(log_path), encoding="utf-8")
        reads_path.write_text("\n".join(collect_read_trace(log_path)) + "\n",
                              encoding="utf-8")

        missing = any(not p.exists() for p in wanted)
        if attempt < total and (missing or (retry_on_error and rc != 0)):
            continue
        break

    return rc
