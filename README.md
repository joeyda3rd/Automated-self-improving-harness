# ASH: Automated Self-improving Harness

ASH turns plain Claude Code into an unattended software builder that improves itself. You give it an assignment. It plans the work into tasks, builds each task in an isolated git worktree, proves the work with your test command, merges it, and learns from every run. Every few tasks it proposes a change to its own skills and prompts, benchmarks that change against a hidden eval suite, and keeps the change only if the harness got measurably better.

It is built only from Claude Code's own primitives: headless sessions, plugins, skills, subagents, hooks, session resume, structured output, budgets and a mod. A small, deterministic Python orchestrator (stdlib only) ties them together. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

```
assignment → plan → task queue → build (worktree, stop-gate verified) → integrate → retro → lessons
                                                     every N builds → propose harness change → eval gate → keep / discard
```

## Quick start

Requirements: Claude Code (`claude`) authenticated on the machine, `git`, and Python 3.9+. Run it in a container or VM: sessions run with `bypassPermissions`, with the ASH guard hook as the safety layer.

```bash
export PATH="$PWD/bin:$PATH"

# 1. Point ASH at a project (an existing repo, or an empty directory)
ash -C ~/code/myapp init --verify "npm test"

# 2. Assign work: free text, a file, or drop markdown files into ~/code/myapp/.ash/inbox/
ash -C ~/code/myapp assign "Build a REST API for todos with SQLite persistence and tests"
ash -C ~/code/myapp add "Fix pagination off-by-one" --accept "page 2 starts at item 11"

# 3. Let it work: continuously, until the queue is empty, or one task at a time
ash -C ~/code/myapp run                  # runs forever, polls the inbox when idle
ash -C ~/code/myapp run --until-empty

# Watch and steer
ash -C ~/code/myapp status               # the queue
ash report                               # success, cost and turns per harness version (the learning curve)
ash lessons                              # what the harness has learned
ash improve                              # run a self-improvement cycle now
ash eval                                 # benchmark the current harness
ash pause / ash resume                   # stop after the current task / clear the circuit breaker
```

To watch the loop from inside Claude Code, load the console mod in a session opened in the project: `claude --plugin-dir mods/harness-console`, then `/ash` opens a live pane. The status line shows the queue at a glance.

## Layout

| Path | What it is | Who may change it |
|---|---|---|
| `ash/` | Orchestrator: queue, session runner, git integration, retro, improvement cycle, evals | humans (kernel) |
| `plugin/hooks/` | Kernel hooks: context injection, guard, telemetry, stop gate, transcript capture | humans (kernel) |
| `evals/tasks/` | Benchmark tasks with hidden `check.sh` acceptance tests | humans (kernel) |
| `harness.json` | Budgets, retry limits, improvement cadence, mutable paths | humans (kernel) |
| `plugin/roles/` | System-prompt personas: builder, planner, retro, improver | the harness, through the eval gate |
| `plugin/skills/` | Procedures: build-task, verify, plan-work, retrospective, improve-harness | the harness, through the eval gate |
| `plugin/agents/` | Subagents: reviewer, test-writer | the harness, through the eval gate |
| `mods/harness-console/` | Claude Code mod: `/ash` pane and status line | humans |
| `state/` (gitignored) | Run records, metrics ledger, lessons, improvement log, eval cache | the orchestrator |
| `<project>/.ash/` | Per-project queue, inbox, worktrees, config and `notes.md` | the orchestrator; sessions may edit only `notes.md` |

## How it improves

- **Fast loop (every run).** A retrospective session reads the run's telemetry, stop-gate history, guard denials and transcript, and distils up to three lessons. They go into capped, deduplicated memory files that the SessionStart hook injects into every later session.
- **Slow loop (every `improve_every` builds).** An improver session edits the harness's own skills, subagents or role prompts in a worktree, guided by evidence such as failure modes, costs, retro suggestions and earlier rejected ideas. The candidate runs on the eval suite, starting with a cheap smoke stage. It is merged only if more eval tasks improve than regress, or results are identical and it is cheaper on most tasks. Changes to the kernel are blocked by the guard and rejected by a diff check.
- **Memory hygiene.** Lessons carry ids. Retros rate the lessons a run was given, and lessons rated harmful, or with a poor track record, are deleted.
- **Integrity.** A `done` result is refused until the project's test command passes. Before merging, a diff that deletes or skips tests is rejected.

How the design was checked against Claude Code's real hook behaviour and prior work on self-improving agents (Darwin Gödel Machine, SICA, memory research) is in [docs/RESEARCH.md](docs/RESEARCH.md).

## Development

```bash
python3 -m unittest discover -s tests -q        # hooks, loop, integration and the improvement ratchet, against a fake claude binary
claude plugin validate plugin                   # the ASH plugin
claude plugin validate mods/harness-console     # the console mod
```

The tests drive the whole loop end to end: assignment, plan, dependent builds, merges, retro lessons, and an accepted self-improvement. They also check that an improvement touching the kernel is rejected, that a lazy "done" is caught by re-verification and fixed by resuming the same session, and that the circuit breaker trips. `tests/fake_claude.py` stands in for `claude`, so the tests spend nothing.
